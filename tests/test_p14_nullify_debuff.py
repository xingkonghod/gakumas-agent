"""P1-4（2026-11-24）nullifyDebuff 低下状态无效拦截 + ⑦/countDebuffs 评估回归。

覆盖五块：

1. 纯规则 ``intercept_debuff_entries``：逐条消耗无效次数拦截 debuff 施加
   （参考 Executor.executeAssignment/executeCallAction：nullifyDebuff>0 时
   每条 setScoreDebuff/setHandDecrease 消耗 1 次并整条跳过）；
2. P 道具解析：``ExamAntiDebuff`` values.count → nullify_debuff 目标
   （classify_effect_target / effect_value / apply_passive / 主数据 11 段）；
3. LessonSim：nullify_debuff 计数器累加、拦截 score_debuffs/hand_decreases、
   无回合倒计时（消耗式，不在 EOT_DECREMENT_FIELDS）、默认 0 不拦截；
4. ExpectState 双镜：fire_p_items / state_from_sim / sim_from_state / canonical /
   end_turn_state 携带 / LessonSim↔ExpectState 逐位对齐；
5. 数据层与 no-op 如实记录：⑦ ExamBuffConsumptionAdd 保持 no-op（卡模型不承载
   buff 花费）、countDebuffs 无落点（参考+主数据零使用）、implemented 1056→1067。

证据（BSD-3 gakumas-tools + 主数据交叉，详见 RULES_REFERENCE §5.7）：
- ``engine/Executor/index.js`` executeAssignment :429 / executeCallAction :507 /
  executeSpecialAction :545：nullifyDebuff>0 且 lhs∈DEBUFF_FIELDS（或动作∈
  DEBUFF_SPECIAL_ACTIONS）→ nullifyDebuff-- 并 return（整条跳过）；
- ``constants.js`` DEBUFF_SPECIAL_ACTIONS = setScoreDebuff/decreaseFullPowerCharge/
  setHandDecrease；DEBUFF_FIELDS 16 项；nullifyDebuff 不在 EOT_DECREMENT_FIELDS；
- ``engine/BuffManager.js`` initializeState :118 nullifyDebuff=0（标量）；
- 主数据 ``ExamAntiDebuff`` values.count（P 道具侧 11 段：偷懒的毛巾 pitem_00-2-116-0
  + 塔 gimmick 初星灯光/旗帜/道具 10 段）；参考 ``p_items.csv`` 317 おさぼりタオル
  ``at:turn { nullifyDebuff+=1; limit:1 }``；卡侧 4 SSR 族（アイドル魂/正確無比な看板づくり/
  紅葉ランニング/スイートトラップ♡）``nullifyDebuff+=1`` 但主数据 values 恒空（延迟）。

⑦ ExamBuffConsumptionAdd（参考 doubleBuffCostTurns，processCost 时 BUFF_FIELDS 花费×2）：
主数据 4 段（不息的风暴 pitem_03-3-345-0/1、迷倒世界的模样 pitem_01-3-349-0/1），
gkbench 22 loadout；但卡模型不承载 buff 花费（card_table cost=0、CardSpec 无 buff_cost
字段，88 张参考 buff-cost 卡未建模花费）→ 机制无落点，保持 no-op。
countDebuffs（低下状態の数，BuffManager.countDebuffs :331，参考标注 UNVERIFIED）：
参考全部 CSV + 主数据零使用 → 无落点，保持未建模。
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
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    EXAM_START,
    PItemSpec,
    apply_passive,
    classify_effect_target,
    effect_value,
    intercept_debuff_entries,
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


def _nullify_spec(count: int = 1, trigger: str = EXAM_START, name: str = "无效") -> PItemSpec:
    """ExamAntiDebuff「低下状态无效N次」（values.count；消耗式计数器）。"""
    return PItemSpec(
        name=name,
        trigger=trigger,
        effect_type="ExamAntiDebuff",
        value=count,
        target_kind="nullify_debuff",
        item_id=name,
    )


def _score_debuff_spec(
    amount: int = 100, turns: int = 1, trigger: str = EXAM_START, name: str = "减分"
) -> PItemSpec:
    """打分上升量减少（setScoreDebuff，千分比；DEBUFF_SPECIAL_ACTIONS 之一）。"""
    return PItemSpec(
        name=name,
        trigger=trigger,
        effect_type="ExamLessonValueMultipleDown",
        value=amount,
        target_kind="score_debuff",
        duration=turns,
        item_id=name,
    )


def _hand_decrease_spec(
    amount: int = 1, turns: int = 0, trigger: str = EXAM_START, name: str = "手牌减少"
) -> PItemSpec:
    """手牌减少（setHandDecrease，DEBUFF_SPECIAL_ACTIONS 之一；turns=0 → 永久 -1）。"""
    return PItemSpec(
        name=name,
        trigger=trigger,
        effect_type="ExamGimmickStartTurnCardDrawDown",
        value=amount,
        target_kind="hand_decrease",
        duration=turns,
        item_id=name,
    )


# ---------------------------------------------------------------- 1. 纯规则拦截


def test_intercept_zero_charges_no_block() -> None:
    """nullify<=0 → 原样返回（不拦截）。"""
    entries = [(100, 1), (200, 2)]
    assert intercept_debuff_entries(0, entries) == (0, entries)
    assert intercept_debuff_entries(-1, entries) == (-1, entries)


def test_intercept_blocks_per_entry() -> None:
    """每条 debuff 消耗 1 次：2 次挡前 2 条，第 3 条保留。"""
    remaining, kept = intercept_debuff_entries(2, [(100, 1), (200, 2), (300, -1)])
    assert remaining == 0
    assert kept == [(300, -1)]


def test_intercept_excess_charges_remain() -> None:
    """次数多于条目：全挡，剩余次数保留（消耗式不浪费）。"""
    remaining, kept = intercept_debuff_entries(5, [(100, 1), (200, 2)])
    assert remaining == 3
    assert kept == []


def test_intercept_empty_entries() -> None:
    """无 debuff 条目：次数不变。"""
    assert intercept_debuff_entries(3, []) == (3, [])


def test_intercept_single_block() -> None:
    """1 次挡 1 条。"""
    remaining, kept = intercept_debuff_entries(1, [(100, 1)])
    assert remaining == 0
    assert kept == []


# ---------------------------------------------------------------- 2. P 道具解析


def test_classify_exam_anti_debuff() -> None:
    """ExamAntiDebuff → nullify_debuff 目标。"""
    assert classify_effect_target("ExamAntiDebuff") == "nullify_debuff"
    assert classify_effect_target("ExamAntiDebuff", "低下状态无效2次") == "nullify_debuff"


def test_effect_value_reads_count() -> None:
    """数值取 values.count（不是 value1）。"""
    effect = {"type": "ExamAntiDebuff", "values": {"count": 2}, "text": "低下状态无效2次"}
    assert effect_value(effect, "nullify_debuff") == 2
    # count 缺失时回退 value1
    assert effect_value({"type": "ExamAntiDebuff", "values": {"value1": 3}}, "nullify_debuff") == 3


def test_apply_passive_nullify_delta() -> None:
    """apply_passive：ExamAntiDebuff → delta.nullify_debuff（纯函数）。"""
    from gkagent.sim.p_items import PassiveEvent, PassiveState

    spec = _nullify_spec(2)
    delta = apply_passive((spec,), PassiveEvent(kind=EXAM_START), PassiveState())
    assert delta.nullify_debuff == 2
    assert delta.applied == ["无效"]


def test_catalog_anti_debuff_specs() -> None:
    """主数据 11 段 ExamAntiDebuff 全部解析为 nullify_debuff（P 道具侧有 count）。"""
    specs = [s for s in load_p_items() if s.effect_type == "ExamAntiDebuff"]
    assert len(specs) == 11
    assert all(s.target == "nullify_debuff" for s in specs)
    assert all(s.value > 0 for s in specs)


def test_real_item_towel_spec() -> None:
    """偷懒的毛巾（pitem_00-2-116-0，おさぼりタオル）：舞蹈回合开始无效 1 次。"""
    specs = [s for s in load_p_items() if s.item_id == "pitem_00-2-116-0"]
    anti = [s for s in specs if s.effect_type == "ExamAntiDebuff"]
    assert len(anti) == 1
    assert anti[0].value == 1
    assert anti[0].target == "nullify_debuff"


def test_anti_debuff_implemented_not_noop() -> None:
    """ExamAntiDebuff 不再是 no-op（implemented +11）。"""
    summary = summarize(load_p_items())
    assert summary["noop_effect_types"].get("ExamAntiDebuff") is None
    assert summary["implemented_effect_types"].get("ExamAntiDebuff") == 11
    assert summary["implemented_modifier_targets"].get("nullify_debuff") == 11


# ---------------------------------------------------------------- 3. LessonSim


def test_nullify_counter_accumulates() -> None:
    """exam_start：nullify_debuff 累加（多个来源合算）。"""
    specs = (_nullify_spec(1, name="a"), _nullify_spec(2, name="b"))
    sim = LessonSim(_deck(12), _config(p_items=specs), rng_seed=0)
    assert sim.nullify_debuff == 3


def test_nullify_blocks_score_debuff() -> None:
    """有无效次数 → setScoreDebuff 被拦截（score_debuffs 空）。"""
    specs = (_nullify_spec(1), _score_debuff_spec(100, 1))
    sim = LessonSim(_deck(12), _config(p_items=specs), rng_seed=0)
    assert sim.nullify_debuff == 0  # 消耗 1 次
    assert sim.score_debuffs == ()


def test_nullify_blocks_hand_decrease() -> None:
    """有无效次数 → setHandDecrease 被拦截（手牌不减，仍 3 张）。"""
    specs = (_nullify_spec(1), _hand_decrease_spec(1))
    sim = LessonSim(_deck(12), _config(p_items=specs), rng_seed=0)
    assert sim.nullify_debuff == 0
    assert sim.hand_decreases == ()
    assert len(sim.hand) == 3  # 未被减少


def test_nullify_blocks_both_order() -> None:
    """拦截顺序 score_debuffs → hand_decreases：1 次只挡 score_debuff，hand_decrease 保留。"""
    specs = (_nullify_spec(1), _score_debuff_spec(100, 1), _hand_decrease_spec(1))
    sim = LessonSim(_deck(12), _config(p_items=specs), rng_seed=0)
    assert sim.nullify_debuff == 0
    assert sim.score_debuffs == ()  # 被挡
    assert sim.hand_decreases == ((1, -1),)  # 保留
    assert len(sim.hand) == 2


def test_nullify_no_eot_decrement() -> None:
    """消耗式计数器无回合倒计时：剩余次数跨回合保持（不在 EOT_DECREMENT_FIELDS）。"""
    sim = LessonSim(_deck(20), _config(p_items=(_nullify_spec(3),)), rng_seed=0)
    assert sim.nullify_debuff == 3
    sim.step(None)  # SKIP → 下一回合
    assert sim.nullify_debuff == 3
    sim.step(None)
    assert sim.nullify_debuff == 3


def test_nullify_default_zero_debuffs_applied() -> None:
    """无无效次数 → debuff 正常施加（默认逐位不变）。"""
    specs = (_score_debuff_spec(100, 1), _hand_decrease_spec(1))
    sim = LessonSim(_deck(12), _config(p_items=specs), rng_seed=0)
    assert sim.nullify_debuff == 0
    assert sim.score_debuffs == ((100, 1),)
    assert sim.hand_decreases == ((1, -1),)
    assert len(sim.hand) == 2


def test_nullify_partial_block_multiple_debuffs() -> None:
    """2 次无效挡 2 条 score_debuff，第 3 条保留。"""
    specs = (
        _nullify_spec(2),
        _score_debuff_spec(100, 1, name="d1"),
        _score_debuff_spec(200, 2, name="d2"),
        _score_debuff_spec(300, -1, name="d3"),
    )
    sim = LessonSim(_deck(12), _config(p_items=specs), rng_seed=0)
    assert sim.nullify_debuff == 0
    assert sim.score_debuffs == ((300, -1),)


# ---------------------------------------------------------------- 4. ExpectState 双镜


def test_expect_fire_nullify_counter() -> None:
    """fire_p_items exam_start → nullify_debuff 落状态。"""
    state = ExpectState(p_items=(_nullify_spec(2),), turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.nullify_debuff == 2


def test_expect_fire_blocks_score_debuff() -> None:
    """fire_p_items：有无效次数 → score_debuffs 被拦截。"""
    state = ExpectState(p_items=(_nullify_spec(1), _score_debuff_spec(100, 1)), turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.nullify_debuff == 0
    assert state.score_debuffs == ()


def test_expect_fire_blocks_hand_decrease() -> None:
    """fire_p_items：有无效次数 → hand_decreases 被拦截。"""
    state = ExpectState(p_items=(_nullify_spec(1), _hand_decrease_spec(1)), turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.nullify_debuff == 0
    assert state.hand_decreases == ()
    assert state.turn_draw_count == 3


def test_state_sim_roundtrip_nullify() -> None:
    """state_from_sim / sim_from_state 双镜带上 nullify_debuff。"""
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.nullify_debuff = 2
    state = state_from_sim(sim)
    assert state.nullify_debuff == 2
    rebuilt = sim_from_state(state, rng=random.Random(1))
    assert rebuilt.nullify_debuff == 2


def test_canonical_includes_nullify() -> None:
    """canonical 区分 nullify_debuff（不同次数 → 不同 canonical）。"""
    a = ExpectState(nullify_debuff=0)
    b = ExpectState(nullify_debuff=2)
    assert a.canonical() != b.canonical()


def test_end_turn_carries_nullify() -> None:
    """end_turn_state 携带 nullify_debuff（无回合倒计时）。"""
    state = ExpectState(nullify_debuff=2, turns_left=3)
    after = end_turn_state(state)
    assert after.nullify_debuff == 2
    assert end_turn_state(after).nullify_debuff == 2


def test_lesson_expect_nullify_parity() -> None:
    """LessonSim ↔ ExpectState 同事件 nullify_debuff/score_debuffs/hand_decreases 逐位对齐。"""
    specs = (
        _nullify_spec(1),
        _score_debuff_spec(100, 1, name="d1"),
        _score_debuff_spec(200, 2, name="d2"),
        _hand_decrease_spec(1),
    )
    sim = LessonSim(_deck(12), _config(p_items=specs), rng_seed=0)
    state = fire_p_items(ExpectState(p_items=specs, turns_left=4), EXAM_START)
    assert sim.nullify_debuff == state.nullify_debuff
    assert sim.score_debuffs == state.score_debuffs
    assert sim.hand_decreases == state.hand_decreases
    # 1 次无效挡第一条 score_debuff；第二条 + hand_decrease 保留
    assert state.nullify_debuff == 0
    assert state.score_debuffs == ((200, 2),)
    assert state.hand_decreases == ((1, -1),)


# ---------------------------------------------------------------- 5. 数据层 / no-op 记录


def test_exam_buff_consumption_add_classify_noop() -> None:
    """⑦ ExamBuffConsumptionAdd 无目标映射（卡模型不承载 buff 花费）→ no-op。"""
    assert classify_effect_target("ExamBuffConsumptionAdd") == ""


def test_buff_consumption_add_catalog_noop() -> None:
    """主数据 4 段 ExamBuffConsumptionAdd 保持 no-op（不息的风暴/迷倒世界的模样±）。"""
    specs = [s for s in load_p_items() if s.effect_type == "ExamBuffConsumptionAdd"]
    assert len(specs) == 4
    assert all(s.target == "" for s in specs)
    ids = {s.item_id for s in specs}
    assert ids == {"pitem_03-3-345-0", "pitem_03-3-345-1", "pitem_01-3-349-0", "pitem_01-3-349-1"}


def test_count_debuffs_no_landing_point() -> None:
    """countDebuffs（低下状態の数）参考+主数据零使用：没有任何 spec 目标依赖它。"""
    specs = load_p_items()
    # 主数据无 debuff 计数目标/触发（countDebuffs 仅参考引擎变量解析器，UNVERIFIED，零使用）
    assert not any(s.target == "count_debuffs" for s in specs)
    assert not any("count_debuffs" in (s.effect_type or "").lower() for s in specs)


def test_p_items_implemented_count() -> None:
    """implemented 1056→1067（P1-4 +11）→1164（P1-5 +97）→1179（P1-7 +15）→1181（P1-8 +2）。"""
    summary = summarize(load_p_items())
    assert summary["implemented"] == 1181
    assert summary["noop"] == 668


def test_nullify_card_side_deferred() -> None:
    """卡侧 ExamAntiDebuff 主数据 values 恒空（需逐卡证据表）→ 卡表无 nullify 字段，延迟。"""
    import json

    card_table = json.loads((ROOT / "data" / "knowledge" / "card_table.json").read_text(encoding="utf-8"))
    anti_cards = [
        row for row in card_table["cards"].values()
        if any(e.get("type") == "ExamAntiDebuff" for e in row.get("effects", []))
    ]
    assert anti_cards  # 4 SSR 族存在
    for row in anti_cards:
        for effect in row["effects"]:
            if effect.get("type") == "ExamAntiDebuff":
                assert not effect.get("values")  # values 恒空（同 P1-3 hold）
    # CardSpec 无 nullify_debuff 字段（卡侧延迟，P 道具侧已落地）
    assert "nullify_debuff" not in CardSpec.__dataclass_fields__
