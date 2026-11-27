"""uinet 1M+ run 时间线与为何不在榜（探针不提交）。"""
import json
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tok = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": "Bearer " + tok}, timeout=90)


def get(p, tries=5):
    for i in range(tries):
        try:
            return c.get(p).raise_for_status().json()
        except Exception:
            time.sleep(4)
    raise SystemExit("fail " + p)


runs = get("/api/runs")
rows = runs if isinstance(runs, list) else runs.get("runs", [])
u = [r for r in rows if r.get("label") == "uinet" and r.get("set") == "hif"]
u.sort(key=lambda r: r.get("finished") or "")
print("uinet hif runs:", len(u))
for r in u:
    print(f"{r.get('finished')}  mean={r.get('mean_score'):>12,.0f} n={r.get('episodes'):>4} "
          f"rules={r.get('rules')} seeds={r.get('template_seeds')} run={r.get('run')}")
lb = get("/api/leaderboard?set=hif&kind=template")
lrows = lb if isinstance(lb, list) else lb.get("rows") or []
for r in lrows:
    if r.get("label") == "uinet":
        print("LB uinet row:", json.dumps({k: r.get(k) for k in
              ("mean", "n", "runs", "names", "seeds_per_problem", "problems")}, ensure_ascii=False)[:900])