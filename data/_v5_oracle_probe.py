"""Probe (not committed): why is vs_oracle None on our rows? compare a full-featured row."""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
lb = json.load(urllib.request.urlopen("https://hiro.matto.top/gkbench/api/leaderboard?set=hif&kind=template",
                                      timeout=120))
if isinstance(lb, dict):
    lb = lb.get("rows") or []
print("n rows", len(lb))
print("row keys:", sorted({k for r in lb for k in r}))


def show(tag, r):
    keep = ("label", "mean", "n", "problems", "seeds_per_problem", "over", "vs_oracle", "sees_seed",
            "step_seconds", "core_problems", "mode", "kind", "family")
    print(f"\n[{tag}] " + json.dumps({k: r.get(k) for k in keep if k in r}, ensure_ascii=False))


for r in lb:
    lab = str(r.get("label")) if r.get("label") is not None else str(r.get("run"))
    if r.get("label") == "gkagent-ex-seed-v5":
        show("ours v5", r)
    elif r.get("label") == "gkagent-ex-seed-v5b":
        show("ours v5b", r)
    elif "UIHorizon-v2.1" in lab:
        show("uihorizon21", r)
    elif r.get("label") == "best-known" and (r.get("n") or 0) >= 900:
        show("best-known", r)
    elif r.get("label") == "gkagent-expectimax" and (r.get("n") or 0) >= 200:
        show("our expectimax", r)
print("\nrows with vs_oracle != None:", sum(1 for r in lb if r.get("vs_oracle")))
print("rows total:", len(lb))
for r in lb[:3]:
    print("\nsample row:", json.dumps(r, ensure_ascii=False)[:800])