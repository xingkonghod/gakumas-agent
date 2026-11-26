"""无画面课程模拟器的离线单测：分数公式 / buff / 合法性 / 终止 / 可复现。"""

from __future__ import annotations

import pytest

from gkagent.sim.lesson import (
    CardSpec,
    DrinkSpec,
    LessonConfig,
    LessonSim,
    greedy_policy,
)


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
    drinks: tuple[DrinkSpec, ...] = (),
    stamina_max: int | None = None,
    attribute_coefficient: float = 1.0, drinks_per_turn: int | None = None,
    # 本文件的机制单测大多要「一回合内连打 3 张」来验证叠加/顺序；真机默认是
    # 每回合 1 张（B3），这里显式给 3 保持旧机制的测试口径不变。
    plays_per_turn: int = 3,
) -> LessonConfig:
    return LessonConfig(
        turns=turns,
        stamina=stamina,
        target_clear=clear,
        target_perfect=perfect,
        hand_size=hand_size,
        drinks=drinks,
        stamina_max=stamina_max,
        attribute_coefficient=attribute_coefficient,
        drinks_per_turn=drinks_per_turn,
        plays_per_turn=plays_per_turn,
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
    sim = LessonSim(
        [CardSpec("魅力的基础", 4, 9)],
        _config(turns=1, stamina=10, clear=9, plays_per_turn=1),
    )

    assert sim.legal_actions() == [0, None]
    sim.step(0)

    assert sim.score == 9
    assert sim.stamina == 6
    assert sim.done is True
    assert sim.result == "CLEAR"


def test_condition_multiplies_by_1_5_and_rounds_up() -> None:
    """好调让 9 分牌变成 ceil(9 × 1.5) = 14（参考引擎 resolveScore 取整口径）。"""
    sim = LessonSim(
        [CardSpec("好调", 0, 0, condition=2), CardSpec("打分", 4, 9)],
        _config(turns=2, stamina=10, plays_per_turn=2),
    )

    sim.step(_index(sim, "好调"))
    assert sim.buffs.condition_turns == 2
    assert sim.score == 0

    sim.step(_index(sim, "打分"))
    assert sim.score == 14
    assert sim.stamina == 6
    # M8：本回合获得的好调 fresh 保护，回合末不扣（引擎 _m8_fresh_cond.py 口径）→ 仍 2。
    assert sim.buffs.condition_turns == 2


def test_audition_multiplier_matches_captured_real_machine_scores() -> None:
    """考试回合属性倍率逐分对齐真机回放捕获值（gakumas-tools fidelity，BSD-3）。

    【試験研修1】好調（250% 回合）：
    - アピールの基本（基础 9 分）无好调：ceil(9 × 2.5) = **23**；
    - 同上 + 好调：ceil(ceil(9 × 1.5) × 2.5) = ceil(14 × 2.5) = **35**；
    - 愛嬌（基础 13 分）+ 好调：ceil(ceil(13 × 1.5) × 2.5) = ceil(20 × 2.5) = **50**。
    【試験研修2】集中（250% 回合）：情熱ターン（基础 11 分）集中 0/3/6 →
    **28**（ceil 27.5）/ **35** / **43**（ceil 42.5）。
    """

    def award(base: int, *, condition_turns: int = 0, focus: int = 0) -> int:
        sim = LessonSim(
            [CardSpec("占位", 0, 0)],
            _config(turns=1, stamina=20, attribute_coefficient=2.5, plays_per_turn=1),
        )
        sim.hand = [CardSpec("实机回放卡", 0, base)]
        sim.deck = []
        sim.discard = []
        sim.buffs.condition_turns = condition_turns
        sim.buffs.focus = focus
        sim.step(0)
        return sim.score

    assert award(9) == 23
    assert award(9, condition_turns=1) == 35
    assert award(13, condition_turns=1) == 50
    assert award(11, focus=0) == 28
    assert award(11, focus=3) == 35
    assert award(11, focus=6) == 43


def test_course_scores_match_captured_real_machine_golden_values() -> None:
    """课程实机回放黄金值（gakumas-tools fidelity 捕获，回合倍率 1.0）。

    【基礎1】好調：ファンサ 10 → **15**、アドリブ 5 → **8**（ceil 7.5）、
    ポーズの基本 2 → **3**。
    【基礎9】温存 1 段階：9 → **5**、2 → **1**、15 → **8**（都是 ceil 半倍）。
    """

    def award(
        base: int, *, condition_turns: int = 0, preservation: bool = False
    ) -> int:
        sim = LessonSim(
            [CardSpec("占位", 0, 0)],
            _config(turns=1, stamina=20, plays_per_turn=1),
        )
        sim.hand = [CardSpec("实机回放卡", 0, base)]
        sim.deck = []
        sim.discard = []
        sim.buffs.condition_turns = condition_turns
        if preservation:
            sim.stance.stance = "save"
            sim.stance.save_level = 1
        sim.step(0)
        return sim.score

    assert award(10, condition_turns=1) == 15
    assert award(5, condition_turns=1) == 8
    assert award(2, condition_turns=1) == 3
    assert award(9, preservation=True) == 5
    assert award(2, preservation=True) == 1
    assert award(15, preservation=True) == 8


def test_lesson_default_attribute_coefficient_is_one() -> None:
    """课程默认倍率 1.0：同样的牌 ceil((37+10)×1.5)=71，不吃考试倍率。"""
    assert (
        LessonConfig(turns=1, stamina=10, target_clear=1).attribute_coefficient == 1.0
    )
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=1, stamina=10, plays_per_turn=1),
    )
    sim.hand = [CardSpec("37分牌", 0, 37)]
    sim.deck = []
    sim.discard = []
    sim.buffs.focus = 10
    sim.buffs.condition_turns = 2

    sim.step(0)

    assert sim.score == 71


