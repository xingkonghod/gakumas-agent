"""一次性：拉 hif 排行榜（公开），找 uinet/greedy/random 参考分与评测进度。"""
import json
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
r = httpx.get("https://hiro.matto.top/gkbench/api/leaderboard",
              params={"set": "hif", "kind": "template"}, timeout=60)
print("status", r.status_code)
j = r.json()
print("top-level type:", type(j).__name__)
if isinstance(j, dict):
    print("keys:", list(j.keys()))
    rows = j.get("rows") or []
else:
    rows = j
print("rows:", len(rows))
for row in rows[:40]:
    if isinstance(row, dict):
        keep = {k: row[k] for k in row if k in (
            "algo", "label", "name", "title", "score", "mean", "avg", "episodes",
            "n", "scope", "rank", "kind", "mode", "family", "run")}
        print(json.dumps(keep, ensure_ascii=False))
    else:
        print(row)