"""Probe (not committed): what algorithm/params produced the best-known rows?"""
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
bk = [r for r in rows if str(r.get("label")) == "best-known" and (r.get("episodes") or 0) >= 900]
print(f"best-known runs with >=900 eps: {len(bk)}")
for r in bk[:3]:
    print("\nrun:", r["run"], "eps:", r.get("episodes"), "mean:", r.get("mean_score"))
    for k in ("algo", "label", "by", "mode", "kind", "engine", "params", "step_seconds",
              "seeds_per_problem", "privileged", "sees_seed", "about", "started", "finished"):
        v = r.get(k)
        if v is not None:
            print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:600]}")