def test_explicit_coefficient_one_matches_course_default() -> None:
    """显式 ``attribute_coefficient=1.0`` 与默认完全一致：课程分数不受新字段影响。"""
    deck = [CardSpec(f"牌{i}", 0, i + 1, draw=1) for i in range(5)]

    def play(config: LessonConfig) -> tuple[int, list[dict]]:
        sim = LessonSim(deck, config, rng_seed=5)
        score, _grade = sim.run(greedy_policy)
        return score, [dict(row) for row in sim.trace]

    assert play(_config(turns=3, stamina=10)) == play(
        _config(turns=3, stamina=10, attribute_coefficient=1.0)
    )


def test_dependent_scores_ignore_attribute_coefficient() -> None:
    """好印象/元气依赖分不吃考试属性倍率（保持保守口径）。"""
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, hand_size=2, attribute_coefficient=4.11),
    )
    sim.hand = [
        CardSpec("依赖", 0, 0, impression_scale=1000, block_scale=1000),
        CardSpec("占位二", 0, 0),
    ]
    sim.deck = []
    sim.discard = []
    sim.buffs.impression = 3
    sim.vitality = 4

    sim.step(0)

    # 30（好印象）+ 40（元气）；若误乘 4.11 会变成 287
    assert sim.score == 70


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


def test_strong_level_switches_stance_and_multiplies_later_cards() -> None:
    """ExamConcentration 解析出的 strong_level 切到強気：本牌不吃自己刚切的倍率。"""
    level1 = LessonSim(
        [CardSpec("强气变更", 0, 0, strong_level=1), CardSpec("打分", 2, 10)],
        _config(turns=2, stamina=10),
    )
    level1.step(_index(level1, "强气变更"))
    assert level1.stance.stance == "strong1"
    assert level1.score == 0  # 纯指針牌自己没分
    level1.step(_index(level1, "打分"))
    assert level1.score == 20  # 10 × 2.0

    level2 = LessonSim(
        [CardSpec("强气2段階", 0, 0, strong_level=2), CardSpec("打分", 2, 10)],
        _config(turns=2, stamina=10),
    )
    level2.step(_index(level2, "强气2段階"))
    level2.step(_index(level2, "打分"))
    assert level2.score == 25  # 10 × 2.5


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
    # M8：本回合获得的好印象 fresh 保护，回合末不扣（引擎 probe5 A 口径）→ 仍 3。
    assert sim.buffs.impression == 3
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


def test_exam_card_draw_draws_exact_count() -> None:
    """ExamCardDraw N：出牌后手牌正好 +N，牌库相应减少，打出的牌进弃牌堆。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=1))
    sim.hand = [CardSpec("抽三", 0, 0, draw=3)]
    sim.deck = [CardSpec(f"牌库{i}", 0, 1) for i in range(4)]
    sim.discard = []

    sim.step(0)

    assert len(sim.hand) == 3
    assert len(sim.deck) == 1
    assert len(sim.discard) == 1  # 刚打出的「抽三」
    assert sim.turns_left == 2    # 还有手牌，回合没结束


def test_exam_card_draw_refills_from_discard_when_deck_empty() -> None:
    """牌库抽空时把弃牌堆洗回牌库再继续抽。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=1))
    sim.hand = [CardSpec("抽二", 0, 0, draw=2)]
    sim.deck = []
    sim.discard = [CardSpec("弃一", 0, 1), CardSpec("弃二", 0, 1), CardSpec("弃三", 0, 1)]

    sim.step(0)

    assert len(sim.hand) == 2
    assert all(card.name.startswith("弃") for card in sim.hand)
    assert sim.deck  # 3 张弃牌抽 2 张，洗回后还剩 1 张
    assert len(sim.hand) + len(sim.deck) + len(sim.discard) == 4  # 3 弃牌 + 1 新弃牌


def test_exam_review_scores_at_turn_end_then_decays() -> None:
    """好印象回合末按层数加分；M8 fresh 保护：获得当回合末不扣，下一回合末才 -1。

    3 层 t1 获得：end1 +3（fresh 存活 3）/ end2 +3（旧层 3→2）→ 累计 6。
    """
    sim = LessonSim(
        [CardSpec("好印象", 0, 0, impression=3), CardSpec("空白", 0, 0)],
        _config(turns=3, stamina=10, hand_size=2),
    )

    sim.step(_index(sim, "好印象"))
    assert sim.score == 0                  # 出牌本身不加分
    assert sim.buffs.impression == 3

    sim.step(None)                         # 回合结束：+3，fresh 保护层数仍 3
    assert sim.score == 3
    assert sim.buffs.impression == 3

    sim.step(None)                         # 再一回合结束：+3，旧层 3 → 2
    assert sim.score == 6
    assert sim.buffs.impression == 2


