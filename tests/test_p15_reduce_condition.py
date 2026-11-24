"""P1-5（2026-11-24）P 道具剩余效果语义补全（bounded batch）回归。

本批三块（纯离线、BSD-3 参考引擎 + 主数据/DSL 双重核实，详见 RULES_REFERENCE §5.8）：

1. **层数减少类**（资源 -= N，参考 executeAssignment op "-=" + NON_NEGATIVE_FIELDS
   夹取 ≥0；这些是资源不是 DEBUFF_FIELDS，nullifyDebuff 不拦截）：
   - ExamAggressiveReduce  干劲减少  ↔ DSL motivation-=1（スタイリッシュモード/初恋の証・麻央）
   - ExamLessonBuffReduce  集中减少  ↔ DSL concentration-=1（イケてるセーター/「Pっち」）
   - ExamFullPowerPointReduce 全力值减少 ↔ DSL fullPowerCharge-=2（ユートピアへの誘い；
     引擎 decreaseFullPowerCharge Math.max(0,…) 同口径）→ 独立 PItemDelta.full_power_point_reduce
     （apply_full_power_point 只表达增加，负 delta 按 0）
   - ExamStaminaDamage     体力减少  ↔ DSL cost-=1（私の「初」の楽譜，genki==0 时
     resolveCost 穿透 stamina-=1/consumedStamina+=1）→ 并入 STAMINA_LOSS_EFFECTS
2. **好调回合**（ExamParameterBuff「好调N回合」）：N 在 turn 列 ↔ DSL
   goodConditionTurns+=N（Dearリトルプリンス/共に戦うタオル）→ condition_turns += N。
3. **好调依赖换算**（「好调的N%数值变为打分上升/集中」）：好调 = condition_turns 整数
   ↔ DSL score+=goodConditionTurns*0.3（初陣の証・佑芽）/ concentration+=goodConditionTurns*0.4
   （アニメイト装備）；源段只作系数（不消耗好调回合），目标增量 int(condition_turns×N/100)。

**保持 no-op 如实记录（证据充分但需新机制/真机，留后续）**：好调增加量增加
（ExamParameterBuffAdditive，setGoodConditionTurnsBuff，需增益倍率接线）、元气增加无效
（ExamBlockRestriction，nullifyGenkiTurns）、不安（ExamBlockAddDown，uneaseTurns，delay）、
塔 gimmick（低谷/紧张/弱气/体力回复无效）、全力/强气效果卡打分（setFullPowerEffectBuff/
setStrengthEffectBuff）、日文好調の%分（眠気卡张数条件、无中文）、ExamParameterBuffReduce
（produce/buff_consume 触发未支持）。
"""

from __future__ import annotations

import random
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.sim.expectimax import (
    ExpectState,
    end_turn_state,
    fire_p_items,
    sim_from_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    EXAM_START,
    TURN_START,
    PassiveEvent,
    PassiveState,
    PItemDelta,
    PItemSpec,
    apply_passive,
    classify_effect_target,
    effect_value,
    load_p_items,
    summarize,
)


def _config(**kwargs) -> LessonConfig:
    base = {
        "turns": 4,
        "stamina": 30,
        "target_clear": 1,
        "hand_size": 3,
        "plays_per_turn": 1,
    }
    base.update(kwargs)
    return LessonConfig(**base)


def _card(name: str = "牌", score: float = 10, cost: int = 0, **kwargs) -> CardSpec:
    return CardSpec(name=name, cost=cost, score=score, **kwargs)


def _deck(n: int, **kwargs) -> list[CardSpec]:
    return [_card(f"牌{i}", **kwargs) for i in range(n)]


def _reduce_spec(
    effect_type: str,
    target: str,
    value: int = 1,
    trigger: str = EXAM_START,
    condition: str = "",
    name: str = "减少",
) -> PItemSpec:
    return PItemSpec(
        name=name,
        trigger=trigger,
        effect_type=effect_type,
        value=value,
        target_kind=target,
        condition=condition,
        item_id=name,
    )


