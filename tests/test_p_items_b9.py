"""B9（T5④ 第二批）单测：P 道具持久倍率 / modifier 类效果。

覆盖三层：

1. **数据层**：``record_to_specs`` 把 effect_type（+ 文本）解析成 target / 数值 /
   持续回合；文本次数上限（「训练内N次」）；指針直给式与卡类强化的区分。
2. **纯规则**：``PItemDelta`` 新字段 + ``apply_passive`` 的增量；
   ``add_timed/tick_timed/total_timed`` 的列表语义。
3. **双镜**：``LessonSim`` 与 ``ExpectState`` 的分数倍率 / 好印象强化 /
   追加发动 / 费用修正 / 回合追加 / 直给指針 / 增益倍率 / 倒计时 / 镜像。

语义来源：gakumas-tools 参考引擎（BSD-3）``Executor/resolvers.js::resolveScore``
f/g（score *= 1+ΣscoreBuff、再 *= max(1−ΣscoreDebuff, 0)）与
``BuffManager.js``（setScoreBuff(amount, turns) 列表 + 回合末倒计时）。
"""

from __future__ import annotations

import pytest

from gkagent.sim.expectimax import (
    ExpectState,
    _card_award,
    effective_cost,
    end_turn_state,
    sim_from_state,
    start_turn_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    CARD_PLAY,
    EXAM_START,
    TURN_START,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    add_timed,
    apply_passive,
    load_p_items,
    record_to_specs,
    summarize,
    tick_timed,
    timed_dict_add,
    timed_dict_tick,
    timed_dict_total,
    total_timed,
)


def spec(**kwargs) -> PItemSpec:
    base = {
        "name": "测试道具",
        "trigger": TURN_START,
        "effect_type": "ExamLessonValueMultiple",
        "value": 500,
        "target_kind": "score_buff",
    }
    base.update(kwargs)
    return PItemSpec(**base)


def record(effects: list[dict], *, trigger: str = "turn_start", text_zh: str = "", **kwargs) -> dict:
    return {
        "id": "pitem_test",
        "name": "测试道具",
        "rarity": "SSR",
        "trigger": trigger,
        "condition": "",
        "max_uses": 0,
        "trigger_params": {},
        "effects": effects,
        "text_zh": text_zh,
        "text_ja": "",
        **kwargs,
    }


def only_spec(rec: dict) -> PItemSpec:
    specs = record_to_specs(rec)
    assert len(specs) == 1, specs
    return specs[0]


# ---------------------------------------------------------------- 纯规则：定时列表


def test_add_timed_merges_same_turns_and_ticks() -> None:
    entries = add_timed((), 500, 2)
    entries = add_timed(entries, 300, 2)  # 同回合数 → amount 加算
    entries = add_timed(entries, 100, 1)  # 不同回合数 → 另起一条
    assert sorted(entries) == [(100, 1), (800, 2)]
    assert total_timed(entries) == 900
    # 回合末 -1：turns=1 的条目消失、turns=2 → 1
    assert sorted(tick_timed(entries)) == [(800, 1)]
    assert sorted(tick_timed(tick_timed(entries))) == []


def test_add_timed_zero_turns_is_permanent() -> None:
    entries = add_timed((), 250, 0)
    assert entries == ((250, -1),)
    assert tick_timed(entries) == entries  # 永久不倒计时


def test_timed_dict_add_and_tick() -> None:
    table = timed_dict_add({}, "review_times", 1, 2)
    table = timed_dict_add(table, "review_times", 1, 2)
    assert timed_dict_total(table, "review_times") == 2
    assert timed_dict_total(tick_timed({}) if False else table, "review_times") == 2
    ticked = timed_dict_tick(table)
    assert timed_dict_total(ticked, "review_times") == 2
    assert timed_dict_total(timed_dict_tick(ticked), "review_times") == 0


# ---------------------------------------------------------------- 数据层


def test_record_to_specs_score_buff_percent_and_duration() -> None:
    """打分上升量增加 50%（1回合）：value=千分比 500，duration=1，target=score_buff。"""
    item = only_spec(
        record([{"type": "ExamLessonValueMultiple", "values": {"percent1": 50, "turn": 1}}])
    )
    assert item.target == "score_buff"
    assert item.value == 500
    assert item.duration == 1
    assert item.implemented is True