def test_exam_review_stops_scoring_at_zero() -> None:
    """好印象减到 0 后不再加分，也不会变成负数。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=3, stamina=10, hand_size=0))
    sim.buffs.impression = 1

    sim.step(None)
    assert sim.score == 1
    assert sim.buffs.impression == 0

    sim.step(None)
    assert sim.score == 1
    assert sim.buffs.impression == 0


def test_depend_exam_review_scores_by_impression_layers() -> None:
    """5 层 × 1000%（每层 10 分）→ 50 分；卡面本身不加层。"""
    sim = LessonSim(
        [CardSpec("200%微笑", 0, 0, impression_scale=1000), CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, hand_size=2),
    )
    sim.buffs.impression = 5

    sim.step(_index(sim, "200%微笑"))

    assert sim.score == 50
    assert sim.buffs.impression == 5
    assert sim.turns_left == 2


def test_depend_exam_review_zero_impression_scores_nothing() -> None:
    """好印象为 0 时依赖分固定 0（即使倍率很高）。"""
    sim = LessonSim(
        [CardSpec("POW", 0, 0, impression_scale=2500), CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, hand_size=2),
    )

    assert sim.buffs.impression == 0
    sim.step(_index(sim, "POW"))

    assert sim.score == 0
    assert sim.buffs.impression == 0


def test_depend_exam_review_formula_truncates() -> None:
    """公式 int(层数 × 倍率 / 100)：6 层 × 1700% = int(102.0) = 102。"""
    sim = LessonSim(
        [CardSpec("POW+", 0, 0, impression_scale=1700), CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, hand_size=2),
    )
    sim.buffs.impression = 6

    sim.step(_index(sim, "POW+"))

    assert sim.score == 102


def test_depend_exam_review_adds_to_base_and_ignores_focus_condition() -> None:
    """依赖分与卡面白值相加；白值部分吃集中/好调，依赖部分按公式单独算。"""
    sim = LessonSim(
        [CardSpec("混合", 2, 9, impression_scale=1000), CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, hand_size=2),
    )
    sim.buffs.impression = 3
    sim.buffs.focus = 2
    sim.buffs.condition_turns = 2

    sim.step(_index(sim, "混合"))

    # 白值 ceil((9 + 2) × 1.5) = 17；依赖 3 层 × 1000% = 30
    assert sim.score == 47


def test_depend_scores_before_own_impression_buff() -> None:
    """保守顺序：本牌自带的 impression 在依赖分之后结算，所以首出 0 分、层数 +5。"""
    sim = LessonSim(
        [CardSpec("200%微笑", 0, 0, impression=5, impression_scale=1000), CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, hand_size=2),
    )

    sim.step(_index(sim, "200%微笑"))

    assert sim.score == 0
    assert sim.buffs.impression == 5


def test_preservation_card_halves_later_scores() -> None:
    """温存 1 段階：先打温存，后续 9 分牌变成 ceil(9 × 0.5) = 5（实机回放值同）。"""
    sim = LessonSim(
        [CardSpec("温存", 0, 0, preservation=1), CardSpec("打分", 2, 9)],
        _config(turns=2, stamina=10, hand_size=2),
    )

    sim.step(_index(sim, "温存"))
    assert sim.score == 0
    assert sim.stance.stance == "save"
    assert sim.stance.save_level == 1

    sim.step(_index(sim, "打分"))
    assert sim.score == 5


def test_full_power_point_triggers_triple_next_turn() -> None:
    """全力值 5+5 攒满 → 回合结束进入「全力」，下一回合打分 ×3。"""
    sim = LessonSim([CardSpec("垫", 0, 0)], _config(turns=3, stamina=10, hand_size=1))
    sim.hand = [CardSpec("全力一", 0, 0, full_power_point=5), CardSpec("占位", 0, 0)]
    sim.deck = [CardSpec("打分", 2, 9), CardSpec("全力二", 0, 0, full_power_point=5)]
    sim.discard = []

    sim.step(0)  # 全力一：+5，手牌还剩占位
    assert sim.stance.full_power_point == 5
    sim.step(0)  # 占位：手牌打空 → 回合结束，5 点不够全力，抽到全力二
    assert sim.stance.stance == "normal"
    assert [card.name for card in sim.hand] == ["全力二"]

    sim.step(0)  # 全力二：+5 = 10 → 回合结束进入全力，抽到打分
    assert sim.stance.stance == "full"
    assert sim.stance.full_power_point == 0
    assert [card.name for card in sim.hand] == ["打分"]

    sim.step(0)  # 全力回合：floor(9 × 3.0) = 27
    assert sim.score == 27


def test_card_does_not_benefit_from_its_own_stance_switch() -> None:
    """9 分 + 温存：本牌先按无指針拿满 9 分，之后才切到温存 0.5×。"""
    sim = LessonSim(
        [CardSpec("温存斩", 2, 9, preservation=1), CardSpec("追击", 2, 9)],
        _config(turns=2, stamina=10, hand_size=2),
    )

    sim.step(_index(sim, "温存斩"))
    assert sim.score == 9  # 不是 ceil(9 × 0.5)
    assert sim.stance.save_level == 1

    sim.step(_index(sim, "追击"))
    assert sim.score == 14  # 9 + ceil(9 × 0.5)


def test_greedy_policy_prioritizes_stance_cards() -> None:
    """温存/全力值牌 score=0，也要被基线策略选中，否则指針永远不会被切换。"""
    sim = LessonSim([CardSpec("垫", 0, 0)], _config(turns=2, stamina=10, hand_size=2))
    sim.hand = [CardSpec("温存", 0, 0, preservation=1), CardSpec("小分", 2, 2)]
    sim.deck = []
    sim.discard = []
    assert greedy_policy(sim) == 0

    full_power = LessonSim([CardSpec("垫", 0, 0)], _config(turns=2, stamina=10, hand_size=2))
    full_power.hand = [CardSpec("全力牌", 0, 0, full_power_point=5), CardSpec("小分", 2, 2)]
    full_power.deck = []
    full_power.discard = []
    assert greedy_policy(full_power) == 0


def test_depend_exam_review_score_ignores_stance_multiplier() -> None:
    """好印象依赖分保持保守口径不吃指針倍率：温存下 3 层 × 1000% 仍是 30。"""
    sim = LessonSim(
        [
            CardSpec("温存", 0, 0, preservation=1),
            CardSpec("依赖", 0, 0, impression_scale=1000),
            CardSpec("占位", 0, 0),
        ],
        _config(turns=2, stamina=10, hand_size=3),
    )
    sim.buffs.impression = 3

    sim.step(_index(sim, "温存"))
    sim.step(_index(sim, "依赖"))

    assert sim.score == 30


# --------------------------------------------------------------------- 可出牌次数
# 真机规则（B3）：每回合基础 1 张；ExamPlayableValueAdd 追加次数，追加的牌打完后
# **自动结束回合**（参考引擎 CardManager.useCard 末尾 cardUsesRemaining<1 → endTurn）。
def test_extra_play_card_allows_one_more_play_this_turn() -> None:
    """基础 1 张 + 卡效果 +1：本回合能出 2 张，第 2 张打完自动结束回合。"""
    sim = LessonSim(
        [CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, plays_per_turn=1)
    )
    sim.hand = [
        CardSpec("次数+1", 0, 0, extra_play=1),
        CardSpec("打1", 0, 1),
        CardSpec("打2", 0, 1),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)  # 次数+1：本牌占 1 次，同时追加 1 次
    assert sim.plays_this_turn == 1
    assert sim.extra_plays == 1
    assert sim.turns_left == 2  # 追加次数还没用完，回合没结束

    sim.step(0)  # 用掉追加的第 2 次 → 次数用尽，自动结束回合
    assert sim.score == 1
    assert sim.turns_left == 1
    assert sim.plays_this_turn == 0  # 新回合重置
    assert sim.extra_plays == 0


def test_card_without_extra_play_ends_turn_after_one_card() -> None:
    """extra_play=0 的牌不追加次数：手牌再多，本回合出 1 张就自动结束。"""
    assert CardSpec("普通", 0, 1).extra_play == 0

    sim = LessonSim(
        [CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, plays_per_turn=1)
    )
    sim.hand = [CardSpec(f"打{i}", 0, 1) for i in range(4)]
    sim.deck = [CardSpec("牌库", 0, 1)]
    sim.discard = []

    sim.step(0)

    assert sim.extra_plays == 0
    assert sim.score == 1
    assert sim.turns_left == 1  # 打 1 张就换回合
    assert sim.plays_this_turn == 0
    assert len(sim.hand) == 3  # 新回合重新摸满


def test_extra_play_cards_stack() -> None:
    """两张 +1 次数牌叠加：基础 1 张 +2 = 本回合可出 3 张，第 3 张后自动结束。"""
    sim = LessonSim(
        [CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, plays_per_turn=1)
    )
    sim.hand = [
        CardSpec("次数+1a", 0, 0, extra_play=1),
        CardSpec("次数+1b", 0, 0, extra_play=1),
        CardSpec("打1", 0, 1),
        CardSpec("打2", 0, 1),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)
    sim.step(0)
    assert sim.extra_plays == 2
    assert sim.turns_left == 2

    sim.step(0)  # 用掉最后一次（基础 1 + 追加 2）
    assert sim.score == 1
    assert sim.turns_left == 1
    assert sim.plays_this_turn == 0
    assert sim.extra_plays == 0


def test_extra_plays_reset_at_turn_start() -> None:
    """额外次数只在当回合有效：SKIP 换手牌后 plays_this_turn / extra_plays 归零。"""
    sim = LessonSim(
        [CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, plays_per_turn=1)
    )
    sim.hand = [
        CardSpec("次数+1", 0, 0, extra_play=1),
        CardSpec("打", 0, 1),
        CardSpec("占位二", 0, 0),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)  # 次数+1：基础 1 次用掉，追加 1 次还在
    assert sim.extra_plays == 1
    assert sim.turns_left == 2

    sim.step(None)  # SKIP：追加次数不用了，结束本回合

    assert sim.turns_left == 1
    assert sim.plays_this_turn == 0
    assert sim.extra_plays == 0


def test_greedy_policy_prioritizes_extra_play_cards() -> None:
    """score=0 的加次数牌也要被基线策略选中，否则策略永远吃不到额外出牌。"""
    sim = LessonSim([CardSpec("垫", 0, 0)], _config(turns=2, stamina=10, hand_size=2))
    sim.hand = [CardSpec("次数+1", 0, 0, extra_play=1), CardSpec("小分", 2, 2)]
    sim.deck = []
    sim.discard = []

    assert greedy_policy(sim) == 0


# ------------------------------------------------------------- 元气依赖分 / 审查基准加成
def _block_award(layers: int, scale: int = 1000) -> int:
    """在指定元气层数下打一张纯依赖分牌，只返回这张牌拿到的分。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=1))
    sim.hand = [CardSpec("依赖元气", 0, 0, block_scale=scale)]
    sim.deck = []
    sim.discard = []
    sim.vitality = layers
    sim.step(0)
    return sim.score


