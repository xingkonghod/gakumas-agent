"""P1-7（2026-11-24）P 道具后续批次（bounded batch）回归。

本批三块新机制 + 一个通用延迟机制（纯离线，BSD-3 参考引擎 + 主数据 + 参考 DSL
三重核实，详见 RULES_REFERENCE §5.9）：

1. **好调增加量增加**（ExamParameterBuffAdditive → condition_gain 增益倍率渠道）：
   参考 ``resolveGoodConditionTurns`` ``goodConditionTurns *= (1 + Σ
   goodConditionTurnsBuffs)``（``setGoodConditionTurnsBuff``，DSL 夜闇の星 313/314
   setGoodConditionTurnsBuff(0.5,4/5)）。乘在好调获得量上向上取整，卡 + P 道具双渠道。
2. **元气增加无效**（ExamBlockRestriction → nullify_genki_turns）/ **不安**
   （ExamBlockAddDown → unease_turns）：参考 ``resolveGenki`` ``if(nullifyGenkiTurns)
   return;`` / ``if(uneaseTurns) genki*=0.67``；两者 ∈ EOT_DECREMENT_FIELDS（回合末 -1）
   且 ∈ DEBUFF_FIELDS（nullifyDebuff 拦截施加）。**只作用 genki+= 渠道**；fixedGenki
   （ExamBlockFix）不受影响（独立 fixed_vitality 字段）。DSL いたずらパペット 149/150、
   初陣の証・美鈴 302/303、雨上がりの花 253/254。
3. **延迟生效**（通用）：主数据 yaml ``e_effect-exam_effect_timer-NNNN-…`` 包装 ↔
   参考 DSL 嵌套 ``at:turn`` / ``delay:NNNN-1``（EffectManager.decrementDelay 每回合末
   -1，到 0 的下一回合开始结算）。34 段标注；修正 おさぼりタオル（nullifyDebuff 下回合）/
   美铃（干劲 3 回合后）/ 温存变更类（下回合）等已实现道具的时序。

**保持 no-op 如实记录**：塔 gimmick（低谷/紧张/弱气/体力回复无效，参考无独立字段）、
塔 ∞ 段（ExamBlockRestriction/ExamBlockAddDown values 恒空 → value=0）、全力・强气效果卡
打分（per-card g.score 成长，values 恒空）、日文好調の%分（眠気卡张数条件）、
ExamParameterBuffReduce（produce/buff_consume 触发未支持）。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.sim.expectimax import (
    ExpectState,
    end_turn_state,
    fire_p_items,
    sim_from_state,
    start_turn_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim, genki_gate
from gkagent.sim.p_items import (
    TURN_START,
    PassiveEvent,
    PassiveState,
    PItemDelta,
    PItemSpec,
    apply_passive,
    classify_effect_target,
    effect_duration,
    effect_value,
    load_p_items,
    summarize,
)


def _config(**kwargs) -> LessonConfig:
    base = {
        "turns": 8,
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


def _spec(effect_type: str, target: str, value: int, *, trigger: str = TURN_START,
          delay: int = 0, name: str = "x", duration: int = 0, max_uses: int = 0) -> PItemSpec:
    return PItemSpec(
        name=name, trigger=trigger, effect_type=effect_type, value=value,
        target_kind=target, item_id=name, delay_turns=delay, duration=duration,
        max_uses=max_uses,
    )


def _by_id(item_id: str) -> list[PItemSpec]:
    return [s for s in load_p_items() if s.item_id == item_id]


# ---------------------------------------------------------------- 1. 分类 / 数值


def test_classify_new_targets() -> None:
    assert classify_effect_target("ExamParameterBuffAdditive") == "condition_gain"
    assert classify_effect_target("ExamBlockRestriction") == "nullify_genki_turns"
    assert classify_effect_target("ExamBlockAddDown") == "unease_turns"


def test_effect_value_nullify_unease_read_turn() -> None:
    assert effect_value({"type": "ExamBlockRestriction", "values": {"turn": 2}}) == 2
    assert effect_value({"type": "ExamBlockAddDown", "values": {"turn": 5}}) == 5
    # 塔 ∞ 段 values 恒空 → 0（保守 no-op）
    assert effect_value({"type": "ExamBlockRestriction", "values": {}}) == 0
    assert effect_value({"type": "ExamBlockAddDown", "values": {}}) == 0


def test_effect_value_condition_gain_permil() -> None:
    eff = {"type": "ExamParameterBuffAdditive", "values": {"percent1": 50, "turn": 4}}
    assert effect_value(eff, "condition_gain") == 500  # 人类百分比 → 千分比
    assert effect_duration(eff, "condition_gain") == 4


# ---------------------------------------------------------------- 2. genki_gate 纯函数


def test_genki_gate_identity() -> None:
    assert genki_gate(10, 0, 0) == 10
    assert genki_gate(0, 0, 0) == 0


def test_genki_gate_nullify() -> None:
    assert genki_gate(10, 1, 0) == 0
    assert genki_gate(10, 2, 1) == 0  # nullify 优先于 unease


def test_genki_gate_unease_ceil() -> None:
    assert genki_gate(12, 0, 1) == 9   # 12×0.67=8.04 → 9
    assert genki_gate(10, 0, 1) == 7   # 6.7 → 7
    assert genki_gate(3, 0, 1) == 3    # 2.01 → 3
    assert genki_gate(1, 0, 1) == 1    # 0.67 → 1


# ---------------------------------------------------------------- 3. PItemDelta freeze/thaw


def test_delta_freeze_thaw_roundtrip() -> None:
    d = PItemDelta(
        score=5, stacks={"vitality": 3}, nullify_genki_turns=2, unease_turns=5,
        fixed_vitality=4, modifiers=[("condition_gain", 500, 4)],
        score_buffs=[(800, 2)], stances=["preservation2"],
    )
    d.delayed.append((3, PItemDelta(unease_turns=5)))
    frozen = d.freeze()
    assert hash(frozen) == hash(d.freeze())  # 可哈希（canonical 用）
    back = PItemDelta.thaw(frozen)
    assert back.score == 5 and back.stacks == {"vitality": 3}
    assert back.nullify_genki_turns == 2 and back.unease_turns == 5
    assert back.fixed_vitality == 4 and back.modifiers == [("condition_gain", 500, 4)]
    assert back.delayed[0][0] == 3 and back.delayed[0][1].unease_turns == 5


def test_delta_merge_new_fields() -> None:
    a = PItemDelta(nullify_genki_turns=2, unease_turns=3, fixed_vitality=4)
    b = PItemDelta(nullify_genki_turns=1, unease_turns=2, fixed_vitality=1)
    a += b
    assert a.nullify_genki_turns == 3 and a.unease_turns == 5 and a.fixed_vitality == 5
    assert not a.is_zero()


# ---------------------------------------------------------------- 4. apply_passive


def test_apply_passive_nullify_unease() -> None:
    specs = [
        _spec("ExamBlockRestriction", "nullify_genki_turns", 2),
        _spec("ExamBlockAddDown", "unease_turns", 5),
    ]
    delta = apply_passive(specs, PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.nullify_genki_turns == 2 and delta.unease_turns == 5


def test_apply_passive_block_fix_separate() -> None:
    """ExamBlock（genki+=）进 stacks.vitality；ExamBlockFix（fixedGenki）进 fixed_vitality。"""
    specs = [
        PItemSpec(name="b", trigger=TURN_START, effect_type="ExamBlock", value=10, item_id="b"),
        PItemSpec(name="f", trigger=TURN_START, effect_type="ExamBlockFix", value=4, item_id="f"),
    ]
    delta = apply_passive(specs, PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.stacks == {"vitality": 10}
    assert delta.fixed_vitality == 4


def test_apply_passive_condition_gain_modifier() -> None:
    spec = _spec("ExamParameterBuffAdditive", "condition_gain", 500, duration=4)
    delta = apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert ("condition_gain", 500, 4) in delta.modifiers


def test_apply_passive_tower_infinite_noop() -> None:
    """塔 ∞ 段 value=0 → 不触发（no-op）。"""
    spec = _spec("ExamBlockRestriction", "nullify_genki_turns", 0)
    delta = apply_passive([spec], PassiveEvent(kind=TURN_START), PassiveState(turn=1))
    assert delta.is_zero()


# ---------------------------------------------------------------- 5. LessonSim 卡渠道


def test_lesson_condition_gain_card() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.modifiers = {"condition_gain": ((500, 4),)}  # +50%
    sim._apply_card_buffs(_card(condition=4))
    assert sim.buffs.condition_turns == 6  # ceil(4×1.5)


def test_lesson_condition_gain_with_additive() -> None:
    """先加 condition_additive 再乘增益倍率（resolveGoodConditionTurns 顺序）。"""
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.buffs.condition_additive = 2
    sim.modifiers = {"condition_gain": ((500, 4),)}
    sim._apply_card_buffs(_card(condition=4))
    assert sim.buffs.condition_turns == 9  # ceil((4+2)×1.5)


def test_lesson_nullify_blocks_card_genki() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.nullify_genki_turns = 2
    sim.motivation = 3
    sim._apply_card_buffs(_card(vitality=5, motivation=2))
    assert sim.vitality == 0          # genki+= 整段无效
    assert sim.motivation == 5        # 干劲是独立赋值，不受影响


def test_lesson_unease_card_genki() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.unease_turns = 5
    sim.motivation = 7
    sim._apply_card_buffs(_card(vitality=5))
    assert sim.vitality == 9          # ceil((5+7)×0.67)=ceil(8.04)


# ---------------------------------------------------------------- 6. LessonSim P 道具渠道


def _fire(sim: LessonSim, specs, kind=TURN_START) -> None:
    sim.p_items = tuple(specs)
    sim._p_items_by_trigger = {kind: tuple(specs)}
    sim._fire_p_items(kind)


def test_lesson_p_item_block_gated_by_unease() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.unease_turns = 5
    spec = PItemSpec(name="b", trigger=TURN_START, effect_type="ExamBlock", value=10, item_id="b")
    _fire(sim, [spec])
    assert sim.vitality == 7          # ceil(10×0.67)


def test_lesson_p_item_block_fix_not_gated() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.unease_turns = 5
    sim.nullify_genki_turns = 2
    spec = PItemSpec(name="f", trigger=TURN_START, effect_type="ExamBlockFix", value=10, item_id="f")
    _fire(sim, [spec])
    assert sim.vitality == 10         # fixedGenki 不受无效/不安影响


def test_lesson_p_item_block_nullified() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.nullify_genki_turns = 2
    spec = PItemSpec(name="b", trigger=TURN_START, effect_type="ExamBlock", value=10, item_id="b")
    _fire(sim, [spec])
    assert sim.vitality == 0


def test_lesson_p_item_condition_gain() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.modifiers = {"condition_gain": ((500, 4),)}
    spec = PItemSpec(name="c", trigger=TURN_START, effect_type="ExamParameterBuff", value=4, item_id="c")
    _fire(sim, [spec])
    assert sim.buffs.condition_turns == 6  # P 道具好调也吃增益倍率


def test_lesson_nullify_debuff_intercepts_nullify_genki() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.nullify_debuff = 1
    _fire(sim, [_spec("ExamBlockRestriction", "nullify_genki_turns", 2)])
    assert sim.nullify_genki_turns == 0   # 被拦截
    assert sim.nullify_debuff == 0        # 消耗 1 次


def test_lesson_nullify_debuff_intercepts_unease() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.nullify_debuff = 1
    _fire(sim, [_spec("ExamBlockAddDown", "unease_turns", 5)])
    assert sim.unease_turns == 0 and sim.nullify_debuff == 0


def test_lesson_eot_decrement_nullify_unease() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.nullify_genki_turns = 2
    sim.unease_turns = 5
    sim.step(None)  # SKIP 结束回合
    assert sim.nullify_genki_turns == 1 and sim.unease_turns == 4


# ---------------------------------------------------------------- 7. 延迟生效（LessonSim）


def test_lesson_delayed_unease_fires_after_3_turns() -> None:
    """雨后的鲜花：turn 1 登记 unease（delay=3），turn 4 开始才生效。"""
    spec = _spec("ExamBlockAddDown", "unease_turns", 5, delay=3, max_uses=1)
    sim = LessonSim(_deck(20), _config(p_items=(spec,)), rng_seed=0)
    # 构造时 turn 1 start 已登记
    assert sim.unease_turns == 0
    assert len(sim._delayed_deltas) == 1 and sim._delayed_deltas[0][0] == 3
    sim.step(None)  # end T1 → countdown 2; T2 start 不触发
    assert sim.unease_turns == 0
    sim.step(None)  # end T2 → 1; T3 start 不触发
    assert sim.unease_turns == 0
    sim.step(None)  # end T3 → 0; T4 start 触发
    assert sim.unease_turns == 5
    assert not sim._delayed_deltas


def test_lesson_delayed_unease_then_eot_decrement() -> None:
    spec = _spec("ExamBlockAddDown", "unease_turns", 5, delay=3, max_uses=1)
    sim = LessonSim(_deck(20), _config(p_items=(spec,)), rng_seed=0)
    for _ in range(3):
        sim.step(None)
    assert sim.unease_turns == 5
    sim.step(None)  # T4 结束 → 4
    assert sim.unease_turns == 4


def test_lesson_delayed_uses_counted_at_registration() -> None:
    """max_uses=1：登记时计次，后续回合不再登记（即使延迟未到点）。"""
    spec = _spec("ExamBlockAddDown", "unease_turns", 5, delay=3, max_uses=1)
    sim = LessonSim(_deck(20), _config(p_items=(spec,)), rng_seed=0)
    assert sim.p_item_uses.get("x") == 1
    sim.step(None)  # T2 start：uses 已满，不再登记
    assert len(sim._delayed_deltas) == 1  # 仍只有 T1 登记的那条


def test_lesson_delayed_stance_change() -> None:
    """温存 2 段階直给 delay=1：登记回合不变指針，下一回合开始才变。"""
    spec = _spec("ExamPreservation", "stance_preservation2", 2, delay=1)
    sim = LessonSim(_deck(20), _config(p_items=(spec,)), rng_seed=0)
    assert str(sim.stance.stance) != "save"
    sim.step(None)  # T2 start 触发
    assert str(sim.stance.stance) == "save" and sim.stance.save_level == 2


# ---------------------------------------------------------------- 8. ExpectState 双镜


def test_expect_fire_nullify_unease() -> None:
    specs = (
        _spec("ExamBlockRestriction", "nullify_genki_turns", 2),
        _spec("ExamBlockAddDown", "unease_turns", 5),
    )
    state = ExpectState(p_items=specs, turns_left=4)
    state = fire_p_items(state, TURN_START)
    assert state.nullify_genki_turns == 2 and state.unease_turns == 5


def test_expect_condition_gain_card() -> None:
    state = ExpectState(modifiers=(("condition_gain", ((500, 4),)),), turns_left=4)
    from gkagent.sim.expectimax import _apply_card_effects
    state, _ = _apply_card_effects(state, _card(condition=4))
    assert state.condition_turns == 6


def test_expect_nullify_blocks_card_genki() -> None:
    from gkagent.sim.expectimax import _apply_card_effects
    state = ExpectState(nullify_genki_turns=2, motivation=3, turns_left=4)
    state, _ = _apply_card_effects(state, _card(vitality=5, motivation=2))
    assert state.vitality == 0 and state.motivation == 5


def test_expect_unease_card_genki() -> None:
    from gkagent.sim.expectimax import _apply_card_effects
    state = ExpectState(unease_turns=5, motivation=7, turns_left=4)
    state, _ = _apply_card_effects(state, _card(vitality=5))
    assert state.vitality == 9


def test_expect_eot_decrement() -> None:
    state = ExpectState(nullify_genki_turns=2, unease_turns=5, turns_left=4)
    after = end_turn_state(state)
    assert after.nullify_genki_turns == 1 and after.unease_turns == 4


def test_expect_delayed_unease_fires_after_3_turns() -> None:
    spec = _spec("ExamBlockAddDown", "unease_turns", 5, delay=3, max_uses=1)
    state = ExpectState(p_items=(spec,), turns_left=8, total_turns=8)
    state = fire_p_items(state, TURN_START)
    assert state.unease_turns == 0 and len(state.delayed) == 1
    for _ in range(3):
        state = end_turn_state(state)
        state = start_turn_state(state)
    assert state.unease_turns == 5 and not state.delayed


def test_expect_delayed_stance_change() -> None:
    spec = _spec("ExamPreservation", "stance_preservation2", 2, delay=1)
    state = ExpectState(p_items=(spec,), turns_left=8, total_turns=8)
    state = fire_p_items(state, TURN_START)
    assert state.stance[0] != "save"
    state = end_turn_state(state)
    state = start_turn_state(state)
    assert state.stance[0] == "save" and state.stance[2] == 2


def test_expect_nullify_debuff_intercepts_nullify_genki() -> None:
    state = ExpectState(
        p_items=(_spec("ExamBlockRestriction", "nullify_genki_turns", 2),),
        nullify_debuff=1, turns_left=4,
    )
    state = fire_p_items(state, TURN_START)
    assert state.nullify_genki_turns == 0 and state.nullify_debuff == 0


def test_lesson_expect_genki_parity() -> None:
    """LessonSim ↔ ExpectState 元气闸门/好调增益逐位对齐。"""
    specs = (
        _spec("ExamBlockRestriction", "nullify_genki_turns", 2, name="n"),
        _spec("ExamBlockAddDown", "unease_turns", 5, name="u"),
    )
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    _fire(sim, specs)
    state = ExpectState(p_items=specs, turns_left=8)
    state = fire_p_items(state, TURN_START)
    assert sim.nullify_genki_turns == state.nullify_genki_turns == 2
    assert sim.unease_turns == state.unease_turns == 5


def test_state_sim_roundtrip_new_fields() -> None:
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.nullify_genki_turns = 2
    sim.unease_turns = 5
    sim._delayed_deltas = [(3, PItemDelta(unease_turns=5))]
    state = state_from_sim(sim)
    assert state.nullify_genki_turns == 2 and state.unease_turns == 5
    assert len(state.delayed) == 1 and state.delayed[0][0] == 3
    rebuilt = sim_from_state(state, rng=random.Random(1))
    assert rebuilt.nullify_genki_turns == 2 and rebuilt.unease_turns == 5
    assert len(rebuilt._delayed_deltas) == 1
    assert rebuilt._delayed_deltas[0][1].unease_turns == 5


def test_canonical_includes_new_fields() -> None:
    a = ExpectState(nullify_genki_turns=2, unease_turns=5, turns_left=4)
    b = ExpectState(nullify_genki_turns=0, unease_turns=0, turns_left=4)
    assert a.canonical() != b.canonical()


# ---------------------------------------------------------------- 9. 真实道具 / 数据层


def test_real_item_star_condition_gain() -> None:
    """暗夜里的明星（夜闇の星 pitem_01-3-161-0）：condition_gain +50% 4 回合。"""
    specs = _by_id("pitem_01-3-161-0")
    cg = [s for s in specs if s.effect_type == "ExamParameterBuffAdditive"]
    assert len(cg) == 1
    assert cg[0].target == "condition_gain" and cg[0].value == 500
    assert cg[0].duration == 4 and cg[0].delay_turns == 0


def test_real_item_flower_unease_delay() -> None:
    """雨后的鲜花（雨上がりの花 pitem_02-3-130-0）：unease 5 回合 delay=3。"""
    specs = _by_id("pitem_02-3-130-0")
    ud = [s for s in specs if s.effect_type == "ExamBlockAddDown"]
    assert len(ud) == 1
    assert ud[0].target == "unease_turns" and ud[0].value == 5 and ud[0].delay_turns == 3


def test_real_item_misuzu_nullify_and_delayed_motivation() -> None:
    """初阵之证・美铃（pitem_02-1-023-0）：nullify 2 回合立即 + 干劲 8 delay=3。"""
    specs = _by_id("pitem_02-1-023-0")
    nr = [s for s in specs if s.effect_type == "ExamBlockRestriction"]
    ag = [s for s in specs if s.effect_type == "ExamCardPlayAggressive"]
    assert nr[0].value == 2 and nr[0].delay_turns == 0
    assert ag[0].value == 8 and ag[0].delay_turns == 3


def test_real_item_towel_nullify_debuff_delay() -> None:
    """偷懒的毛巾（おさぼりタオル pitem_00-2-116-0）：nullifyDebuff 下回合（delay=1）。"""
    specs = _by_id("pitem_00-2-116-0")
    anti = [s for s in specs if s.effect_type == "ExamAntiDebuff"]
    assert anti[0].delay_turns == 1  # P1-7 修正：参考 at:turn 嵌套（下个回合）


def test_real_item_puppet_nullify_genki() -> None:
    """恶作剧木偶（いたずらパペット pitem_01-3-044-0）：nullify_genki 2 回合。"""
    specs = _by_id("pitem_01-3-044-0")
    nr = [s for s in specs if s.effect_type == "ExamBlockRestriction"]
    assert nr[0].target == "nullify_genki_turns" and nr[0].value == 2
    assert nr[0].condition == "体力在50%以下的时候"


def test_delay_annotation_count() -> None:
    """全 catalog delay_turns>0 段 = 34（yaml timer 包装）。"""
    specs = load_p_items()
    assert sum(1 for s in specs if s.delay_turns > 0) == 34


def test_p17_implemented_delta() -> None:
    """P1-7 +15：condition_gain 4 + nullify_genki 9 + unease 2（P1-8 后总数 1181）。"""
    summary = summarize(load_p_items())
    assert summary["implemented"] == 1181
    tgt = summary["implemented_modifier_targets"]
    assert tgt.get("condition_gain") == 4
    assert tgt.get("nullify_genki_turns") == 9
    assert tgt.get("unease_turns") == 2


# ---------------------------------------------------------------- 10. 保持 no-op 如实记录


def test_tower_gimmicks_still_noop() -> None:
    """塔 gimmick 低谷/紧张/弱气/体力回复无效：参考无独立字段 → no-op。"""
    specs = load_p_items()
    for et in ("ExamGimmickSlump", "ExamGimmickLessonDebuff", "ExamGimmickSleepy",
               "ExamStaminaRecoverRestriction"):
        assert all(not s.implemented for s in specs if s.effect_type == et), et


def test_full_power_strength_card_score_still_noop() -> None:
    """全力・强气效果卡打分（per-card g.score 成长，values 恒空）→ no-op。"""
    specs = load_p_items()
    fp = [s for s in specs if s.effect_type == "ExamFullPower" and "打分值增加" in s.effect_text]
    assert fp and all(not s.implemented for s in fp)


def test_parameter_buff_reduce_still_noop() -> None:
    """ExamParameterBuffReduce（produce/buff_consume 触发未支持）→ no-op。"""
    specs = [s for s in load_p_items() if s.effect_type == "ExamParameterBuffReduce"]
    assert len(specs) == 3 and all(not s.implemented for s in specs)
