"""Probe (not committed): locked vs unlocked deficit split from out/_v5_lockscan.json."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
res = json.loads((ROOT / "out/_v5_lockscan.json").read_text(encoding="utf-8"))
oracle = json.loads((ROOT / "data/_v3_slots.json").read_text(encoding="utf-8"))["oracle"]
lock = [v for v in res.values() if v["lock_turn"]]
unl = [v for v in res.values() if not v["lock_turn"]]
print("n", len(res), "locked", len(lock), "unlocked", len(unl))
for name, rs in (("locked", lock), ("unlocked", unl)):
    if not rs:
        continue
    gaps = [(oracle[f"{v['pid']}/{v['slot']}"] - v["score"], v) for v in rs
            if f"{v['pid']}/{v['slot']}" in oracle and oracle[f"{v['pid']}/{v['slot']}"] > v["score"]]
    print(name, "n", len(rs), "mean", round(sum(v["score"] for v in rs) / len(rs)),
          "mean_secs", round(sum(v["secs"] for v in rs) / len(rs), 1),
          "positive_gap", sum(g for g, _ in gaps),
          "mean_over", round(sum(v["over"] for v in rs) / len(rs), 2))
    print("  lock turns:", sorted({v["lock_turn"] for v in lock}))
print()
print("worst slots (deficit):")
rows = [(oracle[f"{v['pid']}/{v['slot']}"] - v["score"], v) for v in res.values()
        if f"{v['pid']}/{v['slot']}" in oracle and oracle[f"{v['pid']}/{v['slot']}"] > v["score"]]
for g, v in sorted(rows, reverse=True)[:12]:
    print(f"  {v['pid']}/{v['slot']} deficit={g:,} lock={v['lock_turn']} modes={v['modes']}")
print()
print("largest over slots:")
for v in sorted(res.values(), key=lambda x: -x["over"])[:6]:
    print(" ", v["pid"], v["slot"], "over", v["over"], "max_ms", v["max_ms"], "secs", v["secs"])
print()
print("modes by lock turn bucket:")
for lo, hi in ((1, 2), (3, 3), (4, 99)):
    rs = [v for v in lock if lo <= v["lock_turn"] <= hi]
    if rs:
        print(f"  lock {lo}-{hi}: n={len(rs)} mean={round(sum(v['score'] for v in rs)/len(rs)):,} "
              f"secs={round(sum(v['secs'] for v in rs)/len(rs))}")