def test_depend_block_scores_linearly_by_vitality_layers() -> None:
    """元气依赖分与层数线性：每层 ×10 分（1000‰），1/3/6 层 → 10/30/60。"""
    assert [_block_award(1), _block_award(3), _block_award(6)] == [10, 30, 60]


def test_depend_block_zero_vitality_scores_nothing() -> None:
    """元气为 0 层时依赖分固定 0，即使倍率很高。"""
    assert _block_award(0, scale=2500) == 0


def test_depend_block_formula_truncates_and_ignores_buffs() -> None:
    """int(层数 × 倍率 / 100) 逐段取整；依赖分不吃好调/集中/指針倍率。"""
    sim = LessonSim(
        [
            CardSpec("温存", 0, 0, preservation=1),
            CardSpec("混合", 2, 9, block_scale=700),
            CardSpec("占位", 0, 0),
        ],
        _config(turns=2, stamina=10, hand_size=3),
    )
    sim.vitality = 3
    sim.buffs.focus = 2
    sim.buffs.condition_turns = 2

    sim.step(_index(sim, "温存"))
    sim.step(_index(sim, "混合"))

    # 白值 ceil((9 + 2) × 1.5 × 0.5) = 9；依赖分 int(3 × 700 / 100) = 21（不吃倍率）
    assert sim.score == 30


