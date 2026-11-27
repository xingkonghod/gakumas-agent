"""gnrpa-spec 探针7（不提交）：L3① additive 口径（prior 作第5路，max(baseline,prior_3)，真单调零下行）
+ multi-start status=2 早停计数。复用 gateL3.json 行（无引擎）。"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = json.load(open(ROOT / "data" / "_gnrpa_gateL3.json", encoding="utf-8"))
MONSTER5 = ["AS-5KZSXANK", "AS-AXME8QK2", "AS-WDKWQYW5", "AS-WNK6ARRZ", "AS-3ZT8ZKB6"]
rows = d["rows"]
# 重组每 (pid,seed) 的 p0_0..3 / mech_3 / distill_3
cell = {}
for r in rows:
    cell.setdefault((r["pid"], r["seed"]), {})[r["arm"]] = r
pairs = [(p, s) for p in d["pids"] for s in d["pid_seeds"][p]]
mon_pairs = [(p, s) for (p, s) in pairs if p in MONSTER5]
low_pairs = [(p, s) for (p, s) in pairs if p not in MONSTER5]


def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return [means[int(0.025 * iters)], means[int(0.975 * iters)]]


def block(deltas):
    lo, hi = boot_ci(deltas)
    return {"n": len(deltas), "mean_delta": round(sum(deltas) / len(deltas), 1), "ci95": [lo, hi],
            "pos": sum(x > 0 for x in deltas), "neg": sum(x < 0 for x in deltas), "zero": sum(x == 0 for x in deltas)}


out = {}
for arm in ("mech", "distill"):
    add_deltas, base_vals, add_vals = [], [], []
    for (p, s) in pairs:
        c = cell[(p, s)]
        base = max(c[f"p0_{i}"]["best"] for i in range(4))
        prior3 = c[f"{arm}_3"]["best"]
        add = max(base, prior3)
        add_deltas.append(add - base)
        base_vals.append(base)
        add_vals.append(add)
    out[f"additive_{arm}"] = {
        "overall": block(add_deltas),
        "low": block([dd for (p, s), dd in zip(pairs, add_deltas) if p not in MONSTER5]),
        "monster": block([dd for (p, s), dd in zip(pairs, add_deltas) if p in MONSTER5]),
        "mean_baseline": round(sum(base_vals) / len(base_vals), 1),
        "mean_additive": round(sum(add_vals) / len(add_vals), 1),
        "per_pair_pos": {f"{p}/{s}": dd for (p, s), dd in zip(pairs, add_deltas) if dd > 0},
    }
    b = out[f"additive_{arm}"]["overall"]
    print(f"additive_{arm} overall: mean={b['mean_delta']:,.0f} ci={[round(x) for x in b['ci95']]} "
          f"p/n/z={b['pos']}/{b['neg']}/{b['zero']}")
    bm = out[f"additive_{arm}"]["monster"]
    print(f"  monster: mean={bm['mean_delta']:,.0f} ci={[round(x) for x in bm['ci95']]} p/n/z={bm['pos']}/{bm['neg']}/{bm['zero']}")
    print(f"  positives: {out[f'additive_{arm}']['per_pair_pos']}")
# status=2 计数
s2 = {}
for r in rows:
    if r["arm"] in ("mech_3", "distill_3") and r["status"] != 0:
        s2.setdefault(r["arm"], []).append(f"{r['pid']}/{r['seed']}(s{r['status']},exp{r['expansions']})")
out["status_nonzero"] = s2
print("status_nonzero:", json.dumps(s2, ensure_ascii=False))
(ROOT / "data" / "_gnrpa_gateL3c.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved data/_gnrpa_gateL3c.json")