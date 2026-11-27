"""v3 salvage 逐题相对上限拖尾分析（探针不提交）：oracle=best-known farm per-(id,slot) max。"""
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOK = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()
H = {"Authorization": f"Bearer {TOK}"}
B = "https://hiro.matto.top/gkbench"
V3RUN = "template-hif-gkagent-ex-seed-v3-xingkonghod-9ba9c00fb468"
LOST = {"AS-B38CARVV", "AS-VWAF2GDN", "AS-HTNFZWKG", "AS-5KZSXANK"}
MONSTER = {"AS-WDKWQYW5", "AS-3ZT8ZKB6", "AS-3EW6E6HV", "AS-F4FPT86S", "AS-AXME8QK2", "AS-WNK6ARRZ"}


def get(path, tries=5):
    for a in range(tries):
        try:
            return httpx.get(B + path, headers=H, timeout=90).json()
        except Exception:
            time.sleep(4)
    raise RuntimeError("fetch fail " + path)


runs = get("/api/runs")
rows = runs if isinstance(runs, list) else runs.get("runs", [])
bk = [r["run"] for r in rows if r.get("run", "").endswith("hif-template-best-known")]
oracle = {}
for rn in bk:
    for e in get(f"/api/runs/{rn}").get("episodes") or []:
        k = (e.get("id"), e.get("seed_index"))
        s = e.get("score")
        if s is not None and (k not in oracle or s > oracle[k]):
            oracle[k] = s

v3 = {}
for e in get(f"/api/runs/{V3RUN}").get("episodes") or []:
    if e.get("finished"):
        v3[(e["id"], int(e["seed_index"]))] = int(e["score"])
v2 = {}
for d in get("/api/evals/db12324b5d57").get("done") or []:
    if d.get("score") is not None:
        v2[(d["id"], d.get("slot"))] = int(d["score"])

pairs = [(k, v3[k], oracle[k]) for k in sorted(v3) if k in oracle and oracle[k] > 0]
ratios = [s / o for _, s, o in pairs]
print(f"v3 pairs={len(pairs)} ratio mean={statistics.mean(ratios):.3f} median={statistics.median(ratios):.3f}")
v2r = [v2[k] / oracle[k] for k in v2 if k in oracle and oracle[k] > 0]
print(f"v2 ratio mean={statistics.mean(v2r):.3f}")

byid = {}
for (i, sl), s, o in pairs:
    d = byid.setdefault(i, {"v3": 0, "o": 0, "n": 0, "v2": 0, "v2n": 0})
    d["v3"] += s
    d["o"] += o
    d["n"] += 1
    if (i, sl) in v2:
        d["v2"] += v2[(i, sl)]
        d["v2n"] += 1
drag = sorted(byid.items(), key=lambda kv: kv[1]["o"] - kv[1]["v3"], reverse=True)
total_gap = sum(d["o"] - d["v3"] for _, d in drag)
print(f"\ntotal gap (oracle-v3) over {len(pairs)} slots = {total_gap:,}")
print("=== 拖尾 top15（按绝对缺口和）===")
for i, d in drag[:15]:
    r3 = d["v3"] / d["o"]
    r2 = d["v2"] / d["o"] if d["v2n"] else float("nan")
    tag = "失锁deck-modify" if i in LOST else ("怪物方差" if i in MONSTER else "锁定/其它")
    print(f"  {i}: v3 {r3*100:5.1f}% / v2 {r2*100:5.1f}%  缺口 {d['o']-d['v3']:>10,}  [{tag}]")
top10 = sum(d["o"] - d["v3"] for _, d in drag[:10])
print(f"top10 缺口占比 {top10/total_gap:.1%}")

# 反事实：top10 题各 slot 达到 v2 全量 mean ratio 0.870 → 全量均分变化
mean_now = sum(s for _, s, _ in pairs) / len(pairs)
cf = []
top10ids = {i for i, _ in drag[:10]}
for (i, sl), s, o in pairs:
    cf.append(max(s, 0.870 * o) if i in top10ids else s)
print(f"\nmean now={mean_now:,.0f}; counterfactual(top10@0.87)={sum(cf)/len(cf):,.0f} "
      f"(+{sum(cf)/len(cf)-mean_now:,.0f})")
print("=== v3 比例分布 ===")
for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.0), (1.0, 99)]:
    n = sum(1 for r in ratios if lo <= r < hi)
    print(f"  [{lo:.0%},{hi:.0%}): {n}")