def test_parameter_buff_multiplies_final_score() -> None:
    """1500‰ = ×1.5：10 分牌变 floor(10 × 1.5) = 15；1000‰ 保持原分。"""
    buffed = LessonSim(
        [CardSpec("加成", 0, 10, parameter_buff=1500)],
        _config(turns=1, stamina=10, clear=15),
    )
    buffed.step(0)
    assert buffed.score == 15
    assert buffed.result == "CLEAR"

    neutral = LessonSim(
        [CardSpec("无加成", 0, 10, parameter_buff=1000)],
        _config(turns=1, stamina=10),
    )
    neutral.step(0)
    assert neutral.score == 10


def test_parameter_buff_multiple_per_turn_affects_later_cards() -> None:
    """MultiplePerTurn 在本回合内持续：后续两张牌都吃 ×1.5。"""
    sim = LessonSim([CardSpec("垫", 0, 0)], _config(turns=2, stamina=10, hand_size=3))
    sim.hand = [
        CardSpec("审查加成", 0, 0, parameter_buff=1500, parameter_buff_turns=2),
        CardSpec("打1", 0, 10),
        CardSpec("打2", 0, 10),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)  # 纯加成牌自身 0 分，但把 1500‰ 记进本回合
    assert sim.score == 0
    assert sim.turn_parameter_buff == 1500

    sim.step(0)  # 10 × 1.5 = 15
    assert sim.score == 15
    sim.step(0)  # 后续牌继续吃：15 + 15 = 30
    assert sim.score == 30


