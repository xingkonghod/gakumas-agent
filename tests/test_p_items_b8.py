"""B8（2026-11-22）P 道具「条件/效果语义」第一批的回归测试。

覆盖四块：

1. 新语法 trigger id 从 id 后缀解析条件/参数（build_p_items.parse_exam_trigger_id）；
2. 依赖换算（「X 的 N% 数值变为 Y」）、「X 变为 0」、最大体力百分比（annotate_effects）；
3. sim/p_items 的结算：依赖换算 / 固定体力消耗 / 百分比体力回复 / 零层 / 新触发时机；
4. LessonSim 与 ExpectState 的事件接线与镜像（turn_start_after / turn_interval /
   status_gain_interval / stance_change / stamina_reduce / 累计量字段）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_p_items

from gkagent.sim.expectimax import (
    ExpectState,
    apply_card,
    start_turn_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    EXAM_START,
    STAMINA_REDUCE,
    STANCE_CHANGE,
    STATUS_GAIN,
    STATUS_GAIN_INTERVAL,
    TURN_INTERVAL,
    TURN_START,
    TURN_START_AFTER,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    apply_passive,
    load_p_items,
)

ITEMS = load_p_items()


# ---- 1. trigger id 解析 -----------------------------------------------------


def test_parse_trigger_id_interval_and_remaining() -> None:
    params, conditions, complete = build_p_items.parse_exam_trigger_id(
        "e_trigger-exam_play_turn_count_interval-2-remaining_turn-5-p_card_search-target",
        "exam_play_turn_count_interval",
    )
    assert complete is True
    assert params["interval"] == 2
    assert params["remaining_turns"] == 5
    assert conditions == []


def test_parse_trigger_id_conditions() -> None:
    _params, conditions, complete = build_p_items.parse_exam_trigger_id(
        "e_trigger-exam_card_play_after-parameter_buff_up-8-p_card_search-mental_skill-target-0_1",
        "exam_card_play_after",
    )
    assert complete is True
    assert "好调在8回合以上" in conditions

    _, conditions, _ = build_p_items.parse_exam_trigger_id(
        "e_trigger-exam_card_play-stamina_up_multiple-800-p_card_search-active_skill-playing-0_1",
        "exam_card_play",
    )
    assert "体力在80%以上" in conditions

    _, conditions, _ = build_p_items.parse_exam_trigger_id(
        "e_trigger-start_play-full_power_point_get_sum_up-10", "start_play"
    )
    assert "累计全力值在10以上" in conditions

    _, conditions, _ = build_p_items.parse_exam_trigger_id(
        "e_trigger-exam_play_count_interval-2-card_play_aggressive_up-5-p_card_search-mental_skill-target",
        "exam_play_count_interval",
    )
    assert "干劲在5以上" in conditions


def test_parse_trigger_id_review_interval_sets_status() -> None:
    params, _, complete = build_p_items.parse_exam_trigger_id(
        "e_trigger-exam_review_up_interval-4-exam_review", "exam_review_up_interval"
    )
    assert complete is True
    assert params["interval"] == 4
    assert params["status"] == "impression"


def test_parse_trigger_id_specific_card_is_incomplete() -> None:
    """B10 起指定卡名/区域张数（tracked 区）已结构化解析 → 不再 incomplete；
    P1-3 起 hold（保留）区已建模、period810_hotfix 证实为非限定标记 → 全部解析；
    只剩真正未知词保守跳过。"""
    for trigger_id in (
        "e_trigger-exam_card_play_after-p_card_search-target-1-p_card-01-act-1_023-0_1",
        "e_trigger-exam_start_turn-card_search_count_up-2-p_card_search-trouble-not_lost",
        "e_trigger-exam_card_play_after-card_search_count_up-1-p_card_search-hand-p_card-00-acc-0_002-p_card_search-target-0_1",
        # P1-3：hold 区张数条件（实现的觉悟）+ period810_hotfix（咲季营养餐・改）
        "e_trigger-exam_card_play_after-card_search_count_up-1-p_card_search-hold-p_card_search-target-1-p_card-03-act-1_038-0_1",
        "e_trigger-exam_play_turn_count_interval-2-p_card_search-target-period810_hotfix",
    ):
        assert build_p_items.trigger_id_has_unparsed_condition(trigger_id) is False
    # 真正未知词仍保守跳过（不猜）
    assert build_p_items.trigger_id_has_unparsed_condition(
        "e_trigger-exam_card_play_after-p_card_search-target-some_unknown_token"
    ) is True


# ---- 2. 效果语义标注 --------------------------------------------------------


def test_annotate_dependency_conversion() -> None:
    """源段（X的%数值变为）把 percent1 挂到后一个空目标效果上（depends_on + percent）。"""
    effects = [
        {"type": "ExamBlock", "values": {"percent1": 50}, "text": "元气的%数值变为"},
        {"type": "ExamLesson", "values": {}, "text": "打分上升"},
        {"type": "ExamStaminaReduceFix", "values": {"value1": 1}, "text": "体力消耗"},
    ]
    annotated = build_p_items.annotate_effects(
        effects, "最终回合的回合开始时，元气的50%数值变为打分上升体力消耗1"
    )
    assert annotated[0]["role"] == "conversion_source"
    assert "percent1" not in annotated[0]["values"]
    assert annotated[1]["depends_on"] == "vitality"
    assert annotated[1]["values"] == {"percent1": 50}


def test_annotate_zero_stack_and_stamina_percent() -> None:
    """「X变为0」→ zero_stack；「最大体力的 N% 数值变为体力消耗」→ percent_max。"""
    effects = [
        {"type": "ExamBlock", "values": {"percent1": 50}, "text": "元气的%数值变为"},
        {"type": "ExamReview", "values": {}, "text": "好印象增加，"},
        {"type": "ExamBlock", "values": {}, "text": "元气变为0"},
        {"type": "ExamStaminaReduceFix", "values": {}, "text": "体力消耗"},
    ]
    annotated = build_p_items.annotate_effects(
        effects, "元气的50%数值变为好印象增加，元气变为0最大体力的15%数值变为体力消耗"
    )
    assert annotated[1]["depends_on"] == "vitality"
    assert annotated[2]["zero_stack"] == "vitality"
    assert annotated[3]["percent_max"] == 15


def test_annotate_stamina_percent_moved_from_previous_effect() -> None:
    """实测 pitem_02-3-076-0：percent1 挂在「技能卡使用数追加」段上，要挪给体力段。"""
    effects = [
        {"type": "ExamCardPlayAggressive", "values": {"value1": 2}, "text": "干劲+"},
        {
            "type": "ExamPlayableValueAdd",
            "values": {"count": 1, "percent1": 15},
            "text": "技能卡使用数追加+最大体力的%数值变为",
        },
        {"type": "ExamStaminaReduceFix", "values": {}, "text": "体力消耗（训练内5次）"},
    ]
    annotated = build_p_items.annotate_effects(effects, "")
    assert annotated[1]["values"]["count"] == 1
    assert "percent1" not in annotated[1]["values"]
    assert annotated[2]["percent_max"] == 15


# ---- 3. 真数据覆盖 ----------------------------------------------------------


def test_real_catalog_b8_stats() -> None:
    import json

    payload = json.loads(
        (ROOT / "data" / "knowledge" / "p_items.json").read_text(encoding="utf-8-sig")
    )
    stats = payload["stats"]
    # B8：条件未知 22→6；B10：p_card_search 限定结构化后条件未知 6→0、
    # 触发未知 103→3；P1-3：hold 保留区建模 + period810_hotfix 证实为非限定
    # 标记 → 触发未知 3→0（B10 遗留清零）。
    assert stats["items_condition_unknown"] == 0
    assert stats["items_trigger_unknown"] == 0
    assert stats["items_trigger_id_parsed"] >= 16
    assert stats["effects_depends_on"] > 0
    assert stats["effects_percent_max"] > 0
    assert stats["effects_zero_stack"] > 0


def test_real_conversion_spec_is_parsed() -> None:
    """真数据里的依赖换算段：pitem_00-1-006-0 = 元气的 50% 数值变为打分上升。"""
    record = next(
        item
        for item in ITEMS
        if item.item_id == "pitem_00-1-006-0" and item.effect_type == "ExamLesson"
    )
    assert record.depends_on == "vitality"
    assert record.percent == 50

    state = build_p_items.parse_exam_trigger_id(
        "e_trigger-start_play-remaining_turn-4", "start_play"
    )
    assert state[0]["remaining_turns"] == 4


# ---- 4. sim/p_items 结算 ----------------------------------------------------


def _spec(**kwargs) -> PItemSpec:
    base = {"name": "测试道具", "trigger": TURN_START, "effect_type": "ExamLesson", "value": 0}
    base.update(kwargs)
    return PItemSpec(**base)


def test_dependency_conversion_applies_from_state() -> None:
    spec = _spec(effect_type="ExamLesson", depends_on="vitality", percent=50)
    assert spec.implemented is True
    delta = apply_passive(
        [spec],
        PassiveEvent(kind=TURN_START),
        PassiveState(turn=1, stacks={"vitality": 10}),
    )
    assert delta.score == 5


def test_zero_stack_and_stamina_fix_deltas() -> None:
    zero = _spec(effect_type="ExamBlock", zero_stack="vitality")
    delta = apply_passive([zero], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.zero_stacks == ["vitality"]

    flat = _spec(trigger=EXAM_START, effect_type="ExamStaminaReduceFix", value=3)
    delta = apply_passive([flat], PassiveEvent(kind=EXAM_START), PassiveState(turn=1))
    assert delta.stamina == -3

    percent = _spec(trigger=EXAM_START, effect_type="ExamStaminaReduceFix", percent_max=10)
    delta = apply_passive(
        [percent], PassiveEvent(kind=EXAM_START), PassiveState(turn=1, stamina=50, stamina_max=100)
    )
    assert delta.stamina == -10

    recover = _spec(trigger=EXAM_START, effect_type="ExamStaminaRecoverFix", percent_max=25)
    delta = apply_passive(
        [recover], PassiveEvent(kind=EXAM_START), PassiveState(turn=1, stamina=10, stamina_max=100)
    )
    assert delta.stamina == 25


def test_new_trigger_matching() -> None:
    after = _spec(trigger=TURN_START_AFTER, value=5, remaining_turns=2)
    assert (
        apply_passive(
            [after], PassiveEvent(kind=TURN_START_AFTER), PassiveState(turn=1, turns_left=2)
        ).score
        == 5
    )
    assert (
        apply_passive(
            [after], PassiveEvent(kind=TURN_START_AFTER), PassiveState(turn=1, turns_left=3)
        ).score
        == 0
    )

    interval = _spec(trigger=TURN_INTERVAL, value=5, every=2)
    for turn in (1, 2, 3, 4):
        delta = apply_passive([interval], PassiveEvent(kind=TURN_INTERVAL), PassiveState(turn=turn))
        assert delta.score == (5 if turn % 2 == 0 else 0)

    gain = _spec(
        trigger=STATUS_GAIN_INTERVAL,
        effect_type="ExamBlock",
        value=3,
        interval=2,
        status="impression",
    )
    delta = apply_passive(
        [gain],
        PassiveEvent(kind=STATUS_GAIN, status="impression", amount=2, status_total=2),
        PassiveState(turn=1),
    )
    assert delta.stacks == {"vitality": 3}
    # 没跨过 2 的整数倍 → 不触发
    delta = apply_passive(
        [gain],
        PassiveEvent(kind=STATUS_GAIN, status="impression", amount=1, status_total=3),
        PassiveState(turn=1),
    )
    assert delta.is_zero()

    stance = _spec(trigger=STANCE_CHANGE, value=2)
    assert (
        apply_passive(
            [stance],
            PassiveEvent(kind=STANCE_CHANGE),
            PassiveState(turn=1, stacks={"stance_full_power": 1}),
        ).score
        == 2
    )

    reduce = _spec(trigger=STAMINA_REDUCE, value=1)
    assert (
        apply_passive(
            [reduce], PassiveEvent(kind=STAMINA_REDUCE, stamina_delta=2), PassiveState(turn=1)
        ).score
        == 1
    )


# ---- 5. LessonSim / ExpectState 接线 ---------------------------------------


def _config(**kwargs) -> LessonConfig:
    base = {"turns": 1, "stamina": 20, "target_clear": 1, "hand_size": 1, "plays_per_turn": 10}
    base.update(kwargs)
    return LessonConfig(**base)


def test_lesson_conversion_and_zero_stack() -> None:
    exam = _spec(name="开局元气", trigger=EXAM_START, effect_type="ExamBlock", value=10)
    convert = _spec(
        name="元气换算打分",
        trigger=TURN_START,
        effect_type="ExamLesson",
        depends_on="vitality",
        percent=50,
    )
    zero = _spec(name="元气清零", effect_type="ExamBlock", zero_stack="vitality")
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(p_items=(exam, convert, zero)), rng_seed=0)
    assert sim.vitality == 0  # 元气 +10 后又被「变为0」清零
    assert sim.score == 5  # 换算发生在清零之前（事件顺序：exam_start → turn_start 内逐段结算）


def test_lesson_turn_start_after_and_interval() -> None:
    after = _spec(name="回合开始后+5", trigger=TURN_START_AFTER, value=5)
    interval = _spec(name="每2回合+5", trigger=TURN_INTERVAL, value=5, every=2)
    deck = [CardSpec("牌", 0, 0)]
    sim = LessonSim(
        deck,
        _config(turns=4, plays_per_turn=10, hand_size=1, p_items=(after, interval)),
        rng_seed=0,
    )
    # turn 1：只吃 turn_start_after（interval 要第 2/4 回合）
    assert sim.score == 5
    sim.step(None)  # 结束第 1 回合 → 第 2 回合开始
    assert sim.score == 15  # +5(after) +5(interval)
    sim.step(None)
    assert sim.score == 20
    sim.step(None)
    assert sim.score == 30


def test_lesson_status_gain_interval() -> None:
    item = _spec(
        name="好印象2次时元气+3",
        trigger=STATUS_GAIN_INTERVAL,
        effect_type="ExamBlock",
        value=3,
        interval=2,
        status="impression",
    )
    sim = LessonSim(
        [CardSpec("好印象牌", 0, 0, impression=2)],
        _config(turns=1, p_items=(item,)),
        rng_seed=0,
    )
    sim.hand = [CardSpec("好印象牌", 0, 0, impression=2)]
    sim.step(0)
    assert sim.buffs.impression == 2
    assert sim.vitality == 3
    assert sim.status_gain_counts.get("impression") == 2


def test_lesson_stance_change_and_stamina_reduce() -> None:
    on_stance = _spec(name="指針变化+2", trigger=STANCE_CHANGE, value=2)
    on_reduce = _spec(name="体力减少+1", trigger=STAMINA_REDUCE, value=1)
    sim = LessonSim(
        [CardSpec("温存牌", 2, 0, preservation=1)],
        _config(turns=1, stamina=10, p_items=(on_stance, on_reduce)),
        rng_seed=0,
    )
    sim.hand = [CardSpec("温存牌", 2, 0, preservation=1)]
    sim.step(0)
    assert sim.score == 3  # 指針变化 +2、消耗体力 +1
    assert sim.consumed_stamina_total == 2


def test_lesson_stamina_fix_item_and_percent_recover() -> None:
    fix = _spec(
        name="固定体力消耗2", trigger=TURN_START, effect_type="ExamStaminaReduceFix", value=2
    )
    recover = _spec(
        name="最大体力25%回复",
        trigger=TURN_START,
        effect_type="ExamStaminaRecoverFix",
        percent_max=25,
    )
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=1, stamina=40, stamina_max=100, p_items=(fix, recover)),
        rng_seed=0,
    )
    # 先扣 2 再回 25（同一 turn_start 事件按列表顺序结算）
    assert sim.stamina == 40 - 2 + 25
    assert sim.consumed_stamina_total == 2


def test_expectimax_mirrors_turn_events_and_counters() -> None:
    convert = _spec(
        name="元气换算打分",
        trigger=TURN_START,
        effect_type="ExamLesson",
        depends_on="vitality",
        percent=50,
    )
    state = ExpectState(
        hand=(CardSpec("打", 0, 0),),
        stamina=10,
        vitality=10,
        turns_left=2,
        total_turns=2,
        clear=1,
        perfect=1000,
        p_items=(convert,),
    )
    successor = start_turn_state(state)
    assert successor.score == 5
    assert successor.p_item_uses  # 记录了触发次数
    # state_from_sim 把新增累计量带回来（B8 新增字段的镜像）
    sim = LessonSim([CardSpec("占位", 0, 0)], _config(turns=2, p_items=(convert,)), rng_seed=0)
    sim.vitality = 10
    sim.full_power_point_total = 7
    sim.consumed_stamina_total = 4
    sim.status_gain_counts = {"impression": 3}
    snap = state_from_sim(sim)
    assert snap.full_power_point_total == 7
    assert snap.consumed_stamina_total == 4
    assert snap.status_counts == (("impression", 3),)


def test_expectimax_stamina_reduce_item() -> None:
    on_reduce = _spec(name="体力减少+1", trigger=STAMINA_REDUCE, value=1)
    state = ExpectState(
        hand=(CardSpec("打", 2, 0),),
        stamina=10,
        turns_left=2,
        total_turns=2,
        clear=1,
        perfect=1000,
        p_items=(on_reduce,),
    )
    outcomes = apply_card(state, state.hand[0])
    assert outcomes
    successor = outcomes[0][1]
    assert successor.score == 1
    assert successor.consumed_stamina_total == 2
    assert successor.p_item_uses
