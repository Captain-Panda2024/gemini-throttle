# Deployment Guide — gemini-throttle

## 前提条件
- Python 3.11+ (httpx, fastapi, uvicorn がインストール済み)
- `GOOGLE_API_KEY` が `.env` に設定済み

## 1. プロキシの配置

```bash
# プロジェクトからプロファイルへシンボリックリンク
ln -s ./proxy/main.py \
      ~/.hermes2/profiles/main/scripts/gemini_throttle_proxy.py

# 設定ファイルをコピー
mkdir -p ~/.hermes2/profiles/main/throttle
cp ./config/gemini.json \
   ~/.hermes2/profiles/main/throttle/gemini.json
```

## 2. 手動起動

```bash
export GEMINI_API_KEY=$(grep 'GOOGLE_API_KEY=' ~/.hermes2/profiles/main/.env | cut -d= -f2 | tr -d '"'"'"')
./start_proxy.sh
```

## 3. 動作確認

```bash
curl -s http://127.0.0.1:8899/v1/models -H "Authorization: Bearer $GEMINI_API_KEY" | head -c 200
```

期待: HTTP 200 + JSON レスポンス

## 4. systemd unit（オプション）

`~/.config/systemd/user/gemini-throttle.service` を作成:

```ini
[Unit]
Description=Gemini Throttle Bypass Proxy
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ~/.hermes2/profiles/main/scripts/gemini_throttle_proxy.py --config ~/.hermes2/profiles/main/throttle/gemini.json
WorkingDirectory=~/.hermes2/profiles/main
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=~/.hermes2/profiles/main/.env
StandardOutput=append:~/.hermes2/profiles/main/throttle/gemini.log
StandardError=append:~/.hermes2/profiles/main/throttle/gemini.log

[Install]
WantedBy=default.target
```

有効化:
```bash
systemctl --user daemon-reload
systemctl --user enable --now gemini-throttle.service
```

## 5. Hermes config.yaml への追加

```yaml
custom_providers:
  - name: gemini-throttled
    base_url: http://127.0.0.1:8899/v1
    api_key: ${GOOGLE_API_KEY}
    model: gemini-3.5-flash-lite
```

**注意**: 既存の `gemini` provider は変更しない。`gemini-throttled` は明示的に選択する時だけ使う。

## 6. テスト実行

```bash
cd ~/projects/gemini-throttle
~/.hermes2/profiles/main/hermes-agent/venv/bin/python -m unittest tests.test_proxy -v
```