def test_parameter_buff_turn_state_resets_at_turn_end() -> None:
    """回合结束清零 ``turn_parameter_buff``，下一回合的牌不再吃旧加成。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=2))
    sim.hand = [
        CardSpec("审查加成", 0, 0, parameter_buff=1500, parameter_buff_turns=2),
        CardSpec("垫", 0, 0),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)
    assert sim.turn_parameter_buff == 1500

    sim.step(None)  # SKIP 结束回合
    assert sim.turn_parameter_buff == 0

    sim.hand = [CardSpec("新打", 0, 10)]
    sim.step(0)
    assert sim.score == 10  # 不是 floor(10 × 1.5)


def test_greedy_policy_prioritizes_dependent_cards() -> None:
    """score=0 的元气依赖牌/审查加成牌也要被基线策略选中。"""
    block = LessonSim([CardSpec("垫", 0, 0)], _config(turns=2, stamina=10, hand_size=2))
    block.hand = [CardSpec("依赖元气", 0, 0, block_scale=1000), CardSpec("小分", 2, 2)]
    block.deck = []
    block.discard = []
    assert greedy_policy(block) == 0

    buff = LessonSim([CardSpec("垫", 0, 0)], _config(turns=2, stamina=10, hand_size=2))
    buff.hand = [CardSpec("审查加成", 0, 0, parameter_buff=1500), CardSpec("小分", 2, 2)]
    buff.deck = []
    buff.discard = []
    assert greedy_policy(buff) == 0


# ---------------------------------------------------------------- 3 张手牌 / SKIP
def test_default_hand_size_is_three_and_refills_each_turn() -> None:
    """默认每回合 3 张（真机手牌数）：第一回合 3 张，SKIP 后补满 3 张且不重复。"""
    assert LessonConfig(turns=2, stamina=10, target_clear=1).hand_size == 3

    deck = [CardSpec(f"牌{i}", 0, 0) for i in range(6)]
    sim = LessonSim(deck, _config(turns=2, stamina=10, clear=1))
    first = [card.name for card in sim.hand]
    assert len(first) == 3
    assert len(set(first)) == 3

    sim.step(None)
    second = [card.name for card in sim.hand]
    assert len(second) == 3
    assert set(first).isdisjoint(second)
    assert len(sim.hand) + len(sim.deck) + len(sim.discard) == 6


def test_three_card_hand_reshuffles_discard_when_deck_empty() -> None:
    """3 张手牌 + 只剩 1 张牌库：换手牌时把弃牌堆洗回牌库，正好补满 3 张。"""
    deck = [CardSpec(f"牌{i}", 0, 0) for i in range(4)]
    sim = LessonSim(deck, _config(turns=3, stamina=10, clear=1))
    assert len(sim.hand) == 3
    assert len(sim.deck) == 1

    sim.step(None)  # 弃 3 张 → 摸掉牌库 1 张 → 洗回弃牌堆再摸 2 张

    assert len(sim.hand) == 3
    assert len(sim.deck) == 1
    assert len(sim.discard) == 0
    assert len(sim.hand) + len(sim.deck) + len(sim.discard) == 4


def test_skip_discards_hand_and_recovers_two_stamina_with_trace() -> None:
    """SKIP：剩余手牌进弃牌堆；回合末出牌次数没用完 → 体力 +2（真机规则），trace 记 skipped=True。"""
    deck = [CardSpec(f"牌{i}", 0, 0) for i in range(6)]
    sim = LessonSim(deck, _config(turns=2, stamina=10))
    first = [card.name for card in sim.hand]
    sim.stamina = 7  # 模拟已经打掉 3 点体力

    sim.step(None)

    # 参考引擎 TurnManager.endTurn：cardUsesRemaining > 0 时体力 +2（封顶 stamina_max）
    assert sim.stamina == 9
    assert len(sim.hand) == 3
    assert set(first).isdisjoint(card.name for card in sim.hand)
    assert sim.trace[-1]["skipped"] is True
    assert sim.trace[-1]["turns_left"] == 2
    assert sim.turns_left == 1


def test_hand_exhaustion_auto_ends_turn_without_skip_flag() -> None:
    """手牌打空是自然结束回合，不是 SKIP：trace 记 `skipped=False`。"""
    sim = LessonSim([CardSpec("零费", 0, 1)], _config(turns=2, stamina=10, hand_size=1))

    sim.step(0)

    assert sim.trace[-1]["skipped"] is False
    assert sim.trace[-1]["plays"] == 1
    assert sim.turns_left == 1


# ------------------------------------------------------------------- 元气挡体力
def test_vitality_absorbs_card_cost_before_stamina() -> None:
    """出牌先扣元气、再扣体力：4 费牌在 3 体力 + 5 元气下把元气扣到 1。"""
    sim = LessonSim(
        [CardSpec("占位", 0, 0)], _config(turns=2, stamina=3, plays_per_turn=2)
    )
    sim.hand = [CardSpec("四费", 4, 9), CardSpec("二费", 2, 5)]
    sim.deck = []
    sim.discard = []
    sim.vitality = 5

    assert 0 in sim.legal_actions()  # 3 体力 + 5 元气 >= 4
    sim.step(0)
    assert (sim.score, sim.stamina, sim.vitality) == (9, 3, 1)

    sim.step(0)  # 2 费：1 元气 + 1 体力
    assert (sim.score, sim.stamina, sim.vitality) == (14, 2, 0)


def test_vitality_pays_card_cost_when_stamina_is_zero() -> None:
    """体力 0 但元气足够时牌仍合法，且完全不动体力。"""
    sim = LessonSim([CardSpec("两费", 2, 5)], _config(turns=1, stamina=2))
    assert sim.done is False
    sim.stamina = 0
    sim.vitality = 3

    assert sim.done is False  # 元气还能付牌费
    assert sim.legal_actions() == [0, None]
    sim.step(0)

    assert sim.score == 5
    assert sim.stamina == 0
    assert sim.vitality == 1


# ----------------------------------------------------------------------- 饮料
def test_drink_restores_stamina_up_to_max() -> None:
    """体力饮料回复体力、不超过 stamina_max；每回合限 1 瓶但下一回合可再喝。"""
    drinks = (DrinkSpec("恢复饮料", 0, "stamina", 6, uses=2),)
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=3, stamina=10, drinks=drinks, stamina_max=12),
    )
    sim.stamina = 5

    sim.use_drink(0)
    assert sim.stamina == 11
    sim.step(None)  # 换回合：SKIP 会回 2 体力（真机规则）→ 封顶 12

    assert sim.stamina == 12
    sim.use_drink(0)
    assert sim.stamina == 12  # 封顶，不是 17


def test_drink_adds_focus_to_later_cards() -> None:
    """集中饮料 +3：本回合后续 9 分牌变 12。"""
    drinks = (DrinkSpec("冰咖啡", 0, "focus", 3),)
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, drinks=drinks))
    sim.hand = [CardSpec("打分", 0, 9), CardSpec("占位", 0, 0)]
    sim.deck = []
    sim.discard = []

    sim.use_drink(0)
    assert sim.buffs.focus == 3
    sim.step(0)
    assert sim.score == 12


def test_drink_condition_and_score_effects() -> None:
    """好调饮料 +3 回合让 10 分牌 ×1.5；分数饮料直接加分、不吃倍率。"""
    condition_sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, drinks=(DrinkSpec("维生素饮料", 0, "condition", 3),)),
    )
    condition_sim.hand = [CardSpec("打分", 0, 10), CardSpec("占位", 0, 0)]
    condition_sim.deck = []
    condition_sim.discard = []
    condition_sim.use_drink(0)
    assert condition_sim.buffs.condition_turns == 3
    condition_sim.step(0)
    assert condition_sim.score == 15

    score_sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, drinks=(DrinkSpec("初星水", 0, "score", 10),)),
    )
    score_sim.use_drink(0)
    assert score_sim.score == 10


def test_drinks_have_no_per_turn_limit_by_default() -> None:
    """真机饮料没有"每回合 1 瓶"限制（用户确认）：同一回合可连喝，只受库存 uses 约束。"""
    drinks = (DrinkSpec("A", 0, "focus", 1), DrinkSpec("B", 0, "focus", 1))
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=3, stamina=10, drinks=drinks))

    assert sim.legal_drinks() == [0, 1]
    sim.use_drink(0)
    assert sim.legal_drinks() == [1]  # A 库存用完；B 仍可同回合喝
    sim.use_drink(1)
    assert sim.legal_drinks() == []
    assert sim.drink_uses == [0, 0]
    assert sim.buffs.focus == 2
    with pytest.raises(ValueError, match="用完"):
        sim.use_drink(0)


def test_drinks_per_turn_cap_is_optional() -> None:
    """显式配置 drinks_per_turn 时才限制每回合瓶数。"""
    drinks = (DrinkSpec("A", 0, "focus", 1), DrinkSpec("B", 0, "focus", 1))
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=3, stamina=10, drinks=drinks, drinks_per_turn=1))

    sim.use_drink(0)
    assert sim.legal_drinks() == []
    with pytest.raises(ValueError, match="最多 1 瓶"):
        sim.use_drink(1)
    sim.step(None)
    assert sim.legal_drinks() == [1]

def test_drink_cost_is_paid_before_effect() -> None:
    """带体力消耗的饮料先扣 cost 再结算效果（真机饮料 cost=0，字段留给自定义）。"""
    drinks = (DrinkSpec("付费饮料", 2, "stamina", 5),)
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=2, stamina=10, drinks=drinks, stamina_max=20),
    )

    sim.use_drink(0)

    assert sim.stamina == 13  # 10 - 2 + 5


def test_unknown_drink_effect_is_rejected() -> None:
    """未建模的饮料效果直接报错，不能静默变成无效饮料。"""
    with pytest.raises(ValueError, match="未建模"):
        DrinkSpec("乌龙茶", 0, "vitality", 7)


def test_same_seed_reproducible_with_three_cards_and_drinks() -> None:
    """3 张手牌 + 饮料 + SKIP：同 seed 的手牌序列、饮料序列、分数、trace 全一致。"""

    def play(seed: int) -> tuple[list, list, int, list]:
        deck = [
            CardSpec("打分A", 2, 9),
            CardSpec("打分B", 3, 12),
            CardSpec("集中", 0, 0, focus=2),
            CardSpec("元气", 1, 0, vitality=4),
            CardSpec("好调", 0, 0, condition=2),
            CardSpec("抽牌", 0, 3, draw=1),
            CardSpec("大牌", 4, 20),
        ]
        drinks = (DrinkSpec("咖啡", 0, "focus", 2), DrinkSpec("水", 0, "stamina", 5, uses=2))
        sim = LessonSim(
            deck,
            _config(turns=4, stamina=16, clear=20, drinks=drinks),
            rng_seed=seed,
        )
        hands: list[tuple[str, ...]] = []
        drunk: list[int] = []
        while not sim.done:
            hands.append(tuple(card.name for card in sim.hand))
            legal = sim.legal_drinks()
            if legal:
                sim.use_drink(legal[0])
                drunk.append(legal[0])
            sim.step(greedy_policy(sim))
        return hands, drunk, sim.score, [dict(row) for row in sim.trace]

    assert play(11) == play(11)

def test_greedy_prefers_buff_in_early_turns() -> None:
    """用户打法：前几个回合先铺层数类 buff，再打分数。"""
    deck = [
        CardSpec("集中", 2, 0, focus=3),
        CardSpec("打分", 2, 25),
        CardSpec("打分B", 2, 25),
    ]
    sim = LessonSim(deck, _config(turns=5, stamina=20, clear=1), rng_seed=3)
    assert greedy_policy(sim) == _index(sim, "集中")


def test_greedy_takes_score_on_last_turn() -> None:
    """最后一回合铺 buff 没收益，必须打分数牌。"""
    deck = [CardSpec("集中", 2, 0, focus=3), CardSpec("打分", 2, 25)]
    sim = LessonSim(deck, _config(turns=1, stamina=10, clear=1), rng_seed=1)
    assert greedy_policy(sim) == _index(sim, "打分")


# ------------------------------------------- 2026-11-16 新卡池：精确建模的 8 种效果
def test_stamina_recover_fix_heals_after_cost_and_caps_at_max() -> None:
    """ExamStaminaRecoverFix：付完牌费后固定回体力，封顶 stamina_max。"""
    sim = LessonSim(
        [CardSpec("回复", 4, 5, stamina_recover=8)],
        _config(turns=2, stamina=5, stamina_max=12, plays_per_turn=1),
    )
    sim.step(0)

    assert (sim.score, sim.stamina) == (5, 9)  # 5 - 4 + 8
    assert sim.done is False  # 回复后还付得起 4 费牌，不提前结束

    capped = LessonSim(
        [CardSpec("回复大", 0, 1, stamina_recover=6)],
        _config(turns=1, stamina=10, stamina_max=12),
    )
    capped.step(0)
    assert capped.stamina == 12  # 10 + 6 封顶 12，不是 16


def test_lesson_full_power_point_adds_scaled_score_before_own_gain() -> None:
    """ExamLessonFullPowerPoint：按出牌前全力值 × 千分比/1000 加进本牌得分。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=1))
    sim.hand = [CardSpec("全力斩", 2, 10, full_power_scale=2000, full_power_point=5)]
    sim.deck = []
    sim.discard = []
    sim.stance.full_power_point = 4

    sim.step(0)

    # 白值 10 + int(4 × 2000 / 1000) = 18；本牌自带的 +5 在算分之后才生效
    assert sim.score == 18
    assert sim.stance.full_power_point == 9

    no_power = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=1))
    no_power.hand = [CardSpec("全力斩", 0, 10, full_power_scale=2000)]
    no_power.deck = []
    no_power.discard = []
    no_power.step(0)
    assert no_power.score == 10  # 全力值 0 时折算分固定 0