def test_record_to_specs_score_buff_without_turn_is_permanent() -> None:
    item = only_spec(
        record([{"type": "ExamLessonValueMultiple", "values": {"percent1": 15}}])
    )
    assert item.duration == 0  # 0 = 永久（参考引擎 turns=None）
    delta = apply_passive([item], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.score_buffs == [(150, -1)]


@pytest.mark.parametrize(
    ("effect", "target", "value", "duration"),
    [
        (
            {"type": "ExamReviewMultiple", "values": {"percent1": 50, "turn": 3}},
            "review_multiple",
            500,
            3,
        ),
        (
            {"type": "ExamReviewCountAdd", "values": {"value1": 1, "turn": 2}},
            "review_times",
            1,
            2,
        ),
        (
            {"type": "ExamEnthusiasticMultiple", "values": {"percent1": 40}},
            "enthusiasm_multiple",
            400,
            0,
        ),
        (
            {"type": "ExamEnthusiasticAdditive", "values": {"value1": 4}},
            "enthusiasm_bonus",
            4,
            0,
        ),
        (
            {"type": "ExamLessonBuffMultiple", "values": {"percent1": 15}},
            "concentration_effect",
            150,
            0,
        ),
        (
            {"type": "ExamLessonBuffAdditive", "values": {"percent1": 25, "turn": 6}},
            "concentration_gain",
            250,
            6,
        ),
        (
            {"type": "ExamReviewAdditive", "values": {"percent1": 50, "turn": 1}},
            "impression_gain",
            500,
            1,
        ),
        (
            {"type": "ExamAggressiveAdditive", "values": {"percent1": 50, "turn": 3}},
            "motivation_gain",
            500,
            3,
        ),
        (
            {"type": "ExamFullPowerPointAdditive", "values": {"percent1": 25, "turn": 1}},
            "full_power_charge",
            250,
            1,
        ),
        (
            {"type": "ExamParameterBuffMultiplePerTurn", "values": {"turn": 2}},
            "perfect_condition_turns",
            2,
            2,
        ),
        (
            {"type": "ExamGimmickParameterDebuff", "values": {"turn": 5}},
            "poor_condition_turns",
            5,
            5,
        ),
        ({"type": "ExamExtraTurn", "values": {}}, "extra_turn", 0, 0),
        (
            {"type": "ExamStaminaConsumptionDownFix", "values": {"value1": 2}},
            "cost_reduction",
            2,
            0,
        ),
        (
            {"type": "ExamStaminaConsumptionAddFix", "values": {"value1": 1}},
            "cost_increase",
            1,
            0,
        ),
        (
            {"type": "ExamStaminaConsumptionDown", "values": {"turn": 2}},
            "half_cost_turns",
            2,
            2,
        ),
        (
            {"type": "ExamStaminaConsumptionAdd", "values": {"turn": 5}},
            "double_cost_turns",
            5,
            5,
        ),
        (
            {"type": "ExamReviewReduce", "values": {"value1": 2}},
            "impression_reduce",
            2,
            0,
        ),
        ({"type": "ExamBlockFix", "values": {"value1": 4}}, "vitality", 4, 0),
    ],
)
def test_record_to_specs_b9_target_mapping(
    effect: dict, target: str, value: int, duration: int
) -> None:
    item = only_spec(record([effect]))
    assert item.target == target, (effect["type"], item.target)
    assert item.implemented is True
    if target in ("perfect_condition_turns", "poor_condition_turns", "half_cost_turns", "double_cost_turns"):
        assert item.duration == duration
    else:
        assert item.value == value
        assert item.duration == duration


def test_stance_effects_only_when_text_says_change() -> None:
    """指針直给式只看「温存变更/强气变更」文本；卡类强化段不是指針变更。"""
    assert (
        only_spec(record([{"type": "ExamPreservation", "values": {}, "text": "温存变更"}])).target
        == "stance_preservation"
    )
    # P1-3：「温存阶段变更」（value1=2）= 温存 2 段階直给（参考 setStance(preservation2)，
    # 叶える覚悟+/はつぼしフィギュア/まあるい春色/夢見る星 交叉）
    assert (
        only_spec(
            record([{"type": "ExamPreservation", "values": {"value1": 2}, "text": "温存阶段变更"}])
        ).target
        == "stance_preservation2"
    )
    assert (
        only_spec(
            record([{"type": "ExamConcentration", "values": {}, "text": "强气变更"}])
        ).target
        == "stance_concentration"
    )
    # 卡类强化/移动：不是指針变更 → 保守 no-op
    for effect_type, text in [
        ("ExamPreservation", "温存效果的技能卡的打分值增加+30"),
        ("ExamPreservation", "温存效果的技能卡向手牌中移动"),
        ("ExamConcentration", "强气效果的技能卡的打分值增加+4"),
        ("ExamConcentration", "强气效果的技能卡向手牌中移动"),
    ]:
        item = only_spec(record([{"type": effect_type, "values": {}, "text": text}]))
        assert item.target == "", (effect_type, text)
        assert item.implemented is False


def test_random_hand_cost_reduction_is_noop() -> None:
    """「削减消耗体力随机1张手牌在…」只作用于随机手牌，不能当全局费用削减。"""
    item = only_spec(
        record(
            [
                {
                    "type": "ExamStaminaConsumptionDownFix",
                    "values": {"value1": 1},
                    "text": "削减消耗体力随机1张手牌在",
                }
            ]
        )
    )
    assert item.target == ""
    assert item.implemented is False


def test_catalog_b9_coverage() -> None:
    """catalog 的 B9 覆盖率：实现段数从 B8 的 676 提升，且新目标都有实现。"""
    stats = summarize(load_p_items())
    assert stats["specs"] == 1849
    assert stats["implemented"] >= 1000  # B8: 676
    assert stats["noop"] <= 900  # B8: 1173
    assert stats["implemented_modifier_specs"] >= 300
    targets = stats["implemented_modifier_targets"]
    for key in (
        "score_buff",
        "score_debuff",
        "review_multiple",
        "review_times",
        "extra_turn",
        "cost_reduction",
        "cost_increase",
        "half_cost_turns",
        "double_cost_turns",
        "stance_preservation",
        "stance_concentration",
        "perfect_condition_turns",
    ):
        assert targets.get(key, 0) > 0, key


def test_catalog_text_max_uses_parsed() -> None:
    """B9 从描述解析次数上限：悔恨的象征「（训练内3次）」→ max_uses=3。"""
    items = [item for item in load_p_items() if item.item_id == "pitem_00-3-012-0"]
    assert items
    assert all(item.max_uses == 3 for item in items)
    assert any(item.target == "score_buff" and item.duration == 1 for item in items)


# ---------------------------------------------------------------- apply_passive


def test_apply_passive_b9_delta_fields() -> None:
    specs = [
        spec(
            effect_type="ExamLessonValueMultiple",
            target_kind="score_buff",
            value=500,
            duration=2,
        ),
        spec(
            effect_type="ExamLessonValueMultipleDown",
            target_kind="score_debuff",
            value=200,
            duration=1,
        ),
        spec(
            effect_type="ExamReviewCountAdd",
            target_kind="review_times",
            value=1,
            duration=2,
        ),
        spec(
            effect_type="ExamStaminaConsumptionDownFix",
            target_kind="cost_reduction",
            value=2,
        ),
        spec(effect_type="ExamExtraTurn", target_kind="extra_turn", value=0),
        spec(effect_type="ExamPreservation", target_kind="stance_preservation", value=0),
        spec(
            effect_type="ExamParameterBuffMultiplePerTurn",
            target_kind="perfect_condition_turns",
            duration=2,
        ),
    ]
    delta = apply_passive(specs, PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.score_buffs == [(500, 2)]
    assert delta.score_debuffs == [(200, 1)]
    assert ("review_times", 1, 2) in delta.modifiers
    assert delta.cost_reduction == 2
    assert delta.extra_turns == 1
    assert delta.stances == ["preservation"]
    assert delta.perfect_condition_turns == 2
    assert not delta.is_zero()


def test_apply_passive_impression_reduce_and_block_fix() -> None:
    specs = [
        spec(effect_type="ExamReviewReduce", target_kind="impression_reduce", value=2),
        spec(effect_type="ExamBlockFix", target_kind="vitality", value=4),
    ]
    delta = apply_passive(specs, PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    # P1-7：ExamBlockFix（fixedGenki+=）走独立 fixed_vitality（不受无效/不安拦截），
    # 不再混进 stacks["vitality"]（genki+= 渠道）。
    assert delta.stacks == {"impression": -2}
    assert delta.fixed_vitality == 4


# ---------------------------------------------------------------- LessonSim


def make_sim(*specs: PItemSpec, turns: int = 3, deck: list[CardSpec] | None = None) -> LessonSim:
    cards = deck or [CardSpec("a", 0, 10.0)]
    return LessonSim(
        cards,
        LessonConfig(turns=turns, stamina=20, target_clear=10, p_items=tuple(specs)),
        rng_seed=1,
    )


def test_lesson_score_buff_multiplies_card_award_and_expires() -> None:
    item = spec(value=500, duration=1, trigger=EXAM_START)
    sim = make_sim(item, turns=3)
    card = CardSpec("a", 0, 10.0)
    assert sim.score_buffs == ((500, 1),)
    assert sim._card_award(card) == 15  # 10 × 1.5
    sim.step(None)  # 回合末倒计时：duration=1 的 buff 到 0 移除
    assert total_timed(sim.score_buffs) == 0
    assert sim._card_award(card) == 10


def test_lesson_score_debuff_multiplies_card_award() -> None:
    item = spec(
        effect_type="ExamLessonValueMultipleDown",
        target_kind="score_debuff",
        value=500,
        duration=2,
    )
    sim = make_sim(item)
    assert sim.score_debuffs == ((500, 2),)
    assert sim._card_award(CardSpec("a", 0, 10.0)) == 5


def test_lesson_score_buffs_stack_additively() -> None:
    sim = make_sim(spec(value=500, duration=2), spec(value=300, duration=2))
    assert total_timed(sim.score_buffs) == 800
    assert sim._card_award(CardSpec("a", 0, 10.0)) == 18


def test_lesson_review_multiple_p_item_boosts_end_turn_impression() -> None:
    item = spec(
        effect_type="ExamReviewMultiple",
        target_kind="review_multiple",
        value=500,
        duration=2,
    )
    sim = make_sim(item)
    sim.buffs.impression = 4
    sim.step(None)  # 回合结束：好印象 4 × 1.5 = 6
    assert sim.score == 6


def test_lesson_review_times_adds_settlement() -> None:
    item = spec(
        effect_type="ExamReviewCountAdd",
        target_kind="review_times",
        value=1,
        duration=2,
    )
    sim = make_sim(item)
    sim.buffs.impression = 4
    sim.step(None)  # 追加发动 1 次 → 4 + 4 = 8
    assert sim.score == 8


def test_lesson_extra_turn_extends_total_turns() -> None:
    item = spec(
        effect_type="ExamExtraTurn",
        target_kind="extra_turn",
        value=1,
        trigger=CARD_PLAY,
    )
    sim = make_sim(item, turns=2)
    assert sim.total_turns == 2
    sim.step(0)  # 出牌后自动结束回合；pending 在 turns_left-1 之后补上
    assert sim.total_turns == 3
    assert sim.turns_left == 2  # 2 - 1 + 1


def test_lesson_half_cost_turns_halves_cost_then_expires() -> None:
    item = spec(
        effect_type="ExamStaminaConsumptionDown",
        target_kind="half_cost_turns",
        duration=2,
        value=2,
        trigger=EXAM_START,
    )
    sim = make_sim(item, turns=3)
    card = CardSpec("a", 4, 10.0)
    assert sim._effective_cost(card) == 2  # ceil(4 × 0.5)
    sim.step(None)
    assert sim.half_cost_turns == 1
    sim.step(None)
    assert sim.half_cost_turns == 0
    assert sim._effective_cost(card) == 4


def test_lesson_cost_reduction_and_increase() -> None:
    reduce_item = spec(
        effect_type="ExamStaminaConsumptionDownFix",
        target_kind="cost_reduction",
        value=2,
        trigger=EXAM_START,
    )
    sim = make_sim(reduce_item)
    card = CardSpec("a", 4, 10.0)
    assert sim._effective_cost(card) == 2
    increase_item = spec(
        effect_type="ExamStaminaConsumptionAddFix",
        target_kind="cost_increase",
        value=3,
        trigger=EXAM_START,
    )
    sim2 = make_sim(increase_item)
    assert sim2._effective_cost(card) == 7


def test_lesson_direct_stance_grants_and_upgrades() -> None:
    item = spec(
        effect_type="ExamPreservation",
        target_kind="stance_preservation",
        value=0,
        trigger=EXAM_START,
    )
    sim = make_sim(item)
    assert str(sim.stance.stance) == "save"
    assert sim.stance.save_level == 1
    sim._fire_p_items(EXAM_START)
    assert sim.stance.save_level == 2  # 参考引擎 setStance：温存中再温存 → 2 段階


def test_lesson_gain_multipliers() -> None:
    specs = [
        spec(
            effect_type="ExamReviewAdditive",
            target_kind="impression_gain",
            value=500,
            duration=3,
            trigger=EXAM_START,
        ),
        spec(
            effect_type="ExamAggressiveAdditive",
            target_kind="motivation_gain",
            value=500,
            duration=3,
            trigger=EXAM_START,
        ),
        spec(
            effect_type="ExamLessonBuffAdditive",
            target_kind="concentration_gain",
            value=500,
            duration=3,
            trigger=EXAM_START,
        ),
        spec(
            effect_type="ExamFullPowerPointAdditive",
            target_kind="full_power_charge",
            value=500,
            duration=3,
            trigger=EXAM_START,
        ),
    ]
    card = CardSpec("a", 0, 10.0, impression=3, motivation=3, focus=3, full_power_point=5)
    sim = make_sim(*specs, deck=[card])
    sim.step(0)  # 手牌打空 → 自动结束回合；M8 fresh 保护获得当回合末不扣
    assert sim.buffs.impression == 5  # ceil(3 × 1.5) = 5，fresh 存活（下一回合末才 -1）
    assert sim.motivation == 5
    assert sim.buffs.focus == 5
    assert sim.stance.full_power_point == 8  # ceil(5 × 1.5)


def test_lesson_concentration_effect_boosts_focus_contribution() -> None:
    item = spec(
        effect_type="ExamLessonBuffMultiple",
        target_kind="concentration_effect",
        value=1000,
        duration=2,
    )
    sim = make_sim(item)
    sim.buffs.focus = 5
    card = CardSpec("a", 0, 10.0)
    # (10 + 5×2) × 1 = 20
    assert sim._card_award(card) == 20


def test_lesson_perfect_condition_p_item() -> None:
    item = spec(
        effect_type="ExamParameterBuffMultiplePerTurn",
        target_kind="perfect_condition_turns",
        duration=2,
        value=2,
    )
    sim = make_sim(item)
    assert sim.buffs.perfect_condition_turns == 2


# ---------------------------------------------------------------- ExpectState 双镜


def test_expect_state_end_turn_ticks_b9_channels() -> None:
    state = ExpectState(
        stamina=10,
        stamina_max=10,
        turns_left=3,
        total_turns=3,
        score_buffs=((500, 2),),
        score_debuffs=((200, 1),),
        modifiers=(("review_times", ((1, 2),)),),
        half_cost_turns=2,
        double_cost_turns=1,
    )
    after = end_turn_state(state)
    assert after.score_buffs == ((500, 1),)
    assert after.score_debuffs == ()
    assert after.mod_total("review_times") == 1
    assert after.half_cost_turns == 1
    assert after.double_cost_turns == 0


def test_expect_state_extra_turns_extend_turns_left() -> None:
    state = ExpectState(
        stamina=10,
        stamina_max=10,
        turns_left=3,
        total_turns=4,
        extra_turns=1,
    )
    after = end_turn_state(state)
    assert after.turns_left == 3  # 3 - 1 + 1
    assert after.extra_turns_granted == 1
    assert after.current_turn == 3  # (4+1) - 3 + 1；回合号不因追加回退


def test_expect_state_score_buff_affects_award_and_effective_cost() -> None:
    state = ExpectState(
        stamina=10,
        stamina_max=10,
        turns_left=3,
        total_turns=3,
        score_buffs=((500, 2),),
        cost_reduction=2,
        half_cost_turns=2,
    )
    card = CardSpec("a", 4, 10.0)
    assert _card_award(state, card)[0] == 15
    assert effective_cost(state, card) == 0  # ceil(4×0.5)=2，再 -2
    debuffed = ExpectState(
        stamina=10, stamina_max=10, turns_left=3, total_turns=3, score_debuffs=((500, 1),)
    )
    assert _card_award(debuffed, CardSpec("a", 0, 10.0))[0] == 5


def test_lesson_expect_award_parity() -> None:
    """LessonSim 与 ExpectState 的算分在 B9 倍率下逐位一致。"""
    item = spec(value=500, duration=2)
    sim = make_sim(item)
    sim.modifiers = {"concentration_effect": ((1000, 2),)}
    sim.buffs.focus = 5
    card = CardSpec("a", 0, 10.0)
    state = ExpectState(
        stamina=sim.stamina,
        stamina_max=sim.stamina_max,
        turns_left=sim.turns_left,
        total_turns=sim.total_turns,
        focus=sim.buffs.focus,
        score_buffs=sim.score_buffs,
        modifiers=(("concentration_effect", ((1000, 2),)),),
    )
    assert sim._card_award(card) == _card_award(state, card)[0]


def test_state_from_sim_sim_from_state_roundtrip_b9_fields() -> None:
    item = spec(value=500, duration=2)
    sim = make_sim(item)
    sim.cost_reduction = 1
    sim.half_cost_turns = 2
    sim.double_cost_turns = 3
    sim.extra_turns_pending = 1
    sim.extra_turns_granted = 2
    sim.modifiers = {"impression_gain": ((500, 2),)}
    sim.buffs.review_multiple = 300
    sim.buffs.review_multiple_turns = 2
    state = state_from_sim(sim)
    assert state.cost_reduction == 1
    assert state.half_cost_turns == 2
    assert state.double_cost_turns == 3
    assert state.extra_turns == 1
    assert state.extra_turns_granted == 2
    assert state.mod_total("impression_gain") == 500
    assert state.review_multiple == 300
    back = sim_from_state(state)
    assert back.cost_reduction == 1
    assert back.half_cost_turns == 2
    assert back.double_cost_turns == 3
    assert back.extra_turns_pending == 1
    assert back.extra_turns_granted == 2
    assert back.modifiers == {"impression_gain": ((500, 2),)}


def test_expect_state_canonical_tracks_b9_fields() -> None:
    base = ExpectState(stamina=10, stamina_max=10, turns_left=3, total_turns=3)
    changed = [
        ExpectState(stamina=10, stamina_max=10, turns_left=3, total_turns=3, score_buffs=((500, 1),)),
        ExpectState(stamina=10, stamina_max=10, turns_left=3, total_turns=3, cost_reduction=2),
        ExpectState(stamina=10, stamina_max=10, turns_left=3, total_turns=3, half_cost_turns=1),
        ExpectState(stamina=10, stamina_max=10, turns_left=3, total_turns=3, extra_turns=1),
    ]
    for state in changed:
        assert state.canonical() != base.canonical()


def test_start_turn_state_fires_p_item_and_applies_buff() -> None:
    item = spec(value=500, duration=1)
    state = ExpectState(
        stamina=10,
        stamina_max=10,
        turns_left=2,
        total_turns=2,
        p_items=(item,),
    )
    after = start_turn_state(state)
    assert after.score_buffs == ((500, 1),)
    assert after.p_item_uses == (("测试道具", 1),)  # 无 item_id 时按名字计数


def test_empty_state_is_unchanged_by_b9_ticks() -> None:
    """没有 B9 状态时 end_turn_state 与旧行为一致（不凭空产生字段/分数）。"""
    state = ExpectState(stamina=10, stamina_max=10, turns_left=3, total_turns=3)
    after = end_turn_state(state)
    assert after.score_buffs == () and after.modifiers == ()
    assert after.turns_left == 2
    assert after.extra_turns_granted == 0
