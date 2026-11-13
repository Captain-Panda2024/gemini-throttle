#!/usr/bin/env python3
"""state.py — Gemini throttle 集計の永続化（原子書込）抽象化

保存対象:
  - counts_history.json  : 日別累積 + 最新24h窓のスナップショット（サーバ再起動で消えない）
  - counts_24h.json      : 最後の24時間窓計算結果

更新は必ず os.replace 付きで行い、途中ファイルが残らないようにする。
"""
import json
import os

BASE = "/home/captain/.hermes2/profiles/main/throttle"
HISTORY_PATH = os.path.join(BASE, "counts_history.json")
CURRENT_WINDOW_PATH = os.path.join(BASE, "counts_24h.json")


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_history():
    return _read(HISTORY_PATH, {"version": 1, "days": {}, "log_start_unix": None})


def save_history(history):
    _write(HISTORY_PATH, history)


def load_current_window():
    return _read(CURRENT_WINDOW_PATH, None)


def save_current_window(payload):
    _write(CURRENT_WINDOW_PATH, payload)


def daily_entry(date):
    """日別履歴から日付別のエントリを取り出す（なければ 0 件）。"""
    history = load_history()
    entry = history.get("days", {}).get(date)
    if entry is None:
        return {"total": 0, "by_model": {}}
    return {"total": entry.get("total", 0), "by_model": dict(entry.get("by_model", {}))}
