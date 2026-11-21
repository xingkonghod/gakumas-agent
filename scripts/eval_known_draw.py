"""完全信息搜索 vs 期望搜索：同牌组 / 同 seed 配对评测。

对比两种搜索输入：

* ``unknown``：现状——``ExpectState`` 只知牌库**多重集**，抽牌是期望机会节点；
* ``known``：把 ``LessonSim`` 的真实剩余牌序写进 ``ExpectState.known_draw``
  （``state_from_sim(known_deck_order=True)``）。抽牌机会节点退化成确定分支；
  ``--policy beam`` 时跨回合 beam 能看到**后面几个回合的真实手牌**（完全信息规划）。

两种出牌策略：

* ``within``：每个出牌点跑回合内 expectimax（当前生产策略）；
* ``beam``：每回合开始跑跨回合 beam（width=4），按计划的整回合序列执行
  （``search_beam`` 的 root plan）——「知道牌序」的价值主要体现在这里：可以为了
  后面几张真实好牌保留体力/出牌位。

牌序数据链路的最终形态是 ``gkagent.sim.exam_oracle``（seed + 牌堆 → 牌序，含支援强化掷点）；
这里用 ``LessonSim`` 自己的真实牌序做离线对照，先量「信息本身值多少分」。

用法：python scripts/eval_known_draw.py [--games 100] [--scenario small|large]
                                      [--policy within|beam] [--seed 0] [--width 4]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import eval_expectimax as ee

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    expectimax_with_stats,
    search_beam,
    state_from_sim,
)
from gkagent.sim.lesson import LessonSim, greedy_policy


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(round(q * (len(ordered) - 1)), len(ordered) - 1)
    return float(ordered[index])


def _card_index(sim: LessonSim, card) -> int | None:
    for index, hand_card in enumerate(sim.hand):
        if hand_card == card:
            return index
    return None


def _play_within(sim: LessonSim, model, *, known: bool, budget_ms: float) -> int:
    """回合内 expectimax：每个出牌点搜一次，返回回退次数。"""
    fallbacks = 0
    actions = sim.legal_actions()
    if actions == [None]:
        sim.step(None)
        return fallbacks
    state = state_from_sim(sim, known_deck_order=known)
    result = expectimax_with_stats(state, model, time_budget_ms=budget_ms)
    index = _card_index(sim, result.card) if result.card is not None else None
    if index is None or index not in actions:
        if result.card is not None:
            fallbacks += 1
        index = greedy_policy(sim)
    sim.step(index)
    return fallbacks


def _execute_plan(sim: LessonSim, names: list[str]) -> int:
    """按 beam 计划的整回合序列执行；执行不动就回退 greedy（返回回退次数）。"""
    fallbacks = 0
    for name in names:
        if name.startswith("drink:"):
            drink_name = name.split(":", 1)[1]
            drinks = sim.legal_drinks()
            index = next(
                (i for i in drinks if sim.config.drinks[i].name == drink_name), None
            )
            if index is None:
                fallbacks += 1
                break
            sim.use_drink(index)
            continue
        actions = sim.legal_actions()
        if not sim.hand or actions == [None]:
            break
        index = next((i for i, card in enumerate(sim.hand) if card.name == name), None)
        if index is None or index not in actions:
            fallbacks += 1
            index = greedy_policy(sim)
            if index is None:
                break
        sim.step(index)
    if not sim.done and sim.legal_actions() != [None]:
        sim.step(None)
    return fallbacks


def play(
    deck,
    config,
    seed: int,
    *,
    known: bool,
    policy: str,
    budget_ms: float = 200.0,
    sigma: float = 60.0,
    width: int = 4,
) -> dict:
    """跑一局课程，返回分数与统计（fallback = 搜索给的牌在模拟器里执行不了）。"""
    sim = LessonSim(deck, config, rng_seed=seed)
    model = AnalyticLeafValue(sigma=sigma)
    fallbacks = 0
    decisions = 0
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            sim.step(None)
            continue
        decisions += 1
        if policy == "within":
            fallbacks += _play_within(sim, model, known=known, budget_ms=budget_ms)
            continue
        state = state_from_sim(sim, known_deck_order=known)
        result = search_beam(state, model, width=width, deadline_ms=budget_ms * 2)
        fallbacks += _execute_plan(sim, list(result.sequence))
    return {
        "score": float(sim.score),
        "clear": 1.0 if sim.score >= config.target_clear else 0.0,
        "perfect": 1.0 if sim.score >= config.target_perfect else 0.0,
        "fallbacks": fallbacks,
        "decisions": decisions,
    }


def summarize(rows: list[dict]) -> dict:
    scores = [row["score"] for row in rows]
    return {
        "mean": sum(scores) / len(scores),
        "p10": _percentile(scores, 0.10),
        "p50": _percentile(scores, 0.50),
        "p90": _percentile(scores, 0.90),
        "clear_rate": sum(row["clear"] for row in rows) / len(rows),
        "perfect_rate": sum(row["perfect"] for row in rows) / len(rows),
        "fallbacks": sum(row["fallbacks"] for row in rows),
        "decisions": sum(row["decisions"] for row in rows),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--scenario", choices=("small", "large"), default="small")
    parser.add_argument("--policy", choices=("within", "beam"), default="within")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--budget-ms", type=float, default=200.0)
    parser.add_argument("--width", type=int, default=4)
    args = parser.parse_args(argv)

    deck = ee.build_deck(args.scenario)
    config = ee.make_config(args.scenario)
    print(
        f"scenario={args.scenario} deck={len(deck)} turns={config.turns} "
        f"policy={args.policy} games={args.games} budget={args.budget_ms:.0f}ms "
        f"width={args.width}"
    )
    rows = {"unknown": [], "known": []}
    for offset in range(args.games):
        seed = args.seed + offset
        for kind, known in (("unknown", False), ("known", True)):
            rows[kind].append(
                play(
                    deck,
                    config,
                    seed,
                    known=known,
                    policy=args.policy,
                    budget_ms=args.budget_ms,
                    width=args.width,
                )
            )

    stats = {kind: summarize(values) for kind, values in rows.items()}
    print(
        f"{'策略':<10}{'均值':>8}{'P10':>8}{'P50':>8}{'P90':>8}{'CLEAR':>8}{'PERFECT':>9}{'回退':>6}"
    )
    for kind in ("unknown", "known"):
        stat = stats[kind]
        print(
            f"{kind:<10}{stat['mean']:>8.1f}{stat['p10']:>8.0f}{stat['p50']:>8.0f}"
            f"{stat['p90']:>8.0f}{stat['clear_rate'] * 100:>7.1f}%"
            f"{stat['perfect_rate'] * 100:>8.1f}%{stat['fallbacks']:>6d}"
        )
    diff = stats["known"]["mean"] - stats["unknown"]["mean"]
    print(
        f"\nknown - unknown：均值 {diff:+.1f}，"
        f"P50 {stats['known']['p50'] - stats['unknown']['p50']:+.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
