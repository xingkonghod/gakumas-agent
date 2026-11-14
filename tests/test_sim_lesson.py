"""无画面课程模拟器的离线单测：分数公式 / buff / 合法性 / 终止 / 可复现。"""

from __future__ import annotations

import pytest

from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim, greedy_policy


def _index(sim: LessonSim, name: str) -> int:
    """按卡名找当前手牌下标。"""
    for index, card in enumerate(sim.hand):
        if card.name == name:
            return index
    raise AssertionError(f"手牌里没有「{name}」：{[card.name for card in sim.hand]}")


def _config(
    *,
    turns: int = 3,
    stamina: int = 20,
    clear: int = 1,
    perfect: int | None = None,
    hand_size: int = 3,
) -> LessonConfig:
    return LessonConfig(
        turns=turns,
        stamina=stamina,
        target_clear=clear,
        target_perfect=perfect,
        hand_size=hand_size,
    )


def test_same_seed_is_reproducible() -> None:
    """同 seed、同策略：手牌序列、分数、评价都要一模一样。"""

    def play(seed: int) -> tuple[list[tuple[str, ...]], int, str]:
        deck = [
            CardSpec("好调", 1, 0, condition=2),
            CardSpec("集中", 2, 0, focus=2),
            CardSpec("打分A", 3, 9),
            CardSpec("打分B", 2, 6),
            CardSpec("元气", 2, 0, vitality=3),
        ]
        sim = LessonSim(deck, _config(turns=4, stamina=24, clear=30), rng_seed=seed)
        hands: list[tuple[str, ...]] = []
        while not sim.done:
            hands.append(tuple(card.name for card in sim.hand))
            sim.step(greedy_policy(sim))
        return hands, sim.score, sim.result

    first = play(7)
    second = play(7)
    assert first == second


def test_score_card_adds_score_and_spends_stamina() -> None:
    """4 费打分 9：分数 +9、体力 -4。"""
    sim = LessonSim([CardSpec("魅力的基础", 4, 9)], _config(turns=1, stamina=10, clear=9))

    assert sim.legal_actions() == [0, None]
    sim.step(0)

    assert sim.score == 9
    assert sim.stamina == 6
    assert sim.done is True
    assert sim.result == "CLEAR"


def test_condition_multiplies_by_1_5_and_rounds_down() -> None:
    """好调让 9 分牌变成 floor(9 × 1.5) = 13（向下取整）。"""
    sim = LessonSim(
        [CardSpec("好调", 0, 0, condition=2), CardSpec("打分", 4, 9)],
        _config(turns=2, stamina=10),
    )

    sim.step(_index(sim, "好调"))
    assert sim.buffs.condition_turns == 2
    assert sim.score == 0

    sim.step(_index(sim, "打分"))
    assert sim.score == 13
    assert sim.stamina == 6
    # 本回合结束：好调 -1，剩余 1 回合仍可在下一回合生效
    assert sim.buffs.condition_turns == 1


def test_focus_adds_flat_score_to_later_cards_only() -> None:
    """先上集中 +2，后续打分 9 变 11；纯 buff 牌自己不吃集中。"""
    sim = LessonSim(
        [CardSpec("集中", 0, 0, focus=2), CardSpec("打分", 2, 9)],
        _config(turns=2, stamina=10),
    )

    sim.step(_index(sim, "集中"))
    assert sim.score == 0
    assert sim.buffs.focus == 2

    sim.step(_index(sim, "打分"))
    assert sim.score == 11
    assert sim.buffs.focus == 2  # 集中是永久的


def test_unaffordable_card_not_in_legal_actions() -> None:
    """体力 3 时，4 费牌不合法，2 费牌仍合法；硬出会报错。"""
    sim = LessonSim(
        [CardSpec("贵", 4, 9), CardSpec("便宜", 2, 3)],
        _config(turns=3, stamina=3),
    )
    expensive = _index(sim, "贵")
    cheap = _index(sim, "便宜")

    legal = sim.legal_actions()
    assert expensive not in legal
    assert cheap in legal
    assert legal[-1] is None  # SKIP 永远在最后

    with pytest.raises(ValueError, match="体力不足"):
        sim.step(expensive)
    assert sim.score == 0
    assert sim.stamina == 3

    sim.step(cheap)
    assert sim.score == 3
    assert sim.stamina == 1


