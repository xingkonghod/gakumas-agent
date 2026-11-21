"""完全信息搜索 vs 期望搜索：同牌组 / 同 seed 配对评测。

对比三种搜索输入：

* ``unknown``：现状——``ExpectState`` 只知牌库**多重集**，抽牌是期望机会节点；
* ``known``：把 ``LessonSim`` 的真实剩余牌序写进 ``ExpectState.known_draw``
  （``state_from_sim(known_deck_order=True)``）。抽牌机会节点退化成确定分支；
  ``--policy beam`` 时跨回合 beam 能看到**后面几个回合的真实手牌**（完全信息规划）。
* ``full``（``--full-info``）：在 known 基础上再把 ``LessonSim`` 的弃牌堆真实顺序
  写进 ``ExpectState.discard_order``，并用 ``reshuffle_from_sim(sim)`` 当重洗钩子
  ——牌堆第一次抽空后的重洗与后续抽牌也按真实顺序走（重洗后段全知）。

两种出牌策略：

* ``within``：每个出牌点跑回合内 expectimax（当前生产策略）；
* ``beam``：每回合开始跑跨回合 beam（width=4），按计划的整回合序列执行
  （``search_beam`` 的 root plan）——「知道牌序」的价值主要体现在这里：可以为了
  后面几张真实好牌保留体力/出牌位。

牌序数据链路的最终形态是 ``gkagent.sim.exam_oracle``（seed + 牌堆 → 牌序，含支援强化掷点）；
这里用 ``LessonSim`` 自己的真实牌序做离线对照，先量「信息本身值多少分」。

用法：python scripts/eval_known_draw.py [--games 100] [--scenario small|large]
                                      [--policy within|beam] [--seed 0] [--width 4]
                                      [--full-info]
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
    RolloutLeafValue,
    expectimax_with_stats,
    reshuffle_from_sim,
    search_beam,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim, greedy_policy


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


def _play_within(
    sim: LessonSim, model, *, known: bool, full_info: bool, budget_ms: float
) -> int:
    """回合内 expectimax：每个出牌点搜一次，返回回退次数。"""
    fallbacks = 0
    actions = sim.legal_actions()
    if actions == [None]:
        sim.step(None)
        return fallbacks
    state = state_from_sim(sim, known_deck_order=known)
    result = expectimax_with_stats(
        state,
        model,
        time_budget_ms=budget_ms,
        reshuffle=reshuffle_from_sim(sim) if full_info else None,
    )
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
    full_info: bool = False,
    budget_ms: float = 200.0,
    sigma: float = 60.0,
    width: int = 4,
    score_tiebreak: float = 0.0,
    branching: int | None = None,
    leaf: str = "analytic",
    rollouts: int = 3,
    rollout_policy: str = "greedy",
    rollout_budget_ms: float = 5.0,
) -> dict:
    """跑一局课程，返回分数与统计（fallback = 搜索给的牌在模拟器里执行不了）。

    ``full_info``：弃牌堆顺序 + ``reshuffle_from_sim`` 钩子，重洗后段也全知。
    ``score_tiebreak``：档位效用封顶导致的平手项（0=历史行为）；``branching``：
    beam 每层抽样分支数（None=默认 max(2, min(width, 3))）。
    ``leaf``：``analytic``=解析式 V_leaf；``rollout``=LessonSim+greedy 快跑剩余回合。
    """
    sim = LessonSim(deck, config, rng_seed=seed)
    if leaf == "rollout":
        model = RolloutLeafValue(
            sigma=sigma,
            score_tiebreak=score_tiebreak,
            rollouts=rollouts,
            policy=rollout_policy,
            rollout_budget_ms=rollout_budget_ms,
        )
    else:
        model = AnalyticLeafValue(sigma=sigma, score_tiebreak=score_tiebreak)
    fallbacks = 0
    decisions = 0
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            sim.step(None)
            continue
        decisions += 1
        if policy == "within":
            fallbacks += _play_within(
                sim, model, known=known, full_info=full_info, budget_ms=budget_ms
            )
            continue
        state = state_from_sim(sim, known_deck_order=known)
        result = search_beam(
            state,
            model,
            width=width,
            deadline_ms=budget_ms * 2,
            branching=branching,
            # 每次决策都从 sim.rng 当前状态取快照（重洗前的 RNG 状态）
            reshuffle=reshuffle_from_sim(sim) if full_info else None,
        )
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


DRAW_SCENARIO = {"turns": 5, "stamina": 34, "clear": 120, "perfect": 170}


def _draw_scenario() -> tuple[list[CardSpec], LessonConfig]:
    """抽牌多的构造牌组：回合内抽牌会把牌堆抽空 → 直接量「重洗后段全知」的增量。"""
    draw = CardSpec("抽1", 2, 0, draw=1)
    big = CardSpec("大", 2, 40)
    mid = CardSpec("中", 1, 15)
    deck = [draw] * 6 + [big] * 2 + [mid] * 6
    config = LessonConfig(
        turns=int(DRAW_SCENARIO["turns"]),
        stamina=int(DRAW_SCENARIO["stamina"]),
        target_clear=int(DRAW_SCENARIO["clear"]),
        target_perfect=int(DRAW_SCENARIO["perfect"]),
    )
    return deck, config


def _make_deck_and_config(scenario: str):
    if scenario == "draw":
        return _draw_scenario()
    return ee.build_deck(scenario), ee.make_config(scenario)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--scenario", choices=("small", "large", "draw"), default="small")
    parser.add_argument("--policy", choices=("within", "beam"), default="within")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--budget-ms", type=float, default=200.0)
    parser.add_argument("--width", type=int, default=4)
    parser.add_argument(
        "--score-tiebreak",
        type=float,
        default=0.0,
        help=(
            "档位效用封顶的平手项（0=历史行为）。2026-11-21 T4 实验：小牌组 beam "
            "unknown 87.9 → 100.2（tiebreak=1e-3），仍低于回合内 expectimax。"
        ),
    )
    parser.add_argument(
        "--branching",
        type=int,
        default=0,
        help="beam 每层抽样分支数（0=默认 max(2, min(width, 3))；实验 6~10 提升明显）",
    )
    parser.add_argument(
        "--full-info",
        action="store_true",
        help="额外跑 full（known_draw + discard_order + reshuffle 钩子，重洗后段全知）",
    )
    parser.add_argument(
        "--leaf",
        choices=("analytic", "rollout"),
        default="analytic",
        help="叶子估值：analytic=解析式；rollout=LessonSim+greedy 快跑剩余回合",
    )
    parser.add_argument(
        "--rollouts",
        type=int,
        default=3,
        help="rollout 叶子的采样次数（牌序未知时取均值+标准差）",
    )
    parser.add_argument(
        "--rollout-policy",
        choices=("greedy", "within"),
        default="greedy",
        help="rollout 内部策略：greedy=基线；within=每回合小预算 expectimax（慢）",
    )
    parser.add_argument(
        "--rollout-budget-ms",
        type=float,
        default=5.0,
        help="rollout-policy=within 时每回合 expectimax 的时间预算",
    )
    args = parser.parse_args(argv)

    deck, config = _make_deck_and_config(args.scenario)
    kinds = ["unknown", "known"]
    if args.full_info:
        kinds.append("full")
    print(
        f"scenario={args.scenario} deck={len(deck)} turns={config.turns} "
        f"policy={args.policy} games={args.games} budget={args.budget_ms:.0f}ms "
        f"width={args.width} full_info={args.full_info} "
        f"score_tiebreak={args.score_tiebreak:g} branching={args.branching or '默认'}"
    )
    rows = {kind: [] for kind in kinds}
    for offset in range(args.games):
        seed = args.seed + offset
        for kind in kinds:
            rows[kind].append(
                play(
                    deck,
                    config,
                    seed,
                    known=kind != "unknown",
                    policy=args.policy,
                    full_info=kind == "full",
                    budget_ms=args.budget_ms,
                    width=args.width,
                    score_tiebreak=args.score_tiebreak,
                    branching=args.branching or None,
                    leaf=args.leaf,
                    rollouts=args.rollouts,
                    rollout_policy=args.rollout_policy,
                    rollout_budget_ms=args.rollout_budget_ms,
                )
            )

    stats = {kind: summarize(values) for kind, values in rows.items()}
    print(
        f"{'策略':<10}{'均值':>8}{'P10':>8}{'P50':>8}{'P90':>8}{'CLEAR':>8}{'PERFECT':>9}{'回退':>6}"
    )
    for kind in kinds:
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
    if args.full_info:
        full_diff = stats["full"]["mean"] - stats["known"]["mean"]
        print(
            f"full - known：均值 {full_diff:+.1f}，"
            f"P50 {stats['full']['p50'] - stats['known']['p50']:+.1f}"
            "（重洗后段全知的增量）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
