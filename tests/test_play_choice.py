"""sim 实时出牌：每张手牌 rollout 后的期望分与选择（policy.json sim_play 的后端）。

真机出牌目前是 LessonPolicy 规则；``choose_card_via_sim`` 用课程模拟器对每张手牌
做「先打这张 + 剩余回合 greedy 打完」的前瞻，比较期望总分。任何异常都必须返回
``None``（调用方退回规则），绝不能让出牌退化。
"""

from __future__ import annotations

import pytest

from gkagent.sim.lesson import CardSpec, LessonConfig
from gkagent.sim.play_choice import (
    CardEstimate,
    best_index,
    choose_card_via_sim,
    estimate_hand,
    specs_from_hand,
)
from gkagent.vision.lesson import LessonCard


class FakeTable:
    """最小卡表：``get(name)`` 返回 cost/effects，行为与 CardTable 一致。"""

    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = rows

    def get(self, name: str) -> dict | None:
        return self.rows.get(name) or self.rows.get((name or "").rstrip("+＋"))


def _card(
    index: int,
    name: str,
    *,
    cost: int | None = 4,
    score: int | None = None,
    hits: int | None = None,
) -> LessonCard:
    return LessonCard(
        index=index,
        box=(40 + index * 200, 890, 180, 220),
        point=(140 + index * 200, 1000),
        name=name,
        score=score,
        hits=hits,
        cost=cost,
    )


# 真机审查手牌：在我发现的世界(buff) / 试行错误+(84分/5费) / 轻快步伐(25分)
TABLE = FakeTable(
    {
        "在我发现的世界": {
            "cost": 4,
            "effects": [{"type": "ExamLessonBuffDependParameterBuff", "values": [1000]}],
        },
        "试行错误+": {"cost": 5, "effects": [{"type": "ExamLesson", "values": [10], "count": 2}]},
        "轻快步伐": {"cost": 4, "effects": [{"type": "ExamLesson", "values": [6]}]},
    }
)
HAND = [
    _card(0, "在我发现的世界", cost=4),
    _card(1, "试行错误+", cost=5, score=42, hits=2),
    _card(2, "轻快步伐", cost=4, score=25, hits=1),
]
DECK = [
    CardSpec(name="在我发现的世界", cost=4, score=0),
    CardSpec(name="试行错误+", cost=5, score=84),
    CardSpec(name="轻快步伐", cost=4, score=25),
]


def test_empty_hand_returns_none() -> None:
    assert choose_card_via_sim([], turns_left=3, stamina=10, deck=DECK, table=TABLE) is None
    assert estimate_hand([], turns_left=3, stamina=10, table=TABLE) == []


def test_single_card_is_always_chosen() -> None:
    hand = [_card(0, "轻快步伐", cost=4, score=25)]
    assert (
        choose_card_via_sim(hand, turns_left=2, stamina=8, deck=DECK, table=TABLE) == 0
    )


def test_high_score_card_preferred_over_cheaper() -> None:
    """体力只够打一张时，84 分的「试行错误+」必须压过 25 分的「轻快步伐」。"""
    chosen = choose_card_via_sim(
        HAND, turns_left=2, stamina=8, deck=DECK, episodes=4, table=TABLE
    )
    assert chosen == 1
    estimates = estimate_hand(
        HAND, turns_left=2, stamina=8, deck=DECK, episodes=4, table=TABLE
    )
    by_name = {item.name: item for item in estimates}
    assert by_name["试行错误+"].expected > by_name["轻快步伐"].expected
    # 纯 buff 牌自己不产分，但也不该被排除（rollout 里它不拖后腿）
    assert by_name["在我发现的世界"].expected > 0


def test_time_budget_is_anytime_and_keeps_best_so_far() -> None:
    """超预算就返回当前最优：第二轮不再跑，每张牌只跑 1 次但仍有选择结果。"""
    ticks = iter(range(10_000))

    def clock() -> float:
        return next(ticks) * 0.06  # 每次调用 +60ms，远大于 10ms 预算

    estimates = estimate_hand(
        HAND,
        turns_left=2,
        stamina=8,
        deck=DECK,
        episodes=8,
        time_budget_ms=10,
        table=TABLE,
        clock=clock,
    )
    assert estimates, "预算再紧也要有第一轮结果"
    assert all(item.episodes == 1 for item in estimates)
    chosen = choose_card_via_sim(
        HAND,
        turns_left=2,
        stamina=8,
        deck=DECK,
        episodes=8,
        time_budget_ms=10,
        table=TABLE,
        clock=clock,
    )
    assert chosen in {item.index for item in estimates}


def test_exception_returns_none() -> None:
    """坏手牌（模拟器/OCR 一起出问题）必须返回 None，让调用方退回规则。"""
    assert choose_card_via_sim([object()], turns_left=3, stamina=10, deck=DECK) is None


def test_unplayable_cards_return_none() -> None:
    """体力一张都打不起时不乱选。"""
    hand = [_card(0, "没见过的重牌", cost=20, score=42, hits=2)]
    assert choose_card_via_sim(hand, turns_left=2, stamina=5, deck=DECK, table=TABLE) is None


def test_specs_from_hand_uses_table_cost_and_marks_estimated() -> None:
    known = specs_from_hand([_card(0, "试行错误+", cost=7, score=42, hits=2)], table=TABLE)[0]
    assert known.cost == 5  # 费用用卡表真值（屏幕爱心常读歪）
    assert known.spec.score == 84  # 分数用屏幕宝石（含强化）优先
    assert known.estimated is False

    unknown = specs_from_hand([_card(0, "没见过的牌", cost=3, score=30)], table=TABLE)[0]
    assert (unknown.cost, unknown.spec.score) == (3, 30)
    assert unknown.estimated is True  # 卡表查不到 → 期望分只是估计


def test_best_index_ties_by_score_then_index() -> None:
    estimates = [
        CardEstimate(index=2, name="b", cost=4, score=25, expected=10.0, episodes=1),
        CardEstimate(index=0, name="a", cost=4, score=25, expected=10.0, episodes=1),
        CardEstimate(index=1, name="c", cost=4, score=84, expected=10.0, episodes=1),
    ]
    assert best_index(estimates) == 1
    assert best_index([]) is None


def test_audition_kind_scales_expected_by_411_percent() -> None:
    """考试/舞台 rollout 用属性倍率 411%；不传 kind 的课程口径仍是 1.0。"""
    hand = [_card(0, "轻快步伐", cost=0, score=100)]
    lesson = estimate_hand(
        hand, turns_left=1, stamina=4, deck=[], episodes=1, table=TABLE
    )[0]
    audition = estimate_hand(
        hand, turns_left=1, stamina=4, deck=[], episodes=1, table=TABLE, kind="audition"
    )[0]

    assert lesson.expected == 100
    assert audition.expected == 411
    assert audition.expected == pytest.approx(lesson.expected * 4.11)
    # 显式 config 优先：调用方自己写了 1.0 就按课程算，不被 kind 覆盖
    course_config = LessonConfig(turns=1, stamina=4, target_clear=1, attribute_coefficient=1.0)
    forced = estimate_hand(
        hand, turns_left=1, stamina=4, deck=[], config=course_config, episodes=1, table=TABLE,
        kind="audition",
    )[0]
    assert forced.expected == 100
    # 选择链路也接受 kind（单张牌时无论如何都选它）
    assert (
        choose_card_via_sim(
            hand, turns_left=1, stamina=4, deck=[], table=TABLE, kind="audition"
        )
        == 0
    )
