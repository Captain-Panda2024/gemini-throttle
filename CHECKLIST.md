# CHECKLIST — gemini-throttle 実装

## Mission
Gemini API 429 レートリミットに対する自律的回避プロキシを完成させる。
429受信時に待機（park）して再試行し、Hermes から `gemini-throttled` provider として利用可能にする。

## 完了条件
- [x] 429受信時の待機・再試行ロジック実装済み（最大3回、最大65秒）
- [x] `parse_retry_window` 実装済み（Retry-After / RetryInfo / 本文からの待機時間抽出）
- [x] `config/gemini.json` 作成済み
- [x] `tests/test_proxy.py` 作成済み・全テストPASS
- [x] `docs/deployment.md` 作成済み
- [x] systemd unit 作成済み
- [x] Hermes `config.yaml` に `custom_providers` 追加済み
- [ ] プロキシ起動・`/v1/models` → 200 確認（APIキー必要・未実行）
- [x] CONTEXT.md 更新済み
- [x] git commit 完了

## 非ゴール
- 他のプロバイダ（DeepInfra, OpenRouter等）のレートリミット対策
- 日次リミット（RPD）超過対策
- フォールバックチェーンの変更

## Abort Triggers
- [ ] captainの明示承認が必要な範囲に入った
- [ ] 依存サービスの認証・課金・権限で詰まった
- [ ] 連続して同種のエラーが2回以上発生した
- [ ] 仕様解釈が複数に分岐し、成果物の方向性が変わる
- [ ] トークン・時間消費が当初見積もりを大きく超える

## Strategic Action Map

| # | Action | Reaction (予測される失敗) | Counteraction (対抗措置) | Verification | Status |
|---|--------|--------------------------|--------------------------|--------------|--------|
| 1 | `parse_retry_window` 実装 | メッセージ形式の多様性 | 複数パターンのフォールバック（Retry-After → RetryInfo → 本文regex → デフォルト） | unit test | ✅ |
| 2 | 429待機・再試行ロジック実装 | 429以外のエラー混入 | ステータスコード厳密チェック、非429は即返却 | unit + integration test | ✅ |
| 3 | `config/gemini.json` 作成 | 設定値の不整合 | README/context.md の制約値と一致させる | JSON validity check | ✅ |
| 4 | `tests/test_proxy.py` 作成 | テスト不足 | parse_retry_window, _join_path, estimate_tokens の全パターン | pytest実行 | ✅ |
| 5 | `docs/deployment.md` 作成 | 手順の曖昧さ | 具体的なコマンド付きで記述 | 読み返し確認 | ✅ |
| 6 | systemd unit 作成 | パス不整合 | context.md の配置計画に従う | systemd-analyze verify | ✅ |
| 7 | Hermes config.yaml に custom_providers 追加 | 既存設定の破壊 | 既存 `gemini` provider は変更しない、追加のみ | YAML validity + diff確認 | ✅ |
| 8 | プロキシ起動・`/v1/models` → 200 確認 | 起動失敗 | ログ確認、依存パッケージ確認 | curl テスト | ☐ |
| 9 | CONTEXT.md 更新 + git commit | コミット漏れ | git status 確認 | git log 確認 | ✅ |

## Execution Rules
1. 指示書の範囲外を勝手に拡張しない。
2. 失敗したら即座にReactionへ分類し、Counteractionを実行する。
3. Abort Triggerに触れたら作業を止めてcaptainへ報告する。
4. 最終成果物は必ず実行・テスト・読み返しなどで検証する。
5. コードを変えたら必ずレビュー（diff確認）してから次へ進む。
6. テストを考えてテストを実行し、問題がない段階になってから次へ進む。

## 進捗ログ

| 日時 | アクション | 結果 |
|------|-----------|------|
| 2026-11-06 22:59 | CONTEXT.md作成 + git commit | 完了 |
| 2026-11-06 23:00 | CHECKLIST.md作成 | 完了 |
