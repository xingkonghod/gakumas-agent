"""sim-fidelity type21: cons vs owned-unique / pool-filter hypotheses (existing jsonl)."""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
tdir = ROOT / "data/GKMSMainWheel/GakumasCLI/ro/master/tables"
rows = [json.loads(l) for l in (tdir / "ProduceCardPool.jsonl").open(encoding="utf-8") if l.strip()]
dec = [r.get("decoded", r) for r in rows]
agg = {r["id"]: r for r in dec}
pool = [r["id"] for r in agg["p_random_pool-all-upgrade_1"]["produceCardRatios"]]
poolset = set(pool)
N = len(pool)
rows2 = [json.loads(l) for l in (tdir / "ProduceCardRandomPool.jsonl").open(encoding="utf-8") if l.strip()]
flat = [r.get("decoded", r).get("produceCardId") for r in rows2 if r.get("decoded", r).get("id") == "p_random_pool-all-upgrade_1"]
flatset = set(flat)

jl = ROOT / "data/_m1b_type21_p1.jsonl"
recs = [json.loads(l) for l in jl.open(encoding="utf-8") if l.strip()]
# find target rows and reconstruct owned zones from the step's before snapshot
for r in recs:
    if r.get("is_target"):
        pid = r["pid"]
        cons = r["consumption"]
        hand = r["hand_before"]
        # deck/grave not in row; need preceding snap. The row has deck_len_before only.
        print(pid, "cons", cons, "deck_len", r["deck_len_before"], "hand", hand,
              "grave_len", r["grave_len_before"], "gen", r["hand_after"])
        print("   174-cons=", N - cons, "164-cons=", len(flat) - cons)