def test_status_enchant_encore_doubles_direct_effects() -> None:
    """ExamStatusEnchantEncore：本牌直接效果执行两次（打分/抽牌/集中…），牌费一次。"""
    sim = LessonSim(
        [CardSpec("再演", 2, 10, draw=1, focus=2, encore=True)],
        _config(turns=2, stamina=10, hand_size=1, plays_per_turn=1),
    )
    sim.step(0)

    assert sim.score == 20  # 10 × 2
    assert sim.buffs.focus == 4  # 2 × 2
    assert sim.stamina == 8  # 2 费只付一次

    draw = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=1))
    draw.hand = [CardSpec("再演抽", 0, 0, draw=1, encore=True)]
    draw.deck = [CardSpec("牌库一", 0, 1), CardSpec("牌库二", 0, 1)]
    draw.discard = []
    draw.step(0)
    assert len(draw.hand) == 2  # draw 1 × 2


def test_review_multiple_boosts_end_of_turn_impression_score() -> None:
    """ExamReviewMultiple：好印象强化放大回合末结算分，到期后恢复。

    sim-fid ①（M8 G3 171 实证 until_turn=获得回合+N）：1 回合强化生效 2 回合
    （t1 获得 → until_turn=2），t2 末才清零。
    """
    sim = LessonSim(
        [CardSpec("好印象强化", 0, 0, review_multiple=2000, review_multiple_turns=1)],
        _config(turns=2, stamina=10, hand_size=1),
    )
    sim.buffs.impression = 5

    sim.step(0)  # 5 层 × (1000+2000)/1000 = 15
    assert sim.score == 15
    assert sim.buffs.impression == 4
    assert sim.buffs.review_multiple == 2000  # turns 1→0，最后生效回合仍生效
    assert sim.buffs.review_multiple_turns == 0

    sim.step(None)  # t2 仍 ×3：4 层结算 12；t2 末（until_turn=2）清零
    assert sim.score == 15 + 12
    assert sim.buffs.review_multiple == 0