def test_done_when_turns_run_out() -> None:
    """回合耗尽 → done：0 费 1 分牌，2 回合正好 2 分。"""
    sim = LessonSim(
        [CardSpec("零费", 0, 1)],
        _config(turns=2, stamina=10, clear=2, hand_size=1),
    )
    while not sim.done:
        sim.step(greedy_policy(sim))

    assert sim.turns_left == 0
    assert sim.score == 2
    assert sim.result == "CLEAR"


def test_done_when_stamina_is_insufficient() -> None:
    """体力付不起牌库任何一张牌 → 立刻 done，不再空转回合。"""
    # 开局体力就不够
    sim = LessonSim([CardSpec("贵", 5, 9)], _config(turns=5, stamina=4, clear=20))
    assert sim.done is True
    assert sim.result == "FAILED"
    assert sim.legal_actions() == []

    # 打光体力也会提前结束（回合还剩）
    sim = LessonSim([CardSpec("两费", 2, 5)], _config(turns=3, stamina=2, hand_size=1))
    sim.step(0)
    assert sim.stamina == 0
    assert sim.done is True


def test_result_thresholds() -> None:
    """分数 >= target_perfect → PERFECT；>= target_clear → CLEAR；否则 FAILED。"""
    deck = [CardSpec("打分", 0, 13)]

    perfect = LessonSim(deck, _config(turns=1, stamina=10, clear=10, perfect=13))
    perfect.step(0)
    assert perfect.result == "PERFECT"

    clear = LessonSim(deck, _config(turns=1, stamina=10, clear=10, perfect=None))
    clear.step(0)
    assert clear.result == "CLEAR"

    failed = LessonSim(deck, _config(turns=1, stamina=10, clear=14, perfect=30))
    failed.step(0)
    assert failed.result == "FAILED"


def test_skip_ends_turn_and_settles_impression() -> None:
    """SKIP 结束回合：好印象按层数加分并 -1，好调回合数 -1。"""
    sim = LessonSim(
        [CardSpec("好印象", 0, 0, impression=3), CardSpec("空白", 0, 0)],
        _config(turns=2, stamina=10, hand_size=2),
    )

    sim.step(_index(sim, "好印象"))
    assert sim.buffs.impression == 3
    assert sim.turns_left == 2  # 手牌还有一张，回合没结束

    sim.step(None)  # SKIP
    assert sim.score == 3
    assert sim.buffs.impression == 2
    assert sim.turns_left == 1


def test_draw_effect_draws_extra_card() -> None:
    """出牌后按 draw 抽牌补进手牌，回合不会因为手牌少一张就结束。"""
    deck = [CardSpec(f"抽牌{i}", 0, 1, draw=1) for i in range(3)]
    sim = LessonSim(deck, _config(turns=2, stamina=10, hand_size=2))

    assert len(sim.hand) == 2
    sim.step(0)

    assert sim.score == 1
    assert sim.turns_left == 2  # 没跳过回合
    assert len(sim.hand) == 2  # 打 1 张、抽 1 张
    assert len(sim.hand) + len(sim.deck) + len(sim.discard) == 3


def test_deck_reshuffles_when_exhausted() -> None:
    """每回合摸光 2 张牌，弃牌堆会洗回牌库；每回合 1+2=3 分，共 9 分。"""
    sim = LessonSim(
        [CardSpec("小", 0, 1), CardSpec("大", 0, 2)],
        _config(turns=3, stamina=10, clear=6, hand_size=2),
    )
    score, grade = sim.run(greedy_policy)

    assert (score, grade) == (9, "CLEAR")  # (1 + 2) × 3 回合
    assert sim.turns_left == 0
