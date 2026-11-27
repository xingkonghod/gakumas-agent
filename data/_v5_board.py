"""Probe (not committed): current hif template leaderboard ranking."""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lb = json.load(urllib.request.urlopen("https://hiro.matto.top/gkbench/api/leaderboard?set=hif&kind=template",
                                      timeout=120))
if isinstance(lb, dict):
    lb = lb.get("rows") or []
rows = [r for r in lb if isinstance(r.get("mean"), (int, float))]
rows.sort(key=lambda r: -r["mean"])
for i, r in enumerate(rows[:10], 1):
    print(f"{i:>2} {r['mean']:>12,.0f}  n={r.get('n'):<4} over={r.get('over'):<4} "
          f"sees={r.get('sees_seed')}  {r.get('label')}")