# gemini-throttle

**バージョン**: 1.0
**ライセンス**: MIT
**著者**: Panda Captain & Reika AI

## 概要

`gemini-throttle` は、アプリケーションと Google Gemini API の間に立つ軽量なゲートウェイ・リバースプロキシです。429（Too Many Requests）の自動待機（Park）と、日次予算の適正管理を提供し、AIエージェントの運用を安定させます。

## v1.0 の改善点

- **予算管理の刷新**: 404ヘルスチェックや503切断などの「不要なカウント」を排除し、真の生成成功（status=200）のみを日次予算（Free Tier）として計上。
- **モデル別上限ガード**: 複数のモデルを併用する場合、モデルごとに適切に上限を管理。
- **モデル名正規化**: `models/` プレフィックスの有無による二重計上を防止。
- **ヘルスチェックの透過**: 生成を伴わないパス（ヘルスチェック等）へのリクエストは予算ガード対象外とし、不要なブロックを排除。
- **観測可能性**: ログに `counted=1|0` フラグを追加し、予算消費の透明性を確保。

## 主要機能

- **日次予算ガード (Budget Guard)**: モデルごとの生成成功回数を追跡し、上限に達した場合は即座に429を返して過剰なAPIコールを未然に防ぐ。
- **429時のParkとRetry**: レートリミット窓がリセットされるまで待機（最大65秒）し、自動的に再試行。
- **TokenBucket事前スロットリング**: 10 req/minのスライディングウィンドウで、429が発生する前にリクエストを平滑化。
- **パス正規化**: プロキシ経由でもヘッダの不整合やパス重複（`/v1/v1beta/`等）を自動修正。
- **APIキー非保存**: クライアントの Authorization ヘッダを透過させ、プロキシ自身は鍵を保持しない。

## 統合方法

### custom_providers（推奨）

`config.yaml` にプロキシを経由するエンドポイントを追加してください。

```yaml
custom_providers:
  - name: gemini-throttled
    base_url: http://127.0.0.1:8899/v1
    api_key: ${GOOGLE_API_KEY}
    model: gemini-3.1-flash-lite
```

既存の `gemini` プロバイダを直接書き換えるのではなく、`gemini-throttled` を追加して切り替えることを推奨します。

## 設定

プロキシの動作設定は `config/gemini.json` で行います。

```json
{
  "listen_host": "127.0.0.1",
  "listen_port": 8899,
  "max_retries": 3,
  "max_wait_sec": 65,
  "timeout_sec": 40
}
```

## アーキテクチャ

```
Application (Hermes, etc.)
    ↓
127.0.0.1:8899 (gemini-throttle)
    ↓ (429 → park → retry / Budget Guard → 429)
generativelanguage.googleapis.com
```

## 運用上の注意

- **日次予算ガード**: 成功したリクエスト（status=200）のみが `daily_count.json` に計上されます。
- **APIキー**: 必ず `GOOGLE_API_KEY` を環境変数としてプロキシに渡してください。
- **ヘルスチェック**: `/v1/models` 等の生成を伴わないクエリはカウント対象外であり、予算が満杯であっても通過します。

## ライセンス

MIT License. Copyright (c) 2026 Panda Captain & Reika AI.
