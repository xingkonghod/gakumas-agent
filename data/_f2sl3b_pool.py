"""f2-sl3b：合并多轮 A/B 的配对 Δ（同配置跨轮样本池化），bootstrap 95% CI。探针不提交。
用法：python data\\_f2sl3b_pool.py ab1 ab2 [...]  （读 data/_f2sl3b_<tag>.json）
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tags = sys.argv[1:] or ["ab1", "ab2"]
runs = {t: json.loads((ROOT / "data" / f"_f2sl3b_{t}.json").read_text(encoding="utf-8")) for t in tags}


def boot_ci(deltas, iters=10000, seed=20261125):
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


cfgs = sorted({c for d in runs.values() for c in d["configs"] if c != "base"})
for c in cfgs:
    deltas, detail = [], []
    for t, d in runs.items():
        if c not in d["configs"]:
            continue
        by = {(r["pid"], r["cfg"]): r for r in d["rows"]}
        for p in d["pids"]:
            if (p, c) in by and (p, "base") in by:
                dd = by[(p, c)]["score"] - by[(p, "base")]["score"]
                deltas.append(dd)
                detail.append((t, p, dd))
    if not deltas:
        continue
    lo, hi = boot_ci(deltas)
    print(f"{c}: n={len(deltas)} meanD={sum(deltas)/len(deltas):.1f} CI95=[{lo:.1f}, {hi:.1f}] "
          f"pos/neg/zero={sum(1 for x in deltas if x>0)}/{sum(1 for x in deltas if x<0)}/{sum(1 for x in deltas if x==0)}")
    for t, p, dd in detail:
        if dd != 0:
            print(f"   {t} {p} {dd:+d}")
