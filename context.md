# Context: Gemini Throttle Bypass

## 問題文脈（2026-11-04 朝の全滅事故）

### 発生日時
2026-11-04 03:00〜08:30 JST

### 現象
- 8つの cron ジョブが全て `RuntimeError: HTTP 404 — Error 404 (Not Found)!!1` で失敗
- 影響ジョブ: 朝4時プロジェクト提案, technews-v3, fugu-strategy, adult-tech-news, wiki-build-index-nightly, Labsゲージ自主較正, top-tools-reset-check
- 正常稼働ジョブ: sentinel-gauge-improve-loop, typo-pipeline-llm-verify（これらはGeminiを使わない）

### 根本原因
`.env` に `GEMINI_BASE_URL=http://generativelanguage.googleapis.com.127.0.0.1.nip.io:8899/openai` を追加したことにより、Hermes の config 読み込みで **全プロバイダの base_url が Google エンドポイントに上書きされた**。

- `config.yaml` の `model.base_url: https://api.deepinfra.com/v1` が無視された
- DeepInfra を使うべきジョブが Google に流された
- Google は `deepseek-ai/DeepSeek-V4-Flash` を知らない → 404

### なぜ GEMINI_BASE_URL が全プロバイダに波及するか
Hermes の config 読み込み機構（`model_switch.py`）は、環境変数 `*_BASE_URL` を config.yaml の値より優先して適用する。
`GEMINI_BASE_URL` は本来 `gemini` プロバイダ専用のオーバーライドだが、実装上是 global に base_url を書き換えてしまう。

## 設計境界

### 対象範囲（IN SCOPE）
- Gemini API エンドポイント（`generativelanguage.googleapis.com`）への短時間レートリミット（429）対策
- 429 受信時の待機（park）と自動再試行
- 1分間の RPM/TPM リミットに対するスロットリング

### 対象外（OUT OF SCOPE）
- 他のプロバイダ（DeepInfra, OpenRouter, fable-distill, etc.）のレートリミット
- 日次リミット（RPD）超過
- モデル不在（404）、認証失敗（401）、サービス不可（503）
- フォールバックチェーンの変更

### 厳格なルール
1. **`.env` への `*_BASE_URL` 追加は禁止**（全局変数のため）
2. **フォールバックは 429 に対して使用しない**——時間経過で解除されるので待機する
3. **他のエンドポイントへの影響を出さない**——Gemini 専用の分離を保証する
4. **Hermes の既存プロバイダ設定は変更しない**——`custom_providers` への追加のみ

## 技術的制約

### Hermes の provider 解決機構
- `auth.py` の `PROVIDER_REGISTRY` が provider を管理
- `gemini` provider の `base_url_env_var` は `GEMINI_BASE_URL`
- `.env` は Hermes 起動時に読み込まれ、`os.environ` に反映される
- config.yaml より環境変数が優先される

### 安全な統合経路
1. `config.yaml` の `custom_providers` に新規エントリ `gemini-throttled` を追加
2. `gemini-throttled` の `base_url` は `http://127.0.0.1:8899/v1`
3. 既存の `gemini` provider は未変更のまま残す
4. 利用側は `--provider gemini-throttled` を明示的に指定

### プロキシ要件
- リッスン: `127.0.0.1:8899`
- 上流: `https://generativelanguage.googleapis.com/v1beta/openai`
- 認証: クライアントの `Authorization` ヘッダをそのまま中継（プロキシは鍵を持たない）
- 429 検出: ステータスコード + `Retry-After` ヘッダ + `RetryInfo` + 本文パターン
- 待機: `time.sleep`（実際にブロックする）
- リトライ: 最大3回
- ログ: `gemini.log` に待機秒・429回数・park を記録

## 既存資産の活用

### 保持すべき設計
- プロキシの RPM/TPM/RPD スロットリング機構（`Limiter` クラス）
- `_join_path` のパス正規化（`/v1` `/openai` `/v1beta` の重複を畳む）
- `parse_retry_window` の429待機時間抽出ロジック
- `record_usage` のTPM見積もり補正

### 破棄すべき設計
- `.env` による `GEMINI_BASE_URL` の全局設定
- `Host` ヘッダの削除（修正済み）
- 404 を 502 に誤訳する Broken pipe ハンドラ

## テスト計画

### unit tests
- `test_join_path`: パス結合の全パターン
- `test_parse_retry_window`: 429 メッセージからの待機時間抽出
- `test_estimate_tokens`: トークン見積もり

### integration tests
- プロキシ起動 → `/v1/models` → 200
- プロキシ経由でのモデル一覧取得
- 429 モックサーバに対する待機・再試行

### smoke tests
- Hermes から `gemini-throttled` provider でモデル呼び出し
- cron ジョブで `gemini-throttled` を使用して dry-run

## 配置計画

### ファイル配置
```
./
├── README.md
├── context.md
├── scripts/
│   └── gemini_throttle_proxy.py    # プロキシ本体
├── config/
│   └── gemini.json                 # プロキシ設定
├── tests/
│   └── test_proxy.py
└── docs/
    └── deployment.md

# 実行配置
~/.hermes2/profiles/main/scripts/gemini_throttle_proxy.py  → scripts/ からシンボリックリンク
~/.hermes2/profiles/main/throttle/gemini.json              → config/ からコピー
```

### systemd unit
`~/.config/systemd/user/gemini-throttle.service`

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

### Hermes config.yaml への追加
```yaml
custom_providers:
  - name: gemini-throttled
    base_url: http://127.0.0.1:8899/v1
    api_key: ${GOOGLE_API_KEY}
    model: gemini-3.5-flash-lite
```

## 決定記録

| 日時 | 決定 | 理由 |
|------|------|------|
| 2026-11-04 | `.env` の `GEMINI_BASE_URL` を削除 | 全局変数が他のプロバイダに影響 |
| 2026-11-04 | プロキシを `custom_providers` の個別エントリとして統合 | 既存 `gemini` provider を変更しない |
| 2026-11-04 | 429 には待機（park）のみ、フォールバック禁止 | 429 は時間で解除される |
| 2026-11-04 | プロキシは `127.0.0.1` にバインド | 外部からのアクセス禁止 |
| 2026-11-04 | 環境変数の読み込みは systemd の `EnvironmentFile` で | プロキシプロセスに直接渡す |
