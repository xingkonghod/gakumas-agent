"""Ablation: P 道具接入课程结算 / 饮料作为搜索动作（300 局，固定 seed）。"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sim_produce as sp

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    expectimax_with_stats,
    state_from_sim,
)
from gkagent.sim.lesson import DrinkSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import load_p_items
from gkagent.sim.produce import (
    ProduceConfig,
    ProduceSim,
    StrategyParams,
    eval_value,
    strategy_from_params,
)

EPISODES = 300
DECK = [sp._spec_from_row(row) for row in sp.build_deck(rich=True)]
POOL = [sp._spec_from_row(row) for row in sp.build_pool(rich=True)]
STRATEGY = strategy_from_params(StrategyParams())


def p50(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * 0.5)]


def _eval_rows(config: ProduceConfig) -> list[int]:
    values = []
    for seed in range(EPISODES):
        sim = ProduceSim(DECK, config=config, rng_seed=seed)
        sim.reward_pool = POOL
        result = sim.run(STRATEGY)
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"):
                rank = row["exam"]["rank"]
                break
        values.append(eval_value(result.total, rank, result.exam_score))
    return values


def ablate_p_items() -> None:
    items = tuple(load_p_items())
    print(f"P 道具 specs: {len(items)}（implemented {sum(i.implemented for i in items)}）")
    before = _eval_rows(ProduceConfig(p_items=()))
    started = time.perf_counter()
    after = _eval_rows(ProduceConfig(p_items=items))
    elapsed = time.perf_counter() - started
    print(
        {
            "before_p50": p50(before),
            "before_mean": round(statistics.fmean(before), 1),
            "after_p50": p50(after),
            "after_mean": round(statistics.fmean(after), 1),
            "p50_delta": p50(after) - p50(before),
            "elapsed_s": round(elapsed, 1),
        }
    )


def _drink_config() -> LessonConfig:
    drinks = (
        DrinkSpec("体力饮料", 0, "stamina", 10, uses=3),
        DrinkSpec("集中饮料", 0, "focus", 3, uses=3),
        DrinkSpec("分数饮料", 0, "score", 20, uses=3),
    )
    return LessonConfig(
        turns=5,
        stamina=34,
        stamina_max=44,
        target_clear=150,
        target_perfect=220,
        hand_size=3,
        drinks=drinks,
    )


def _run_drinks(*, allow_drinks: bool) -> tuple[list[int], list[float], int]:
    config = _drink_config()
    model = AnalyticLeafValue(sigma=60.0)
    scores: list[int] = []
    latencies: list[float] = []
    for seed in range(EPISODES):
        sim = LessonSim(DECK, config, rng_seed=seed)
        steps = 0
        while not sim.done and steps < 2000:
            steps += 1
            started = time.perf_counter()
            result = expectimax_with_stats(
                state_from_sim(sim),
                model,
                time_budget_ms=200,
                allow_drinks=allow_drinks,
            )
            latencies.append((time.perf_counter() - started) * 1000.0)
            if result.drink is not None:
                sim.use_drink(result.drink)
                continue
            if result.card is None:
                sim.step(None)
                continue
            index = next(
                (i for i, card in enumerate(sim.hand) if card == result.card), None
            )
            if index is None:
                sim.step(None)
            else:
                sim.step(index)
        scores.append(sim.score)
    return scores, latencies, sum(1 for row in scores if row >= 220)


def ablate_drinks() -> None:
    before, _lat_before, perf_before = _run_drinks(allow_drinks=False)
    after, lat_after, perf_after = _run_drinks(allow_drinks=True)
    print(
        {
            "before_p50": p50(before),
            "before_mean": round(statistics.fmean(before), 1),
            "before_perfect": perf_before,
            "after_p50": p50(after),
            "after_mean": round(statistics.fmean(after), 1),
            "after_perfect": perf_after,
            "p50_delta": p50(after) - p50(before),
            "mean_delta": round(statistics.fmean(after) - statistics.fmean(before), 1),
            "latency_mean_ms": round(statistics.fmean(lat_after), 2),
            "latency_p95_ms": round(sorted(lat_after)[int(len(lat_after) * 0.95)], 2),
        }
    )


if __name__ == "__main__":
    print("=== P 道具 接入前 vs 后 ===")
    ablate_p_items()
    print("=== 饮料 可搜索前 vs 后 ===")
    ablate_drinks()
