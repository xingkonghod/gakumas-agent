"""gnrpa-spec 探针6（不提交）：L3② per-problem 门控 prior（纯分析，复用 L1 gate1 行，无引擎）。

仅低 oracle 锁定题 opt-in 带 prior、怪物题禁用（prior=0）。opt_in = LOW12 − MONSTER5（11 题，
WDKWQYW5 虽低 oracle 但属 monster5 → 禁用）。单变量：gated_delta = (prior_arm − p0) if pid∈opt_in else 0。
门 vs v3 全 prior=0（=p0），n=32，bootstrap 10000 CI 种子 20261126。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = json.load(open(ROOT / "data" / "_gnrpa_gate1.json", encoding="utf-8"))
LOW12 = ["AS-3G6FFZZT", "AS-QV6QCSN9", "AS-P8ZJTXNA", "AS-VH8WYE6J", "AS-5XB2AEHN", "AS-DE36RWPS",
         "AS-BD5EAA22", "AS-DEBX8BX7", "AS-WDKWQYW5", "AS-B38CARVV", "AS-VWAF2GDN", "AS-HTNFZWKG"]
MONSTER5 = ["AS-5KZSXANK", "AS-AXME8QK2", "AS-WDKWQYW5", "AS-WNK6ARRZ", "AS-3ZT8ZKB6"]
OPT_IN = sorted(set(LOW12) - set(MONSTER5))
by = {(r["pid"], r["seed"], r["arm"]): r["best"] for r in d["rows"]}
pairs = [(p, s) for p in d["pids"] for (s, lab) in d["pid_seeds"][p]]


def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return [means[int(0.025 * iters)], means[int(0.975 * iters)]]


def block(deltas):
    lo, hi = boot_ci(deltas)
    return {"n": len(deltas), "mean_delta": round(sum(deltas) / len(deltas), 1), "ci95": [lo, hi],
            "pos": sum(x > 0 for x in deltas), "neg": sum(x < 0 for x in deltas), "zero": sum(x == 0 for x in deltas)}


print("OPT_IN (低oracle锁定 opt-in, 怪物禁用):", OPT_IN)
out = {"opt_in": OPT_IN}
for arm in ("distill", "mech"):
    deltas = [(by[(p, s, arm)] - by[(p, s, "p0")]) if p in OPT_IN else 0 for (p, s) in pairs]
    opt_deltas = [by[(p, s, arm)] - by[(p, s, "p0")] for (p, s) in pairs if p in OPT_IN]
    out[arm] = {"overall_gated": block(deltas), "opt_in_only": block(opt_deltas)}
    b = out[arm]["overall_gated"]
    print(f"gated_{arm} overall: mean={b['mean_delta']:,.0f} ci={[round(x) for x in b['ci95']]} "
          f"p/n/z={b['pos']}/{b['neg']}/{b['zero']}")
    b2 = out[arm]["opt_in_only"]
    print(f"  opt_in_only(n={b2['n']}): mean={b2['mean_delta']:,.0f} ci={[round(x) for x in b2['ci95']]} "
          f"p/n/z={b2['pos']}/{b2['neg']}/{b2['zero']}")
(ROOT / "data" / "_gnrpa_gateL3b.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved data/_gnrpa_gateL3b.json")