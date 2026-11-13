import os
import re
import time
from datetime import datetime
import httpx
from fastapi import FastAPI, Request, Response
from limiter import TokenBucket
import asyncio

app = FastAPI()
# 10 req/min 制限（事前スロットリング）
limiter = TokenBucket(10)
UPSTREAM_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
API_KEY = os.environ.get("GOOGLE_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

MAX_RETRIES = 3
MAX_WAIT_SEC = 65

# ── 日次予算ガード（2026-11-12 captain裁定「無料Geminiを使いたい」対応）──
# Free Tier は 1日500リクエスト/モデル（RPD）。枯渇すると回復まで7時間待ちになる。
# しかも agent ループは 1ターン=1リクエストじゃけん、cron 十数本で簡単に食い尽くす。
# だから「上限の手前で止めて、残りを対話用に予約する」。
#   MAX_DAILY_REQUESTS: このプロキシが1日に上流へ投げる上限（成功分のみ数える）
#   0 以下なら無効（無制限）
COUNTER_PATH = os.environ.get(
    "THROTTLE_COUNTER", "/home/captain/.hermes2/profiles/main/throttle/daily_count.json")
MAX_DAILY_REQUESTS = int(os.environ.get("THROTTLE_MAX_DAILY", "430"))


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _read_counter():
    import json
    try:
        with open(COUNTER_PATH) as f:
            data = json.load(f)
    except Exception:
        data = {}
    if data.get("date") != _today():
        data = {"date": _today(), "count": 0, "by_model": {}}
    return data


def _bump_counter(model: str):
    import json
    data = _read_counter()
    data["count"] = int(data.get("count", 0)) + 1
    by_model = data.setdefault("by_model", {})
    by_model[model] = int(by_model.get(model, 0)) + 1
    try:
        os.makedirs(os.path.dirname(COUNTER_PATH), exist_ok=True)
        tmp = COUNTER_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, COUNTER_PATH)
    except Exception as e:
        print(f"[COUNTER] write failed: {e}", flush=True)
    return data


def _extract_model(body: bytes) -> str:
    import json
    try:
        return str(json.loads(body or b"{}").get("model") or "?")
    except Exception:
        return "?"


def _normalize_model(raw: str) -> str:
    """モデル名の表記揺れを吸収する（予算の別勘定化を防ぐ）。

    Google は `models/gemini-3.1-flash-lite` / `google/gemini-3.1-flash-lite` /
    `gemini-3.1-flash-lite` を同じモデルとして扱うので、こちらも同一キーに寄せる。
    接頭辞だけ落とし、未知は ? のまま。
    """
    if not raw or raw == "?":
        return "?"
    m = raw.strip()
    for prefix in ("models/", "google/", "publishers/google/models/"):
        if m.startswith(prefix):
            m = m[len(prefix):]
    return m or "?"


def _join_path(*parts: str) -> str:
    """パス結合の正規化。/v1 /openai /v1beta の重複を畳む。"""
    segments = []
    seen = set()
    for part in parts:
        for seg in part.split("/"):
            if not seg:
                continue
            if seg in ("v1", "openai", "v1beta") and seg in seen:
                continue
            segments.append(seg)
            seen.add(seg)
    return "/" + "/".join(segments)


def parse_retry_window(response: httpx.Response) -> float:
    """429 レスポンスから待機秒数を抽出する。

    優先順位:
    1. Retry-After ヘッダ
    2. RetryInfo (JSON body) — retryDelay フィールド
    3. 本文の文言（"retry after X seconds" 等）
    4. デフォルト 10秒
    """
    # 1. Retry-After ヘッダ
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), MAX_WAIT_SEC)
        except ValueError:
            pass

    # 2. RetryInfo (JSON body)
    try:
        body = response.json()
        details = body.get("error", {}).get("details", [])
        for detail in details:
            if "retryDelay" in detail:
                delay_str = detail["retryDelay"]
                m = re.match(r"(\d+(?:\.\d+)?)s", delay_str)
                if m:
                    return min(float(m.group(1)), MAX_WAIT_SEC)
    except Exception:
        pass

    # 3. 本文の文言
    try:
        text = response.text
        m = re.search(r"retry\s*(?:after|in)\s*(\d+(?:\.\d+)?)\s*s", text, re.IGNORECASE)
        if m:
            return min(float(m.group(1)), MAX_WAIT_SEC)
    except Exception:
        pass

    # 4. デフォルト
    return 10.0


