"""P1-8（2026-11-24）P 道具剩段 bounded batch：日文好調の%分（天生的才能）回归。

本批只挑「证据充分、离线可定、映射既有机制」的低风险段（不贪多），语义经 BSD-3
参考引擎 gakumas-tools + 主数据 + 参考 DSL 三重核实（详见 RULES_REFERENCE §5.10）：

**日文好調の%分（天生的才能 pitem_01-3-346-0/1）**——参考 DSL 天性の才能 493/494
``at:afterCardUsed { if:countCards[hand & baseId(23)]>=1 { score+=goodConditionTurns*0.3 } }``
（+ 变体 ``genki+=1; score+=goodConditionTurns*0.5``）。眠気卡张数条件 baseId(23)
（skill_cards.csv 23 眠気 ↔ card_table/card_meta 睡意 p_card-00-acc-0_002）已由 B10
zone_count 结构化解析；本批只补「好調の%分」→ parameter_buff 的**日文换算源标注**
（build_p_items.CONVERSION_SOURCES_JA），结算复用 P1-5 依赖换算渠道
（目标增量 int(condition_turns × N / 100)，源段只作系数不消耗好调回合）。

**保持 no-op 如实记录（证据充分但需新机制/真机，留后续）**：
- 全力・强气效果卡打分（ExamFullPower/ExamConcentration「打分值增加+N」43 段，
  per-card g.score 成长，参考 DSL target:effect(fullPowerCharge){g.score+=11}，
  values 恒空需逐卡证据表 + 新成长机制）；
- 塔 gimmick（低谷/紧张/弱气/体力回复无效 29 段，参考引擎 ALL_FIELDS 无对应字段）；
- ExamParameterBuffReduce（produce_start_lesson/buff_consume 触发未支持 3 段）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_p_items

from gkagent.sim.expectimax import ExpectState, fire_p_items
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    CARD_PLAY,
    TURN_START,
    CardFilter,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    ZoneCount,
    apply_passive,
    load_p_items,
    record_to_specs,
    summarize,
)

_TALENT_IDS = ("pitem_01-3-346-0", "pitem_01-3-346-1")
_SLEEPY_ID = "p_card-00-acc-0_002"  # 眠気（睡意），skill_cards.csv baseId 23


def _card(name: str = "牌", score: float = 10, cost: int = 0, **kwargs) -> CardSpec:
    return CardSpec(name=name, cost=cost, score=score, **kwargs)


def _config(**kwargs) -> LessonConfig:
    base = {"turns": 4, "stamina": 30, "target_clear": 1, "hand_size": 3, "plays_per_turn": 1}
    base.update(kwargs)
    return LessonConfig(**base)


def _specs(item_id: str) -> list[PItemSpec]:
    import json

    payload = json.loads((ROOT / "data" / "knowledge" / "p_items.json").read_text(encoding="utf-8-sig"))
    rec = next(r for r in payload["items"] if r["id"] == item_id)
    return record_to_specs(rec)


def _state(pb: int, hand: tuple[str, ...], known: bool = True) -> PassiveState:
    return PassiveState(turn=1, stacks={"parameter_buff": pb}, hand=hand, zones_known=known)


def _play_event() -> PassiveEvent:
    return PassiveEvent(kind=CARD_PLAY, card_name="魅力の基本", card_category="ActiveSkill")


# ---------------------------------------------------------------- 1. 数据层日文换算源标注


def test_ja_source_annotation_basic() -> None:
    """好調の%分 源段标 conversion_source，目标 ExamLesson 挂 depends_on+percent1。"""
    effects = [
        {"type": "ExamParameterBuff", "values": {"percent1": 30}, "text": "好調の%分"},
        {"type": "ExamLesson", "values": {}, "text": "パラメータ上昇"},
    ]
    out = build_p_items.annotate_effects(effects, "")
    assert out[0]["role"] == "conversion_source"
    assert "percent1" not in out[0]["values"]  # 源段只作系数
    assert out[1]["depends_on"] == "parameter_buff"
    assert out[1]["values"] == {"percent1": 30}


def test_ja_source_annotation_plus_variant() -> None:
    """+ 变体：元気+1 段不动，好調の%分(50) 换算挂到 ExamLesson。"""
    effects = [
        {"type": "ExamBlock", "values": {"value1": 1}, "text": "元気+"},
        {"type": "ExamParameterBuff", "values": {"percent1": 50}, "text": "好調の%分"},
        {"type": "ExamLesson", "values": {}, "text": "パラメータ上昇"},
    ]
    out = build_p_items.annotate_effects(effects, "")
    assert out[0]["values"] == {"value1": 1} and "role" not in out[0]
    assert out[1]["role"] == "conversion_source"
    assert out[2]["depends_on"] == "parameter_buff"
    assert out[2]["values"] == {"percent1": 50}


def test_zh_source_still_works() -> None:
    """中文「好调的%数值变为」换算不受日文扩展影响（回归）。"""
    effects = [
        {"type": "ExamParameterBuff", "values": {"percent1": 30}, "text": "好调的%数值变为"},
        {"type": "ExamLesson", "values": {}, "text": "打分上升"},
    ]
    out = build_p_items.annotate_effects(effects, "")
    assert out[0]["role"] == "conversion_source"
    assert out[1]["depends_on"] == "parameter_buff"
    assert out[1]["values"] == {"percent1": 30}


def test_ja_unknown_source_not_converted() -> None:
    """日文源不在 CONVERSION_SOURCES_JA（如 集中の%分）→ 保守不换算。"""
    effects = [
        {"type": "ExamLessonBuff", "values": {"percent1": 40}, "text": "集中の%分"},
        {"type": "ExamLesson", "values": {}, "text": "パラメータ上昇"},
    ]
    out = build_p_items.annotate_effects(effects, "")
    assert "role" not in out[0]
    assert out[0]["values"] == {"percent1": 40}
    assert "depends_on" not in out[1]


def test_ja_source_no_target_no_crash() -> None:
    """只有源段没有目标段 → 不换算、不抛异常（percent1 保留）。"""
    effects = [{"type": "ExamParameterBuff", "values": {"percent1": 30}, "text": "好調の%分"}]
    out = build_p_items.annotate_effects(effects, "")
    assert "role" not in out[0]
    assert out[0]["values"] == {"percent1": 30}


def test_ja_map_bounded() -> None:
    """日文换算源目前仅 好調（天生的才能），不贪多。"""
    assert build_p_items.CONVERSION_SOURCES_JA == {"好調": "parameter_buff"}


# ---------------------------------------------------------------- 2. record_to_specs / catalog


def test_talent_minus_specs() -> None:
    specs = _specs("pitem_01-3-346-0")
    lesson = [s for s in specs if s.effect_type == "ExamLesson"]
    assert len(lesson) == 1
    assert lesson[0].depends_on == "parameter_buff"
    assert lesson[0].percent == 30
    assert lesson[0].target == "score"
    assert lesson[0].implemented
    src = [s for s in specs if s.effect_type == "ExamParameterBuff"]
    assert len(src) == 1
    assert src[0].value == 0 and not src[0].depends_on
    assert not src[0].implemented  # 源段只作系数


def test_talent_plus_specs() -> None:
    specs = _specs("pitem_01-3-346-1")
    lesson = [s for s in specs if s.effect_type == "ExamLesson"]
    assert lesson[0].percent == 50 and lesson[0].implemented
    block = [s for s in specs if s.effect_type == "ExamBlock"]
    assert block[0].value == 1 and block[0].target == "vitality" and block[0].implemented


def test_talent_zone_count_parsed() -> None:
    """眠気卡张数条件（hand≥1）已由 B10 结构化；触发/条件均已知。"""
    for item_id in _TALENT_IDS:
        for s in _specs(item_id):
            assert s.trigger == "card_played"
            assert s.condition_known and s.trigger_known
            zc = s.zone_count
            assert zc is not None
            assert zc.zones == ("hand",) and zc.minimum == 1 and not zc.negate
            assert zc.filter is not None
            assert zc.filter.kind == "card" and zc.filter.card_id == _SLEEPY_ID


def test_talent_trigger_id_parse() -> None:
    tid = (
        "e_trigger-exam_card_play_after-card_search_count_up-1-"
        "p_card_search-hand-p_card-00-acc-0_002-p_card_search-target-0_1"
    )
    play_filter, zone_count, unresolved = build_p_items.parse_card_search(tid)
    assert unresolved is False
    assert play_filter is None  # target-0_1 = 任意卡
    assert zone_count["zones"] == ["hand"] and zone_count["min"] == 1
    assert zone_count["filter"]["card_id"] == _SLEEPY_ID


def test_catalog_implemented_count() -> None:
    """implemented 1179（P1-7）→1181（P1-8 +2）；depends_on 76→78。"""
    summary = summarize(load_p_items())
    assert summary["implemented"] == 1181
    assert summary["noop"] == 668
    assert summary["depends_on_specs"] == 78


def test_catalog_parameter_buff_conversion_13() -> None:
    specs = load_p_items()
    targets = [s for s in specs if s.depends_on == "parameter_buff" and s.percent > 0]
    assert len(targets) == 13  # P1-5 11 + P1-8 2
    assert all(s.implemented for s in targets)


def test_catalog_ja_conversion_only_talent() -> None:
    """新增的 2 段好调换算目标恰为天生的才能（bounded，无误伤）。"""
    specs = load_p_items()
    ja = [
        s for s in specs
        if s.depends_on == "parameter_buff" and s.effect_type == "ExamLesson"
        and s.item_id in _TALENT_IDS
    ]
    assert len(ja) == 2
    assert sorted(s.percent for s in ja) == [30, 50]


# ---------------------------------------------------------------- 3. apply_passive 端到端


def test_apply_minus_score() -> None:
    d = apply_passive(_specs("pitem_01-3-346-0"), _play_event(), _state(10, ("睡意",)))
    assert d.score == 3  # int(10 × 30 / 100)
    assert d.applied == ["pitem_01-3-346-0"]


def test_apply_minus_floor() -> None:
    d = apply_passive(_specs("pitem_01-3-346-0"), _play_event(), _state(7, ("睡意",)))
    assert d.score == 2  # int(7 × 0.3) = 2（向下取整，与 P1-5 同口径）


def test_apply_minus_zero_condition() -> None:
    d = apply_passive(_specs("pitem_01-3-346-0"), _play_event(), _state(0, ("睡意",)))
    assert d.score == 0 and not d.applied


def test_apply_minus_no_sleepy() -> None:
    d = apply_passive(_specs("pitem_01-3-346-0"), _play_event(), _state(10, ("魅力の基本",)))
    assert d.score == 0 and not d.applied


def test_apply_minus_zones_unknown() -> None:
    d = apply_passive(_specs("pitem_01-3-346-0"), _play_event(), _state(10, ("睡意",), known=False))
    assert d.score == 0 and not d.applied


def test_apply_minus_ja_alias() -> None:
    """日文卡名 眠気 经 ja_aliases 解析到 睡意，同样命中。"""
    d = apply_passive(_specs("pitem_01-3-346-0"), _play_event(), _state(10, ("眠気",)))
    assert d.score == 3


def test_apply_plus_score_genki() -> None:
    d = apply_passive(_specs("pitem_01-3-346-1"), _play_event(), _state(10, ("睡意",)))
    assert d.score == 5  # int(10 × 50 / 100)
    assert d.stacks.get("vitality") == 1  # genki+=1


def test_apply_plus_no_sleepy() -> None:
    d = apply_passive(_specs("pitem_01-3-346-1"), _play_event(), _state(10, ("魅力の基本",)))
    assert d.score == 0 and not d.stacks


def test_apply_wrong_trigger() -> None:
    """card_played 触发只在出牌事件结算，回合开始不触发。"""
    ev = PassiveEvent(kind=TURN_START)
    d = apply_passive(_specs("pitem_01-3-346-0"), ev, _state(10, ("睡意",)))
    assert d.score == 0 and not d.applied


def test_apply_multiple_sleepy_not_per_card() -> None:
    """张数条件 ≥1 是门槛，不是按张乘（2 张眠気仍只结算一次换算）。"""
    d = apply_passive(_specs("pitem_01-3-346-0"), _play_event(), _state(10, ("睡意", "睡意")))
    assert d.score == 3


def test_apply_sleepy_in_deck_not_hand() -> None:
    """区域限定 hand：眠気 在牌堆不在手牌 → 不触发。"""
    st = PassiveState(turn=1, stacks={"parameter_buff": 10}, hand=(), deck=("睡意",), zones_known=True)
    d = apply_passive(_specs("pitem_01-3-346-0"), _play_event(), st)
    assert d.score == 0 and not d.applied


# ---------------------------------------------------------------- 4. ExpectState / LessonSim 双镜


def _talent_spec(percent: int) -> PItemSpec:
    return PItemSpec(
        name="天生的才能", trigger="card_played", effect_type="ExamLesson",
        depends_on="parameter_buff", percent=percent, item_id="talent",
        zone_count=ZoneCount(zones=("hand",), minimum=1, filter=CardFilter(kind="card", card_id=_SLEEPY_ID)),
    )


def test_expect_fire_talent_conversion() -> None:
    state = ExpectState(
        p_items=(_talent_spec(30),), condition_turns=10,
        hand=(_card("睡意"),), turns_left=3,
    )
    after = fire_p_items(state, CARD_PLAY, card_name="魅力の基本", card_category="ActiveSkill")
    assert after.score == 3


def test_expect_fire_talent_no_sleepy() -> None:
    state = ExpectState(
        p_items=(_talent_spec(30),), condition_turns=10,
        hand=(_card("魅力の基本"),), turns_left=3,
    )
    after = fire_p_items(state, CARD_PLAY, card_name="魅力の基本", card_category="ActiveSkill")
    assert after.score == 0


def test_expect_fire_talent_plus() -> None:
    specs = (_talent_spec(50), PItemSpec(
        name="天生的才能+", trigger="card_played", effect_type="ExamBlock", value=1, item_id="talent",
        zone_count=ZoneCount(zones=("hand",), minimum=1, filter=CardFilter(kind="card", card_id=_SLEEPY_ID)),
    ))
    state = ExpectState(p_items=specs, condition_turns=10, hand=(_card("睡意"),), turns_left=3)
    after = fire_p_items(state, CARD_PLAY, card_name="魅力の基本", card_category="ActiveSkill")
    assert after.score == 5 and after.vitality == 1


def test_lesson_expect_talent_parity() -> None:
    """LessonSim ↔ ExpectState 同事件好調の%分换算逐位对齐。"""
    spec = _talent_spec(30)
    sim = LessonSim([_card("d1"), _card("d2")], _config(), rng_seed=0)
    sim.hand = [_card("睡意")]
    sim.buffs.condition_turns = 10
    sim.p_items = (spec,)
    sim._p_items_by_trigger = {"card_played": (spec,)}
    sim._fire_p_items(CARD_PLAY, card_name="魅力の基本", card_category="ActiveSkill")
    state = ExpectState(p_items=(spec,), condition_turns=10, hand=(_card("睡意"),), turns_left=4)
    state = fire_p_items(state, CARD_PLAY, card_name="魅力の基本", card_category="ActiveSkill")
    assert sim.score == state.score == 3


# ---------------------------------------------------------------- 5. 保持 no-op 如实记录


def test_tower_gimmicks_noop_evidence() -> None:
    """塔 gimmick 低谷11/紧张6/弱气6/体力回复无效6 = 29 段，参考无独立字段 → no-op。"""
    specs = load_p_items()
    counts = {"ExamGimmickSlump": 11, "ExamGimmickLessonDebuff": 6,
              "ExamGimmickSleepy": 6, "ExamStaminaRecoverRestriction": 6}
    for et, n in counts.items():
        group = [s for s in specs if s.effect_type == et]
        assert len(group) == n, et
        assert all(not s.implemented for s in group), et


def test_fullpower_concentration_card_score_noop() -> None:
    """全力・强气效果卡打分（per-card g.score 成长，values 恒空）43 段 → no-op。"""
    specs = load_p_items()
    fp = [s for s in specs if s.effect_type in ("ExamFullPower", "ExamConcentration")
          and "打分值增加" in s.effect_text]
    assert len(fp) == 43
    assert all(not s.implemented for s in fp)


def test_parameter_buff_reduce_noop() -> None:
    """ExamParameterBuffReduce（produce_start_lesson/buff_consume 触发未支持）3 段 → no-op。"""
    specs = [s for s in load_p_items() if s.effect_type == "ExamParameterBuffReduce"]
    assert len(specs) == 3
    assert all(not s.implemented for s in specs)
    assert {s.trigger for s in specs} == {"produce_start_lesson", "buff_consume"}


def test_buff_consume_trigger_unsupported() -> None:
    from gkagent.sim.p_items import SUPPORTED_TRIGGERS

    assert "buff_consume" not in SUPPORTED_TRIGGERS
    assert "produce_start_lesson" not in SUPPORTED_TRIGGERS