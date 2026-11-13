#!/usr/bin/env python3
"""aggregate.py — Gemini throttle のリクエスト集計（24時間ウィンドウ）本体

データ源: /home/captain/.hermes2/profiles/main/throttle/gemini.log
  [REQ] 2026-11-12T09:47:32 path=/v1/chat/completions status=200 attempts=1
         model=gemini-3.5-flash-lite today=1/430
  [429] attempt=1/3 wait=2.5s        ← タイムスタンプなし
  [BUDGET] 2026-11-12T22:12:24 blocked path=/api/show used=430/430

方針（captain裁定）:
  - 24時間窓は「このAPIを呼んだ瞬間」を基準に [now-24h, now]
  - モデル別カウントは「成功（status=200）」のみ（include_failed=0）
  - モデル名は正規化（"models/" prefix 除去、未知は "?"）
  - ログが現在のプロキシの生きた間より古いと partial=true になる
"""
import json
import os
import re
from datetime import datetime, timedelta

LOG_PATH = os.environ.get(
    "GEMINI_LOG",
    "/home/captain/.hermes2/profiles/main/throttle/gemini.log",
)
DAY_COUNTER_PATH = os.environ.get(
    "DAY_COUNTER",
    "/home/captain/.hermes2/profiles/main/throttle/daily_count.json",
)
HISTORY_PATH = os.environ.get(
    "COUNTS_HISTORY",
    "/home/captain/.hermes2/profiles/main/throttle/counts_history.json",
)
CURRENT_WINDOW_PATH = os.environ.get(
    "CURRENT_WINDOW",
    "/home/captain/.hermes2/profiles/main/throttle/counts_24h.json",
)

# [REQ] 2026-11-12T09:47:32 path=... status=... attempts=... model=... today=N/430 counted=0|1
REQ_RE = re.compile(
    r"\[REQ\] (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) "
    r"path=(\S+) status=(\d+) attempts=(\d+) model=(\S+) today=\d+/\d+"
    r"(?: counted=(\d))?"
)
# [429] 2026-11-14T00:00:48 attempt=1/3 wait=2.5s   ← 時刻あり（新形式）
# [429] attempt=1/3 wait=2.5s                       ← 時刻なし（旧形式）
REQ_429_RE = re.compile(
    r"^\[429\] (?:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) )?attempt=(\d+)/(\d+) wait=([\d.]+)s"
)
# [BUDGET] 2026-11-12T22:12:24 blocked path=/api/show used=430/430
BUDGET_RE = re.compile(
    r"\[BUDGET\] (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) blocked path=(\S+) used=\d+/\d+"
)

MODEL_PREFIX = "models/"


def normalize_model(raw: str) -> str:
    """モデルの揺れを吸収する。未知は "?" へ。"""
    if not raw or raw == "?":
        return "?"
    model = raw.strip()
    if model.startswith(MODEL_PREFIX):
        model = model[len(MODEL_PREFIX):]
    return model


def _parse_dt(s: str):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default


def _write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_daily_counter():
    """daily_count.json: {date, count, by_model}（今日分の成功リクエスト）"""
    data = _read_json(DAY_COUNTER_PATH, None)
    if isinstance(data, dict) and data.get("date"):
        return data
    return None


def _read_history():
    """counts_history.json: 日別履歴 + ログ開始時刻 + partial情報"""
    return _read_json(HISTORY_PATH, {"version": 1, "days": {}, "log_start_unix": None})


def _read_current_window():
    return _read_json(CURRENT_WINDOW_PATH, None)


def load_daily_entry(date: str) -> dict:
    """日別履歴から日付別のエントリを取り出す（なければ 0 件）。"""
    history = _read_history()
    entry = history.get("days", {}).get(date)
    if entry is None:
        return {"total": 0, "by_model": {}}
    return {"total": entry.get("total", 0), "by_model": dict(entry.get("by_model", {}))}