def estimate_tokens(text: str) -> int:
    """テキストからトークン数を概算する（4文字 ≈ 1トークン）。"""
    if not text:
        return 0
    return max(1, len(text) // 4)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str):
    await limiter.consume()

    body = await request.body()
    req_model = _extract_model(body)
    counter_model = _normalize_model(req_model)  # 予算の別勘定化を防ぐ

    # 日次予算ガード: 上限に達しとったら上流を叩かず即座に429を返す。
    # 対象は「生成呼び出し」だけ。ヘルスチェック（/v1/models, /props 等）まで
    # 429で止めると、クライアントがリトライを繰り返して無駄に叩き続ける。
    # 上限はモデル別（Google Free Tier の RPD がモデル単位のため）。
    is_generate_req = "chat/completions" in path or path.endswith("/completions")
    if is_generate_req and MAX_DAILY_REQUESTS > 0:
        _c = _read_counter()
        budget_used = int(_c.get("by_model", {}).get(counter_model, 0))
        if budget_used >= MAX_DAILY_REQUESTS:
            print(f"[BUDGET] {datetime.now().isoformat(timespec='seconds')} "
                  f"blocked path=/{path} model={counter_model} "
                  f"used={budget_used}/{MAX_DAILY_REQUESTS}", flush=True)
            return Response(
                content=(
                    '{"error":{"code":429,"status":"RESOURCE_EXHAUSTED","message":'
                    f"'gemini-throttle daily budget guard: model {counter_model} "
                    f"{budget_used}/{MAX_DAILY_REQUESTS} used today. "
                    "Reserved remainder for interactive use. Falling back is expected.'}}"
                ),
                status_code=429,
                media_type="application/json",
            )

    # パスから v1 プレフィックスを除去（upstream が v1beta/openai を含むため）
    clean_path = path
    if clean_path.startswith("v1/"):
        clean_path = clean_path[3:]
    elif clean_path == "v1":
        clean_path = ""
    url = f"{UPSTREAM_URL}/{clean_path}" if clean_path else UPSTREAM_URL
    headers = dict(request.headers)
    # Google OpenAI互換エンドポイントは Authorization: Bearer *** を期待する
    headers["Authorization"] = f"Bearer {API_KEY}"
    # Host ヘッダを削除（Google は正しい Host を期待する）
    headers.pop("host", None)
    headers.pop("Host", None)
    # Accept-Encoding を削除（upstream の圧縮応答を回避）
    headers.pop("accept-encoding", None)
    headers.pop("Accept-Encoding", None)

    body = await request.body()

    response = None
    for attempt in range(MAX_RETRIES):
        async with httpx.AsyncClient(timeout=40.0) as client:
            proxy_req = client.build_request(
                request.method,
                url,
                params=request.query_params,
                headers=headers,
                content=body,
            )

            try:
                response = await client.send(proxy_req)
            except httpx.TimeoutException:
                return Response(content="Gateway Timeout", status_code=504)
            except Exception as e:
                return Response(content=str(e), status_code=502)

        if response.status_code != 429:
            resp_headers = dict(response.headers)
            # Content-Encoding を削除（クライアントの自動解凍を回避）
            for h in ("content-encoding", "Content-Encoding", "content-length",
                      "Content-Length", "transfer-encoding", "Transfer-Encoding"):
                resp_headers.pop(h, None)
            # 予算の会計は「生成の成功」だけ数える。
            # ヘルスチェックの404やクライアント切断の503まで数えると、
            # 実際のAIリクエストが120件でも予算が430に達して無駄に枯渇する。
            is_generate = "chat/completions" in path or path.endswith("/completions")
            counted = is_generate and response.status_code == 200
            if counted:
                stats = _bump_counter(counter_model)
                today = stats.get("count")
            else:
                stats = _read_counter()
                today = stats.get("count")
            print(f"[REQ] {datetime.now().isoformat(timespec='seconds')} "
                  f"path=/{path} status={response.status_code} attempts={attempt + 1} "
                  f"model={counter_model} today={today}/{MAX_DAILY_REQUESTS} "
                  f"counted={1 if counted else 0}", flush=True)
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=resp_headers,
            )

        # 429: 待機して再試行
        wait_sec = parse_retry_window(response)
        print(f"[429] {datetime.now().isoformat(timespec='seconds')} "
              f"attempt={attempt + 1}/{MAX_RETRIES} wait={wait_sec}s", flush=True)
        await asyncio.sleep(wait_sec)

    # 最大リトライ超過
    if response is None:
        return Response(content="No response", status_code=502)
    resp_headers = dict(response.headers)
    # Content-Encoding を削除（body は httpx が既に解凍済みのため、
    # ヘッダを残すとクライアント側で gzip 解凍に失敗する）
    resp_headers.pop("content-encoding", None)
    resp_headers.pop("Content-Encoding", None)
    resp_headers.pop("content-length", None)
    resp_headers.pop("Content-Length", None)
    resp_headers.pop("transfer-encoding", None)
    resp_headers.pop("Transfer-Encoding", None)
    return Response(
        content=response.content,
        status_code=429,
        headers=resp_headers,
    )


if __name__ == "__main__":
    import uvicorn
    # ワーカー数は必ず1
    uvicorn.run(app, host="127.0.0.1", port=8899, workers=1)
