"""Probe (not committed): compute site-style vs_oracle metrics (geo mean ratio + win rate) for our runs."""
import json
import math
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
V4 = {f"{r['pid']}/{r['slot']}": r for r in json.loads((ROOT / "out/_v5_slots.json").read_text(encoding="utf-8"))}
V5 = json.loads((ROOT / "out/_v5_final.json").read_text(encoding="utf-8"))["scores"]
V5B = json.loads((ROOT / "out/_v5b_scores.json").read_text(encoding="utf-8"))


def site_metrics(name, scores, base=V4):
    ks = [k for k in scores if base.get(k, {}).get("oracle")]
    ratios = [scores[k] / base[k]["oracle"] for k in ks]
    geo = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    win = sum(1 for r in ratios if r >= 1.0) / len(ratios)
    se = statistics.stdev(ratios) / len(ratios) ** 0.5
    print(f"{name}: n={len(ks)} geo={geo:.4f} win={win:.4f} arith={statistics.mean(ratios):.4f} se(arith)={se:.4f} "
          f"median={statistics.median(ratios):.4f}")
    return {"n": len(ks), "geo": round(geo, 4), "win": round(win, 4),
            "arith": round(statistics.mean(ratios), 4)}


out = {}
out["v4"] = site_metrics("v4 ", {k: v["ours"] for k, v in V4.items()})
out["v5"] = site_metrics("v5 ", V5)
out["v5b"] = site_metrics("v5b", V5B)
(ROOT / "out/_vs_oracle.json").write_text(json.dumps(out, indent=1))
print("\nsaved out/_vs_oracle.json")
print("\n参考（站上口径）：best-known geo=1.0 win=0.5；UIHorizon v2.1 geo=0.511 win=0.0167")