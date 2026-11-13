#!/usr/bin/env python3
"""gemini_throttle_report.py — Geminiスロットルの24時間リクエスト集計をTelegramに送信するcronスクリプト。

対象: 毎日 4:30 / 12:00 / 18:30
宛先: TelegramのレイカDM (chat_id = REIKA_DM_CHAT_ID or 既定のTelegram通知経路)
"""
import json
import os
import urllib.request
import urllib.parse

API_URL = "http://127.0.0.1:8900/v1/gemini/throttle/requests"
TELEGRAM_CONFIG = "/home/captain/.hermes2/profiles/main/.env"


def get_telegram_target():
    """Telegramの送信先とトークンを取得する。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("REIKA_DM_CHAT_ID", os.environ.get("TELEGRAM_CHAT_ID", ""))
    
    if not token or not chat_id:
        try:
            with open(TELEGRAM_CONFIG, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    elif line.startswith("REIKA_DM_CHAT_ID=") or line.startswith("TELEGRAM_CHAT_ID="):
                        if not chat_id:
                            chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return token, chat_id


def fetch_throttle_data():
    req = urllib.request.Request(API_URL)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_report(data):
    start = data.get("window_start", "").replace("T", " ")
    end = data.get("window_end", "").replace("T", " ")
    success = data.get("success", 0)
    by_model = data.get("by_model", {})
    attempts = data.get("attempts", {})
    partial = data.get("partial", False)

    lines = [
        "📊 *【レイカのGemini使用量レポート】*",
        f"⏳ 期間: `{start}` ～ `{end}`",
        f"✅ 成功リクエスト総数: *{success}件*",
        "",
        "📌 *モデル別内訳（成功）*:"
    ]

    if by_model:
        for model, count in by_model.items():
            lines.append(f"  - `{model}`: *{count}件*")
    else:
        lines.append("  - (なし)")

    lines.extend([
        "",
        "⚙️ *プロセス試行の内訳*:",
        f"  - 200 OK: {attempts.get('http_200', 0)}",
        f"  - 非200応答: {attempts.get('non200', 0)}",
        f"  - 429再試行: {attempts.get('status429', 0)}",
        f"  - 予算ガード阻止: {attempts.get('budget_block', 0)}",
    ])

    if partial:
        lines.append("\n⚠️ *注*: プロキシ再起動前のログ区間を含むため、窓の一部が欠損しています。")

    return "\n".join(lines)


def main():
    try:
        data = fetch_throttle_data()
    except Exception as e:
        print(f"[ERROR] API fetch failed: {e}")
        return

    text = format_report(data)
    token, chat_id = get_telegram_target()

    if not token or not chat_id:
        print("[ERROR] Telegram token or chat_id not found")
        print(text)
        return

    try:
        res = send_telegram(token, chat_id, text)
        print(f"[OK] Telegram sent successfully: {res.get('ok')}")
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
        print(text)


if __name__ == "__main__":
    main()
