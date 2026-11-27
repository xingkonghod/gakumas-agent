"""Probe (not committed): current hif leaderboard + top runs + our rows."""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
API = "https://hiro.matto.top/gkbench/api"


def g(p):
    with urllib.request.urlopen(API + p, timeout=120) as f:
        return json.load(f)


rows = g("/runs?set=hif")
rows = rows if isinstance(rows, list) else rows.get("runs", [])
rows = [r for r in rows if r.get("finished") and r.get("mean_score")]
print(f"finished runs: {len(rows)}")
for r in sorted(rows, key=lambda r: -r["mean_score"])[:16]:
    print(f"{r['mean_score']:>10,} eps={r.get('episodes')} kind={r.get('kind')} sees={r.get('sees_seed')} "
          f"rules={r.get('rules')} label={r.get('label')} algo={r.get('algo')} run={r['run'][-16:]}")
print("---- our runs ----")
for r in rows:
    if "gkagent" in str(r.get("label") or "") or "gkagent" in str(r.get("algo") or ""):
        print(f"{r['mean_score']:>10,} eps={r.get('episodes')} kind={r.get('kind')} label={r.get('label')} "
              f"params={r.get('params')}")
print("---- leaderboard template ----")
try:
    lb = g("/leaderboard?set=hif&kind=template")
    print(json.dumps(lb, ensure_ascii=False)[:4000])
except Exception as e:  # noqa: BLE001
    print("lb fail", e)