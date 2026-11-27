"""pscale 稳健性：w32t16 门 CI 下界仅 +4k，做 leave-one-out（LOO）检查是否单题驱动。
用法：python _pscale_robust.py
"""
from __future__ import annotations
import json, random
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
G = json.loads((ROOT / "data" / "_pscale_gate.json").read_text(encoding="utf-8"))

def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed); n = len(deltas)
    if n == 0: return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025*iters)], means[int(0.975*iters)]

pairs = G["pairs"]
for nm in ("w32t16", "w12t16", "w12t4", "w24t16"):
    ab = G["ab_vs_orig"][nm]
    ds = [ab["per_pair"][f"{p}/{s}"] for (p, s) in pairs]
    print(f"== {nm}: meanΔ={ab['mean_delta']:,} CI={ab['ci95']} overΔ={ab['over_delta_total']}")
    for (p, s), d in zip(pairs, ds):
        print(f"   {p}/{s}: {d:+,}")
    loo_pass = 0
    for i in range(len(ds)):
        sub = ds[:i] + ds[i+1:]
        lo, hi = boot_ci(sub)
        ok = lo > 0
        loo_pass += ok
        print(f"   LOO drop {pairs[i][0]}: meanΔ={sum(sub)/len(sub):+,.0f} CI=[{lo:+,.0f},{hi:+,.0f}] {'PASS' if ok else 'fail'}")
    print(f"   LOO pass {loo_pass}/{len(ds)}")
    print()