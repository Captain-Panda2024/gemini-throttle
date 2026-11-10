# gemini-throttle

**バージョン**: 0.8
**ライセンス**: MIT
**著者**: Panda Captain & Reika AI

## 概要

`gemini-throttle` は、アプリケーションと Google Gemini API の間に立つ軽量リバースプロキシです。429（Too Many Requests）を受けた際に、**待機（Park）** してレートリミット窓がリセットされるまで待ち、自動的に再試行します。

このツールは**短時間クォータ制限（RPM/TPM、1分間窓）のみ**を対象とします。日次制限（RPD）、認証エラー、モデル不在エラーは対象外です。他のプロバイダへのフォールバックはスコープ外です — このツールはGeminiの短時間クォータ回避のみに特化しています。

## 問題

- Google Gemini API は厳格な短時間レートリミット（RPM/TPM）を課す
- 無料枠: 1分間に約10〜20リクエスト
- AIエージェント（Hermes, Claude Code等）がツール呼び出しを連続実行すると、数秒で上限に達する
- 429エラーは一時的 — 時間窓が過ぎれば解除される
- 即座にリトライしても解決しない。窓がリセットされるまで待つ必要がある

## 解決策

`gemini-throttle` は `127.0.0.1:8899` にプロキシを配置し、Gemini APIへのリクエストを中継します。429を受けたとき:

1. レスポンスから待機秒数を抽出する（Retry-Afterヘッダ → RetryInfo JSON → 本文文言 → デフォルト10秒の3段フォールバック）
2. その秒数だけ実際に待機する（最大65秒）
3. リクエストを自動的に再試行する（最大3回）

さらに、429が発生する前にリクエストを平滑化するTokenBucket（10 req/min）を事前スロットリングとして実装しました。

## アーキテクチャ

```
Application (Hermes, etc.)
    ↓
127.0.0.1:8899 (gemini-throttle)
    ↓ (429 → park → retry)
generativelanguage.googleapis.com/v1beta/openai
```

## 主要機能

- **429時のPark**: レートリミット窓がリセットされるまで待機し、再試行
- **TokenBucket事前スロットリング**: 10 req/minのスライディングウィンドウで429を事前回避
- **3段待機秒数抽出**: Retry-Afterヘッダ → RetryInfo JSON → 本文文言 → デフォルト10秒
- **最大待機**: 65秒（設定可能）
- **最大リトライ**: 3回（設定可能）
- **ローカルホスト限定**: 127.0.0.1にバインド（外部露出禁止）
- **APIキー非保存**: クライアントのAuthorizationヘッダを中継（プロキシは鍵を持たない）
- **パス正規化**: `/v1`, `/openai`, `/v1beta` セグメントの重複を畳む
- **Gemini専用スコープ**: 他のプロバイダ（DeepInfra, OpenRouter等）に影響しない

## 統合方法

### custom_providers（推奨）

`config.yaml` に追加:

```yaml
custom_providers:
  - name: gemini-throttled
    base_url: http://127.0.0.1:8899/v1
    api_key: ${GOOGLE_API_KEY}
    model: gemini-3.5-flash-lite
```

既存の `gemini` プロバイダは変更しない。`gemini-throttled` を明示的に選択する時だけ使う。

### 重要: GEMINI_BASE_URL は使用禁止

`.env` に `GEMINI_BASE_URL` を設定すると、Hermesのconfig読み込み機構が**全プロバイダのbase_urlをGoogleエンドポイントに上書き**する。DeepInfra等の他のプロバイダがGoogleに流され、404が発生する。過去に8つのcronジョブが全滅した事故の原因だった。

gemini-throttleは`custom_providers`の個別エントリとして統合し、既存プロバイダに影響を与えない。

## 設定

プロキシ設定は `config/gemini.json` から読み込む:

```json
{
  "rate_per_min": 10,
  "max_retries": 3,
  "max_wait_sec": 65,
  "timeout_sec": 40
}
```

## 制約

- 429待機中はリクエストを同期的にブロックする
- 最大待機: 65秒
- 最大リトライ: 3回
- バインド: 127.0.0.1 のみ
- 環境変数 `GOOGLE_API_KEY` を中継（プロキシは鍵を持たない）
- シングルワーカー（uvicorn workers=1）でTokenBucket状態を共有

## ディレクトリ構成

```
gemini-throttle/
├── README.md
├── README.ja.md
├── context.md
├── proxy/
│   ├── main.py
│   └── limiter.py
├── config/
│   └── gemini.json
├── tests/
│   └── test_proxy.py
└── docs/
    └── deployment.md
```

## ライセンス

MIT License. Copyright (c) 2026 Panda Captain & Reika AI.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```