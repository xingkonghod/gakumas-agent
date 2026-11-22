"""sim 实时出牌：每张手牌 rollout 后的期望分与选择（policy.json sim_play 的后端）。

真机出牌目前是 LessonPolicy 规则；``choose_card_via_sim`` 用课程模拟器对每张手牌
做「先打这张 + 剩余回合 greedy 打完」的前瞻，比较期望总分。任何异常都必须返回
``None``（调用方退回规则），绝不能让出牌退化。
"""

from __future__ import annotations

import statistics

import pytest

from gkagent.sim.lesson import CardSpec, LessonConfig
from gkagent.sim.play_choice import (
    MAX_APPROX_DECK,
    CardEstimate,
    approx_deck,
    best_index,
    choose_card_via_sim,
    estimate_hand,
    plan_pick,
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

# PIMC 的近似牌库：真实基础牌组里常见的 12 张（数值与 data/knowledge/card_table.json
# 一致）。旧实现把「手牌」直接当牌库，组成和手上 3 张完全相同 → 洗牌序不影响总分，
# K 再大期望也不变。多给 12 张未知抽牌，rollout 才会真的对牌序敏感。
PIMC_DECK = [
    CardSpec("魅力的基础", 4, 9),
    CardSpec("魅力的基础+", 3, 14),
    CardSpec("表现的基础", 0, 0),
    CardSpec("平衡感", 1, 0, focus=2),
    CardSpec("准备运动", 4, 6, focus=2),
    CardSpec("粉丝服务", 2, 10),
    CardSpec("聊天时间", 6, 27),
    CardSpec("凭势而行", 4, 6, focus=3),
    CardSpec("重新开始", 4, 0),
    CardSpec("姿势的基础", 3, 2),
    CardSpec("今天也早安", 4, 7),
    CardSpec("视角的基础", 2, 0),
]
# PIMC 测试共用的局面：3 回合 / 体力 8 / 12 张近似牌库（采样只洗顺序）
PIMC_KW: dict = {
    "turns_left": 3,
    "stamina": 8,
    "deck": PIMC_DECK,
    "table": TABLE,
}


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


def test_specs_from_hand_maps_enthusiasm_effects() -> None:
    """T5② 熱意：卡表 effect → CardSpec 熱意字段（含 buff 回合 / 延長）。"""
    table = FakeTable(
        {
            "火力全开": {
                "cost": 2,
                "effects": [
                    {"type": "ExamPreservation", "values": [1]},
                    {"type": "ExamEnthusiasticMultiple", "values": [1000], "turn": 3},
                ],
            },
            "作为结果的现在": {
                "cost": 0,
                "effects": [{"type": "ExamEnthusiasticTurnAdd", "values": [1]}],
            },
            "新生的光芒": {
                "cost": 4,
                "effects": [
                    {"type": "ExamEnthusiasticAdditive", "values": [5], "turn": -1}
                ],
            },
            "伸手所向之处": {
                "cost": 6,
                "effects": [
                    {"type": "ExamMultipleEnthusiasticLesson", "values": [1, 1000]}
                ],
            },
        }
    )
    specs = {
        name: specs_from_hand([_card(0, name)], table=table)[0].spec
        for name in table.rows
    }
    throttle = specs["火力全开"]
    assert (throttle.enthusiasm_multiple, throttle.enthusiasm_multiple_turns) == (1000, 3)
    assert throttle.preservation == 1
    assert specs["作为结果的现在"].enthusiasm_extension == 1
    fresh = specs["新生的光芒"]
    assert (fresh.enthusiasm_bonus, fresh.enthusiasm_bonus_turns) == (5, -1)
    reach = specs["伸手所向之处"]
    assert (reach.enthusiasm_multiplier, reach.score) == (2000, 1.0)
    # 没有熱意效果的卡保持默认 0（旧行为逐位不变）
    assert specs_from_hand([_card(0, "试行错误+", cost=5, score=42, hits=2)], table=TABLE)[0].spec.enthusiasm_bonus == 0


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


# ---------------------------------------------------------------- PIMC 真搜索


def _best_expected(estimates: list[CardEstimate]) -> float:
    return max(item.expected for item in estimates)


def test_pimc_same_seed_is_reproducible() -> None:
    """同一个 seed + 同样 K：牌序完全复现，期望分/标准差逐位相同。"""
    first = estimate_hand(HAND, episodes=8, seed=3, **PIMC_KW)
    second = estimate_hand(HAND, episodes=8, seed=3, **PIMC_KW)
    assert [(item.index, item.expected, item.stdev, item.episodes) for item in first] == [
        (item.index, item.expected, item.stdev, item.episodes) for item in second
    ]


def test_pimc_different_seed_changes_deck_order() -> None:
    """不同 seed → 不同的未知牌序，rollout 结果必须变（采样确实生效）。"""
    seed_a = estimate_hand(HAND, episodes=4, seed=0, **PIMC_KW)
    seed_b = estimate_hand(HAND, episodes=4, seed=1, **PIMC_KW)
    assert [(item.expected, item.stdev) for item in seed_a] != [
        (item.expected, item.stdev) for item in seed_b
    ]


def test_pimc_k16_expectation_differs_from_k1() -> None:
    """K=1 只是某一种牌序；K=16 平均 16 种牌序，期望分必须不同（K 有边际收益）。

    旧实现固定牌序时两者完全相等（实测都是 193.0），这条测试就是防回归。
    """
    k1 = estimate_hand(HAND, episodes=1, seed=0, **PIMC_KW)
    k16 = estimate_hand(HAND, episodes=16, seed=0, **PIMC_KW)
    assert abs(_best_expected(k16) - _best_expected(k1)) >= 3.0
    # K=1 只有一个样本，样本标准差为 0；K=16 对牌序敏感的牌必须有波动
    assert all(item.stdev == 0 for item in k1)
    assert any(item.stdev > 0 for item in k16)


def test_pimc_more_episodes_reduce_estimator_variance() -> None:
    """更多样本更稳：换 16 个基础 seed 重复决策，K=16 的期望分波动远小于 K=1。

    单次估计的样本标准差 K=1 恒为 0（一个样本），所以「稳不稳」要看**跨 seed
    重复整次决策**的标准差——K 越大，估计器标准差越小、决策越不容易被牌序带偏。
    """
    def best_across_seeds(episodes: int) -> list[float]:
        return [
            _best_expected(estimate_hand(HAND, episodes=episodes, seed=seed, **PIMC_KW))
            for seed in range(16)
        ]

    k1 = best_across_seeds(1)
    k16 = best_across_seeds(16)
    assert statistics.pstdev(k16) < statistics.pstdev(k1) * 0.5


def test_pimc_empty_hand_returns_none() -> None:
    """空手牌：不采样、不选牌，调用方继续用规则。"""
    assert estimate_hand([], episodes=8, seed=0, **PIMC_KW) == []
    assert choose_card_via_sim([], episodes=8, seed=0, **PIMC_KW) is None
    assert plan_pick([], episodes=8, seed=0, **PIMC_KW) == (None, [])


def test_pimc_anytime_budget_keeps_best_so_far() -> None:
    """预算为 0：第一轮仍保证每张牌各 1 次，然后 anytime 返回当前最优。"""
    estimates = estimate_hand(HAND, episodes=32, time_budget_ms=0, seed=0, **PIMC_KW)
    assert estimates
    assert all(item.episodes == 1 for item in estimates)
    chosen = choose_card_via_sim(HAND, episodes=32, time_budget_ms=0, seed=0, **PIMC_KW)
    assert chosen in {item.index for item in estimates}


def test_approx_deck_caps_dedups_and_drops_current_hand() -> None:
    """近似牌库：去重、最多 12 张、当前手牌不再从牌库抽；没外部信息时退回手牌。"""
    hand = [CardSpec("a", 1, 5), CardSpec("b", 2, 6)]
    extra = [CardSpec(f"card{i}", 1, i) for i in range(20)]
    extra.append(CardSpec("a", 1, 999))  # 手牌同名重复不应该再进牌库
    deck = approx_deck(hand, extra)
    assert len(deck) == MAX_APPROX_DECK
    assert {item.name for item in deck}.isdisjoint({"a", "b"})
    assert len({item.name for item in deck}) == len(deck)
    assert [item.name for item in approx_deck(hand)] == ["a", "b"]


def test_pimc_estimate_reports_stdev_and_stable_pick() -> None:
    """候选全在、K 记在结果里、标准差进日志文本；这手牌 12 张近似牌库下选大牌。"""
    estimates = estimate_hand(HAND, episodes=16, seed=0, **PIMC_KW)
    assert [item.index for item in estimates] == [0, 1, 2]
    assert all(item.episodes == 16 for item in estimates)
    best = max(estimates, key=lambda item: item.expected)
    assert best.index == 1  # 试行错误+（84 分）压过轻快步伐（25 分）
    assert "±" in str(best)
    assert "K=16" in str(best)
