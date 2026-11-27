"""f2-sl3b 离线 A/B：gkagent-seedlock 基线 vs 变体，16 个固定 F0 种子配对。

方法：每题在同一负载窗口内背靠背跑 base + 各变体（同 seed 同 Referee 管线），
报逐题 Δ + 均值 + bootstrap 95% CI（10000 次重采样，固定 RNG 种子可复现）。
离线不需要服务器/令牌。探针不提交。

用法：
    .venv\\Scripts\\python.exe data\\_f2sl3b_ab.py [configs_csv] [out_tag]
 configs: base,fp0,scan4,scan3,st500k（缺省全跑）；组合阶段可加 combo（脚本内定义）。
"""
from __future__ import annotations

import gc
import json
import random
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-seedlock"
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.path.insert(0, str(SUB))

import algo as A  # noqa: E402  模块导入时自配置引擎路径

from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee, IllegalAction  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

# 16 题：4 大题（任务指定）+ 2 旧探针小题 + 10 核心题（_f2sl2_core_ids.txt 内、dev 种子表可查）
PIDS = ["AS-2AXJNW8X", "AS-323ADZVK", "AS-8MY3XH4R", "AS-ADDTACFE",
        "AS-227HBGHS", "AS-23D5RE8A",
        "AS-33JYSHDF", "AS-499M4D9B", "AS-663NKTY4", "AS-93WKA9BK",
        "AS-C3Y5EFGV", "AS-E8M2YFR2", "AS-K2ER4ZRJ", "AS-P8NM4YAA",
        "AS-VBZG5R3W", "AS-Z4VBZFDZ"]
PIDS = [p for p in PIDS if p in seeds["problems"] and p in saves]
if len(sys.argv) > 3:
    PIDS = [p for p in sys.argv[3].split(",") if p in seeds["problems"] and p in saves]

CONFIGS = {
    "base": {},                          # 基线 = 提交 4391bef 行为（forced_play=1, scan_min=6, step_trans=300k）
    "fp0": {"forced_play": 0},           # 杠杆1：关掉硬规矩，允许 GNRPA 蓄体力主动 end
    "scan4": {"scan_min": 4},            # 杠杆2：起扫抽牌数 4
    "scan3": {"scan_min": 3},            # 杠杆2：起扫抽牌数 3（第 1 回合即扫）
    "st500k": {"step_trans": 500000},    # 杠杆3：步搜索预算 300k→500k
    "fp0st": {"forced_play": 0, "step_trans": 500000},   # 组合：关硬规矩 + 500k（run1 显示 st500k 负Δ主因是 forced_play 交互）
    "fp0s4": {"forced_play": 0, "scan_min": 4},          # 组合：关硬规矩 + 起扫 4
}

names = (sys.argv[1] if len(sys.argv) > 1 else "base,fp0,scan4,scan3,st500k").split(",")
tag = sys.argv[2] if len(sys.argv) > 2 else "ab1"
for n in names:
    if n not in CONFIGS:
        raise SystemExit(f"unknown config {n}; known: {list(CONFIGS)}")
if "base" not in names:
    names.insert(0, "base")


def play(pid, cfg_name, params):
    seed = int(seeds["problems"][pid][0]["seed"])
    lo = expand_loadout(saves[pid]["loadout"])
    algo = A.SeedLockAlgo(procs=8, report=0, **params)
    ref = Referee(lo, seed)
    ctx = types.SimpleNamespace(obs=ref.obs(), budget=5.0, loadout=ref.loadout_public,
                                meta=ref.public_meta(), rng=random.Random(f"{pid}/0/algo"), worlds_made=0)
    t0 = time.perf_counter()
    algo.begin(ctx)
    err, dts, hard, n = None, [], 0, 0
    while not ref.finished and n < 300:
        if time.perf_counter() - t0 > 900:
            err = "game wall > 900s"
            break
        ctx.obs = ref.obs()
        ta = time.perf_counter()
        try:
            d = algo.decide(ctx)
        except Exception as e:  # noqa: BLE001
            err = f"decide {type(e).__name__}: {e}"
            break
        dts.append(time.perf_counter() - ta)
        hard += 1 if d.meta.get("hard_rule") else 0
        try:
            ref.step(d.action)
        except IllegalAction as e:
            err = f"illegal {e}"
            break
        except Exception as e:  # noqa: BLE001
            err = f"step {type(e).__name__}: {e}"
            break
        n += 1
    wall = time.perf_counter() - t0
    g = algo.g
    locked_seed = int(algo.mirror.config.seed) if algo.mirror is not None else None
    dts_sorted = sorted(dts)
    row = {"pid": pid, "cfg": cfg_name, "params": params, "seed": seed,
           "score": int(ref.score), "finished": bool(ref.finished), "decisions": n, "err": err,
           "state": g.state, "lock_turn": g.lock_turn, "seed_found": locked_seed == seed,
           "scan_s": g.scan_s, "rescans": g.rescans, "hard_rule": hard,
           "counts": dict(g.counts),
           "target": algo.pool.target if algo.pool else None,
           "adopted": algo.pool.stats["adopted"] if algo.pool else None,
           "bad_routes": algo.pool.stats["bad_routes"] if algo.pool else None,
           "think_s": round(sum(dts), 1), "wall_s": round(wall, 1),
           "max_ms": round(max(dts) * 1000) if dts else 0,
           "p95_ms": round(dts_sorted[min(len(dts) - 1, int(0.95 * len(dts)))] * 1000) if dts else 0,
           "over5": sum(1 for x in dts if x > 5.0), "over6": sum(1 for x in dts if x > 6.05),
           "why": g.why}
    del algo, ref
    return row


def boot_ci(deltas, iters=10000, seed=20261125):
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


rows = []
for pid in PIDS:
    for name in names:
        row = play(pid, name, CONFIGS[name])
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    gc.collect()

by = {(r["pid"], r["cfg"]): r for r in rows}
summary = {}
for name in names:
    rs = [by[(p, name)] for p in PIDS]
    summary[name] = {"mean_score": sum(r["score"] for r in rs) / len(rs),
                     "lock_rate": sum(1 for r in rs if r["seed_found"]) / len(rs),
                     "mean_lock_turn": sum(r["lock_turn"] or 99 for r in rs) / len(rs),
                     "mean_wall_s": sum(r["wall_s"] for r in rs) / len(rs),
                     "over5": sum(r["over5"] for r in rs), "over6": sum(r["over6"] for r in rs),
                     "max_ms": max(r["max_ms"] for r in rs),
                     "errors": sum(1 for r in rs if r["err"] or not r["finished"])}
ab = {}
for name in names:
    if name == "base":
        continue
    deltas = [by[(p, name)]["score"] - by[(p, "base")]["score"] for p in PIDS]
    lo, hi = boot_ci(deltas)
    ab[name] = {"mean_delta": sum(deltas) / len(deltas), "ci95": [lo, hi],
                "pos": sum(1 for d in deltas if d > 0), "neg": sum(1 for d in deltas if d < 0),
                "zero": sum(1 for d in deltas if d == 0),
                "per_pid": {p: d for p, d in zip(PIDS, deltas)}}
out = {"configs": {n: CONFIGS[n] for n in names}, "pids": PIDS, "rows": rows,
       "summary": summary, "ab_vs_base": ab}
out_path = ROOT / "data" / f"_f2sl3b_{tag}.json"
out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("SUMMARY:", json.dumps(summary, ensure_ascii=False), flush=True)
print("AB:", json.dumps(ab, ensure_ascii=False), flush=True)
print("saved:", out_path, flush=True)
