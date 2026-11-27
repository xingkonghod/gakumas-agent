# -*- coding: utf-8 -*-
"""v2 逐题相对上限（vs best-known oracle）比例，找最低题（最大提升空间）。探针不提交。"""
import httpx
import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TOK = (Path.home() / ".config/gkbench/token").read_text().strip()
H = {"Authorization": f"Bearer {TOK}"}
B = "https://hiro.matto.top/gkbench"


def get(path, tries=4):
    for a in range(tries):
        try:
            return httpx.get(B + path, headers=H, timeout=60).json()
        except Exception:
            time.sleep(4)
    raise RuntimeError("fetch fail " + path)


# 1. best-known farm per-(id,slot) oracle
runs = get("/api/runs")
rows = runs if isinstance(runs, list) else runs.get("runs", [])
hif_bk = [r["run"] for r in rows if r.get("run", "").endswith("hif-template-best-known")]
oracle = {}
for rn in hif_bk:
    for e in get(f"/api/runs/{rn}").get("episodes") or []:
        k = (e.get("id"), e.get("seed_index"))
        s = e.get("score")
        if s is not None and (k not in oracle or s > oracle[k]):
            oracle[k] = s
print(f"oracle pairs: {len(oracle)}")

# 2. v2 scores
v2 = get("/api/evals/db12324b5d57").get("done") or []
ratios = []
for d in v2:
    k = (d.get("id"), d.get("slot"))
    o = oracle.get(k)
    if o and o > 0 and d.get("score") is not None:
        ratios.append((d["score"] / o, d["id"], d.get("slot"), d["score"], o))
ratios.sort()
print(f"v2 games with oracle: {len(ratios)}")
print(f"ratio mean={statistics.mean(r[0] for r in ratios):.3f} median={statistics.median(r[0] for r in ratios):.3f}")
print("\n=== 相对上限最低 20 题（最大提升空间）===")
for r in ratios[:20]:
    print(f"  {r[1]}#{r[2]}: {r[0]*100:5.1f}%  v2 {r[3]:>10,} / oracle {r[4]:>10,}  缺口 {r[4]-r[3]:>10,}")
print("\n=== 比例分布 ===")
for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.0), (1.0, 99)]:
    n = sum(1 for r in ratios if lo <= r[0] < hi)
    print(f"  [{lo:.0%},{hi:.0%}): {n} 局")
# 按题聚合（同题两 slot 平均），找最差題
byid = {}
for r in ratios:
    byid.setdefault(r[1], []).append(r[0])
worst_ids = sorted(byid.items(), key=lambda kv: statistics.mean(kv[1]))[:12]
print("\n=== 按题平均比例最低 12 题 ===")
for i, rs in worst_ids:
    print(f"  {i}: {statistics.mean(rs)*100:5.1f}%  (slots {len(rs)})")
