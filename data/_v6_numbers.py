"""Probe (not committed): final v6 numbers for docs (starts/step, clone-cost symptom, gate-vs-full noise)."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
v6 = json.loads((ROOT / "out/_v6_v6steps.json").read_text(encoding="utf-8"))
gate = json.loads((ROOT / "out/_v6_gatesteps.json").read_text(encoding="utf-8"))
v5f = json.loads((ROOT / "out/_v5_final.json").read_text(encoding="utf-8"))
v6f = json.loads((ROOT / "out/_gkagent-ex-seed-v6_final.json").read_text(encoding="utf-8"))

pool, full, part, over, mode_ms = [], 0, 0, Counter(), Counter()
for k, g in v6.items():
    for s in g["steps"]:
        if s.get("pool_searches") is not None:
            pool.append(int(s["pool_searches"]))
        full += int(s.get("pool_full") or 0)
        part += int(s.get("pool_partial") or 0)
        if float(s.get("ms") or 0) > 12050:
            over["total"] += 1
            over[s.get("mode")] += 1
            over["big40s" if float(s["ms"]) > 40000 else "12-40s"] += 1
        mode_ms[s.get("mode")] += float(s.get("ms") or 0)
print(f"v6 240 slots: starts/step mean={statistics.mean(pool):.1f} "
      f"p10={sorted(pool)[len(pool)//10]} p50={sorted(pool)[len(pool)//2]} "
      f"p90={sorted(pool)[int(.9*(len(pool)-1))]} max={max(pool)}  full={full} partial={part}")
print("over:", dict(over))
print("think by mode (s):", {m: round(v / 1000) for m, v in sorted(mode_ms.items())})

# gate vs full on the same 30 slots = same algorithm, same fixed secret seeds -> rerun noise
gk = set(gate) & set(v6)
d = [v6[k]["score"] - gate[k]["score"] for k in gk]
print(f"\nv6 gate-vs-full rerun on {len(gk)} same slots: meanΔ={statistics.mean(d):+,.0f} "
      f"medianΔ={statistics.median(d):+,.0f} sd={statistics.stdev(d):,.0f} "
      f"max|Δ|={max(abs(x) for x in d):,.0f}")
for k in sorted(gk, key=lambda k: -abs(v6[k]["score"] - gate[k]["score"]))[:6]:
    print(f"  {k:16s} gate={gate[k]['score']:>12,} full={v6[k]['score']:>12,} "
          f"Δ={v6[k]['score']-gate[k]['score']:>+12,}")

# per-tier summary v6 vs v5
slots = {s["key"]: s for s in json.loads((ROOT / "out/_v5_slots.json").read_text(encoding="utf-8"))}
v5 = v5f["scores"]
for nm, cond in (("FINAL", lambda r: int(r.get("limit_turn") or 0) >= 12),
                 ("MID", lambda r: 0 < int(r.get("limit_turn") or 0) < 12)):
    ks = [k for k in v6f["scores"] if cond(slots[k])]
    dd = [v6f["scores"][k] - v5[k] for k in ks]
    print(f"{nm}: n={len(ks)} v5mean={statistics.mean(v5[k] for k in ks):,.0f} "
          f"v6mean={statistics.mean(v6f['scores'][k] for k in ks):,.0f} "
          f"meanΔ={statistics.mean(dd):+,.0f} win={sum(1 for x in dd if x>0)} "
          f"lose={sum(1 for x in dd if x<0)} tie={sum(1 for x in dd if x==0)}")