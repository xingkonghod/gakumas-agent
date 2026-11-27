"""sim-fidelity type21 pool analysis (no-commit, pure local, no engine)."""
import io
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
tdir = ROOT / "data/GKMSMainWheel/GakumasCLI/ro/master/tables"
rows = [json.loads(l) for l in (tdir / "ProduceCardRandomPool.jsonl").open(encoding="utf-8") if l.strip()]
dec = [r.get("decoded", r) for r in rows]
pool = [r for r in dec if r.get("id") == "p_random_pool-all-upgrade_1"]
print("pool total:", len(pool))
plans = Counter(r["produceCardId"].split("-")[1] for r in pool)
print("by plan prefix:", dict(sorted(plans.items())))
ratios = Counter(r.get("ratio") for r in pool)
print("ratios:", dict(ratios))
ups = Counter(r.get("upgradeCount") for r in pool)
print("upgradeCounts:", dict(ups))
# other pools
ids = Counter(r.get("id") for r in dec)
print("all pool ids:", dict(ids))
# generated cards from m1b probe
gen = ["p_card-01-act-2_061", "p_card-01-act-2_032", "p_card-00-men-3_003"]
poolmap = {(r["produceCardId"], r.get("upgradeCount")): i for i, r in enumerate(pool)}
for g in gen:
    print("generated", g, "in pool at index", poolmap.get((g, 1)))
# problem plans
dl = ROOT / "data/bench_local/gkbench_dl/hif"
saves = {}
with (dl / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r
for pid in ["AS-4BFABQK9", "AS-3TJXEB7T", "AS-JQXN3NK5"]:
    s = saves.get(pid, {})
    lo = s.get("loadout") or {}
    keys = {k: lo.get(k) for k in ("plan_type", "planType", "idol_plan", "produce_plan") if k in lo}
    print(pid, "plan keys:", keys, "loadout top keys:", sorted(lo.keys())[:20])