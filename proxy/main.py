import os
import re
import time
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
            resp_headers.pop("content-encoding", None)
            resp_headers.pop("Content-Encoding", None)
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=resp_headers,
            )

        # 429: 待機して再試行
        wait_sec = parse_retry_window(response)
        print(f"[429] attempt={attempt + 1}/{MAX_RETRIES} wait={wait_sec}s")
        await asyncio.sleep(wait_sec)

    # 最大リトライ超過
    if response is None:
        return Response(content="No response", status_code=502)
    return Response(
        content=response.content,
        status_code=429,
        headers=dict(response.headers),
    )


if __name__ == "__main__":
    import uvicorn
    # ワーカー数は必ず1
    uvicorn.run(app, host="127.0.0.1", port=8899, workers=1)