def compute_window(now=None, window_hours=24, include_failed=False):
    """24時間ウィンドウの集計。

    Returns: {
      window_start, window_end, by_model(成功・モデル別),
      attempts: {status200, non200_req, status429, budget_block},
      unwindowed: int,
      partial, log_start_unix, gap_from
    }
    """
    if now is None:
        now = datetime.now()
    window_start = now - timedelta(hours=window_hours)

    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    else:
        lines = []

    # 現在のプロキシの生きた間の開始（ログ先頭の [REQ] 時刻）
    log_start_dt = None
    for line in lines:
        m = re.match(r"^\[REQ\] (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", line)
        if m:
            log_start_dt = _parse_dt(m.group(1))
            break

    by_model = {}
    attempts = {"http_200": 0, "non200": 0, "status429": 0, "budget_block": 0}
    unwindowed = 0
    records = 0

    for line in lines:
        m = REQ_RE.search(line)
        if m:
            ts = _parse_dt(m.group(1))
            if log_start_dt is not None and ts < log_start_dt:
                continue
            if ts < window_start or ts > now:
                continue
            # [REQ] はすべて 429 以外（200/404/502/504 など）の処理済みリクエスト。
            # 予算・モデル別集計は「生成の成功」だけを数える。
            # 旧ログ（counted= なし）は status=200 かつ chat/completions で判定し直す。
            status = int(m.group(3))
            model = normalize_model(m.group(5))
            req_path = m.group(2)
            counted_flag = m.group(6)
            if counted_flag is not None:
                is_counted = counted_flag == "1"
            else:
                is_counted = status == 200 and "chat/completions" in req_path
            if is_counted:
                by_model[model] = by_model.get(model, 0) + 1
                attempts["http_200"] += 1
            else:
                # ヘルスチェック・失敗・切断は生成回数に含めない
                attempts["non200"] += 1
            records += 1
            continue

        m = REQ_429_RE.search(line)
        if m:
            # 新形式は時刻を持つので窓で切れる。
            # 旧形式（時刻なし）は窓に配置できないため集計に混ぜず unwindowed に退避する。
            ts_str = m.group(1)
            if not ts_str:
                unwindowed += 1
                continue
            ts = _parse_dt(ts_str)
            if ts < window_start or ts > now:
                continue
            attempts["status429"] += 1
            continue

        m = BUDGET_RE.search(line)
        if m:
            ts = _parse_dt(m.group(1))
            if ts < window_start or ts > now:
                continue
            attempts["budget_block"] += 1
            records += 1
            continue

    total = sum(by_model.values())

    partial = False
    gap_from = None
    if log_start_dt is not None:
        gap_from = (log_start_dt - timedelta(hours=window_hours)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        if window_start < log_start_dt:
            partial = True
    elif not lines:
        partial = True

    return {
        "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
        "window_end": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "by_model": dict(sorted(by_model.items(), key=lambda kv: (-kv[1], kv[0]))),
        "success": total,
        "attempts": attempts,
        "unwindowed": unwindowed,
        "records": records,
        "source": "gemini.log",
        "partial": partial,
        "log_start_unix": log_start_dt.timestamp() if log_start_dt else None,
        "gap_from": gap_from,
    }


def merge_history(window, now=None):
    """集計結果を日別履歴へ統合する。"""
    if now is None:
        now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    history = _read_history()
    history.setdefault("days", {})
    if history.get("log_start_unix") is None and window.get("log_start_unix") is not None:
        history["log_start_unix"] = window["log_start_unix"]

    daily = _read_daily_counter()
    if daily and daily.get("date") == today:
        norm_by_model = {}
        for raw, count in dict(daily.get("by_model", {})).items():
            key = normalize_model(str(raw))
            norm_by_model[key] = norm_by_model.get(key, 0) + int(count)
        history["days"][today] = {
            "total": int(daily.get("count", 0)),
            "by_model": norm_by_model,
            "recorded_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    history["current_window"] = {
        "window_start": window["window_start"],
        "window_end": window["window_end"],
        "success": window["success"],
        "by_model": window["by_model"],
        "attempts": window["attempts"],
        "unwindowed": window["unwindowed"],
        "partial": window["partial"],
        "log_start_unix": window["log_start_unix"],
        "gap_from": window["gap_from"],
        "computed_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    _write_json_atomic(HISTORY_PATH, history)
    return history


def write_current_window(window, now=None):
    if now is None:
        now = datetime.now()
    payload = {
        "window_start": window["window_start"],
        "window_end": window["window_end"],
        "success": window["success"],
        "by_model": window["by_model"],
        "attempts": window["attempts"],
        "unwindowed": window["unwindowed"],
        "partial": window["partial"],
        "log_start_unix": window["log_start_unix"],
        "gap_from": window["gap_from"],
        "computed_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _write_json_atomic(CURRENT_WINDOW_PATH, payload)
    return payload
