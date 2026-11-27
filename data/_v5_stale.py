"""Probe (not committed): which v5 slots were produced by the superseded configs (need re-run)?"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
API = "https://hiro.matto.top/gkbench/api"
# 配置沿革：这些 run 的局是旧缺省（portfolio+mirror_vote waves=1 / 填满预算）跑的，最终配置要覆盖它们
STALE = {"d943f444dfb0", "d617abc6ed04", "9bd9f671f5dc"}


def g(p):
    with urllib.request.urlopen(API + p, timeout=120) as f:
        return json.load(f)


rows = g("/runs?set=hif")
rows = rows if isinstance(rows, list) else rows.get("runs", [])
stale, current = [], []
for r in rows:
    if str(r.get("label")) != "gkagent-ex-seed-v5":
        continue
    rid = r["run"].rsplit("-", 1)[-1]
    eps = g("/runs/" + r["run"]).get("episodes") or []
    slot = (stale if rid in STALE else current)
    for e in eps:
        if e.get("finished") and e.get("score") is not None:
            slot.append((f"{e['id']}/{e['seed_index']}", int(e["score"]), rid))
print(f"stale slots ({len(stale)}):")
for k, s, rid in sorted(stale):
    print(f"  {k:<20} score={s:>12,} run={rid}")
print(f"\ncurrent slots ({len(current)})")
probs = sorted({k.rsplit("/", 1)[0] for k, _s, _r in stale})
print("stale problems to re-run:", ",".join(probs))
json.dump({"stale": stale, "problems": probs}, open("out/_v5_stale.json", "w"), ensure_ascii=False)