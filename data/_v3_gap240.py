"""v3 merged-240 per-problem gap vs best-known oracle (probe, not committed)."""
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOK = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()
H = {"Authorization": f"Bearer {TOK}"}
B = "https://hiro.matto.top/gkbench"
V3RUNS = [
    "template-hif-gkagent-ex-seed-v3-xingkonghod-a478c651d4f4",
    "template-hif-gkagent-ex-seed-v3-xingkonghod-b60d6b23b475",
    "template-hif-gkagent-ex-seed-v3-xingkonghod-9ba9c00fb468",
    "template-hif-gkagent-ex-seed-v3-xingkonghod-40312fcb77a0",
]
MONSTER = {"AS-WDKWQYW5", "AS-3ZT8ZKB6", "AS-3EW6E6HV", "AS-F4FPT86S", "AS-AXME8QK2", "AS-WNK6ARRZ",
           "AS-K46XXQEY", "AS-3BB4BWTR", "AS-DS9H9NRD", "AS-ADDTACFE"}


def get(path, tries=5):
    for _ in range(tries):
        try:
            return httpx.get(B + path, headers=H, timeout=90).json()
        except Exception:  # noqa: BLE001
            time.sleep(4)
    raise RuntimeError("fetch fail " + path)


rows = get("/api/runs")
rows = rows if isinstance(rows, list) else rows.get("runs", [])
bk = [r["run"] for r in rows if r.get("run", "").endswith("hif-template-best-known")]
oracle = {}
for rn in bk:
    for e in get(f"/api/runs/{rn}").get("episodes") or []:
        k = (e.get("id"), e.get("seed_index"))
        s = e.get("score")
        if s is not None and (k not in oracle or s > oracle[k]):
            oracle[k] = s

v3 = {}
for rn in V3RUNS:
    for e in get(f"/api/runs/{rn}").get("episodes") or []:
        if not e.get("finished") or e.get("score") is None:
            continue
        k = (e["id"], int(e["seed_index"]))
        at = e.get("at") or ""
        prev = v3.get(k)
        if prev is None or at >= prev[0]:
            v3[k] = (at, int(e["score"]), rn.split("-")[-1])
pairs = [(k, s, oracle[k]) for k, (_, s, _r) in v3.items() if k in oracle and oracle[k] > 0]
ratios = [s / o for _, s, o in pairs]
print(f"v3 merged slots={len(v3)} paired={len(pairs)} ratio mean={statistics.mean(ratios):.3f} "
      f"median={statistics.median(ratios):.3f} mean_score={sum(s for _k, s, _o in pairs)/len(pairs):,.0f}")
byid = {}
for (i, sl), s, o in pairs:
    d = byid.setdefault(i, {"v3": 0, "o": 0, "n": 0})
    d["v3"] += s
    d["o"] += o
    d["n"] += 1
drag = sorted(byid.items(), key=lambda kv: kv[1]["o"] - kv[1]["v3"], reverse=True)
total_gap = sum(d["o"] - d["v3"] for _, d in drag)
print(f"total gap={total_gap:,} over {len(pairs)} slots")
print("=== top15 ===")
for i, d in drag[:15]:
    tag = "怪物" if i in MONSTER else ""
    print(f"  {i}: {d['v3']/d['o']*100:5.1f}%  gap {d['o']-d['v3']:>10,} slate {d['v3']:>10,}/{d['o']:>10,} {tag}")
print(f"top10 share {sum(d['o']-d['v3'] for _, d in drag[:10])/total_gap:.1%}")
cf = []
top10 = {i for i, _ in drag[:10]}
for (i, sl), s, o in pairs:
    cf.append(max(s, 0.90 * o) if i in top10 else s)
print(f"counterfactual(top10@0.90) mean={sum(cf)/len(cf):,.0f} (+{sum(cf)/len(cf)-sum(s for _k,s,_o in pairs)/len(pairs):,.0f})")