def test_condition_additive_fix_adds_turns_to_condition_gain() -> None:
    """ExamParameterBuffAdditiveFix：获得好调时额外 +N 回合。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=2))
    sim.hand = [
        CardSpec("好调追加", 0, 0, condition_additive=2, condition_additive_turns=2),
        CardSpec("好调", 0, 0, condition=3),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)
    assert sim.buffs.condition_additive == 2
    sim.step(0)  # (3 + 2) = 5，M8 fresh 保护回合末不扣 → 仍 5
    assert sim.buffs.condition_turns == 5
    assert sim.buffs.condition_additive_turns == 1

    same = LessonSim(
        [
            CardSpec(
                "好调+追加", 0, 0, condition=3, condition_additive=2, condition_additive_turns=1
            )
        ],
        _config(turns=2, stamina=10, hand_size=1),
    )
    same.step(0)
    assert same.buffs.condition_turns == 5  # 同一张牌：先追加再结算 (3+2)，M8 fresh 不扣


def test_full_power_lesson_multiple_boosts_full_power_conversion() -> None:
    """ExamFullPowerLessonMultipleAdditive：只放大全力值折算出的那一段分。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=1))
    sim.hand = [
        CardSpec("全力强化斩", 0, 0, full_power_scale=2000, full_power_lesson_multiple=100)
    ]
    sim.deck = []
    sim.discard = []
    sim.stance.full_power_point = 5

    sim.step(0)

    # 5 × 2000/1000 = 10；卡面 +10%（千分比 100）→ int(10 × 1100/1000) = 11
    assert sim.score == 11


def test_grow_effect_increases_score_with_use_count() -> None:
    """ExamAddGrowEffect：同一张牌第 k 次使用时按 1+(k-1)×grow_score/100 计分。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=3, stamina=10, hand_size=1))
    sim.hand = [CardSpec("成长牌", 0, 10, grow_score=50)]
    sim.deck = []
    sim.discard = []

    sim.step(0)
    assert sim.score == 10  # 第 1 次：不吃成长
    sim.step(0)
    assert sim.score == 25  # 第 2 次：10 × 1.5 = 15
    sim.step(0)
    assert sim.score == 45  # 第 3 次：10 × 2.0 = 20


def test_grow_counter_is_per_card_instance() -> None:
    """成长计数器按牌对象记：两张同名牌各用一次都还是第 1 次。"""
    first = CardSpec("成长A", 0, 10, grow_score=100)
    second = CardSpec("成长B", 0, 10, grow_score=100)
    sim = LessonSim([first], _config(turns=3, stamina=10, hand_size=2))
    sim.hand = [first, second]
    sim.deck = []
    sim.discard = []

    sim.step(0)
    sim.step(0)

    assert sim.score == 20  # 不是 10 + 20
    assert sim.card_uses[id(first)] == 1
    assert sim.card_uses[id(second)] == 1