def _condition_spec(turns: int = 3, trigger: str = EXAM_START, name: str = "好调") -> PItemSpec:
    """ExamParameterBuff「好调N回合」（N 在 turn 列；value 由 effect_value 读出）。"""
    return PItemSpec(
        name=name,
        trigger=trigger,
        effect_type="ExamParameterBuff",
        value=turns,
        item_id=name,
    )


# ---------------------------------------------------------------- 1. 分类 / 数值


def test_classify_reduce_targets() -> None:
    assert classify_effect_target("ExamAggressiveReduce") == "aggressive_reduce"
    assert classify_effect_target("ExamLessonBuffReduce") == "focus_reduce"
    assert classify_effect_target("ExamFullPowerPointReduce") == "full_power_point_reduce"


def test_stamina_damage_is_stamina_loss() -> None:
    """ExamStaminaDamage 并入固定体力消耗（target=stamina，负增量）。"""
    from gkagent.sim.p_items import STAMINA_LOSS_EFFECTS

    assert "ExamStaminaDamage" in STAMINA_LOSS_EFFECTS
    spec = PItemSpec(name="体力减少", trigger=EXAM_START, effect_type="ExamStaminaDamage", value=1)
    assert spec.target == "stamina"
    assert spec.implemented


def test_effect_value_reduce_reads_value1() -> None:
    for et in ("ExamAggressiveReduce", "ExamLessonBuffReduce", "ExamFullPowerPointReduce"):
        assert effect_value({"type": et, "values": {"value1": 3}}) == 3


def test_effect_value_parameter_buff_reads_turn() -> None:
    """好调N回合：N 在 turn 列；value1 优先（直接加层数旧口径）。"""
    assert effect_value({"type": "ExamParameterBuff", "values": {"turn": 3}}) == 3
    assert effect_value({"type": "ExamParameterBuff", "values": {"value1": 2, "turn": 3}}) == 2
    # 依赖换算源段（values 已清空）→ 0
    assert effect_value({"type": "ExamParameterBuff", "values": {}}) == 0


# ---------------------------------------------------------------- 2. apply_passive 纯函数


def test_apply_passive_aggressive_reduce() -> None:
    spec = _reduce_spec("ExamAggressiveReduce", "aggressive_reduce", 1)
    delta = apply_passive((spec,), PassiveEvent(kind=EXAM_START), PassiveState())
    assert delta.stacks == {"aggressive": -1}
    assert delta.applied == ["减少"]


def test_apply_passive_focus_reduce() -> None:
    spec = _reduce_spec("ExamLessonBuffReduce", "focus_reduce", 2)
    delta = apply_passive((spec,), PassiveEvent(kind=EXAM_START), PassiveState())
    assert delta.stacks == {"focus": -2}


def test_apply_passive_full_power_point_reduce() -> None:
    spec = _reduce_spec("ExamFullPowerPointReduce", "full_power_point_reduce", 3)
    delta = apply_passive((spec,), PassiveEvent(kind=EXAM_START), PassiveState())
    assert delta.full_power_point_reduce == 3
    assert delta.stacks == {}  # 不走 full_power_point 增加渠道


def test_apply_passive_stamina_damage() -> None:
    spec = PItemSpec(name="体力减少", trigger=EXAM_START, effect_type="ExamStaminaDamage", value=1)
    delta = apply_passive((spec,), PassiveEvent(kind=EXAM_START), PassiveState())
    assert delta.stamina == -1
    assert delta.stamina_consumed == 1


def test_apply_passive_condition_turns() -> None:
    spec = _condition_spec(3)
    delta = apply_passive((spec,), PassiveEvent(kind=EXAM_START), PassiveState())
    assert delta.stacks == {"parameter_buff": 3}


def test_apply_passive_condition_conversion() -> None:
    """好调的30%数值变为打分上升：score += int(condition_turns × 30 / 100)。"""
    spec = PItemSpec(
        name="佑芽",
        trigger=EXAM_START,
        effect_type="ExamLesson",
        depends_on="parameter_buff",
        percent=30,
        item_id="佑芽",
    )
    state = PassiveState(stacks={"parameter_buff": 7})
    delta = apply_passive((spec,), PassiveEvent(kind=EXAM_START), state)
    assert delta.score == int(7 * 30 / 100)  # 2
    assert delta.applied == ["佑芽"]


