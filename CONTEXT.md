# CONTEXT — gemini-throttle

## 1. これは何か
Gemini API の短時間レートリミット（429）に対する自律的回避プロキシ。
Hermes と Google AI Studio の間に配置し、429 を受信したら待機して再試行する。

## 2. 背景（2026-11-04 朝の全滅事故）
`.env` に `GEMINI_BASE_URL` を追加したことにより、Hermes の config 読み込みで
**全プロバイダの base_url が Google エンドポイントに上書きされた**。
DeepInfra を使うべきジョブが Google に流され、`deepseek-ai/DeepSeek-V4-Flash` が見つからず 404。
→ `.env` の `GEMINI_BASE_URL` は削除済み。今後は `custom_providers` への個別追加のみ。

## 3. 現在の状態
- `proxy/main.py` — FastAPIプロキシ（127.0.0.1:8899）。トークンバケット事前スロットリング + 429受信時の待機・再試行（最大3回、最大65秒）実装済み。`parse_retry_window` / `_join_path` / `estimate_tokens` 実装済み。
- `proxy/limiter.py` — `TokenBucket` クラス（非同期トークンバケット）
- `start_proxy.sh` — 起動スクリプト
- `config/gemini.json` — プロキシ設定
- `tests/test_proxy.py` — 12テスト全PASS
- `docs/deployment.md` — 配置手順
- systemd unit — `~/.config/systemd/user/gemini-throttle.service`（verify済み）
- Hermes config — `custom_providers` に `gemini-throttled` 追加済み

### 完了済み
- [x] 429受信時の待機・再試行ロジック実装済み（最大3回、最大65秒）
- [x] `parse_retry_window` 実装済み
- [x] `config/gemini.json` 作成済み
- [x] `tests/test_proxy.py` 作成済み・12テスト全PASS
- [x] `docs/deployment.md` 作成済み
- [x] systemd unit 作成済み・verify済み
- [x] Hermes config.yaml に custom_providers 追加済み
- [ ] プロキシ起動・`/v1/models` → 200 確認（未実行・APIキー必要）

## 4. 次の一手
1. プロキシ起動・`/v1/models` → 200 確認（APIキー必要）
2. 実際の429に対する待機・再試行の動作確認（モックサーバでの統合テスト）
3. systemd service の enable/start（captain判断）

## 5. 設計境界
- **対象**: `generativelanguage.googleapis.com` への短時間レートリミット（429）対策
- **対象外**: 他のプロバイダ（DeepInfra, OpenRouter, fable-distill等）のレートリミット
- **厳格なルール**:
  1. `.env` への `*_BASE_URL` 追加は禁止（全局変数のため）
  2. 429 には待機（park）のみ、フォールバック禁止
  3. 他のエンドポイントへの影響を出さない
  4. Hermes の既存プロバイダ設定は変更しない（`custom_providers` への追加のみ）

## 6. 技術的制約
- リッスン: `127.0.0.1:8899`
- 上流: `https://generativelanguage.googleapis.com/v1beta/openai`
- 認証: クライアントの `Authorization` ヘッダをそのまま中継（プロキシは鍵を持たない）
- 最大待機時間: 65秒
- 最大リトライ回数: 3回
- プロキシは `127.0.0.1` にバインド（外部露出禁止）

## 7. 資料の置き場
- `README.md` — プロジェクト概要・アーキテクチャ
- `context.md` — 問題文脈・制約・決定記録
- `CONTEXT.md` — このファイル（セッション復元用）
- `proxy/main.py` — プロキシ本体
- `proxy/limiter.py` — トークンバケット
- `start_proxy.sh` — 起動スクリプト
