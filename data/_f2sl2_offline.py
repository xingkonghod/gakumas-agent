"""f2-sl2 离线验收探针：gkagent-seedlock 适配器 × F0 已知种子（gkbench.referee 真实 obs 管线）。

验收点：
  1. seed-lock 找回真种子（mirror.config.seed == 已知 seed），记录 lock_turn / 重扫次数
  2. 引擎建局手牌 MATCH（Referee 的 obs 即引擎手牌；锁定核对含手牌）
  3. GNRPA 路径可回放核分（路线池 offer 时 _replay_score 已核；终局分与路线 target 对照）
  4. 全部动作合法（Referee.step 非法即抛 IllegalAction）
  5. 对照：已知种子大预算 GNRPA 上界 + 引擎贪心基线
探针不提交。
"""
from __future__ import annotations

import json
import os
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
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from GakumasCLI.scenario.exam_session import greedy_policy  # noqa: E402

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

PIDS = sys.argv[1:] or ["AS-227HBGHS", "AS-23D5RE8A", "AS-2AXJNW8X", "AS-2BQJNW8X", "AS-2C5JNW8X", "AS-2D7JNW8X"]
PIDS = [p for p in PIDS if p in seeds["problems"] and p in saves]
if not PIDS:
    PIDS = list(seeds["problems"])[:6]

nat, ns = engine.native()
master = engine.master()
results = []
algo = A.SeedLockAlgo(procs=8, report=1)

for pid in PIDS:
    group = seeds["problems"][pid][0]
    seed = int(group["seed"])
    lo = expand_loadout(saves[pid]["loadout"])
    t0 = time.perf_counter()
    ref = Referee(lo, seed)
    ctx = types.SimpleNamespace(obs=ref.obs(), budget=5.0, loadout=ref.loadout_public,
                                meta=ref.public_meta(), rng=random.Random(f"{pid}/0/algo"), worlds_made=0)
    algo.begin(ctx)
    err = None
    metas = []
    n = 0
    while not ref.finished and n < 300:
        ctx.obs = ref.obs()
        try:
            d = algo.decide(ctx)
        except Exception as e:
            err = f"decide {type(e).__name__}: {e}"
            break
        metas.append(d.meta)
        try:
            ref.step(d.action)
        except IllegalAction as e:
            err = f"illegal {e}"
            break
        except Exception as e:
            err = f"step {type(e).__name__}: {e}"
            break
        n += 1
    wall = time.perf_counter() - t0
    g = algo.g
    locked_seed = int(algo.mirror.config.seed) if algo.mirror is not None else None
    # 上界：已知种子大预算 GNRPA；基线：引擎贪心
    sess, _ = build_hif_loadout_session(master, lo, seed)
    ns._cache = None
    _p, st = ns.policy_search(sess, transitions=2_000_000, seed=182, variant="gnrpa", stabilization=3)
    ub = int(st["best_score"])
    gs = sess.clone()
    while not gs.finished:
        choice = greedy_policy(gs, list(gs.deck.hand))
        gs.step(("end",) if choice is None else ("play", int(choice)), observe=False)
    greedy = int(gs.state.score)
    row = {"pid": pid, "seed": seed, "score": ref.score, "finished": bool(ref.finished), "decisions": n,
           "err": err, "state": g.state, "lock_turn": g.lock_turn, "locked_seed": locked_seed,
           "seed_found": locked_seed == seed, "scan_s": g.scan_s, "rescans": g.rescans,
           "target": algo.pool.target if algo.pool else None,
           "adopted": algo.pool.stats["adopted"] if algo.pool else None,
           "bad_routes": algo.pool.stats["bad_routes"] if algo.pool else None,
           "hard_rule": sum(1 for m in metas if m.get("hard_rule")),
           "errors_meta": sum(1 for m in metas if m.get("error")),
           "gnrpa_ub_2M": ub, "greedy": greedy, "wall_s": round(wall, 1),
           "why": g.why}
    results.append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)

out = {"problems": results,
       "lock_rate": sum(1 for r in results if r["seed_found"]) / max(1, len(results)),
       "mean_score": sum(r["score"] for r in results) / max(1, len(results)),
       "mean_ub": sum(r["gnrpa_ub_2M"] for r in results) / max(1, len(results)),
       "mean_greedy": sum(r["greedy"] for r in results) / max(1, len(results))}
(ROOT / "data" / "_f2sl2_offline.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("SUMMARY:", json.dumps({k: out[k] for k in ("lock_rate", "mean_score", "mean_ub", "mean_greedy")}), flush=True)