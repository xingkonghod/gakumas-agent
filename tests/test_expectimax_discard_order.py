"""重洗后段全知：``ExpectState.discard_order`` + 确定性重洗钩子的 L1 测试。

背景：考试牌序从 seed 能整段推出来（``gkagent.sim.exam_oracle``），牌堆抽空时
客户端会用**弃牌堆的真实顺序**做 Fisher-Yates 重洗。搜索侧原来只有弃牌堆的
多重集（顺序未知），所以第一次重洗之后又退回期望模型。

``ExpectState.discard_order`` 带上「进弃牌堆的先后」（None = 未知，() = 已知为空）；
搜索入口的 ``reshuffle`` 钩子（``Callable[[grave], list[CardSpec]]``，返回重洗后的
**抽牌顺序**）配合已知顺序，让重洗与之后的抽牌也变成确定分支。
"""

from __future__ import annotations

import random

import pytest

from gkagent.sim.exam_oracle import ExamDrawOracle
from gkagent.sim.exam_shuffle import NativeRandom, reshuffle_grave
from gkagent.sim.expectimax import (
    ExpectState,
    apply_card,
    end_turn_state,
    expectimax_with_stats,
    reshuffle_from_sim,
    sample_apply_card,
    sample_draws,
    search_beam,
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


def _reverse_reshuffle(grave: tuple[CardSpec, ...]) -> list[CardSpec]:
    """确定性的「重洗」：把 grave 反转当抽牌顺序（方便手算期望）。"""
    return list(reversed(tuple(grave)))


# ---------------------------------------------------------------- 顺序维护


def test_apply_card_maintains_discard_order():
    state = _state(hand=(SMALL, ZERO), discard_order=(), play_limit=2)
    successor = apply_card(state, SMALL)[0][1]
    assert successor.discard == (SMALL,)
    assert successor.discard_order == (SMALL,)
    successor = apply_card(successor, ZERO)[0][1]
    assert successor.discard == (SMALL, ZERO)
    assert successor.discard_order == (SMALL, ZERO)


def test_unknown_discard_order_stays_unknown():
    """``discard_order=None``（默认）时不能凭空造出顺序。"""
    state = _state(hand=(SMALL,), discard=(BIG,))
    assert state.discard_order is None
    successor = apply_card(state, SMALL)[0][1]
    assert successor.discard_order is None


def test_end_turn_appends_hand_in_hand_order():
    state = _state(
        hand=(BIG, ZERO),
        discard=(SMALL,),
        discard_order=(SMALL,),
        turns_left=2,
    )
    end = end_turn_state(state)
    assert end.discard == (SMALL, BIG, ZERO)
    assert end.discard_order == (SMALL, BIG, ZERO)


def test_canonical_distinguishes_discard_order():
    """同一个弃牌多重集、不同顺序 → 重洗结果不同，必须是不同的记忆化键。"""
    left = _state(discard=(ZERO, SMALL), discard_order=(ZERO, SMALL))
    right = _state(discard=(ZERO, SMALL), discard_order=(SMALL, ZERO))
    assert left.canonical() != right.canonical()


# ---------------------------------------------------------------- 确定性重洗


def test_known_draw_reshuffle_is_deterministic():
    """已知段抽完 + 弃牌顺序已知 + 重洗钩子 → 单分支，按钩子顺序入手。"""
    state = _state(
        hand=(DRAW2,),
        deck=(BIG,),
        known_draw=(BIG,),
        discard=(ZERO, SMALL),
        discard_order=(ZERO, SMALL),
    )
    # reverse((ZERO, SMALL)) = (SMALL, ZERO)：BIG 之后抽到 SMALL
    outcomes = apply_card(state, DRAW2, reshuffle=_reverse_reshuffle)
    assert len(outcomes) == 1
    probability, successor = outcomes[0]
    assert probability == pytest.approx(1.0)
    assert successor.hand == (BIG, SMALL)
    assert successor.deck == (ZERO,)
    assert successor.known_draw == (ZERO,)
    # 打出的牌在抽牌结算后才进弃牌堆；此时弃牌堆只剩刚打的这张
    assert successor.discard == (DRAW2,)
    assert successor.discard_order == (DRAW2,)


def test_empty_deck_uses_reshuffle_hook():
    """牌堆本来已空（known_draw 为空）也能按弃牌顺序确定性重洗。"""
    state = _state(
        hand=(DRAW2,),
        deck=(),
        discard=(ZERO, SMALL),
        discard_order=(ZERO, SMALL),
    )
    outcomes = apply_card(state, DRAW2, reshuffle=_reverse_reshuffle)
    assert len(outcomes) == 1
    assert outcomes[0][1].hand == (SMALL, ZERO)
    assert outcomes[0][1].discard == (DRAW2,)


def test_without_reshuffle_hook_falls_back_to_expectation():
    """没给钩子（默认生产行为）→ 仍是多重集期望，不因 discard_order 变化。"""
    state = _state(
        hand=(DRAW2,),
        deck=(BIG,),
        known_draw=(BIG,),
        discard=(ZERO, SMALL),
        discard_order=(ZERO, SMALL),
    )
    outcomes = apply_card(state, DRAW2)
    assert len(outcomes) == 2
    assert {successor.hand[-1] for _, successor in outcomes} == {ZERO, SMALL}
    assert all(successor.known_draw == () for _, successor in outcomes)


def test_mismatched_discard_order_falls_back():
    """discard_order 与 discard 多重集不一致（搜索模拟的弃牌堆和真实线不同）→ 退回期望。"""
    state = _state(
        hand=(DRAW2,),
        deck=(BIG,),
        known_draw=(BIG,),
        discard=(ZERO, SMALL),
        discard_order=(ZERO, BIG),
    )
    outcomes = apply_card(state, DRAW2, reshuffle=_reverse_reshuffle)
    assert len(outcomes) == 2


def test_bad_hook_output_falls_back():
    """钩子返回的牌堆多重集和弃牌堆不一致 → 不信任，退回期望。"""
    state = _state(
        hand=(DRAW2,),
        deck=(BIG,),
        known_draw=(BIG,),
        discard=(ZERO, SMALL),
        discard_order=(ZERO, SMALL),
    )
    outcomes = apply_card(state, DRAW2, reshuffle=lambda grave: [BIG])
    assert len(outcomes) == 2


def test_known_reshuffle_value_is_deterministic_outcome():
    """知道重洗后下一张是大牌时，档位价值 = 确定结果（不知道时期望 50）。"""
    known = _state(
        hand=(DRAW,),
        deck=(),
        discard=(ZERO, BIG),
        # reverse((ZERO, BIG)) = (BIG, ZERO) → 抽到 BIG（再打出去拿 100 分）
        discard_order=(ZERO, BIG),
    )
    unknown = _state(hand=(DRAW,), deck=(), discard=(ZERO, BIG))
    known_value = expectimax_with_stats(
        known,
        _ScoreValue(),
        reshuffle=_reverse_reshuffle,
        allow_drinks=False,
    ).utility
    unknown_value = expectimax_with_stats(
        unknown, _ScoreValue(), allow_drinks=False
    ).utility
    assert known_value == pytest.approx(100.0)
    assert unknown_value == pytest.approx(50.0)


# ---------------------------------------------------------------- 采样（beam 用）


def test_sample_draws_uses_reshuffle_hook():
    state = _state(
        hand=(),
        deck=(BIG,),
        known_draw=(BIG,),
        discard=(ZERO, SMALL),
        discard_order=(ZERO, SMALL),
    )
    after = sample_draws(state, 2, random.Random(0), reshuffle=_reverse_reshuffle)
    assert after.hand == (BIG, SMALL)
    assert after.deck == (ZERO,)


def test_sample_apply_card_maintains_discard_order():
    state = _state(hand=(SMALL,), discard_order=())
    after = sample_apply_card(state, SMALL, random.Random(0))
    assert after.discard == (SMALL,)
    assert after.discard_order == (SMALL,)


def test_sample_draws_random_reshuffle_invalidates_order():
    """没给钩子、靠随机洗弃牌时，顺序不再已知（不能留旧的 discard_order）。"""
    state = _state(
        hand=(),
        deck=(),
        discard=(ZERO, SMALL),
        discard_order=(ZERO, SMALL),
    )
    after = sample_draws(state, 1, random.Random(0))
    assert len(after.hand) == 1
    assert after.discard_order in (None, ())
    assert after.known_draw == ()


# ---------------------------------------------------------------- 数据源钩子


def test_oracle_reshuffle_is_pure_and_matches_model():
    deck = [("c1", 0), ("c2", 0), ("c3", 0)]
    oracle = ExamDrawOracle(0x1234, deck, 5)
    before = oracle.rng_state
    grave = [("c1", 0), ("c2", 0)]
    got = oracle.reshuffle(grave)
    assert oracle.rng_state == before  # 纯预览：不推进考试 RNG
    assert got == reshuffle_grave(NativeRandom(before), list(grave))
    assert oracle.reshuffle(grave) == got  # 同输入同输出


def test_reshuffle_from_sim_matches_lesson_sim():
    """钩子预测的第一张 = ``LessonSim`` 真实重洗后抽到的第一张。"""
    cards = [CardSpec(f"c{i}", 0, i) for i in range(5)]
    config = LessonConfig(turns=3, stamina=10, target_clear=10, hand_size=2)
    sim = LessonSim(list(cards), config, rng_seed=7)
    sim.hand = []
    sim.deck = []
    sim.discard = [cards[1], cards[3], cards[0], cards[4]]
    predicted = reshuffle_from_sim(sim)(tuple(sim.discard))
    assert sim._draw_one() == predicted[0]
    assert sim._draw_one() == predicted[1]


def test_state_from_sim_carries_discard_order():
    cards = [CardSpec(f"c{i}", 0, i) for i in range(4)]
    config = LessonConfig(turns=3, stamina=10, target_clear=10, hand_size=1)
    sim = LessonSim(list(cards), config, rng_seed=3)
    sim.hand = []
    sim.deck = []
    sim.discard = [cards[2], cards[0]]
    state = state_from_sim(sim, known_deck_order=True)
    assert state.discard_order == (cards[2], cards[0])
    # 牌堆空 + 钩子 → 抽牌确定（不再是随机的）
    after = sample_draws(state, 1, random.Random(9), reshuffle=reshuffle_from_sim(sim))
    assert after.hand == (reshuffle_from_sim(sim)(tuple(sim.discard))[0],)


def test_beam_with_known_reshuffle_is_reproducible():
    """beam 也接受 reshuffle：同一输入两次结果一致，且拿到合法首牌。"""
    state = _state(
        hand=(DRAW,),
        deck=(BIG,),
        known_draw=(BIG,),
        discard=(ZERO, SMALL),
        discard_order=(ZERO, SMALL),
        turns_left=2,
        total_turns=2,
    )
    first = search_beam(
        state,
        _ScoreValue(),
        width=2,
        deadline_ms=200,
        rng=1,
        reshuffle=_reverse_reshuffle,
    )
    second = search_beam(
        state,
        _ScoreValue(),
        width=2,
        deadline_ms=200,
        rng=1,
        reshuffle=_reverse_reshuffle,
    )
    assert first.card == second.card == DRAW
    assert first.sequence == second.sequence
