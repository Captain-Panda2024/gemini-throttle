#!/usr/bin/env python3
"""snapshot.py — 定期スナップショット用。

プロキシのログや daily_count.json が失われても、24時間窓と日別累積を
状態ファイルへ固定する。systemd timer から15分ごとに実行する。
"""
import sys
from datetime import datetime

sys.path.insert(0, "/home/captain/projects/gemini-throttle/api")

from aggregate import compute_window, merge_history, write_current_window  # noqa: E402

now = datetime.now()
window = compute_window(now=now, window_hours=24, include_failed=False)
merge_history(window, now=now)
write_current_window(window, now=now)
print(
    f"[snapshot] {now.strftime('%Y-%m-%dT%H:%M:%S')} "
    f"success={window['success']} partial={window['partial']} "
    f"by_model={window['by_model']}",
    flush=True,
)
