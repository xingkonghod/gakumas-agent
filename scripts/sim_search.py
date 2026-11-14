"""模拟器上的策略参数随机搜索：把"怎么打最强"搜出来。

用法：
    python scripts/sim_search.py --episodes 1500 --samples 60
    python scripts/sim_search.py --write          # 最优参数写 data/knowledge/policy_sim.json

搜索空间（StrategyParams）：休息阈值 / 上课节奏 / 练哪个属性 / 外出门槛 / 硬练下限。
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import statistics as stats
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "data" / "knowledge" / "policy_sim.json"

GRID = {
    "rest_threshold": [6, 8, 10, 12, 14],
    "lesson_every": [1, 2, 3],
    "attr_choice": ["weight", "lowest"],
    "outing_below": [-1, 16, 20],
    "min_stamina_to_train": [8, 10, 12],
}


def evaluate(task: tuple) -> dict:
    params_dict, episodes, seed, deck_raw, pool_raw = task
    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import ProduceConfig, ProduceSim, StrategyParams, strategy_from_params

    deck = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in deck_raw]
    pool = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in pool_raw]
    params = StrategyParams(**params_dict)
    strategy = strategy_from_params(params)
    config = ProduceConfig(reward_pick="best", support_bonus=1.15)

    totals, grades, exams, clears, lessons = [], [], 0, 0, 0
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=seed + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        totals.append(result.total)
        grades.append(result.grade)
        exams += result.exams_passed
        clears += result.cleared
        lessons += result.lessons
    return {
        "params": params_dict,
        "mean": round(stats.mean(totals), 1),
        "p10": round(sorted(totals)[max(0, len(totals) // 10)], 1),
        "exams": round(exams / episodes, 2),
        "clear_rate": round(clears / max(lessons, 1), 3),
        "fail_exam_rate": round(1 - exams / 2, 3),
        "n": episodes,
    }


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=1200)
    parser.add_argument("--samples", type=int, default=60, help="随机采样多少组参数")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    import sim_produce as sp

    deck_raw = sp.build_deck()
    pool_raw = sp.build_pool()
    keys = list(GRID)
    all_combos = list(itertools.product(*(GRID[key] for key in keys)))
    rng = random.Random(7)
    combos = rng.sample(all_combos, min(args.samples, len(all_combos)))
    print(f"搜索空间 {len(all_combos)} 组，本次采样 {len(combos)} 组 x {args.episodes} 局")

    tasks = [
        (dict(zip(keys, combo)), args.episodes, 5000 + index * 131, deck_raw, pool_raw)
        for index, combo in enumerate(combos)
    ]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool_exec:
        results = list(pool_exec.map(evaluate, tasks))
    elapsed = time.perf_counter() - started

    results.sort(key=lambda row: row["mean"], reverse=True)
    print(f"\n{elapsed:.1f}s，共 {len(results) * args.episodes} 局")
    print("Top-10 参数组合：")
    for row in results[:10]:
        print(
            f"  mean={row['mean']:>7} p10={row['p10']:>6} 考试通过={row['exams']}/2 "
            f"过关率={row['clear_rate']:.2f} {row['params']}"
        )
    best = results[0]
    if args.write:
        OUT.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source": "sim_search",
                    "produce": best["params"],
                    "stats": {k: v for k, v in best.items() if k != "params"},
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print("已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
