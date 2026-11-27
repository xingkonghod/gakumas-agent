"""pscale 门表生成：读 _pscale_rows_gate.jsonl（已完成 pair 块），输出逐配置 markdown 表 + AB。
用法：python _pscale_table.py [tag] [names_csv|all]
"""
from __future__ import annotations
import json, random, sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
ORDER = ["orig"] + [f"w{w}t{t}" for w in (6, 12, 24, 32) for t in (4, 8, 16)] + ["w12t4_o", "w32t4_o", "w32t16_o"]

def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed); n = len(deltas)
    if n == 0: return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025*iters)], means[int(0.975*iters)]

def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "gate"
    names = ORDER if len(sys.argv) <= 2 or sys.argv[2] == "all" else sys.argv[2].split(",")
    rows = [json.loads(l) for l in (ROOT / "data" / f"_pscale_rows_{tag}.jsonl").open(encoding="utf-8")]
    by = {(r["pid"], r["seed"], r["cfg"]): r for r in rows}
    prs = sorted({(r["pid"], r["seed"]) for r in rows})
    pairs = [pr for pr in prs if all((pr[0], pr[1], nm) in by for nm in names)]
    print(f"complete pairs={len(pairs)}/{len(prs)}: {pairs}")
    print()
    print("| 配置 | 均分 | meanΔ | CI95 | 胜/负/平 | over | Δover | step均ms | decide均ms | worlds_s | sec/search | 门 |")
    print("|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---|")
    def agg(nm):
        rs = [by[(p, s, nm)] for (p, s) in pairs]
        return rs
    ro = agg("orig")
    mo = sum(r["score"] for r in ro) / len(ro)
    oo = sum(r["over_steps"] for r in ro)
    print(f"| orig（基线 w6t4 u85） | {round(mo):,} | — | — | — | {oo} | — | "
          f"{round(sum(r['step_ms_mean'] for r in ro)/len(ro))} | {round(sum(r['decide_ms_mean'] for r in ro)/len(ro))} | "
          f"{sum(r['worlds_s_mean'] or 0 for r in ro)/len(ro):.3f} | {sum(r['sec_per_search_mean'] or 0 for r in ro)/len(ro):.3f} | — |")
    for nm in names:
        if nm == "orig": continue
        rs = agg(nm)
        m = sum(r["score"] for r in rs) / len(rs)
        ov = sum(r["over_steps"] for r in rs)
        deltas = [r["score"] - o["score"] for r, o in zip(rs, ro)]
        do = ov - oo
        lo, hi = boot_ci(deltas)
        pos = sum(1 for d in deltas if d > 0); neg = sum(1 for d in deltas if d < 0); zero = len(deltas) - pos - neg
        gate = "PASS" if (lo > 0 and do <= 0) else ("over-only" if do < 0 else "FAIL")
        print(f"| {nm} | {round(m):,} | {round(sum(deltas)/len(deltas)):,} | [{round(lo):,}, {round(hi):,}] | "
              f"{pos}/{neg}/{zero} | {ov} | {do:+d} | {round(sum(r['step_ms_mean'] for r in rs)/len(rs))} | "
              f"{round(sum(r['decide_ms_mean'] for r in rs)/len(rs))} | {sum(r['worlds_s_mean'] or 0 for r in rs)/len(rs):.3f} | "
              f"{sum(r['sec_per_search_mean'] or 0 for r in rs)/len(rs):.3f} | {gate} |")
    print()
    print("per-pair deltas（vs orig）:")
    for nm in names:
        if nm == "orig": continue
        ds = {f"{p}/{s}": by[(p, s, nm)]["score"] - by[(p, s, "orig")]["score"] for (p, s) in pairs}
        print(f"  {nm}: " + " ".join(f"{k.split('/')[0][3:]}:{v:+,}" for k, v in ds.items()))

if __name__ == "__main__":
    main()