def test_reduce_zero_value_noop() -> None:
    spec = _reduce_spec("ExamAggressiveReduce", "aggressive_reduce", 0)
    delta = apply_passive((spec,), PassiveEvent(kind=EXAM_START), PassiveState())
    assert delta.is_zero()


# ---------------------------------------------------------------- 3. PItemDelta 字段


def test_delta_full_power_point_reduce_merge() -> None:
    a = PItemDelta(full_power_point_reduce=2)
    b = PItemDelta(full_power_point_reduce=3)
    assert not a.is_zero()
    assert a.as_dict()["full_power_point_reduce"] == 2
    a += b
    assert a.full_power_point_reduce == 5
    merged = PItemDelta(full_power_point_reduce=1) + PItemDelta(full_power_point_reduce=4)
    assert merged.full_power_point_reduce == 5


# ---------------------------------------------------------------- 4. LessonSim


def test_lesson_aggressive_reduce_clamp() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.motivation = 5
    sim.p_items = (_reduce_spec("ExamAggressiveReduce", "aggressive_reduce", 2, TURN_START),)
    sim._p_items_by_trigger = {TURN_START: sim.p_items}
    sim._fire_p_items(TURN_START)
    assert sim.motivation == 3


def test_lesson_aggressive_reduce_clamp_zero() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.motivation = 1
    sim.p_items = (_reduce_spec("ExamAggressiveReduce", "aggressive_reduce", 5, TURN_START),)
    sim._p_items_by_trigger = {TURN_START: sim.p_items}
    sim._fire_p_items(TURN_START)
    assert sim.motivation == 0  # 夹取 ≥0


def test_lesson_focus_reduce_clamp() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.buffs.focus = 2
    sim.p_items = (_reduce_spec("ExamLessonBuffReduce", "focus_reduce", 5, TURN_START),)
    sim._p_items_by_trigger = {TURN_START: sim.p_items}
    sim._fire_p_items(TURN_START)
    assert sim.buffs.focus == 0


def test_lesson_full_power_point_reduce_clamp() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.stance = replace(sim.stance, full_power_point=8)
    sim.p_items = (_reduce_spec("ExamFullPowerPointReduce", "full_power_point_reduce", 3, TURN_START),)
    sim._p_items_by_trigger = {TURN_START: sim.p_items}
    sim._fire_p_items(TURN_START)
    assert sim.stance.full_power_point == 5
    assert sim.full_power_point_total == 0  # 减少不计累计


def test_lesson_full_power_point_reduce_clamp_zero() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.stance = replace(sim.stance, full_power_point=2)
    sim.p_items = (_reduce_spec("ExamFullPowerPointReduce", "full_power_point_reduce", 5, TURN_START),)
    sim._p_items_by_trigger = {TURN_START: sim.p_items}
    sim._fire_p_items(TURN_START)
    assert sim.stance.full_power_point == 0


def test_lesson_stamina_damage() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.stamina = 10
    sim.p_items = (PItemSpec(name="体力减少", trigger=TURN_START, effect_type="ExamStaminaDamage", value=1, item_id="x"),)
    sim._p_items_by_trigger = {TURN_START: sim.p_items}
    sim._fire_p_items(TURN_START)
    assert sim.stamina == 9
    assert sim.consumed_stamina_total == 1


def test_lesson_condition_turns_gain() -> None:
    sim = LessonSim(_deck(12), _config(p_items=(_condition_spec(3),)), rng_seed=0)
    assert sim.buffs.condition_turns == 3


def test_lesson_reduce_condition_gate() -> None:
    """干劲在3以上才减：motivation=2 不触发，=3 触发减到 2。"""
    spec = _reduce_spec("ExamAggressiveReduce", "aggressive_reduce", 1, TURN_START, condition="干劲在3以上的时候")
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.motivation = 2
    sim.p_items = (spec,)
    sim._p_items_by_trigger = {TURN_START: sim.p_items}
    sim._fire_p_items(TURN_START)
    assert sim.motivation == 2  # 条件不满足
    sim.motivation = 3
    sim._fire_p_items(TURN_START)
    assert sim.motivation == 2  # 触发减 1


# ---------------------------------------------------------------- 5. ExpectState 双镜


