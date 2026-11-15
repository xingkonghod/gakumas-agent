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
    """好印象每回合结束先按层数加分、再 -1；3 层连续两回合 → +3、+2。"""
    sim = LessonSim(
        [CardSpec("好印象", 0, 0, impression=3), CardSpec("空白", 0, 0)],
        _config(turns=3, stamina=10, hand_size=2),
    )

    sim.step(_index(sim, "好印象"))
    assert sim.score == 0                  # 出牌本身不加分
    assert sim.buffs.impression == 3

    sim.step(None)                         # 回合结束：+3，层数 3 → 2
    assert sim.score == 3
    assert sim.buffs.impression == 2

    sim.step(None)                         # 再一回合结束：+2，层数 2 → 1
    assert sim.score == 5
    assert sim.buffs.impression == 1


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

    # 白值 floor((9 + 2) × 1.5) = 16；依赖 3 层 × 1000% = 30
    assert sim.score == 46


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
    """温存 1 段階：先打温存，后续 9 分牌变成 floor(9 × 0.5) = 4。"""
    sim = LessonSim(
        [CardSpec("温存", 0, 0, preservation=1), CardSpec("打分", 2, 9)],
        _config(turns=2, stamina=10, hand_size=2),
    )

    sim.step(_index(sim, "温存"))
    assert sim.score == 0
    assert sim.stance.stance == "save"
    assert sim.stance.save_level == 1

    sim.step(_index(sim, "打分"))
    assert sim.score == 4


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
    assert sim.score == 9  # 不是 floor(9 × 0.5)
    assert sim.stance.save_level == 1

    sim.step(_index(sim, "追击"))
    assert sim.score == 13  # 9 + floor(9 × 0.5)


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
def test_extra_play_card_allows_one_more_play_this_turn() -> None:
    """+1 次数牌结算后本回合上限 3+1：能多出 1 张，用尽后只剩 SKIP。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=3))
    sim.hand = [
        CardSpec("次数+1", 0, 0, extra_play=1),
        CardSpec("打1", 0, 1),
        CardSpec("打2", 0, 1),
        CardSpec("打3", 0, 1),
        CardSpec("打4", 0, 1),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)  # 次数+1：本牌占 1 次，同时追加 1 次
    assert sim.plays_this_turn == 1
    assert sim.extra_plays == 1

    for _ in range(3):
        sim.step(0)
    assert sim.plays_this_turn == 4
    assert sim.score == 3
    assert len(sim.hand) == 1  # 还剩一张，但次数已经用尽
    assert sim.legal_actions() == [None]
    with pytest.raises(ValueError, match="次数已用尽"):
        sim.step(0)


def test_card_without_extra_play_does_not_extend_limit() -> None:
    """extra_play=0 的牌不追加次数：手牌再多，本回合也只能出 plays_per_turn 张。"""
    assert CardSpec("普通", 0, 1).extra_play == 0

    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=3))
    sim.hand = [CardSpec(f"打{i}", 0, 1) for i in range(4)]
    sim.deck = []
    sim.discard = []

    for _ in range(3):
        sim.step(0)

    assert sim.extra_plays == 0
    assert sim.plays_this_turn == 3
    assert sim.score == 3
    assert len(sim.hand) == 1
    assert sim.legal_actions() == [None]


def test_extra_play_cards_stack() -> None:
    """两张 +1 次数牌叠加：本回合上限变成 3+2，可以连出 5 张。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=3))
    sim.hand = [
        CardSpec("次数+1a", 0, 0, extra_play=1),
        CardSpec("次数+1b", 0, 0, extra_play=1),
        CardSpec("打1", 0, 1),
        CardSpec("打2", 0, 1),
        CardSpec("打3", 0, 1),
        CardSpec("打4", 0, 1),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)
    sim.step(0)
    assert sim.extra_plays == 2

    for _ in range(3):
        sim.step(0)

    assert sim.plays_this_turn == 5
    assert sim.score == 3
    assert len(sim.hand) == 1
    assert sim.legal_actions() == [None]


def test_extra_plays_reset_at_turn_start() -> None:
    """额外次数只在当回合有效：SKIP 换手牌后 plays_this_turn / extra_plays 归零。"""
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, stamina=10, hand_size=3))
    sim.hand = [
        CardSpec("次数+1", 0, 0, extra_play=1),
        CardSpec("打", 0, 1),
        CardSpec("占位二", 0, 0),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)
    sim.step(0)
    assert sim.extra_plays == 1

    sim.step(None)  # SKIP 结束本回合，抽下一手

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

    # 白值 floor((9 + 2) × 1.5 × 0.5) = 8；依赖分 int(3 × 700 / 100) = 21（不吃倍率）
    assert sim.score == 29


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
