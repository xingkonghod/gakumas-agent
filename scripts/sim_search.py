"""模拟器上的策略参数随机搜索：把"怎么打最强"搜出来。

用法：
    python scripts/sim_search.py --episodes 1500 --samples 60
    python scripts/sim_search.py --write          # 最优参数写 data/knowledge/policy_sim.json

搜索空间（StrategyParams）：休息阈值 / 训练节奏 / 训练体力门 / 上课体力门 / 练哪个属性 / 外出门槛。
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

PLAY_GRID = {
    "reserve_per_turn": [0.0, 1.0, 2.0, 3.0],
    "buff_score_guard": [3.0, 5.0, 8.0],
    "negligible": [0.0, 0.5, 2.0],
}

GRID = {
    "rest_threshold": [6, 8, 10, 12, 14],
    "training_every": [1, 2, 3],
    # 训练体力门：真机 0 体力进训练一张牌都打不出，只白送回合。
    # 8 是低于训练消耗(10)的反例，10/12/14 是安全区，让搜索自己选。
    "training_min_stamina": [8, 10, 12, 14],
    "attr_choice": ["weight", "lowest"],
    "outing_below": [-1, 16, 20],
    "min_stamina_for_class": [8, 10, 12],
}


def evaluate(task: tuple) -> dict:
    params_dict, episodes, seed, deck_raw, pool_raw = task

    from gkagent.sim.produce import (
        ProduceConfig,
        ProduceSim,
        StrategyParams,
        eval_value,
        strategy_from_params,
    )

    deck = _to_specs(deck_raw)
    pool = _to_specs(pool_raw)
    params = StrategyParams(**params_dict)
    strategy = strategy_from_params(params)
    # 不覆盖 calibration 默认值：training_gain_ratio=0.5 / support_bonus=1.2
    # （真机 C/4135 反推，见 ProduceConfig docstring）
    config = ProduceConfig(reward_pick="best")

    totals, evals, grades, exams, clears, trainings = [], [], [], 0, 0, 0
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=seed + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        totals.append(result.total)
        grades.append(result.grade)
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"):
                rank = row["exam"]["rank"]
                break
        evals.append(eval_value(result.total, rank, result.exam_score))
        exams += result.exams_passed
        clears += result.cleared
        trainings += result.trainings
    return {
        "params": params_dict,
        "mean": round(stats.mean(totals), 1),
        "p10": round(sorted(totals)[max(0, len(totals) // 10)], 1),
        "exams": round(exams / episodes, 2),
        "clear_rate": round(clears / max(trainings, 1), 3),
        "fail_exam_rate": round(1 - exams / episodes / 2, 3),
        "n": episodes,
        "mean_eval": round(stats.mean(evals), 1),
        "p50_eval": round(sorted(evals)[len(evals) // 2], 1),
        "p90_eval": round(sorted(evals)[int(len(evals) * 0.9)], 1),
        "p95_eval": round(sorted(evals)[int(len(evals) * 0.95)], 1),
        "cplus_rate": round(sum(1 for value in evals if value >= 4500) / len(evals), 3),
    }



def _to_specs(rows):
    """Rich/legacy 卡行 -> CardSpec（worker 内懒导入，避免 spawn 后缺模块）。"""
    import sim_produce as sp

    return [sp._spec_from_row(row) for row in rows]

def evaluate_play(task: tuple) -> dict:
    """固定培育策略，只扫"出牌参数"（真机 LessonPolicy）。"""
    play_params, episodes, seed, deck_raw, pool_raw = task
    import tempfile
    from pathlib import Path as _Path

    from gkagent.sim.produce import (
        ProduceConfig,
        ProduceSim,
        StrategyParams,
        eval_value,
        strategy_from_params,
    )

    deck = _to_specs(deck_raw)
    pool = _to_specs(pool_raw)
    # 用校准后的默认值（ratio=0.5 / support=1.2），不要在这里改单卡收益口径
    config = ProduceConfig(reward_pick="best")
    strategy = strategy_from_params(StrategyParams(rest_threshold=8, training_every=1,
                                                   training_min_stamina=12, attr_choice="weight",
                                                   outing_below=16, min_stamina_for_class=8))

    with tempfile.TemporaryDirectory() as tmp:
        path = _Path(tmp) / "policy.json"
        path.write_text(json.dumps({"version": 1, "lesson": play_params}, ensure_ascii=False), encoding="utf-8")
        from gkagent.policy.lesson import LessonPolicy
        from gkagent.vision.lesson import LessonCard, LessonState

        policy_obj = LessonPolicy(params_path=str(path))

        def adapter(sim_inner):
            cards = []
            for index, card in enumerate(sim_inner.hand):
                cards.append(
                    LessonCard(
                        index=index, box=(0, 0, 0, 0), point=(0, 0),
                        name=card.name.split("#")[0], score=card.score or None, cost=card.cost,
                        buff=card.score <= 0, text="",
                    )
                )
            state = LessonState(cards=tuple(cards), turns_left=sim_inner.turns_left, stamina=sim_inner.stamina)
            action = policy_obj.decide(state)
            if action.kind == "card" and action.index is not None:
                policy_obj.note_play(action.card)
                return action.index
            return None

        totals, evals, exam_pass = [], [], 0
        for episode in range(episodes):
            sim = ProduceSim(deck, config=config, rng_seed=seed + episode)
            sim.reward_pool = pool
            sim.lesson_policy_fn = adapter
            result = sim.run(strategy)
            totals.append(result.total)
            exams = [row["exam"] for row in sim.trace if row["action"] == "exam"]
            exam_pass += sum(1 for exam in exams if exam["passed"])
            rank = exams[-1]["rank"] if exams else 3
            evals.append(eval_value(result.total, rank, result.exam_score))
    return {
        "params": play_params,
        "mean": round(sum(totals) / len(totals), 1),
        "exam_pass": round(exam_pass / (episodes * 2), 3),
        "n": episodes,
        "mean_eval": round(stats.mean(evals), 1),
        "p50_eval": round(sorted(evals)[len(evals) // 2], 1),
        "p90_eval": round(sorted(evals)[int(len(evals) * 0.9)], 1),
        "p95_eval": round(sorted(evals)[int(len(evals) * 0.95)], 1),
        "cplus_rate": round(sum(1 for value in evals if value >= 4500) / len(evals), 3),
    }


def mutate(params: dict, keys: list[str], rng) -> dict:
    """随机改 1-2 个参数（在 GRID 里采样）。"""
    child = dict(params)
    for _ in range(rng.choice([1, 1, 2])):
        key = rng.choice(keys)
        child[key] = rng.choice(GRID[key])
    return child


def run_evolution(args, keys, deck_raw, pool_raw, rng, seeds) -> int:
    """进化搜索：每代保留 Top-4，其余用变异补齐，记录学习曲线。"""
    population = [dict(zip(keys, combo)) for combo in seeds[: args.population]]
    while len(population) < args.population:
        population.append(dict(zip(keys, rng.choice(seeds))))
    curve = []
    for generation in range(1, args.generations + 1):
        tasks = [
            (params, args.episodes, 7000 + generation * 100 + index * 37, deck_raw, pool_raw)
            for index, params in enumerate(population)
        ]
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(evaluate, tasks))
        results.sort(key=lambda row: _score(row, args.objective), reverse=True)
        best = results[0]
        curve.append({"generation": generation, "best_mean": best["mean"], "best": best["params"], "avg": round(sum(r["mean"] for r in results) / len(results), 1)})
        print(f"第 {generation} 代: best={best['mean']:.0f} avg={curve[-1]['avg']:.0f} params={best['params']}")
        # 保留 Top-4，其余变异
        survivors = [dict(row["params"]) for row in results[:4]]
        population = list(survivors)
        while len(population) < args.population:
            parent = rng.choice(survivors)
            population.append(mutate(parent, keys, rng))
    best_all = max(curve, key=lambda row: row["best_mean"])
    print(f"\n最优（第 {best_all['generation']} 代）: mean={best_all['best_mean']} {best_all['best']}")
    if args.write:
        OUT.write_text(
            json.dumps({"version": 1, "source": "sim_evolve", "objective": args.objective,
                        "produce": best_all["best"],
                        "stats": {"best_mean": best_all["best_mean"]}, "curve": curve},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print("已写入", OUT)
    return 0


def _score(row: dict, objective: str) -> float:
    from gkagent.sim.objective import score

    return score(objective, row)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=1200)
    parser.add_argument("--samples", type=int, default=60, help="随机采样多少组参数")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--objective", default="cplus", choices=("cplus", "rank", "attr", "exam"),
                        help="评价口径：cplus=课题达成率 / rank=冲榜P95 / attr=属性 / exam=过本")
    parser.add_argument("--play", action="store_true", help="扫真机出牌参数（培育策略固定）")
    parser.add_argument("--evolve", action="store_true", help="进化式搜索（保留强者+变异，输出学习曲线）")
    parser.add_argument("--generations", type=int, default=8)
    parser.add_argument("--population", type=int, default=12)
    args = parser.parse_args(argv)


    import sim_produce as sp

    deck_raw = sp.build_deck(rich=True)
    pool_raw = sp.build_pool(rich=True)
    keys = list(GRID)
    all_combos = list(itertools.product(*(GRID[key] for key in keys)))
    rng = random.Random(7)
    # 已知好参数（rest=8/每周训练/训练体力门12/按权重/外出16/上课体力门8）
    warm_params = {
        "rest_threshold": 8,
        "training_every": 1,
        "training_min_stamina": 12,
        "attr_choice": "weight",
        "outing_below": 16,
        "min_stamina_for_class": 8,
    }
    warm = tuple(warm_params[key] for key in keys)
    combos = [warm] + [combo for combo in rng.sample(all_combos, min(args.samples, len(all_combos))) if combo != warm]
    print(f"搜索空间 {len(all_combos)} 组，本次采样 {len(combos)} 组 x {args.episodes} 局")

    if args.play:
        import itertools as _it

        keys_p = list(PLAY_GRID)
        combos_p = list(_it.product(*(PLAY_GRID[key] for key in keys_p)))
        print(f"出牌参数扫描: {len(combos_p)} 组 x {args.episodes} 局")
        tasks_p = [
            (dict(zip(keys_p, combo)), args.episodes, 11000 + index * 41, deck_raw, pool_raw)
            for index, combo in enumerate(combos_p)
        ]
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            results_p = list(executor.map(evaluate_play, tasks_p))
        results_p.sort(key=lambda row: _score(row, args.objective), reverse=True)
        for row in results_p[:6]:
            print(f"  mean={row['mean']:>7} 考试通过={row['exam_pass']*100:.0f}% {row['params']}")
        spread = results_p[0]["mean"] - results_p[-1]["mean"]
        print(f"最优-最差 = {spread:.1f}")
        return 0

    if args.evolve:
        return run_evolution(
            args, keys, deck_raw, pool_raw, rng, combos
        )

    tasks = [
        (dict(zip(keys, combo)), args.episodes, 5000 + index * 131, deck_raw, pool_raw)
        for index, combo in enumerate(combos)
    ]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool_exec:
        results = list(pool_exec.map(evaluate, tasks))
    elapsed = time.perf_counter() - started

    results.sort(key=lambda row: _score(row, args.objective), reverse=True)
    print(f"\n{elapsed:.1f}s，共 {len(results) * args.episodes} 局")
    print("Top-10 参数组合：")
    for row in results[:10]:
        print(
            f"  C+率={row.get('cplus_rate', 0)*100:3.0f}% P50={row.get('p50_eval', 0):>6} "
            f"P90={row.get('p90_eval', 0):>6} {row['params']}"
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
