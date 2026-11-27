"""无 seed（screen）榜真实排序（探针不提交）。"""
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


lb = get("/api/leaderboard?set=hif&kind=template")
rows = lb if isinstance(lb, list) else lb.get("rows") or []
screen = [r for r in rows if not r.get("sees_seed")]
screen.sort(key=lambda r: r.get("mean") or 0, reverse=True)
print("screen rows", len(screen))
for r in screen[:12]:
    eng = r.get("engine") or {}
    print(f"{r.get('mean'):>12,.0f} n={r.get('n'):>4} rules={eng.get('rules_version')} "
          f"step={r.get('step_seconds')} over={r.get('over')} {r.get('label')} by={r.get('by')}")
print("--- seed top5 ---")
seed = [r for r in rows if r.get("sees_seed")]
seed.sort(key=lambda r: r.get("mean") or 0, reverse=True)
for r in seed[:5]:
    eng = r.get("engine") or {}
    print(f"{r.get('mean'):>12,.0f} n={r.get('n'):>4} rules={eng.get('rules_version')} "
          f"{r.get('label')} by={r.get('by')}")