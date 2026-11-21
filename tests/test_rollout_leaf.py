"""rollout 叶子估值（T4 起点）的回归测试。

覆盖：ExpectState → LessonSim 快照重建、rollout 预测/缓存的数值契约、
``turns_left<=0`` 边界、utility 的档位单调性、known_draw 确定性。
不跑真机，全部离线小牌组。
"""

from __future__ import annotations

from dataclasses import replace

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    RolloutLeafValue,
    end_turn_state,
    sim_from_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim

DECK = [
    CardSpec("大", 2, 40),
    CardSpec("中", 1, 15),
    CardSpec("小", 1, 8),
    CardSpec("大", 2, 40),
    CardSpec("中", 1, 15),
    CardSpec("小", 1, 8),
]
CONFIG = LessonConfig(turns=5, stamina=34, target_clear=120, target_perfect=170)


def _fresh() -> LessonSim:
    return LessonSim(DECK, CONFIG, rng_seed=0)


def _state():
    return state_from_sim(_fresh())


def test_sim_from_state_round_trip_keeps_snapshot() -> None:
    sim = _fresh()
    # 打两张牌再结束回合，让快照有 score/stamina/discard 变化
    sim.step(0)
    sim.step(0)
    sim._end_turn(skipped=False)
    state = state_from_sim(sim)

    rebuilt = sim_from_state(state)
    assert rebuilt.score == state.score
    assert rebuilt.stamina == state.stamina
    assert rebuilt.vitality == state.vitality
    assert rebuilt.turns_left == state.turns_left
    assert [card.name for card in rebuilt.hand] == [card.name for card in state.hand]
    assert sorted(card.name for card in rebuilt.deck) == sorted(
        card.name for card in state.deck
    )
    assert sorted(card.name for card in rebuilt.discard) == sorted(
        card.name for card in state.discard
    )
    # 重建后的模拟器还能继续跑完（不崩、结束）
    rebuilt.run(lambda _sim: None)
    assert rebuilt.done


def test_rollout_leaf_predict_and_cache() -> None:
    leaf = RolloutLeafValue(rollouts=2)
    mu, sigma = leaf.predict(_state())
    assert mu >= 0.0
    assert sigma > 0.0
    assert leaf.predict(_state()) == (mu, sigma)  # 同状态命中缓存


def test_rollout_leaf_zero_turns_returns_zero() -> None:
    leaf = RolloutLeafValue(rollouts=2)
    state = replace(_state(), turns_left=0)
    assert leaf.predict(state) == (0.0, 0.0)
    assert leaf.utility(state) == 0.0


def test_rollout_leaf_utility_prefers_more_score() -> None:
    leaf = RolloutLeafValue(rollouts=2)
    state = _state()
    low = leaf.utility(replace(state, score=0))
    high = leaf.utility(replace(state, score=state.clear + 100))
    assert high >= low


def test_rollout_leaf_known_draw_is_deterministic() -> None:
    leaf = RolloutLeafValue(rollouts=2)
    state = _state()
    known = replace(state, known_draw=tuple(state.deck))
    first = leaf.predict(known)
    second = RolloutLeafValue(rollouts=2).predict(known)
    assert first == second


def test_rollout_leaf_utility_matches_analytic_scale_on_finished_lesson() -> None:
    """分数已超过 PERFECT：两种叶子的终局效用都应该是 1+1（满分档）。"""
    state = replace(_state(), turns_left=0, score=CONFIG.target_perfect)
    expected = 2.0
    assert AnalyticLeafValue().utility(state) == expected
    assert RolloutLeafValue().utility(state) == expected


def test_rollout_leaf_does_not_mutate_input_state() -> None:
    leaf = RolloutLeafValue(rollouts=1)
    state = _state()
    before = state.canonical()
    leaf.predict(state)
    leaf.utility(end_turn_state(state))
    assert state.canonical() == before
