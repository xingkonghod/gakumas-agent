"""Probe (not committed): hif template leaderboard summary sorted by mean."""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
API = "https://hiro.matto.top/gkbench/api"


def g(p):
    with urllib.request.urlopen(API + p, timeout=120) as f:
        return json.load(f)


lb = g("/leaderboard?set=hif&kind=template")
if isinstance(lb, dict):
    lb = lb.get("rows") or lb.get("leaderboard") or []
print(f"rows={len(lb)}")
keys = ["mean", "n", "seeds_per_problem", "step_seconds", "label", "by", "sees_seed", "over",
        "vs_oracle", "run"]
for r in sorted(lb, key=lambda r: -(r.get("mean") or 0))[:14]:
    vo = r.get("vs_oracle") or {}
    print(f"{r.get('mean'):>12,.0f} n={r.get('n')} sp={r.get('seeds_per_problem')} sec={r.get('step_seconds')} "
          f"over={r.get('over')} geo={vo.get('geo')} win={vo.get('win')} sees={r.get('sees_seed')} "
          f"by={r.get('by')} label={r.get('label')}")
print("---- ours / best-known / oracle ----")
for r in lb:
    lab = str(r.get("label") or "")
    if any(k in lab.lower() for k in ("gkagent-ex-seed-v4", "gkagent-ex-seed-v3", "best-known", "oracle")):
        print(f"{r.get('mean'):>12,.0f} n={r.get('n')} sp={r.get('seeds_per_problem')} over={r.get('over')} "
              f"by={r.get('by')} label={lab} run={str(r.get('run'))[-20:]}")