"""P 道具被动效果的单测：触发时机匹配 / 已实现效果 / 未实现一律 no-op。

数据侧的解析与规模校验另有 test_p_items_data.py；这里只测建模层语义。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.sim.p_items import (
    CARD_PLAY,
    EXAM_START,
    STATUS_GAIN,
    TURN_END,
    TURN_START,
    PassiveEvent,
    PassiveState,
    PItemDelta,
    PItemSpec,
    apply_passive,
    evaluate_condition,
    load_p_items,
    record_to_specs,
    summarize,
    unsupported_effect_types,
)


def make_spec(**kwargs) -> PItemSpec:
    base = {
        "name": "测试道具",
        "trigger": TURN_START,
        "effect_type": "ExamLesson",
        "value": 5,
    }
    base.update(kwargs)
    return PItemSpec(**base)


# ---- 每种已实现效果至少一条 ------------------------------------------------


def test_turn_start_stamina_recover() -> None:
    """回合开始时 体力回复 +2：只加体力，不碰分数。"""
    spec = make_spec(effect_type="ExamStaminaRecoverFix", value=2, label="体力回复")
    delta = apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.stamina == 2
    assert delta.score == 0
    assert delta.is_zero() is False


def test_turn_start_block_stack() -> None:
    """回合开始时 元气 +15 → vitality 层数 +15。"""
    spec = make_spec(effect_type="ExamBlock", value=15, label="元气")
    delta = apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.stacks == {"vitality": 15}
    assert delta.score == 0 and delta.stamina == 0


def test_turn_start_impression_stack() -> None:
    """好印象（ExamReview）叠到 impression。"""
    spec = make_spec(effect_type="ExamReview", value=3, label="好印象")
    delta = apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.stacks == {"impression": 3}


def test_turn_start_focus_stack() -> None:
    """集中（ExamLessonBuff）叠到 focus。"""
    spec = make_spec(effect_type="ExamLessonBuff", value=1, label="集中")
    delta = apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.stacks == {"focus": 1}


def test_turn_end_aggressive_stack() -> None:
    """干劲（ExamCardPlayAggressive）在回合结束事件里叠 aggressive。"""
    spec = make_spec(trigger=TURN_END, effect_type="ExamCardPlayAggressive", value=4, label="干劲")
    assert apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1)).is_zero()
    delta = apply_passive([spec], PassiveEvent(kind=TURN_END), PassiveState(turn=1))
    assert delta.stacks == {"aggressive": 4}


def test_turn_end_full_power_point_stack() -> None:
    """全力值（ExamFullPowerPoint）叠到 full_power_point。"""
    spec = make_spec(trigger=TURN_END, effect_type="ExamFullPowerPoint", value=2, label="全力值")
    delta = apply_passive([spec], PassiveEvent(kind=TURN_END), PassiveState(turn=3))
    assert delta.stacks == {"full_power_point": 2}


def test_card_play_interval_scores_every_n_cards() -> None:
    """回合内每打出 2 张牌 +5 分：只在第 2/4… 张时触发。"""
    spec = make_spec(trigger="card_play_interval", effect_type="ExamLesson", value=5, interval=2)
    state = PassiveState(turn=1)
    for played, expected in ((0, 0), (1, 0), (2, 5), (3, 0), (4, 5)):
        event = PassiveEvent(kind=CARD_PLAY, cards_played_this_turn=played, cards_played_total=played)
        assert apply_passive([spec], event, state).score == expected


def test_card_play_interval_exam_scope_uses_total() -> None:
    """interval_scope="exam" 用整场累计次数；turn 计数对不上就不触发。"""
    spec = make_spec(
        trigger="card_play_interval",
        effect_type="ExamLesson",
        value=3,
        interval=3,
        interval_scope="exam",
    )
    state = PassiveState(turn=2)
    event = PassiveEvent(kind=CARD_PLAY, cards_played_this_turn=1, cards_played_total=3)
    assert apply_passive([spec], event, state).score == 3
    event = PassiveEvent(kind=CARD_PLAY, cards_played_this_turn=3, cards_played_total=2)
    assert apply_passive([spec], event, state).score == 0


def test_card_played_with_category_filter() -> None:
    """主动技能卡使用后：只有打的是主动技能卡才触发。"""
    spec = make_spec(trigger="card_played", effect_type="ExamLesson", value=4, card_filter="ActiveSkill")
    state = PassiveState(turn=1)
    assert apply_passive([spec], PassiveEvent(kind=CARD_PLAY, card_category="ActiveSkill"), state).score == 4
    assert apply_passive([spec], PassiveEvent(kind=CARD_PLAY, card_category="MentalSkill"), state).score == 0
    # 类别未知（不知道打的是什么卡）时保守不触发
    assert apply_passive([spec], PassiveEvent(kind=CARD_PLAY), state).score == 0


def test_status_gain_requires_matching_status() -> None:
    """直接效果使好印象增加后：只在好印象增加时触发。"""
    spec = make_spec(trigger=STATUS_GAIN, effect_type="ExamLesson", value=3, status="impression")
    state = PassiveState(turn=1)
    hit = PassiveEvent(kind=STATUS_GAIN, status="impression", amount=2)
    miss = PassiveEvent(kind=STATUS_GAIN, status="focus", amount=2)
    assert apply_passive([spec], hit, state).score == 3
    assert apply_passive([spec], miss, state).score == 0
    # 事件里没带状态 = 不知道，不触发
    assert apply_passive([spec], PassiveEvent(kind=STATUS_GAIN), state).score == 0


# ---- 触发时机 / 参数 --------------------------------------------------------


def test_trigger_must_match_event() -> None:
    """时机不匹配的事件不触发（回合开始的效果不响应出牌/回合结束）。"""
    spec = make_spec(effect_type="ExamLesson", value=7)
    assert apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1)).score == 7
    assert apply_passive([spec], PassiveEvent(kind=TURN_END), PassiveState(turn=1)).score == 0
    assert apply_passive([spec], PassiveEvent(kind=CARD_PLAY), PassiveState(turn=1)).score == 0


def test_specific_turn_param() -> None:
    """「第4回合开始时」只在第 4 回合触发。"""
    spec = make_spec(effect_type="ExamLesson", value=10, turn=4)
    assert apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=4)).score == 10
    assert apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=3)).score == 0


def test_remaining_turns_param_needs_state() -> None:
    """「剩余 2 回合内」：state 不给剩余回合数时不触发。"""
    spec = make_spec(effect_type="ExamLesson", value=6, remaining_turns=2)
    event = PassiveEvent(kind=TURN_START)
    assert apply_passive([spec], event, PassiveState(turn=8)).score == 0
    assert apply_passive([spec], event, PassiveState(turn=8, turns_left=2)).score == 6
    assert apply_passive([spec], event, PassiveState(turn=8, turns_left=3)).score == 0


def test_final_turn_and_lesson_filter() -> None:
    """最终回合 / 【仅限歌唱训练】：状态没给就不触发。"""
    final = make_spec(effect_type="ExamLesson", value=8, final_turn=True)
    event = PassiveEvent(kind=TURN_START)
    assert apply_passive([final], event, PassiveState(turn=5)).score == 0
    assert apply_passive([final], event, PassiveState(turn=5, is_final_turn=True)).score == 8

    vocal = make_spec(effect_type="ExamLesson", value=2, lesson_filter="vocal")
    assert apply_passive([vocal], event, PassiveState(turn=1)).score == 0
    assert apply_passive([vocal], event, PassiveState(turn=1, lesson_type="vocal")).score == 2


def test_max_uses_capped_only_when_uses_given() -> None:
    """次数上限：state.uses 给了才封顶（没给就按不限处理）。"""
    spec = make_spec(effect_type="ExamLesson", value=2, item_id="pitem_x", max_uses=2)
    event = PassiveEvent(kind=TURN_START)
    assert apply_passive([spec], event, PassiveState(turn=1, uses={"pitem_x": 0})).score == 2
    assert apply_passive([spec], event, PassiveState(turn=1, uses={"pitem_x": 2})).score == 0
    assert apply_passive([spec], event, PassiveState(turn=1)).score == 2


# ---- 条件求值 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("condition", "stacks", "expected"),
    [
        ("好印象在6以上的时候", {"impression": 6}, True),
        ("好印象在6以上的时候", {"impression": 5}, False),
        ("元气为0的时候", {"vitality": 0}, True),
        ("元气为0的时候", {"vitality": 3}, False),
        ("好调状态的时候", {"parameter_buff": 1}, True),
        ("好调状态的时候", {}, False),
        # 指针类条件（强气/温存/全力）也要求模拟器把指針当层数喂进来
        ("强气的时候", {"stance_concentration": 1}, True),
        ("全力的时候", {}, False),
    ],
)
def test_evaluate_condition_on_stacks(condition: str, stacks: dict, expected: bool) -> None:
    assert evaluate_condition(condition, PassiveState(stacks=stacks)) is expected


def test_evaluate_condition_remaining_turns() -> None:
    """剩余 N 回合内：state 不给剩余回合数时返回 None（保守不触发）。"""
    assert evaluate_condition("剩余2回合内", PassiveState(turns_left=2)) is True
    assert evaluate_condition("剩余2回合内", PassiveState(turns_left=3)) is False
    assert evaluate_condition("剩余2回合内的时候", PassiveState(turns_left=1)) is True
    assert evaluate_condition("剩余2回合内的时候", PassiveState()) is None


def test_evaluate_condition_stamina_percent() -> None:
    """体力百分比条件；stamina_max 未知（0）时返回 None。"""
    state = PassiveState(stamina=50, stamina_max=100)
    assert evaluate_condition("体力在50%以上的时候", state) is True
    assert evaluate_condition("体力在80%以上的时候", state) is False
    assert evaluate_condition("体力在50%以下的时候", PassiveState(stamina=40, stamina_max=100)) is True
    assert evaluate_condition("体力在50%以上的时候", PassiveState(stamina=50)) is None


def test_evaluate_condition_unknown_returns_none() -> None:
    """认不出的条件返回 None，apply_passive 就当不触发。"""
    assert evaluate_condition("牌堆或弃牌中的干扰卡在7张以上的时候", PassiveState()) is None
    assert evaluate_condition("刚刚使用过辅助技能卡的时候", PassiveState()) is None
    assert evaluate_condition("", PassiveState()) is True


def test_condition_param_buff_turns_and_full_power_total() -> None:
    """B8：好调按剩余回合数比较；累计全力值看本场累计（伪 stack key）。

    好调在模拟器里的 stack 投影就是剩余回合数（``LessonSim._passive_state``），所以
    「好调在 N 回合以上」可以直接比层数；累计全力值没有单独状态字段，用
    ``full_power_point_total`` 伪 key。认不出的写法仍返回 None（保守）。
    """
    assert (
        evaluate_condition("好调在6回合以上的时候", PassiveState(stacks={"parameter_buff": 6}))
        is True
    )
    assert (
        evaluate_condition("好调在6回合以上的时候", PassiveState(stacks={"parameter_buff": 5}))
        is False
    )
    assert (
        evaluate_condition(
            "这个训练中的累计全力值在5以上的时候",
            PassiveState(stacks={"full_power_point_total": 5}),
        )
        is True
    )
    assert (
        evaluate_condition(
            "累计全力值在5以上的时候", PassiveState(stacks={"full_power_point_total": 4})
        )
        is False
    )
    assert evaluate_condition("强气2阶段的时候", PassiveState(stacks={"stance_concentration": 2})) is None


def test_condition_false_blocks_trigger() -> None:
    """条件不满足时不触发（好印象≥6 的效果在 5 层时不加分）。"""
    spec = make_spec(effect_type="ExamLesson", value=9, condition="好印象在6以上的时候")
    event = PassiveEvent(kind=TURN_START)
    assert apply_passive([spec], event, PassiveState(turn=1, stacks={"impression": 6})).score == 9
    assert apply_passive([spec], event, PassiveState(turn=1, stacks={"impression": 5})).score == 0


# ---- 未实现：必须 no-op，不得抛异常 ----------------------------------------


@pytest.mark.parametrize(
    "effect_type",
    [
        # B9 起 ExamLessonValueMultiple 已实现（持久分数倍率）；P1-2 起
        # ExamLessonValueMultipleDependReviewOrAggressive 已实现（自尊 pride_turns，
        # 见 tests/test_p12_hand_decrease_pride.py）；这里留真正没建模的：
        "ExamConcentration",  # 指針直给必须先有「强气变更」文本，否则保守 no-op（B9）
        "ExamPreservation",  # 同上（「温存变更」文本才触发）
        "ExamCardCreateId",  # 生成卡：未标注 create（随机/卡名未知）仍 no-op；确定式见 B10
        "unknown",
        "",
    ],
)
def test_unsupported_effect_type_is_noop(effect_type: str) -> None:
    spec = make_spec(effect_type=effect_type, value=10)
    delta = apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.is_zero()
    assert delta.applied == []
    assert spec.implemented is False


@pytest.mark.parametrize(
    "trigger",
    [
        "buff_consume",
        "produce_start_lesson",
        "card_play_interval_after",
        "no_such_trigger",
        "",
    ],
)
def test_unsupported_trigger_is_noop(trigger: str) -> None:
    spec = make_spec(trigger=trigger, effect_type="ExamLesson", value=10)
    for kind in (TURN_START, TURN_END, CARD_PLAY, STATUS_GAIN, EXAM_START):
        delta = apply_passive([spec], PassiveEvent(kind=kind), PassiveState(turn=1))
        assert delta.is_zero()


def test_exam_start_fires_only_on_exam_start_event() -> None:
    """训练/考试开始类效果只在 EXAM_START 事件触发；回合事件不触发。"""
    spec = make_spec(trigger=EXAM_START, effect_type="ExamLesson", value=9)
    assert spec.implemented is True
    for kind in (TURN_START, TURN_END, CARD_PLAY, STATUS_GAIN):
        assert apply_passive([spec], PassiveEvent(kind=kind), PassiveState(turn=1)).is_zero()
    delta = apply_passive([spec], PassiveEvent(kind=EXAM_START), PassiveState(turn=1))
    assert delta.score == 9
    assert delta.applied == [spec.item_id or spec.name]


def test_extra_play_effect_adds_action_slot() -> None:
    """ExamPlayableValueAdd（技能卡使用数追加）→ extra_plays，不是分数/层数。"""
    spec = make_spec(trigger=EXAM_START, effect_type="ExamPlayableValueAdd", value=1)
    assert spec.target == "extra_plays"
    delta = apply_passive([spec], PassiveEvent(kind=EXAM_START), PassiveState(turn=1))
    assert delta.extra_plays == 1
    assert delta.score == 0 and delta.stamina == 0 and not delta.stacks
    assert delta.is_zero() is False


def test_extra_play_zero_value_is_noop() -> None:
    spec = make_spec(effect_type="ExamPlayableValueAdd", value=0)
    delta = apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.is_zero()


def test_no_value_is_noop() -> None:
    """有触发、效果类型也认识，但数值是 0（例如只有百分比）→ no-op。"""
    spec = make_spec(effect_type="ExamLesson", value=0)
    assert apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1)).is_zero()


# ---- 增量对象 / 数据加载 ---------------------------------------------------


def test_delta_accumulates() -> None:
    """PItemDelta 可累加，applied 记录触发了哪些道具。"""
    a = PItemDelta(score=5, stamina=1, extra_plays=1, stacks={"vitality": 2}, applied=["a"])
    b = PItemDelta(score=1, stacks={"vitality": 3, "focus": 1}, applied=["b"])
    merged = a + b
    assert (merged.score, merged.stamina, merged.extra_plays) == (6, 1, 1)
    assert merged.stacks == {"vitality": 5, "focus": 1}
    assert merged.applied == ["a", "b"]
    assert a.stacks == {"vitality": 2}  # 原对象不被改
    assert PItemDelta().is_zero()
    assert PItemDelta(extra_plays=1).is_zero() is False


def test_record_to_specs_expands_effects() -> None:
    """一条记录有多个效果时展开成多条 spec；没有效果的记录也留一条 unknown。"""
    record = {
        "id": "pitem_test",
        "name": "测试",
        "rarity": "SR",
        "trigger": TURN_START,
        "condition": "",
        "max_uses": 2,
        "trigger_params": {},
        "effects": [
            {"type": "ExamBlock", "label": "元气", "values": {"value1": 5}, "max_uses": 0},
            {"type": "ExamLessonBuff", "label": "集中", "values": {"value1": 2, "count": 3}, "max_uses": 3},
        ],
        "text_zh": "回合开始时，元气+5集中+2",
    }
    specs = record_to_specs(record)
    assert [s.effect_type for s in specs] == ["ExamBlock", "ExamLessonBuff"]
    assert [s.value for s in specs] == [5, 2]
    assert specs[0].max_uses == 2  # 记录级次数上限兜底
    assert specs[1].max_uses == 3  # 效果自带（「（3次）」）
    assert specs[0].item_id == "pitem_test"

    empty = record_to_specs({**record, "effects": []})
    assert len(empty) == 1 and empty[0].effect_type == "unknown" and empty[0].implemented is False


def test_record_to_specs_uses_count_for_playable_add() -> None:
    """技能卡使用数追加的 N 在 ``count`` 列（不是 value1）——别被解析成 0 分。"""
    record = {
        "id": "pitem_test",
        "name": "再动 P 道具",
        "rarity": "SR",
        "trigger": EXAM_START,
        "condition": "",
        "max_uses": 1,
        "trigger_params": {},
        "effects": [
            {"type": "ExamPlayableValueAdd", "label": "技能卡使用数追加", "values": {"count": 1}},
        ],
        "text_zh": "训练开始时，技能卡使用数追加+1（训练内1次）",
    }
    specs = record_to_specs(record)
    assert len(specs) == 1
    assert specs[0].value == 1
    assert specs[0].target == "extra_plays"
    assert specs[0].implemented is True
    assert specs[0].max_uses == 1


def test_record_to_specs_carries_condition_known_and_ja_text() -> None:
    """B7：新增道具的记录带 ``condition_known=False`` + ``i18n_text_source="ja"``。

    - 条件未知的 spec **不触发**（别把带条件的道具当无条件结算）；
    - 中文描述缺失时 ``text`` 回退 yaml 日文（调试可见），不是空串。
    """
    record = {
        "id": "pitem_new-001",
        "name": "新道具",
        "rarity": "SSR",
        "trigger": TURN_START,
        "condition": "",
        "condition_known": False,
        "max_uses": 0,
        "trigger_params": {},
        "effects": [{"type": "ExamBlock", "label": "元气", "values": {"value1": 7}, "max_uses": 0}],
        "text_zh": "",
        "text_ja": "ターン開始時、元気+7",
        "i18n_text_source": "ja",
    }
    specs = record_to_specs(record)
    assert len(specs) == 1
    assert specs[0].condition_known is False
    assert specs[0].text == "ターン開始時、元気+7"
    # data 层仍算 implemented（效果/触发/数值都清楚），但 apply_passive 保守跳过。
    assert specs[0].implemented is True
    delta = apply_passive([specs[0]], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.is_zero() is True
    # 同一条件已知的 spec 会正常触发（对照组）。
    known = record_to_specs({**record, "condition_known": True})[0]
    assert apply_passive([known], PassiveEvent(kind=TURN_START), PassiveState(turn=1)).stacks == {"vitality": 7}


def test_summarize_counts_condition_unknown() -> None:
    """``summarize`` 单独统计条件未知的 spec（不混进 implemented/noop 口径）。"""
    known = make_spec(effect_type="ExamBlock", value=5)
    unknown = make_spec(effect_type="ExamBlock", value=5, condition_known=False)
    summary = summarize([known, unknown])
    assert summary["condition_unknown"] == 1
    assert summary["implemented"] == 2  # 效果/触发/数值都清楚；触发与否由 apply_passive 决定


def test_real_data_playable_add_count_is_extracted() -> None:
    """真数据里 51 条 ExamPlayableValueAdd 全是 count=1；不能退化成 0 值 no-op。

    B8 起 47 段 implemented（B7 是 44）：新增的 ``turn_start_after`` / ``stamina_reduce``
    等触发时机也支持了，所以带这些时机的「技能卡使用数追加」不再算 no-op。
    """
    specs = [spec for spec in load_p_items() if spec.effect_type == "ExamPlayableValueAdd"]
    assert len(specs) == 51
    assert all(spec.value == 1 for spec in specs)
    assert all(spec.target == "extra_plays" for spec in specs)
    assert sum(1 for spec in specs if spec.implemented) == 47


def test_load_real_data_and_never_raise() -> None:
    """真数据（1115 件道具 = 本地 1068 + 上游新增 47）能加载，四种事件全过一遍都不抛异常。"""
    specs = load_p_items()
    assert len(specs) > 1000
    assert all(isinstance(spec, PItemSpec) for spec in specs)
    assert all(spec.name for spec in specs)

    state = PassiveState(turn=3, turns_left=3, stamina=50, stamina_max=100, lesson_type="vocal")
    events = [
        PassiveEvent(kind=TURN_START),
        PassiveEvent(kind=TURN_END),
        PassiveEvent(kind=CARD_PLAY, card_category="ActiveSkill", cards_played_this_turn=2, cards_played_total=2),
        PassiveEvent(kind=STATUS_GAIN, status="impression", amount=1),
    ]
    for event in events:
        delta = apply_passive(specs, event, state)
        assert isinstance(delta, PItemDelta)
        assert delta.is_zero() is False  # 真数据每种事件都该有点东西

    summary = summarize(specs)
    assert summary["implemented"] > 0
    assert summary["noop"] > 0
    assert isinstance(unsupported_effect_types(specs), list)


def test_real_data_covers_every_implemented_effect_type() -> None:
    """数据里 7 种已实现效果都能对上（防止解析口径变了悄悄退化成 no-op）。"""
    summary = summarize(load_p_items())
    implemented = summary["implemented_effect_types"]
    for effect_type in (
        "ExamLesson",
        "ExamStaminaRecoverFix",
        "ExamBlock",
        "ExamReview",
        "ExamLessonBuff",
        "ExamCardPlayAggressive",
        "ExamFullPowerPoint",
        "ExamPlayableValueAdd",
    ):
        assert implemented.get(effect_type, 0) > 0, effect_type


def test_data_file_stats_are_consistent() -> None:
    """p_items.json 的 stats 必须和 items 对得上（防止手改/生成半截）。"""
    path = Path(__file__).resolve().parents[1] / "data" / "knowledge" / "p_items.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    items = payload["items"]
    stats = payload["stats"]

    assert stats["count"] == len(items)
    assert len({item["id"] for item in items}) == len(items)  # id 唯一
    assert all(item["name"] for item in items)
    assert {item["rarity"] for item in items} <= {"N", "R", "SR", "SSR", "unknown"}
    assert sum(stats["trigger"].values()) == len(items)
    rebuilt: dict[str, int] = {}
    for item in items:
        for effect in item["effects"]:
            rebuilt[effect["type"]] = rebuilt.get(effect["type"], 0) + 1
    assert rebuilt == stats["effect_types"]
    # B7：本地 master 件数 + yaml 新增件数 = 总数；中文缺失/条件未知都显式计数。
    assert stats["items_local_master"] + stats["items_from_yaml"] == len(items)
    assert sum(1 for item in items if item.get("i18n_text_source") == "ja") == stats["items_i18n_text_ja"]
    assert (
        sum(1 for item in items if item.get("condition_known") is False)
        == stats["items_condition_unknown"]
    )