def test_expect_fire_aggressive_reduce() -> None:
    spec = _reduce_spec("ExamAggressiveReduce", "aggressive_reduce", 2)
    state = ExpectState(p_items=(spec,), motivation=5, turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.motivation == 3


def test_expect_fire_focus_reduce_clamp() -> None:
    spec = _reduce_spec("ExamLessonBuffReduce", "focus_reduce", 5)
    state = ExpectState(p_items=(spec,), focus=2, turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.focus == 0


def test_expect_fire_full_power_point_reduce() -> None:
    spec = _reduce_spec("ExamFullPowerPointReduce", "full_power_point_reduce", 3)
    state = ExpectState(p_items=(spec,), stance=("normal", 0, 0, 8), turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.stance_state.full_power_point == 5
    assert state.full_power_point_total == 0


def test_expect_fire_stamina_damage() -> None:
    spec = PItemSpec(name="体力减少", trigger=EXAM_START, effect_type="ExamStaminaDamage", value=1, item_id="x")
    state = ExpectState(p_items=(spec,), stamina=10, stamina_max=30, turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.stamina == 9
    assert state.consumed_stamina_total == 1


def test_expect_fire_condition_turns() -> None:
    state = ExpectState(p_items=(_condition_spec(3),), turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.condition_turns == 3


def test_expect_fire_condition_conversion() -> None:
    spec = PItemSpec(name="佑芽", trigger=EXAM_START, effect_type="ExamLesson", depends_on="parameter_buff", percent=30, item_id="佑芽")
    state = ExpectState(p_items=(spec,), condition_turns=7, turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.score == 2


def test_lesson_expect_reduce_parity() -> None:
    """LessonSim ↔ ExpectState 同事件层数减少逐位对齐。"""
    specs = (
        _reduce_spec("ExamAggressiveReduce", "aggressive_reduce", 2, TURN_START, name="a"),
        _reduce_spec("ExamLessonBuffReduce", "focus_reduce", 1, TURN_START, name="f"),
        _reduce_spec("ExamFullPowerPointReduce", "full_power_point_reduce", 3, TURN_START, name="p"),
    )
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.motivation = 5
    sim.buffs.focus = 4
    sim.stance = replace(sim.stance, full_power_point=8)
    sim.p_items = specs
    sim._p_items_by_trigger = {TURN_START: specs}
    sim._fire_p_items(TURN_START)
    state = ExpectState(p_items=specs, motivation=5, focus=4, stance=("normal", 0, 0, 8), turns_left=4)
    state = fire_p_items(state, TURN_START)
    assert sim.motivation == state.motivation == 3
    assert sim.buffs.focus == state.focus == 3
    assert sim.stance.full_power_point == state.stance_state.full_power_point == 5


def test_state_sim_roundtrip_full_power_point() -> None:
    """state_from_sim / sim_from_state 携带全力值（减少后）。"""
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.stance = replace(sim.stance, full_power_point=5)
    state = state_from_sim(sim)
    assert state.stance_state.full_power_point == 5
    rebuilt = sim_from_state(state, rng=random.Random(1))
    assert rebuilt.stance.full_power_point == 5


def test_end_turn_carries_condition_turns() -> None:
    """好调回合回合末 -1（EOT_DECREMENT_FIELDS）。"""
    state = ExpectState(condition_turns=3, turns_left=3)
    after = end_turn_state(state)
    assert after.condition_turns == 2


# ---------------------------------------------------------------- 6. 数据层 / no-op 记录


def test_catalog_condition_conversion_specs() -> None:
    """好调依赖换算目标 13 段（9 ExamLesson + 4 ExamLessonBuff；P1-8 +2 天生的才能）。"""
    specs = load_p_items()
    targets = [s for s in specs if s.depends_on == "parameter_buff" and s.percent > 0]
    assert len(targets) == 13
    types = {s.effect_type for s in targets}
    assert types == {"ExamLesson", "ExamLessonBuff"}
    assert all(s.implemented for s in targets)


def test_real_item_yume_conversion() -> None:
    """初阵之证・佑芽（pitem_01-1-022-0）：好调的30%数值变为打分上升。"""
    specs = [s for s in load_p_items() if s.item_id == "pitem_01-1-022-0"]
    conv = [s for s in specs if s.effect_type == "ExamLesson" and s.depends_on == "parameter_buff"]
    assert len(conv) == 1
    assert conv[0].percent == 30
    src = [s for s in specs if s.effect_type == "ExamParameterBuff"]
    assert len(src) == 1
    assert src[0].value == 0  # 源段只作系数


def test_catalog_reduce_specs() -> None:
    specs = load_p_items()
    assert sum(1 for s in specs if s.effect_type == "ExamAggressiveReduce" and s.implemented) == 4
    assert sum(1 for s in specs if s.effect_type == "ExamLessonBuffReduce" and s.implemented) == 3
    assert sum(1 for s in specs if s.effect_type == "ExamFullPowerPointReduce" and s.implemented) == 4
    assert sum(1 for s in specs if s.effect_type == "ExamStaminaDamage" and s.implemented) == 2


def test_catalog_condition_turns_specs() -> None:
    """好调N回合（turn 列） implemented 77 段。"""
    specs = load_p_items()
    assert sum(1 for s in specs if s.effect_type == "ExamParameterBuff" and s.implemented) == 77


def test_p_items_implemented_count() -> None:
    """implemented 1067→1164（P1-5 +97）→1179（P1-7 +15）→1181（P1-8 +2）。"""
    summary = summarize(load_p_items())
    assert summary["implemented"] == 1181
    assert summary["noop"] == 668
    assert summary["depends_on_specs"] == 78


def test_deferred_good_condition_gain_noop() -> None:
    """好调增加量增加（ExamParameterBuffAdditive）P1-5 留后续 → P1-7 已实现 condition_gain。"""
    assert classify_effect_target("ExamParameterBuffAdditive") == "condition_gain"
    specs = [s for s in load_p_items() if s.effect_type == "ExamParameterBuffAdditive"]
    assert len(specs) == 4
    assert all(s.implemented for s in specs)


def test_deferred_genki_unease_debuff_noop() -> None:
    """元气增加无效 / 不安 P1-5 留后续 → P1-7 已实现（塔 ∞ 段 value=0 仍 no-op）。"""
    assert classify_effect_target("ExamBlockRestriction") == "nullify_genki_turns"
    assert classify_effect_target("ExamBlockAddDown") == "unease_turns"
    specs = load_p_items()
    restriction = [s for s in specs if s.effect_type == "ExamBlockRestriction"]
    add_down = [s for s in specs if s.effect_type == "ExamBlockAddDown"]
    # 非塔段（turn>0）已实现；塔 gimmick ∞ 段（values 恒空 → value=0）保守 no-op。
    assert sum(1 for s in restriction if s.implemented) == 9
    assert sum(1 for s in add_down if s.implemented) == 2
    assert all(not s.implemented for s in restriction if s.value == 0)
    assert all(not s.implemented for s in add_down if s.value == 0)


def test_deferred_parameter_buff_reduce_unsupported_trigger() -> None:
    """ExamParameterBuffReduce（好调减少）触发 produce/buff_consume 未支持 → no-op。"""
    specs = [s for s in load_p_items() if s.effect_type == "ExamParameterBuffReduce"]
    assert len(specs) == 3
    assert all(not s.implemented for s in specs)


def test_japanese_condition_conversion_implemented() -> None:
    """日文好調の%分（天生的才能）P1-5 留后续 → P1-8 已实现换算（眠気卡张数条件 B10 已解析）。

    源段（ExamParameterBuff 好調の%分）只作系数 value=0/无 depends_on；目标段
    （ExamLesson パラメータ上昇）挂 depends_on=parameter_buff + percent=30/50。
    """
    specs = [s for s in load_p_items() if s.item_id in ("pitem_01-3-346-0", "pitem_01-3-346-1")]
    pb = [s for s in specs if s.effect_type == "ExamParameterBuff"]
    assert pb
    assert all(s.value == 0 and not s.depends_on for s in pb)  # 源段只作系数
    lesson = [s for s in specs if s.effect_type == "ExamLesson"]
    assert len(lesson) == 2
    assert all(s.depends_on == "parameter_buff" and s.implemented for s in lesson)
    assert sorted(s.percent for s in lesson) == [30, 50]
