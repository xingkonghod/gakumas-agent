"""sim-fidelity item 1 (no-commit): W9 engine replay score_mult / half_cost_until trajectory.

Extract per-decision score_mult + half_cost_until + turn from out/_drinks_test_W9.json
(engine oracle, already captured) to check drink-channel timed duration convention.
Pure local parse, no engine run.
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "out/_drinks_test_W9.json").read_text(encoding="utf-8"))
print("rules", d["rules"], "final", d["final_score"], "mismatches", d["decision_mismatches"])
print("drink steps:")
for s in d["drink_steps"]:
    b, a = s["before"], s["after"]
    print("  i=%s drink=%s turn=%s score_mult %s -> %s half_until %s -> %s" % (
        s["i"], s["drink"], b["turn"], b["score_mult"], a["score_mult"],
        b["half_cost_until"], a["half_cost_until"]))
# rows carry per-decision before snapshots (45 decisions)
rows = d.get("rows") or []
print("rows:", len(rows))
prev = None
for r in rows:
    b = r["before"]
    cur = (b["turn"], b["score_mult"], b["half_cost_until"])
    if prev is None or cur[1:] != prev[1:]:
        print("  i=%s kind=%s turn=%s score_mult=%s half_until=%s" % (
            r["i"], r["kind"], b["turn"], b["score_mult"], b["half_cost_until"]))
    prev = cur