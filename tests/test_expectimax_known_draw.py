"""完全信息搜索（known_draw）的 L1 机制测试。

``ExpectState.known_draw`` 是「已知的后续抽牌顺序」（下标 0 = 下一张）。非空时
``expectimax`` 的抽牌机会节点退化成确定分支；空时保持原来的「只知多重集」期望模型。
数据来源见 ``gkagent.sim.exam_oracle``（seed + 牌堆 → 整段牌序）。
"""

from __future__ import annotations

import random

import pytest

from gkagent.sim.expectimax import (
    ExpectState,
    apply_card,
    expectimax_with_stats,
    sample_draws,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim

DRAW = CardSpec("抽", 0, 0, draw=1, extra_play=1)
DRAW2 = CardSpec("抽2", 0, 0, draw=2)
BIG = CardSpec("大", 0, 100)
ZERO = CardSpec("零", 0, 0)
SMALL = CardSpec("小", 0, 5)


class _ScoreValue:
    """把「最终分数」直接当效用的叶子估值（让本文件的期望可以手算）。"""

    def predict(self, state: ExpectState) -> tuple[float, float]:
        return (float(state.score), 0.0)

    def utility(self, state: ExpectState) -> float:
        return float(state.score)


def _state(**kwargs) -> ExpectState:
    base = {
        "turns_left": 1,
        "play_limit": 1,
        "clear": 1,
        "perfect": 1000,
    }
    base.update(kwargs)
    return ExpectState(**base)


# ---------------------------------------------------------------- 机制


def test_known_draw_collapses_chance_node_to_single_branch():
    state = _state(hand=(DRAW,), deck=(BIG, ZERO), known_draw=(BIG, ZERO))
    outcomes = apply_card(state, DRAW)
    assert len(outcomes) == 1
    probability, successor = outcomes[0]
    assert probability == pytest.approx(1.0)
    assert successor.hand == (BIG,)  # 抽到的是已知的第一张
    assert successor.deck == (ZERO,)
    assert successor.known_draw == (ZERO,)


def test_known_draw_consumes_in_known_order():
    state = _state(hand=(DRAW2,), deck=(BIG, ZERO), known_draw=(BIG, ZERO))
    successor = apply_card(state, DRAW2)[0][1]
    assert successor.hand == (BIG, ZERO)  # 按 known_draw 顺序入手
    assert successor.deck == ()
    assert successor.known_draw == ()
    assert state.hand == (DRAW2,)  # 不修改原状态


def test_known_draw_value_is_deterministic_outcome():
    """同一多重集：知道下一张是大牌时最优价值=100；不知道时期望=50。"""
    known = _state(hand=(DRAW,), deck=(BIG, ZERO), known_draw=(BIG, ZERO))
    unknown = _state(hand=(DRAW,), deck=(BIG, ZERO))
    known_value = expectimax_with_stats(known, _ScoreValue()).utility
    unknown_value = expectimax_with_stats(unknown, _ScoreValue()).utility
    assert known_value == pytest.approx(100.0)
    assert unknown_value == pytest.approx(50.0)


def test_known_draw_invalid_length_falls_back_to_expectation():
    """known_draw 和 deck 长度不一致（牌被效果移动过）→ 退回多重集期望。"""
    broken = _state(hand=(DRAW,), deck=(BIG, ZERO), known_draw=(BIG,))
    outcomes = apply_card(broken, DRAW)
    assert len(outcomes) == 2
    assert {successor.hand[0] for _, successor in outcomes} == {BIG, ZERO}


def test_known_draw_exhausted_then_reshuffles_by_expectation():
    """已知段抽完、牌库空：剩余抽牌要洗弃牌，退回多重集期望（仍有概率分支）。"""
    state = _state(
        hand=(DRAW2,),
        deck=(BIG,),
        known_draw=(BIG,),
        discard=(ZERO, SMALL),
    )
    outcomes = apply_card(state, DRAW2)
    assert len(outcomes) == 2  # 弃牌堆两张，洗回后抽哪张未知
    assert {successor.hand[-1] for _, successor in outcomes} == {ZERO, SMALL}
    assert all(successor.known_draw == () for _, successor in outcomes)


def test_sample_draws_respects_known_order():
    state = _state(hand=(), deck=(BIG, ZERO), known_draw=(BIG, ZERO))
    rng = random.Random(1)
    after = sample_draws(state, 1, rng)
    assert after.hand == (BIG,)
    assert after.deck == (ZERO,)
    assert after.known_draw == (ZERO,)


def test_state_from_sim_known_deck_order_uses_draw_order():
    """LessonSim 从 deck 尾部 pop() → 抽牌顺序 = reversed(deck)。"""
    deck = [DRAW, BIG, ZERO]
    sim = LessonSim(deck, LessonConfig(turns=1, stamina=3, target_clear=100), rng_seed=1)
    sim.hand = []
    sim.deck = [DRAW, BIG, ZERO]
    state = state_from_sim(sim, known_deck_order=True)
    assert state.known_draw == (ZERO, BIG, DRAW)
    assert len(state.known_draw) == len(state.deck)
    assert state_from_sim(sim).known_draw == ()
