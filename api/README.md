# Gemini Throttle Request Counter API

Gemini スロットル（`gemini-throttle-bypass.service` / 127.0.0.1:8899）の
リクエストログを集計し、モデル別の24時間ウィンドウ件数と日別累積を永続化して返す。

- データ源: `/home/captain/.hermes2/profiles/main/throttle/gemini.log` の `[REQ]` 行
- 集計: `/home/captain/.hermes2/profiles/main/throttle/counts_24h.json`（最新窓）
- 履歴: `/home/captain/.hermes2/profiles/main/throttle/counts_history.json`（日別、再起動に強い）

## 起動

```
systemctl --user enable --now gemini-throttle-counts.service        # API本体（:8900）
systemctl --user enable --now gemini-throttle-counts-snapshot.timer # 15分ごとのスナップショット
```

## エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/health` | 死活確認 |
| GET | `/v1/gemini/throttle/requests?since=24h[&include_failed=1]` | 24時間ウィンドウのモデル別件数を集計し、状態ファイルへ書込んで返す |
| GET | `/v1/gemini/throttle/requests/latest` | 直近に計算・永続化した窓の値（ログ再走査なし） |
| GET | `/v1/gemini/throttle/counts?date=YYYY-MM-DD` | 日別カウント（RPD確認用） |
| GET | `/v1/gemini/throttle/state` | 現在の永続化状態 |

## 集計の意味

- `success`: プロキシが処理したリクエスト（429を嵌っていないもの）の件数。
  `daily_count.json` の当日 `count` と一致する（例: 2026-11-12 は 430/430）。
- `by_model`: モデル別の内訳。`models/` プレフィックスは正規化して合算。`?` はモデル不明。
- `attempts`: `http_200` / `non200` / `status429` / `budget_block` の内訳。
- `unwindowed`: タイムスタンプを持たない `[429]` 行の数（窓に配置できない）。
- `partial`: 窓の開始がログ開始より前なら `true`。ログが現在のプロキシの生きた間より短いことを示す。
  ただし `daily_count.json` とログの `[REQ]` が一致していれば、当日分は完全に捕捉できている。

## 再起動に対する耐性

- `gemini-throttle-bypass.service` は `StandardOutput=append:` でログを追記する。
  systemd 再起動ではログは truncate されない。
- 失われやすいのは「前回のプロキシの生きた間のログ」と「日次リセットのカウンタ」。
  そのため API は `counts_history.json` に日別累積を 15 分ごとに固定する。
  プロキシが再起動しても、RPD の日別履歴はここから読める。
- `partial: true` かつ `daily_count.json` と件数が合わない場合だけ、欠損を疑う。
