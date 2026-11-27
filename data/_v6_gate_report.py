"""Probe (not committed): v6 门小样报告（v6 30 槽 vs 同槽 v5/v4）。

先跑：.venv\\Scripts\\python.exe data\\_v6_stepscan.py gkagent-ex-seed-v6 _v6_gatesteps.json
再跑本脚本。
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]


def boot_ci(deltas, iters=10000, seed=20261127):
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return (0, 0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def stats(xs):
    if not xs:
        return {}
    xs = sorted(xs)
    return {"n": len(xs), "mean": round(statistics.mean(xs)), "p50": round(xs[len(xs) // 2]),
            "p95": round(xs[int(0.95 * (len(xs) - 1))]), "max": round(max(xs)),
            "sum_s": round(sum(xs) / 1000)}


def main():
    v5 = json.loads((ROOT / "out/_v5_final.json").read_text(encoding="utf-8"))["scores"]
    slots = json.loads((ROOT / "out/_v5_slots.json").read_text(encoding="utf-8"))
    meta = {s["key"]: s for s in slots}
    v6doc = json.loads((ROOT / "out/_v6_gatesteps.json").read_text(encoding="utf-8"))
    if isinstance(v6doc, list):                      # stepscan saves dict; tolerate list of slots
        v6doc = {f"{r['pid']}/{r['slot']}": r for r in v6doc}
    v6 = {k: v["score"] for k, v in v6doc.items()}
    keys = sorted(v6)
    print(f"v6 gate slots={len(keys)}")
    paired = [k for k in keys if k in v5]
    print(f"paired with v5={len(paired)}")
    d = [v6[k] - v5[k] for k in paired]
    lo, hi = boot_ci(d)
    print(f"\n--- paired v6 vs v5 (same slots) ---")
    print(f"v5 mean={statistics.mean(v5[k] for k in paired):,.0f}  "
          f"v6 mean={statistics.mean(v6[k] for k in paired):,.0f}")
    print(f"meanΔ={statistics.mean(d):+,.0f}  sd={statistics.stdev(d) if len(d)>1 else 0:,.0f}  "
          f"CI95=[{lo:+,.0f},{hi:+,.0f}]  win={sum(1 for x in d if x>0)} "
          f"lose={sum(1 for x in d if x<0)} tie={sum(1 for x in d if x==0)}")
    orc = [(k, meta[k]["oracle"]) for k in paired if meta.get(k, {}).get("oracle")]
    if orc:
        r5 = statistics.mean(v5[k] / o for k, o in orc)
        r6 = statistics.mean(v6[k] / o for k, o in orc)
        print(f"oracle ratio: v5={r5:.4f} v6={r6:.4f}")
    print("\n--- per slot ---")
    print(f"{'slot':18s} {'v4':>12s} {'v5':>12s} {'v6':>12s} {'Δv6-v5':>12s} {'oracle':>12s} {'ratio6':>7s}")
    for k in keys:
        m = meta.get(k) or {}
        o = m.get("oracle")
        print(f"{k:18s} {m.get('ours',0):>12,} {v5.get(k,0):>12,} {v6[k]:>12,} "
              f"{v6[k]-v5.get(k,0):>+12,} {(o or 0):>12,} "
              f"{(v6[k]/o if o else 0):>7.3f}")

    # step composition v6 vs v5
    print("\n--- step composition: v6 vs v5 ---")
    v5steps = json.loads((ROOT / "out/_v6_v5steps.json").read_text(encoding="utf-8"))
    v5sel = {k: v5steps[k] for k in keys if k in v5steps}
    for tag, doc in (("v5", v5sel), ("v6", v6doc)):
        by = defaultdict(list)
        pool = []
        full = partial = 0
        over = Counter()
        for k, g in doc.items():
            for s in g["steps"]:
                by[s.get("mode")].append(float(s.get("ms") or 0))
                if s.get("pool_searches") is not None:
                    pool.append(int(s["pool_searches"]))
                full += int(s.get("pool_full") or 0)
                partial += int(s.get("pool_partial") or 0)
                if float(s.get("ms") or 0) > 12050:
                    over[s.get("mode")] += 1
        tot = sum(sum(v) for v in by.values()) / 1000
        print(f"[{tag}] games={len(doc)} steps={sum(len(v) for v in by.values())} think={tot:.0f}s "
              f"over={sum(over.values())} {dict(over)}")
        print(f"     pool_searches/step mean={statistics.mean(pool):.1f} p95={sorted(pool)[int(.95*(len(pool)-1))]} "
              f"max={max(pool)} full={full} partial={partial}")
        for m, v in sorted(by.items(), key=lambda x: -sum(x[1])):
            st = stats(v)
            print(f"     {str(m):9s} n={st['n']:5d} mean={st['mean']:7d} p95={st['p95']:7d} "
                  f"max={st['max']:8d} sum={st['sum_s']:6d}s")


if __name__ == "__main__":
    main()