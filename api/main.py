#!/usr/bin/env python3
"""main.py — Gemini throttle のリクエスト回数API（FastAPI）

端点:
  GET /health
  GET /v1/gemini/throttle/requests?since=24h[&include_failed=1]
      24時間ウィンドウのモデル別リクエスト件数を集計し、状態ファイルへ書込んで返す
  GET /v1/gemini/throttle/requests/latest
      直近に計算・永続化した24時間窓の値（ログ再走査しない）
  GET /v1/gemini/throttle/counts?date=2026-11-12
      特定の日別カウント（RPD確認用）
  GET /v1/gemini/throttle/state
      現在の永続化状態（history + 最新窓）
"""
import os
from datetime import datetime

from fastapi import FastAPI, Query
from pydantic import BaseModel

from aggregate import (
    compute_window,
    load_daily_entry,
    merge_history,
    write_current_window,
)
from state import daily_entry, load_current_window, load_history

app = FastAPI(title="Gemini Throttle Request Counter")

HOST = os.environ.get("API_HOST", "127.0.0.1")
PORT = int(os.environ.get("API_PORT", "8900"))


class RequestCountResponse(BaseModel):
    window_start: str
    window_end: str
    by_model: dict
    success: int
    attempts: dict
    unwindowed: int
    partial: bool
    log_start_unix: int | None
    gap_from: str | None
    computed_at: str


class CountsResponse(BaseModel):
    date: str
    total: int
    by_model: dict
    source: str


def now_str():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


@app.get("/health")
def health():
    return {"status": "ok", "service": "gemini-throttle-request-counter"}


@app.get("/v1/gemini/throttle/requests", response_model=RequestCountResponse)
def requests(
    since: str = Query("24h", description="ウィンドウ（現在は 24h 固定）"),
    include_failed: bool = Query(
        False,
        description="成功(200)のみでなく、429再試行・budget-block・non-200も数える",
    ),
):
    if since != "24h":
        return {"error": f"未対応の since={since!r}（現在は 24h 固定）"}, 400
    now = datetime.now()
    window = compute_window(now=now, window_hours=24, include_failed=include_failed)
    merge_history(window, now=now)
    write_current_window(window, now=now)

    if include_failed:
        return RequestCountResponse(
            window_start=window["window_start"],
            window_end=window["window_end"],
            by_model=window["by_model"],
            success=window["success"],
            attempts=window["attempts"],
            unwindowed=window["unwindowed"],
            partial=window["partial"],
            log_start_unix=window["log_start_unix"],
            gap_from=window["gap_from"],
            computed_at=now.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    return RequestCountResponse(
        window_start=window["window_start"],
        window_end=window["window_end"],
        by_model=window["by_model"],
        success=window["success"],
        attempts=window["attempts"],
        unwindowed=window["unwindowed"],
        partial=window["partial"],
        log_start_unix=window["log_start_unix"],
        gap_from=window["gap_from"],
        computed_at=now.strftime("%Y-%m-%dT%H:%M:%S"),
    )


@app.get("/v1/gemini/throttle/requests/latest")
def requests_latest():
    latest = load_current_window()
    if latest is None:
        return {"error": "まだ計算された窓がありません。まず /v1/gemini/throttle/requests を叩いてください。"}
    return latest


@app.get("/v1/gemini/throttle/counts", response_model=CountsResponse)
def counts(date: str = Query(..., description="YYYY-MM-DD")):
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        return {"error": "date は YYYY-MM-DD 形式で指定してください。"}, 400
    if date > now_str():
        return {"error": "date は未来日は指定できません。"}, 400
    entry = load_daily_entry(date)
    return CountsResponse(
        date=date,
        total=entry["total"],
        by_model=entry["by_model"],
        source="counts_history.json",
    )


@app.get("/v1/gemini/throttle/state")
def state():
    return {
        "history": load_history(),
        "current_window": load_current_window(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, workers=1)
