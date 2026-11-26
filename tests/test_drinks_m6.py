"""M6 饮料全 catalog + sim 效果建模 + 莉波 W9 实机重放门（阶段1）。

覆盖：
  * catalog（``data/knowledge/drinks.json``）段数 / W9 三 id 逐字 / unknown 显式 no-op；
  * 逐效果单测（``LessonSim.use_drink`` + ``expectimax.use_drink_state`` 双镜）；
  * W9 全重放门（引擎 oracle，``scripts/replay_rinami.py`` 子进程）：终分 1,426,865
    + 逐决策 rng/score/turn/card 匹配（含 4 饮料步）；W7（0 饮料）回归 655,198；
  * opt-in 接线（``data/drinks_db.resolve_drink_ids`` 默认关 = 逐位不变）。

引擎/实机样本缺失时重放门自动 skip（``data/_rinami_live`` 不提交、DLL 不重编）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from gkagent.data.drinks_db import (
    DrinkDataUnavailable,
    get_catalog,
    load_drink_catalog,
    resolve_drink_ids,
)
from gkagent.sim.drinks import (
    DrinkEffect,
    classify_drink_effect,
    effects_to_delta,
    legacy_effect,
    rng_caliber,
)
from gkagent.sim.expectimax import (
    ExpectState,
    _drink_draw_state,
    apply_card,
    end_turn_state,
    start_turn_state,
    state_from_sim,
    use_drink_state,
)
from gkagent.sim.lesson import CardSpec, DrinkSpec, LessonConfig, LessonSim

ROOT = Path(__file__).resolve().parents[1]
DRINKS_JSON = ROOT / "data" / "knowledge" / "drinks.json"
RINAMI = ROOT / "data" / "_rinami_live"
REPLAY_SCRIPT = ROOT / "scripts" / "replay_rinami.py"
DLL = ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"
BENCH_REPO = ROOT / "data" / "bench_repo" / "gkbench"

W9_IDS = ("pdrink_00-3-001", "pdrink_00-2-010", "pdrink_00-2-009")


# --------------------------------------------------------------------- catalog
@pytest.fixture(scope="module")
def catalog_payload() -> dict:
    if not DRINKS_JSON.is_file():
        pytest.skip("缺少 data/knowledge/drinks.json（先跑 scripts/build_drinks.py）")
    return json.loads(DRINKS_JSON.read_text(encoding="utf-8"))


def test_catalog_counts(catalog_payload) -> None:
    assert catalog_payload["count"] == 29
    assert catalog_payload["segments_total"] == 51
    # 阶段2 batch2 后 45 段语义确定已实现，6 段显式 no-op（不猜）。
    # （阶段1 33 → 1.5 +7 = 40 → batch2 +5：强气×2 + 黑醋汁 move/cost0 + 精华再发动 = 45。）
    assert catalog_payload["segments_implemented"] == 45
    drinks = catalog_payload["drinks"]
    assert len(drinks) == 29
    assert sum(d["total"] for d in drinks) == 51
    assert sum(d["implemented"] for d in drinks) == 45


def test_w9_drinks_fully_implemented(catalog_payload) -> None:
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    for did in W9_IDS:
        assert did in by_id, did
        d = by_id[did]
        assert d["implemented"] == d["total"], (did, d["effects"])
        assert d["total"] > 0


def test_w9_protein_effect(catalog_payload) -> None:
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    effs = by_id["pdrink_00-3-001"]["effects"]
    assert len(effs) == 1
    assert effs[0]["kind"] == "extra_plays"
    assert effs[0]["value"] == 1
    assert effs[0]["effect_type"] == "ExamPlayableValueAdd"
    # 实机 label：技能卡使用数追加+1
    assert "技能卡使用数追加" in by_id["pdrink_00-3-001"]["text_zh"]


def test_w9_soda_effects(catalog_payload) -> None:
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    effs = by_id["pdrink_00-2-010"]["effects"]
    kinds = {e["kind"]: e for e in effs}
    assert len(effs) == 4
    assert kinds["score_buff"]["value"] == 100  # 千分比 +10%
    assert kinds["score_buff"]["turns"] == 5
    assert kinds["draw"]["value"] == 2
    assert kinds["stamina_cost"]["value"] == 2
    assert kinds["turn_start_draw"]["value"] == 1
    assert kinds["turn_start_draw"]["turns"] == 5
    assert kinds["turn_start_draw"]["trigger"] == "turn_start_after"
    text = by_id["pdrink_00-2-010"]["text_zh"]
    assert "打分上升量增加10%" in text and "技能卡抽取2张" in text
    assert "体力消耗2" in text and "回合开始后" in text


def test_w9_herbal_effects(catalog_payload) -> None:
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    effs = by_id["pdrink_00-2-009"]["effects"]
    kinds = {e["kind"]: e for e in effs}
    assert len(effs) == 2
    assert kinds["search_move"]["search"] == "p_card_search-deck_grave-idol-unique-1"
    assert kinds["search_move"]["move_to"] == "hand"
    assert kinds["half_cost"]["turns"] == 3
    text = by_id["pdrink_00-2-009"]["text_zh"]
    assert "偶像固有技能卡" in text and "消耗体力减少3回合" in text


def test_aojiru_random_create_is_unknown(catalog_payload) -> None:
    """青汁（初星特制青汁/X）随机生成/强制打搜索牌 = RNG 消费入口，真机流未知 → 显式 no-op。"""
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    for did in ("pdrink_00-3-005", "pdrink_00-3-013"):
        d = by_id[did]
        assert d["implemented"] == 0, (did, d["effects"])
        assert d["rng"]["unknown"], did
    # 青汁本体（00-3-005）是随机卡池生成（create_random_unknown）。
    assert any(
        e["rng"] == "create_random_unknown" for e in by_id["pdrink_00-3-005"]["effects"]
    )


def test_unknown_segments_are_explicit_noop(catalog_payload) -> None:
    unknown = [
        e for d in catalog_payload["drinks"] for e in d["effects"] if not e["implemented"]
    ]
    assert len(unknown) == 6
    assert all(e["kind"] == "unknown" for e in unknown)
    # 未建模段不结算（effects_to_delta 跳过）。
    specs = tuple(
        DrinkEffect(kind="unknown", effect_type=e["effect_type"], implemented=False)
        for e in unknown
    )
    assert effects_to_delta(specs).is_zero()


# --------------------------------------------------------------------- 逐效果单测
def _sim_with_drink(drink: DrinkSpec, deck=None, **cfg) -> LessonSim:
    deck = deck if deck is not None else [CardSpec("占位", 0, 0)] * 6
    config = LessonConfig(
        turns=cfg.pop("turns", 4),
        stamina=cfg.pop("stamina", 30),
        target_clear=cfg.pop("target_clear", 100),
        hand_size=cfg.pop("hand_size", 3),
        drinks=(drink,),
        **cfg,
    )
    return LessonSim(list(deck), config, rng_seed=0)


def _mirror(drink: DrinkSpec, deck=None, **cfg):
    """返回 (sim, state)：同一开局，state 由 sim 镜像（双镜配对，带真实牌序）。"""
    sim = _sim_with_drink(drink, deck=deck, **cfg)
    state = state_from_sim(sim, known_deck_order=True)
    return sim, state


def _assert_mirror(sim: LessonSim, state: ExpectState) -> None:
    assert sim.score == state.score
    assert sim.stamina == state.stamina
    assert sim.buffs.focus == state.focus
    assert sim.buffs.condition_turns == state.condition_turns
    assert sim.extra_plays == state.extra_plays
    assert tuple(sim.score_buffs) == tuple(state.score_buffs)
    assert sim.half_cost_turns == state.half_cost_turns
    assert tuple(sim.turn_start_draw) == tuple(state.turn_start_draw)
    assert sim.vitality == state.vitality
    # M6 阶段1.5：回合边界附魔 / fresh 保护 / 干劲 / 指針 / 保留区双镜。
    assert tuple(sim.turn_enchants) == tuple(state.turn_enchants)
    assert sim.review_enchant_fresh == state.review_enchant_fresh
    assert sim.buffs.impression == state.impression
    assert sim.motivation == state.motivation
    assert (
        sim.stance.stance, sim.stance.strong_level,
        sim.stance.save_level, sim.stance.full_power_point,
    ) == state.stance
    assert sorted(c.name for c in sim.held) == sorted(c.name for c in state.held)
    assert sorted(c.name for c in sim.hand) == sorted(c.name for c in state.hand)
    assert sorted(c.name for c in sim.deck) == sorted(c.name for c in state.deck)


def test_extra_plays_effect() -> None:
    drink = DrinkSpec("蛋白粉", 0, "multi", 0, effects=(
        DrinkEffect(kind="extra_plays", value=1, effect_type="ExamPlayableValueAdd"),
    ))
    sim, state = _mirror(drink)
    base_plays = sim.extra_plays
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.extra_plays == base_plays + 1
    assert state.extra_plays == base_plays + 1
    assert sim.drink_uses == [0]
    _assert_mirror(sim, state)


def test_score_buff_timed_effect() -> None:
    drink = DrinkSpec("苏打", 0, "multi", 0, effects=(
        DrinkEffect(kind="score_buff", value=100, turns=5, effect_type="ExamLessonValueMultiple"),
    ))
    sim, state = _mirror(drink)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert tuple(sim.score_buffs) == ((100, 5),)
    assert tuple(state.score_buffs) == ((100, 5),)
    _assert_mirror(sim, state)
    # 回合末倒计时：5 → 4。
    sim.step(None)
    assert tuple(sim.score_buffs) == ((100, 4),)


def test_stamina_cost_effect() -> None:
    drink = DrinkSpec("苏打", 0, "multi", 0, effects=(
        DrinkEffect(kind="stamina_cost", value=2, effect_type="ExamStaminaReduceFix"),
    ))
    sim, state = _mirror(drink, stamina=33, stamina_max=35)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.stamina == 31
    assert state.stamina == 31
    assert sim.consumed_stamina_total == 2
    _assert_mirror(sim, state)


def test_immediate_draw_effect() -> None:
    drink = DrinkSpec("苏打", 0, "multi", 0, effects=(
        DrinkEffect(kind="draw", value=2, effect_type="ExamCardDraw"),
    ))
    deck = [CardSpec(f"卡{i}", 0, 0) for i in range(8)]
    sim, state = _mirror(drink, deck=deck)
    hand0 = len(sim.hand)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert len(sim.hand) == hand0 + 2
    assert len(state.hand) == hand0 + 2
    _assert_mirror(sim, state)


def test_turn_start_draw_effect() -> None:
    from gkagent.sim.expectimax import _drink_draw_state, end_turn_state, start_turn_state

    drink = DrinkSpec("苏打", 0, "multi", 0, effects=(
        DrinkEffect(kind="turn_start_draw", value=1, turns=5, trigger="turn_start_after",
                    effect_type="ExamStatusEnchant"),
    ))
    deck = [CardSpec(f"卡{i}", 0, 0) for i in range(12)]
    sim, state = _mirror(drink, deck=deck)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert tuple(sim.turn_start_draw) == ((1, 5),)
    assert tuple(state.turn_start_draw) == ((1, 5),)
    # 喝饮料当回合不额外抽；下一回合开始 base 3 + 1 = 4 张。
    assert len(sim.hand) == 3
    sim.step(None)  # SKIP 换回合（sim 内部抽 base + extra）
    # state 侧：回合末弃手牌 → 抽 base 3 → 回合开始结算（extra 1）。
    state = end_turn_state(state)
    state = _drink_draw_state(state, state.hand_size)
    state = start_turn_state(state)
    assert len(sim.hand) == 4
    assert len(state.hand) == 4
    # 倒计时 5 → 4。
    assert tuple(sim.turn_start_draw) == ((1, 4),)
    assert tuple(state.turn_start_draw) == ((1, 4),)
    _assert_mirror(sim, state)


def test_half_cost_effect() -> None:
    drink = DrinkSpec("汉方", 0, "multi", 0, effects=(
        DrinkEffect(kind="half_cost", value=3, turns=3, effect_type="ExamStaminaConsumptionDown"),
    ))
    sim, state = _mirror(drink)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.half_cost_turns == 3
    assert state.half_cost_turns == 3
    _assert_mirror(sim, state)


def test_search_move_idol_unique() -> None:
    idol = CardSpec("固有", 0, 0, category="IdolUnique")
    deck = [CardSpec("普通", 0, 0)] * 5 + [idol]
    drink = DrinkSpec("汉方", 0, "multi", 0, effects=(
        DrinkEffect(kind="search_move", value=1, search="p_card_search-deck_grave-idol-unique-1",
                    move_to="hand", effect_type="ExamCardMove"),
    ))
    sim, state = _mirror(drink, deck=deck)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert any(c.category == "IdolUnique" for c in sim.hand)
    assert any(c.category == "IdolUnique" for c in state.hand)
    assert not any(c.category == "IdolUnique" for c in sim.deck)
    _assert_mirror(sim, state)


def test_legacy_single_effect_unchanged() -> None:
    """旧单效果路径（effects 空）逐位不变：stamina/focus/condition/score。"""
    for et, val in (("stamina", 5), ("focus", 3), ("condition", 3), ("score", 10)):
        drink = DrinkSpec("旧", 0, et, val)
        sim, state = _mirror(drink, stamina=20, stamina_max=30)
        sim.use_drink(0)
        state = use_drink_state(state, 0)
        _assert_mirror(sim, state)
    # 旧未建模效果仍报错（不静默）。
    with pytest.raises(ValueError, match="未建模"):
        DrinkSpec("乌龙茶", 0, "vitality", 7)


def test_unknown_effect_segment_noop() -> None:
    drink = DrinkSpec("青汁", 0, "multi", 0, effects=(
        DrinkEffect(kind="unknown", effect_type="ExamCardCreateSearch", implemented=False,
                    rng="create_random_unknown"),
    ))
    sim, state = _mirror(drink)
    score0, stamina0 = sim.score, sim.stamina
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.score == score0 and sim.stamina == stamina0
    assert sim.drink_uses == [0]  # 仍消耗一瓶
    _assert_mirror(sim, state)


def test_rng_caliber_taxonomy() -> None:
    protein = (DrinkEffect(kind="extra_plays", value=1, rng="none"),)
    assert rng_caliber(protein)["deterministic"] is True
    soda = (
        DrinkEffect(kind="score_buff", value=100, turns=5, rng="none"),
        DrinkEffect(kind="draw", value=2, rng="draw_support"),
    )
    cal = rng_caliber(soda)
    assert cal["deterministic"] is False
    assert "draw_support" in cal["entries"]
    herbal = (DrinkEffect(kind="search_move", value=1, rng="type9_search"),)
    assert "type9_search" in rng_caliber(herbal)["entries"]
    aojiru = (DrinkEffect(kind="unknown", implemented=False, rng="create_random_unknown"),)
    assert rng_caliber(aojiru)["unknown"]


def test_classify_w9_effect_bodies() -> None:
    """主数据效果本体 → 分类（与 build_drinks 同口径）。"""
    p = classify_drink_effect("ExamPlayableValueAdd", {"effectCount": 1})
    assert p.kind == "extra_plays" and p.value == 1 and p.implemented
    s = classify_drink_effect("ExamLessonValueMultiple", {"effectValue1": 100, "effectTurn": 5})
    assert s.kind == "score_buff" and s.value == 100 and s.turns == 5
    d = classify_drink_effect("ExamCardDraw", {"effectValue1": 2})
    assert d.kind == "draw" and d.value == 2 and d.rng == "draw_support"
    h = classify_drink_effect("ExamStaminaConsumptionDown", {"effectTurn": 3})
    assert h.kind == "half_cost" and h.turns == 3
    m = classify_drink_effect(
        "ExamCardMove", {}, search="p_card_search-deck_grave-idol-unique-1", move_to="hand"
    )
    assert m.kind == "search_move" and m.rng == "type9_search"
    e = classify_drink_effect(
        "ExamStatusEnchant", {"effectTurn": 5},
        inner=[{"type": "ExamCardDraw", "values": {"effectValue1": 1}, "trigger": "e_trigger-start_play"}],
    )
    assert e.kind == "turn_start_draw" and e.value == 1 and e.turns == 5
    c = classify_drink_effect("ExamCardCreateSearch", {})
    assert c.kind == "unknown" and not c.implemented and c.rng == "create_random_unknown"


# ------------------------------------------------- 阶段1.5：确定式增量批（catalog）
STAGE15_IDS = (
    "pdrink_01-3-002", "pdrink_02-3-006", "pdrink_02-3-007",
    "pdrink_03-3-008", "pdrink_03-2-007",
)


def test_stage15_enchant_drinks_catalog(catalog_payload) -> None:
    """4 种严选初星附魔：内层效果 × 触发时机 → 确定式 kind，effectTurn=-1 永久。"""
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    want = {
        "pdrink_01-3-002": ("turn_end_focus", "turn_end"),
        "pdrink_02-3-006": ("turn_end_impression", "turn_end"),
        "pdrink_02-3-007": ("turn_end_aggressive", "turn_end"),
        "pdrink_03-3-008": ("turn_start_full_power", "turn_start"),
    }
    for did, (kind, trigger) in want.items():
        d = by_id[did]
        assert d["implemented"] == d["total"] == 1, (did, d["effects"])
        eff = d["effects"][0]
        assert eff["kind"] == kind and eff["value"] == 1, (did, eff)
        assert eff["turns"] == -1 and eff["trigger"] == trigger, (did, eff)
        assert eff["effect_type"] == "ExamStatusEnchant" and eff["rng"] == "none"
        assert eff["enchant"] == f"enchant-{did}-enc01"
        assert d["rng"]["deterministic"] is True


def test_stage15_hot_green_tea_catalog(catalog_payload) -> None:
    """热绿茶：ExamCardMove deck_grave→hold（Select）+ ExamPreservation 温存 2 段階。"""
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    d = by_id["pdrink_03-2-007"]
    assert d["implemented"] == d["total"] == 2
    kinds = {e["kind"]: e for e in d["effects"]}
    mv = kinds["search_hold"]
    assert mv["search"] == "p_card_search-deck_grave" and mv["move_to"] == "hold"
    assert mv["rng"] == "none" and mv["effect_type"] == "ExamCardMove"
    pres = kinds["preservation"]
    assert pres["value"] == 2 and pres["rng"] == "none"
    assert pres["effect_type"] == "ExamPreservation"
    assert d["rng"]["deterministic"] is True
    assert "保留" in d["text_zh"] and "温存2阶段变更" in d["text_zh"]


def test_stage15_hojicha_preservation_side_effect(catalog_payload) -> None:
    """焙茶（温存变更 value1=1）随 ExamPreservation 映射一并实现（side-effect，oracle 验证）。"""
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    d = by_id["pdrink_03-1-010"]
    assert d["implemented"] == d["total"] == 2
    kinds = {e["kind"]: e for e in d["effects"]}
    assert kinds["preservation"]["value"] == 1
    assert kinds["full_power_point"]["value"] == 2


def test_stage15_aojiru_still_unknown(catalog_payload) -> None:
    """青汁×2（随机生成/强制打搜索牌）保持 unknown——决策层保守不喝=免费杠杆。"""
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    for did in ("pdrink_00-3-005", "pdrink_00-3-013"):
        assert by_id[did]["implemented"] == 0
        assert by_id[did]["rng"]["unknown"]


def test_stage15_classify_effect_bodies() -> None:
    """主数据效果本体 → 分类（阶段1.5 新映射，与 build_drinks 同口径）。"""
    for ctype, kind, trigger in (
        ("ExamLessonBuff", "turn_end_focus", "turn_end"),
        ("ExamReview", "turn_end_impression", "turn_end"),
        ("ExamCardPlayAggressive", "turn_end_aggressive", "turn_end"),
    ):
        e = classify_drink_effect(
            "ExamStatusEnchant", {"effectTurn": -1},
            inner=[{"type": ctype, "values": {"effectValue1": 1},
                    "trigger": "e_trigger-exam_end_turn"}],
        )
        assert e.kind == kind and e.value == 1 and e.turns == -1
        assert e.trigger == trigger and e.rng == "none" and e.implemented
    f = classify_drink_effect(
        "ExamStatusEnchant", {"effectTurn": -1},
        inner=[{"type": "ExamFullPowerPoint", "values": {"effectValue1": 1},
                "trigger": "e_trigger-exam_start_turn"}],
    )
    assert f.kind == "turn_start_full_power" and f.turns == -1 and f.rng == "none"
    # 内层类型/触发不匹配仍 unknown（不猜）。
    u = classify_drink_effect(
        "ExamStatusEnchant", {"effectTurn": -1},
        inner=[{"type": "ExamLessonBuff", "values": {"effectValue1": 1},
                "trigger": "e_trigger-start_play"}],
    )
    assert u.kind == "unknown" and not u.implemented
    # ExamCardMove：Select→hold（1.5）/ Select→hand（batch2 黑醋汁）均实现；
    # 非 Select / 非 deck_grave 变体仍 unknown。
    h = classify_drink_effect(
        "ExamCardMove", {}, search="p_card_search-deck_grave", move_to="hold", pick="Select"
    )
    assert h.kind == "search_hold" and h.rng == "none"
    uh = classify_drink_effect(
        "ExamCardMove", {}, search="p_card_search-deck_grave", move_to="hand", pick="Select"
    )
    assert uh.kind == "select_move_hand" and uh.rng == "none"
    assert classify_drink_effect(
        "ExamCardMove", {}, search="p_card_search-deck_grave", move_to="hand", pick="Random"
    ).kind == "unknown"
    # ExamPreservation：value1=1/2 → 温存直给；其余 unknown。
    p1 = classify_drink_effect("ExamPreservation", {"effectValue1": 1})
    assert p1.kind == "preservation" and p1.value == 1 and p1.rng == "none"
    p2 = classify_drink_effect("ExamPreservation", {"effectValue1": 2})
    assert p2.kind == "preservation" and p2.value == 2
    assert classify_drink_effect("ExamPreservation", {}).kind == "unknown"
    # ExamConcentration（强气）阶段2 batch2 已实现（同 stance 渠道）。
    assert classify_drink_effect("ExamConcentration", {"effectValue1": 1}).kind == "concentration"


# ------------------------------------------------- 阶段1.5：逐效果单测（双镜）
def _stage15_sim(kind: str, value: int = 1, turns: int = -1,
                 effect_type: str = "ExamStatusEnchant", **mirror_kw):
    eff = DrinkEffect(kind=kind, value=value, turns=turns, effect_type=effect_type)
    drink = DrinkSpec("阶段1.5", 0, "multi", 0, effects=(eff,))
    return _mirror(drink, **mirror_kw)


def test_turn_end_focus_effect() -> None:
    sim, state = _stage15_sim("turn_end_focus")
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert tuple(sim.turn_enchants) == (("turn_end_focus", 1, -1),)
    assert sim.buffs.focus == 0  # 登记不立即加
    _assert_mirror(sim, state)
    sim.step(None)
    state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    assert sim.buffs.focus == 1 and state.focus == 1
    sim.step(None)
    state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    assert sim.buffs.focus == 2 and state.focus == 2  # 永久（-1）
    _assert_mirror(sim, state)


def test_turn_end_aggressive_effect() -> None:
    sim, state = _stage15_sim("turn_end_aggressive")
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    sim.step(None)
    state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    assert sim.motivation == 1 and state.motivation == 1
    _assert_mirror(sim, state)


def test_turn_end_impression_fresh_protection() -> None:
    """茶：附魔在好印象结算前触发 + fresh 保护（引擎 probe5 实测口径）。

    0 层起步：end1 结算 1 层 / impression 净+1（fresh 存活）；end2 结算 2 层 /
    旧层 -1 / impression 净 0；end3 同 end2（永久）。sim 结算层 1,2,2 ↔ 引擎
    B 场景 score 35,74,50（=1×35 / 2×37 / 2×25 属性倍率）逐层配对。
    """
    sim, state = _stage15_sim("turn_end_impression")
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.buffs.impression == 0
    layers = []
    for k in range(3):
        score0 = sim.score
        sim.step(None)
        state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
        layers.append(sim.score - score0)
        assert sim.buffs.impression == 1 and state.impression == 1
        _assert_mirror(sim, state)
    assert layers == [1, 2, 2]


def test_turn_end_impression_mixed_sources() -> None:
    """混合渠道：立即好印象（路易波士茶 +3）走既有衰减口径，附魔 +1 走 fresh。

    引擎 C 场景 end1 结算 4 层（3+1）；sim 同。end2 起立即渠道按既有 sim 口径
    （下一回合开始 -1）衰减、附魔渠道 fresh 保护——与引擎的通用 fresh 保护存在
    既有差一回合缺口（卡/立即渠道，engine-gap 已记），不在阶段1.5 范围。
    """
    drink = DrinkSpec("混合", 0, "multi", 0, effects=(
        DrinkEffect(kind="impression", value=3, effect_type="ExamReview"),
        DrinkEffect(kind="turn_end_impression", value=1, turns=-1,
                    effect_type="ExamStatusEnchant"),
    ))
    sim, state = _mirror(drink)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.buffs.impression == 3
    sim.step(None)
    state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    assert sim.score == 4  # 结算 3+1 层（附魔在结算前）
    assert sim.buffs.impression == 3  # 立即 3→2（既有口径）+ 附魔 fresh 1 存活
    _assert_mirror(sim, state)


def test_turn_start_full_power_effect() -> None:
    sim, state = _stage15_sim("turn_start_full_power")
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.stance.full_power_point == 0  # 登记不立即加
    sim.step(None)
    state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    assert sim.stance.full_power_point == 1
    assert state.stance[3] == 1
    assert sim.full_power_point_total == 1
    sim.step(None)
    state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    assert sim.stance.full_power_point == 2 and state.stance[3] == 2
    _assert_mirror(sim, state)


def test_search_hold_effect() -> None:
    """热绿茶 move：deck_grave 选白值最高 1 张进保留区（Select 玩家选择，rng=none）。"""
    from gkagent.sim.hold import HOLD_LIMIT

    hi = CardSpec("高分", 0, 9)
    lo = CardSpec("低分", 0, 1)
    deck = [lo, hi] + [CardSpec("占位", 0, 0)] * 4
    eff = DrinkEffect(kind="search_hold", value=1, search="p_card_search-deck_grave",
                      move_to="hold", effect_type="ExamCardMove")
    drink = DrinkSpec("热绿茶", 0, "multi", 0, effects=(eff,))
    sim, state = _mirror(drink, deck=deck)
    deck_n0 = len(sim.deck)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert [c.name for c in sim.held] == ["高分"]
    assert [c.name for c in state.held] == ["高分"]
    # 高分来自牌堆/弃牌（初始洗牌可能把低分抽进手牌）：牌堆恰好减 1。
    assert hi not in sim.deck and len(sim.deck) == deck_n0 - 1
    _assert_mirror(sim, state)
    # 保留区上限 2：再喝两瓶（3 张候选）→ 最旧进弃牌堆。
    drink2 = DrinkSpec("热绿茶", 0, "multi", 0, uses=3, effects=(eff,))
    sim2, state2 = _mirror(drink2, deck=[CardSpec(f"卡{i}", 0, i) for i in range(6)])
    for _ in range(3):
        sim2.use_drink(0)
        state2 = use_drink_state(state2, 0)
    assert len(sim2.held) == HOLD_LIMIT == len(state2.held)
    assert len(sim2.discard) == 1 and len(state2.discard) == 1
    _assert_mirror(sim2, state2)


def test_search_hold_empty_noop() -> None:
    eff = DrinkEffect(kind="search_hold", value=1, search="p_card_search-deck_grave",
                      move_to="hold", effect_type="ExamCardMove")
    drink = DrinkSpec("热绿茶", 0, "multi", 0, effects=(eff,))
    sim, state = _mirror(drink, deck=[])
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.held == [] and state.held == ()
    assert sim.drink_uses == [0]
    _assert_mirror(sim, state)


def test_preservation_stance_direct() -> None:
    """温存指針直给（value1=2 → save2 / 1 → save1），走 PItemDelta.stances 渠道。"""
    for value, level in ((2, 2), (1, 1)):
        eff = DrinkEffect(kind="preservation", value=value, effect_type="ExamPreservation")
        drink = DrinkSpec("温存", 0, "multi", 0, effects=(eff,))
        sim, state = _mirror(drink)
        sim.use_drink(0)
        state = use_drink_state(state, 0)
        assert str(sim.stance.stance) == "save" and sim.stance.save_level == level
        assert state.stance[0] == "save" and state.stance[2] == level
        _assert_mirror(sim, state)
    # 温存 2 段階：出牌体力消耗 ×0.25（stance.stamina_cost_multiplier 既有口径）。
    from gkagent.sim.stance import stamina_cost_multiplier

    assert stamina_cost_multiplier(sim.stance) == 0.5  # value=1 最后一轮


def test_preservation_cost_multiplier() -> None:
    eff = DrinkEffect(kind="preservation", value=2, effect_type="ExamPreservation")
    drink = DrinkSpec("热绿茶", 0, "multi", 0, effects=(eff,))
    sim, state = _mirror(drink, deck=[CardSpec("打分", 8, 0)] * 6)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    from gkagent.sim.expectimax import effective_cost

    card = sim.hand[0]
    assert effective_cost(state, card) == 2  # ceil(8 × 0.25)，向上取整既有口径
    _assert_mirror(sim, state)


def test_stage15_rng_caliber_deterministic() -> None:
    from gkagent.sim.drinks import rng_caliber

    for kind in ("turn_end_focus", "turn_end_impression", "turn_end_aggressive",
                 "turn_start_full_power", "search_hold", "preservation"):
        cal = rng_caliber((DrinkEffect(kind=kind, value=1, rng="none"),))
        assert cal["deterministic"] is True, kind


# ------------------------------------------------- 阶段1.5：引擎 oracle 配对
PROBE5_SCRIPT = ROOT / "data" / "_drinks_probe5.py"
PROBE5_JSON = ROOT / "data" / "_drinks_probe5.json"


@pytest.fixture(scope="module")
def probe5() -> dict:
    """引擎 oracle 逐瓶探针（data/_drinks_probe5.py 不提交；缺失时 skip）。"""
    if not PROBE5_SCRIPT.is_file():
        pytest.skip("缺少 data/_drinks_probe5.py（探针不提交）")
    if not (RINAMI / "W9").is_dir():
        pytest.skip("缺少实机样本 data/_rinami_live/W9（不提交）")
    if not _engine_available():
        pytest.skip("缺少引擎核心 gkmscore.dll 或 data/bench_repo")
    proc = subprocess.run(
        [sys.executable, str(PROBE5_SCRIPT)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    assert proc.returncode == 0, f"probe5 失败：{proc.stderr}\n{proc.stdout}"
    return json.loads(PROBE5_JSON.read_text(encoding="utf-8"))


def test_probe5_all_bottles_pass(probe5) -> None:
    """6 瓶（5 批次 + 焙茶）确定式段 rng_advances=0 + 结构增量全 PASS。"""
    assert probe5["all_pass"] is True
    assert len(probe5["bottles"]) == 6
    for rec in probe5["bottles"]:
        assert rec["drink_rng_advances"] == 0, rec["id"]
        assert rec["all_pass"] is True, (rec["id"], rec["checks"])


def test_probe5_drink_deltas_match_sim(probe5) -> None:
    """喝一瓶前后状态增量 ↔ sim 逐效果配对（指針/保留区/全力值/立即层数）。"""
    cat = get_catalog()
    for rec in probe5["bottles"]:
        spec = cat.spec_for(rec["id"])
        assert spec is not None
        deck = [CardSpec("占位", 0, 0)] * 6
        sim = LessonSim(
            list(deck),
            LessonConfig(turns=12, stamina=35, target_clear=1, stamina_max=35,
                         drinks=(spec,), hand_size=3),
            rng_seed=0,
        )
        sim.use_drink(0)
        d = rec["drink_delta"]
        # 立即增量：附魔类 0（登记）；焙茶 fpp+2；热绿茶指針 step2。
        assert sim.buffs.focus == d.get("focus", 0), rec["id"]
        assert sim.buffs.impression == d.get("impression", 0), rec["id"]
        assert sim.motivation == d.get("aggressive", 0), rec["id"]
        assert sim.stance.full_power_point == d.get("fpp", 0), rec["id"]
        assert sim.stance.save_level == d.get("stance_step", 0), rec["id"]
        if rec["id"] == "pdrink_03-2-007":
            assert len(sim.held) == rec["drink_hold_delta"] == 1
            assert str(sim.stance.stance) == "save"
        if rec["id"] == "pdrink_03-1-010":
            assert str(sim.stance.stance) == "save" and sim.stance.save_level == 1


def test_probe5_tea_decay_trajectory_pairing(probe5) -> None:
    """茶附魔好印象轨迹 ↔ 引擎 B 场景：impression 1,1,1 / 结算层 1,2,2。"""
    rows = {r["step"]: r for r in probe5["decay"]["B_tea"]}
    engine_imp = [rows[f"end{k}"]["impression"] for k in (1, 2, 3)]
    assert engine_imp == [1, 1, 1]
    engine_gains = [rows["end1"]["score"],
                    rows["end2"]["score"] - rows["end1"]["score"],
                    rows["end3"]["score"] - rows["end2"]["score"]]
    assert all(g > 0 for g in engine_gains)
    # sim 同口径：结算层 1,2,2（引擎分 = 层 × 当回合属性倍率，层数逐位配对）。
    spec = get_catalog().spec_for("pdrink_02-3-006")
    sim = LessonSim(
        [CardSpec("占位", 0, 0)] * 12,
        LessonConfig(turns=4, stamina=30, target_clear=100, drinks=(spec,), hand_size=3),
        rng_seed=0,
    )
    sim.use_drink(0)
    layers, imps = [], []
    for _ in range(3):
        s0 = sim.score
        sim.step(None)
        layers.append(sim.score - s0)
        imps.append(sim.buffs.impression)
    assert layers == [1, 2, 2] and imps == engine_imp
    # 引擎结算层数 = score_gain / 当回合倍率（35/35=1, 74/37=2, 50/25=2）——
    # 倍率未知但层数比一致：gain2/gain1 ≈ 2×(mult2/mult1)，这里只断言层数轨迹。


def test_probe5_hot_green_tea_select_is_player_choice(probe5) -> None:
    """热绿茶 Select 选牌事件：greedy_select_policy 玩家选择代理、候选∈deck_grave、不掷点。"""
    rec = next(r for r in probe5["bottles"] if r["id"] == "pdrink_03-2-007")
    assert len(rec["selects"]) == 1
    sel = rec["selects"][0]
    assert sel["produce_card_search_id"] == "p_card_search-deck_grave"
    assert sel["rule"] == "greedy_select_policy"
    assert sel["pick_min"] == sel["pick_max"] == 1
    assert len(sel["picked_numbers"]) == 1
    assert sel["picked_numbers"][0] in sel["candidate_numbers"]
    # sim 侧玩家选择代理 = hold_pick 白值降序（与引擎 greedy 是两种确定性代理，
    # 真实选取由玩家决定；结构增量 hold+1/deck-1 已在 deltas 测试配对）。


# ------------------------------------------------- 阶段2 batch2：catalog + classify
def test_batch2_catalog(catalog_payload) -> None:
    by_id = {d["id"]: d for d in catalog_payload["drinks"]}
    # 姜汁汽水 / 超级苏打：强气直给 1/2（+ 既有 fpp/half_cost）。
    assert {e["kind"] for e in by_id["pdrink_03-1-009"]["effects"]} == {
        "concentration", "full_power_point"}
    assert by_id["pdrink_03-1-009"]["implemented"] == 2
    conc = next(e for e in by_id["pdrink_03-3-009"]["effects"] if e["kind"] == "concentration")
    assert conc["value"] == 2 and conc["rng"] == "none"
    assert by_id["pdrink_03-3-009"]["implemented"] == 2
    # 黑醋汁：Select→hand + cost0（count=2）+ 既有 stamina_cost/double_cost。
    vinegar = by_id["pdrink_01-3-012"]
    assert vinegar["implemented"] == vinegar["total"] == 4
    kinds = {e["kind"]: e for e in vinegar["effects"]}
    assert kinds["select_move_hand"]["move_to"] == "hand" and kinds["select_move_hand"]["rng"] == "none"
    assert kinds["zero_cost"]["value"] == 2 and kinds["zero_cost"]["rng"] == "none"
    # 特制精华：再发动（v1=1/count=1/turn=1）。
    essence = by_id["pdrink_02-3-010"]
    assert essence["implemented"] == essence["total"] == 3
    enc = next(e for e in essence["effects"] if e["kind"] == "encore_active")
    assert enc["value"] == 1 and enc["turns"] == 1 and enc["rng"] == "none"


def test_batch2_classify() -> None:
    c1 = classify_drink_effect("ExamConcentration", {"effectValue1": 1})
    assert c1.kind == "concentration" and c1.value == 1 and c1.rng == "none"
    c2 = classify_drink_effect("ExamConcentration", {"effectValue1": 2})
    assert c2.kind == "concentration" and c2.value == 2
    assert classify_drink_effect("ExamConcentration", {}).kind == "unknown"
    m = classify_drink_effect(
        "ExamCardMove", {}, search="p_card_search-deck_grave", move_to="hand", pick="Select"
    )
    assert m.kind == "select_move_hand" and m.rng == "none"
    z = classify_drink_effect(
        "ExamSearchPlayCardStaminaConsumptionChange",
        {"effectValue1": 0, "effectCount": 2, "effectTurn": -1},
    )
    assert z.kind == "zero_cost" and z.value == 2 and z.rng == "none"
    assert classify_drink_effect(
        "ExamSearchPlayCardStaminaConsumptionChange", {"effectValue1": 5, "effectCount": 2}
    ).kind == "unknown"
    e = classify_drink_effect(
        "ExamCardSearchEffectPlayCountBuff",
        {"effectValue1": 1, "effectCount": 1, "effectTurn": 1},
    )
    assert e.kind == "encore_active" and e.turns == 1 and e.rng == "none"
    assert classify_drink_effect(
        "ExamCardSearchEffectPlayCountBuff", {"effectValue1": 2, "effectCount": 1, "effectTurn": 1}
    ).kind == "unknown"


# ------------------------------------------------- 阶段2 batch2：逐效果单测（双镜）
def _batch2_play(sim, state):
    """打手牌首张（0 抽牌），双镜同步；sim 自动换回合时 state 跟进。"""
    card = sim.hand[0]
    turn0 = sim.current_turn
    sim.step(0)
    outcomes = apply_card(state, card)
    assert len(outcomes) == 1
    state = outcomes[0][1]
    if sim.current_turn != turn0:
        state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    return state


def test_batch2_concentration_stance() -> None:
    for did, level, stance in (("pdrink_03-1-009", 1, "strong1"), ("pdrink_03-3-009", 2, "strong2")):
        spec = get_catalog().spec_for(did)
        sim, state = _mirror(spec)
        sim.use_drink(0)
        state = use_drink_state(state, 0)
        assert str(sim.stance.stance) == stance and sim.stance.strong_level == level
        assert state.stance[0] == stance and state.stance[1] == level
        _assert_mirror(sim, state)


def test_batch2_select_move_hand() -> None:
    hi = CardSpec("高分", 0, 9)
    deck = [hi, CardSpec("低分", 0, 1)] + [CardSpec("占位", 0, 0)] * 4
    spec = get_catalog().spec_for("pdrink_01-3-012")
    sim, state = _mirror(spec, deck=deck)
    # 初始洗牌可能把高分抽进手牌：期望选取 = 当时 deck+discard 白值最高张。
    expected = max(list(sim.deck) + list(sim.discard), key=lambda c: c.score)
    hand0 = len(sim.hand)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert len(sim.hand) == hand0 + 1 and len(state.hand) == hand0 + 1
    assert sim.hand[-1] == expected and state.hand[-1] == expected
    assert expected not in sim.deck
    _assert_mirror(sim, state)


def test_batch2_zero_cost_charges() -> None:
    """cost0：前 2 张正费牌整费归零（stamina/block 支付 0），0 费牌不耗次数，第 3 张恢复。"""
    deck = [CardSpec("打分", 8, 10)] * 10
    spec = get_catalog().spec_for("pdrink_01-3-012")
    sim, state = _mirror(spec, deck=deck, plays_per_turn=4)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.zero_cost_charges == 2 and state.zero_cost_charges == 2
    stamina0 = sim.stamina
    state = _batch2_play(sim, state)
    assert sim.stamina == stamina0 and sim.zero_cost_charges == 1
    assert state.zero_cost_charges == 1
    state = _batch2_play(sim, state)
    assert sim.stamina == stamina0 and sim.zero_cost_charges == 0
    state = _batch2_play(sim, state)
    assert sim.stamina < stamina0  # 第 3 张正常扣费（double_cost ×2）
    _assert_mirror(sim, state)


def test_batch2_zero_cost_free_card_no_consume() -> None:
    # 全 0 费牌堆：连打 4 张（跨自动换回合）次数始终不耗（probe6 口径）。
    deck = [CardSpec("免费", 0, 5)] * 10
    spec = get_catalog().spec_for("pdrink_01-3-012")
    sim, state = _mirror(spec, deck=deck, plays_per_turn=4)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    for _ in range(4):
        state = _batch2_play(sim, state)
        assert sim.zero_cost_charges == 2 and state.zero_cost_charges == 2
    _assert_mirror(sim, state)


def test_batch2_encore_active() -> None:
    """再发动：首张 ActiveSkill 直接效果 ×2（1 次），第 2 张正常，跨回合过期。"""
    deck = [CardSpec("主动", 0, 18, category="ActiveSkill")] * 10
    spec = get_catalog().spec_for("pdrink_02-3-010")
    sim, state = _mirror(spec, deck=deck, plays_per_turn=3)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    assert sim.encore_charges == 1 and sim.encore_turns == 2
    state = _batch2_play(sim, state)
    assert sim.score == 36 and state.score == 36  # 18 × 2
    assert sim.encore_charges == 0 and state.encore_charges == 0
    state = _batch2_play(sim, state)
    assert sim.score == 54 and state.score == 54  # 第 2 张 +18 正常
    sim.step(None)
    state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    state = _batch2_play(sim, state)
    assert sim.score == 72 and state.score == 72  # 下一回合 +18（次数已耗尽）
    _assert_mirror(sim, state)


def test_batch2_encore_mental_not_doubled() -> None:
    deck = [CardSpec("mental", 0, 18, category="MentalSkill")] * 8
    spec = get_catalog().spec_for("pdrink_02-3-010")
    sim, state = _mirror(spec, deck=deck, plays_per_turn=2)
    sim.use_drink(0)
    state = use_drink_state(state, 0)
    state = _batch2_play(sim, state)
    assert sim.score == 18 and state.score == 18  # MentalSkill 不触发再发动
    assert sim.encore_charges == 1  # 次数保留到下一张主动卡
    _assert_mirror(sim, state)


# ------------------------------------------------- SAFE 划分 + 特征提取器
def test_safe_kinds_classification() -> None:
    from gkagent.sim.drinks import SAFE_KINDS, drink_is_safe

    cat = get_catalog()
    # SAFE：纯数值段（蛋白粉/强化精华/姜汁汽水/严选初星附魔/焙茶/超级苏打）。
    for did in ("pdrink_00-3-001", "pdrink_00-2-008", "pdrink_03-1-009",
                "pdrink_01-3-002", "pdrink_03-1-010", "pdrink_03-3-009"):
        assert drink_is_safe(cat.spec_for(did).effects), did
    # EXCLUDE：改牌区/回合数/再发动/unknown。
    for did in ("pdrink_00-2-010", "pdrink_00-2-009", "pdrink_03-2-007",
                "pdrink_01-3-012", "pdrink_02-3-010", "pdrink_03-3-011",
                "pdrink_00-3-005", "pdrink_00-3-013"):
        assert not drink_is_safe(cat.spec_for(did).effects), did
    assert "encore_active" not in SAFE_KINDS
    assert "concentration" in SAFE_KINDS and "zero_cost" in SAFE_KINDS
    assert not drink_is_safe(())


def test_drink_feature_extractor() -> None:
    from gkagent.sim.drink_features import (
        DRINK_FEATURE_DIM,
        DRINK_FEATURE_NAMES,
        drink_feature_vector,
        drink_features_from_ids,
    )

    cat = get_catalog()
    protein = cat.spec_for("pdrink_00-3-001")
    vec = drink_feature_vector((protein,), (1,))
    assert len(vec) == DRINK_FEATURE_DIM == len(DRINK_FEATURE_NAMES)
    idx = DRINK_FEATURE_NAMES.index("drink_kind_extra_plays")
    assert vec[idx] == 1.0
    assert vec[DRINK_FEATURE_NAMES.index("drink_slots_remaining")] == 1.0
    assert vec[DRINK_FEATURE_NAMES.index("drink_safe_slots")] == 1.0
    assert vec[DRINK_FEATURE_NAMES.index("drink_unknown_segments")] == 0.0
    # 青汁：unknown 计段不计值，非 SAFE。
    aojiru = cat.spec_for("pdrink_00-3-005")
    vec2 = drink_feature_vector((aojiru,), (1,))
    assert vec2[DRINK_FEATURE_NAMES.index("drink_unknown_segments")] == 1.0
    assert vec2[DRINK_FEATURE_NAMES.index("drink_safe_slots")] == 0.0
    # 剩余次数加权：耗尽槽位 kind 位/剩余位归零，total_slots 仍计初始库存。
    exhausted = drink_feature_vector((protein,), (0,))
    assert exhausted[idx] == 0.0
    assert exhausted[DRINK_FEATURE_NAMES.index("drink_slots_remaining")] == 0.0
    assert exhausted[DRINK_FEATURE_NAMES.index("drink_total_slots")] == 1.0
    assert drink_features_from_ids(None) == (0.0,) * DRINK_FEATURE_DIM
    v_ids = drink_features_from_ids(["pdrink_00-3-001", "pdrink_00-3-001"])
    assert v_ids[idx] == 2.0  # 不去重
    assert v_ids == drink_feature_vector((protein, protein))


# ------------------------------------------------- 阶段2 ②：allow_drinks opt-in
def test_policy_allow_drinks_default_off() -> None:
    from gkagent.policy.lesson import LessonPolicy

    assert LessonPolicy.DEFAULT_PARAMS["allow_drinks"] is False
    assert LessonPolicy().params["allow_drinks"] is False
    assert LessonPolicy(allow_drinks=True).params["allow_drinks"] is True


def test_expectimax_allow_drinks_gate() -> None:
    """搜索层：allow_drinks=False 不枚举饮料（旧行为）；True 时有益饮料被选中。"""
    from gkagent.sim.expectimax import AnalyticLeafValue, expectimax_with_stats

    protein = get_catalog().spec_for("pdrink_00-3-001")
    hand = (CardSpec("打分A", 3, 10), CardSpec("打分B", 3, 10))
    state = ExpectState(
        hand=hand, deck=(CardSpec("占位", 0, 0),) * 6,
        stamina=30, stamina_max=30, turns_left=3, total_turns=3,
        play_limit=1, plays_used=0, clear=100, perfect=200,
        drinks=(protein,), drink_uses=(1,),
    )
    off = expectimax_with_stats(state, AnalyticLeafValue(), time_budget_ms=2000, allow_drinks=False)
    assert off.drink is None
    on = expectimax_with_stats(state, AnalyticLeafValue(), time_budget_ms=2000, allow_drinks=True)
    assert on.drink == 0  # extra_plays 解锁第 2 张打分牌


def test_policy_drink_action_branch(monkeypatch) -> None:
    """LessonPolicy opt-in：搜索选中饮料 → LessonAction(kind='drink', index=槽位)。"""
    import gkagent.sim.expectimax as ex
    from gkagent.policy.lesson import LessonAction, LessonPolicy

    policy = LessonPolicy(engine="expectimax", allow_drinks=True)
    protein = get_catalog().spec_for("pdrink_00-3-001")
    sim_state = ExpectState(
        hand=(CardSpec("打分", 3, 10),), stamina=30, turns_left=3,
        drinks=(protein,), drink_uses=(1,),
    )
    monkeypatch.setattr(policy, "_search_state", lambda state: (sim_state, [], None))

    class _Result:
        card = None
        drink = 0
        utility = 42.0
        nodes = 7
        elapsed_ms = 1.0
        complete = True
        actions = ()

    captured = {}

    def fake_search(state, leaf, **kw):
        captured.update(kw)
        return _Result()

    monkeypatch.setattr(ex, "expectimax_with_stats", fake_search)
    from gkagent.vision.lesson import LessonState

    action = policy._try_expectimax(LessonState(turns_left=3, stamina=30), allow_skip=True)
    assert captured["allow_drinks"] is True
    assert isinstance(action, LessonAction) and action.kind == "drink" and action.index == 0
    # 默认 off：allow_drinks=False 传给搜索（逐位不变）。
    policy_off = LessonPolicy(engine="expectimax")
    monkeypatch.setattr(policy_off, "_search_state", lambda state: (sim_state, [], None))
    policy_off._try_expectimax(LessonState(turns_left=3, stamina=30), allow_skip=True)
    assert captured["allow_drinks"] is False


def test_local_bench_drink_legal_wiring() -> None:
    """local_bench：--drinks auto 时 legal 暴露 drink 动作；off 逐位不变（无 drink）。"""
    problems = ROOT / "data" / "bench_local" / "problems_hif.json"
    if not problems.is_file() or not DRINKS_JSON.is_file():
        pytest.skip("缺少题集或 drinks.json")
    lb = _local_bench_module()
    raw = lb.load_problems(problems)[0]
    rows, index, refs = lb.load_card_table()
    auto = lb.build_problem(raw, rows, index, refs, drinks_mode="auto")
    off = lb.build_problem(raw, rows, index, refs, drinks_mode="off")
    deck = [CardSpec("占位", 0, 0)] * 8
    sim_auto = LessonSim(list(deck), auto.config, rng_seed=0)
    sim_off = LessonSim(list(deck), off.config, rng_seed=0)
    obs_auto = lb.sim_to_uiobs(sim_auto, auto, decision=0, played=[])
    obs_off = lb.sim_to_uiobs(sim_off, off, decision=0, played=[])
    assert not any(a[0] == "drink" for a in obs_off["legal"])
    if auto.config.drinks:
        assert any(a[0] == "drink" for a in obs_auto["legal"])


# ------------------------------------------------- 阶段3①：饮料搜索预算杠杆
def _lever_state():
    """蛋白粉有益局面：play_limit=1，手牌 2 张正分牌 → extra_plays 解锁第 2 张。"""
    protein = get_catalog().spec_for("pdrink_00-3-001")
    return ExpectState(
        hand=(CardSpec("打分A", 3, 10), CardSpec("打分B", 3, 10)),
        deck=tuple(CardSpec(f"占位{i}", 0, 0) for i in range(6)),
        stamina=30, stamina_max=30, turns_left=2, total_turns=2,
        play_limit=1, plays_used=0, clear=100, perfect=200,
        drinks=(protein,), drink_uses=(1,),
    )


def test_lever_defaults_bit_identical() -> None:
    from gkagent.sim.expectimax import AnalyticLeafValue, ExpectimaxConfig, expectimax_with_stats

    cfg = ExpectimaxConfig()
    assert cfg.drink_root_only is False and cfg.drink_first is False and cfg.drink_top_k == 1
    state = _lever_state()
    base = expectimax_with_stats(state, AnalyticLeafValue(), time_budget_ms=5000)
    explicit = expectimax_with_stats(
        state, AnalyticLeafValue(), time_budget_ms=5000,
        drink_root_only=False, drink_first=False, drink_top_k=1,
    )
    assert (base.card, base.drink, base.utility, base.nodes) == (
        explicit.card, explicit.drink, explicit.utility, explicit.nodes)
    assert base.drink == 0  # 完全搜索：蛋白粉解锁第 2 张


def test_lever_drink_first_anytime_retention() -> None:
    """杠杆②：节点上限构造超时——drink_first 保留已搜到的 drink；旧序全丢。"""
    from gkagent.sim.expectimax import AnalyticLeafValue, expectimax_with_stats

    protein = get_catalog().spec_for("pdrink_00-3-001")
    state = ExpectState(
        hand=tuple(CardSpec(f"c{i}", 3, 10 + i) for i in range(4)),
        deck=tuple(CardSpec(f"p{i}", 0, 0) for i in range(10)),
        stamina=30, stamina_max=30, turns_left=3, total_turns=3,
        play_limit=1, clear=100, perfect=200, drinks=(protein,), drink_uses=(1,),
    )
    # cap=18 实测分离点：旧序卡先搜（~8 节点）后饮料子树撞上限 → drink 从未评估；
    # 新序饮料子树（~14 节点）先完成 → 超时保留 drink=0（单变量 drink_first）。
    old = expectimax_with_stats(
        state, AnalyticLeafValue(), time_budget_ms=5000, max_nodes=18)
    new = expectimax_with_stats(
        state, AnalyticLeafValue(), time_budget_ms=5000, max_nodes=18, drink_first=True)
    assert not old.complete and not new.complete
    assert old.drink is None
    assert new.drink == 0


def test_lever_root_only_saves_nodes() -> None:
    """杠杆①：递归不展开饮料 → 完全搜索节点数严格下降，根仍选有益饮料。"""
    from gkagent.sim.expectimax import AnalyticLeafValue, expectimax_with_stats

    protein = get_catalog().spec_for("pdrink_00-3-001")
    # uses=2：递归节点可再喝（默认展开）；root_only 只根节点 1 个饮料子树。
    state = ExpectState(
        hand=(CardSpec("A", 3, 10), CardSpec("B", 3, 11)),
        deck=tuple(CardSpec(f"p{i}", 0, 0) for i in range(6)),
        stamina=30, stamina_max=30, turns_left=2, total_turns=2,
        play_limit=1, clear=100, perfect=200, drinks=(protein,), drink_uses=(2,),
    )
    base = expectimax_with_stats(state, AnalyticLeafValue(), time_budget_ms=5000)
    lean = expectimax_with_stats(
        state, AnalyticLeafValue(), time_budget_ms=5000, drink_root_only=True)
    assert base.complete and lean.complete
    assert base.drink == 0 and lean.drink == 0
    assert lean.nodes < base.nodes  # 实测 14 → 7


def test_lever_top_k_candidates() -> None:
    """杠杆③：候选 top-k（默认 1 → k 按优先级）。"""
    from gkagent.sim.expectimax import _candidate_drinks

    cat = get_catalog()
    protein = cat.spec_for("pdrink_00-3-001")
    coffee = cat.spec_for("pdrink_01-1-003")  # 集中+3（priority 2）
    state = ExpectState(
        hand=(CardSpec("打分", 3, 10),), stamina=30, turns_left=2,
        play_limit=1, clear=100, perfect=200,
        drinks=(protein, coffee), drink_uses=(1, 1),
    )
    assert len(_candidate_drinks(state)) == 1
    assert len(_candidate_drinks(state, 2)) == 2
    assert _candidate_drinks(state, 2)[0] == _candidate_drinks(state)[0]


# --------------------------------------------------------------------- opt-in 接线
def test_resolve_drink_ids_none_is_empty() -> None:
    loadout = resolve_drink_ids(None)
    assert loadout.specs == ()
    assert loadout.ids == ()
    assert not loadout.has_unknown


def test_resolve_w9_loadout_slots() -> None:
    if not DRINKS_JSON.is_file():
        pytest.skip("缺少 drinks.json")
    ids = ["pdrink_00-2-010", "pdrink_00-2-010", "pdrink_00-3-001", "pdrink_00-2-009"]
    loadout = resolve_drink_ids(ids)
    assert len(loadout.specs) == 4  # 不去重：两瓶苏打 = 两个槽位
    assert loadout.unknown_ids == ()
    # 4 槽位 = 苏打×2 + 蛋白粉 + 汉方；段数 4+4+1+2 = 11 全实现。
    assert loadout.summary()["implemented"] == 4 + 4 + 1 + 2
    assert all(spec.effects for spec in loadout.specs)


def test_resolve_unknown_id_reported() -> None:
    if not DRINKS_JSON.is_file():
        pytest.skip("缺少 drinks.json")
    loadout = resolve_drink_ids(["pdrink_no-such-999"])
    assert loadout.specs == ()
    assert loadout.unknown_ids == ("pdrink_no-such-999",)


def test_default_off_bit_identical() -> None:
    """默认不注入饮料（drinks=()）与显式空 loadout 注入逐位一致。"""
    deck = [CardSpec("打分", 1, 9), CardSpec("占位", 0, 0)] * 3
    cfg = LessonConfig(turns=3, stamina=20, target_clear=30)
    base = LessonSim(list(deck), cfg, rng_seed=7)
    empty = resolve_drink_ids(None)
    injected = LessonSim(
        list(deck),
        LessonConfig(turns=3, stamina=20, target_clear=30, drinks=empty.specs),
        rng_seed=7,
    )
    assert base.score == injected.score
    assert base.stamina == injected.stamina
    assert base.drink_uses == injected.drink_uses == []


def test_missing_catalog_raises() -> None:
    with pytest.raises(DrinkDataUnavailable):
        load_drink_catalog(ROOT / "data" / "knowledge" / "no_such_drinks.json")


# --------------------------------------------------------------------- 实机重放门
def _engine_available() -> bool:
    return DLL.is_file() and BENCH_REPO.is_dir()


def _run_replay(round_name: str) -> dict:
    round_dir = RINAMI / round_name
    if not round_dir.is_dir():
        pytest.skip(f"缺少实机样本 data/_rinami_live/{round_name}（不提交）")
    if not _engine_available():
        pytest.skip("缺少引擎核心 gkmscore.dll 或 data/bench_repo")
    out = ROOT / "out" / f"_drinks_test_{round_name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(REPLAY_SCRIPT), str(round_dir), "--out", str(out)],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode == 2:
        pytest.skip(f"重放脚本退出码 2（样本/引擎缺失）：{proc.stderr.strip()}")
    assert proc.returncode == 0, f"重放失败：{proc.stderr}\n{proc.stdout}"
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def w9_replay() -> dict:
    return _run_replay("W9")


@pytest.fixture(scope="module")
def w7_replay() -> dict:
    return _run_replay("W7")


def test_w9_replay_final_score(w9_replay) -> None:
    """W9 全重放门：终分逐位 = 1,426,865（GKMS rev318/v55 实机一致）。"""
    assert w9_replay["final_score"] == 1426865
    assert w9_replay["expect_score"] == 1426865
    assert w9_replay["finished"] is True
    assert w9_replay["turns"] == 12


def test_w9_replay_opening_matches(w9_replay) -> None:
    assert w9_replay["opening_rng_match"] is True
    assert w9_replay["opening_rng"] == 374278409
    assert w9_replay["hand_match"] is True
    assert w9_replay["deck_match"] is True


def test_w9_replay_per_decision_rng(w9_replay) -> None:
    """逐决策 rng/score/turn/card 全匹配（含 4 饮料步），0 mismatch。"""
    assert w9_replay["n_actions"] == 45
    assert w9_replay["n_decisions"] == 45
    assert w9_replay["decision_mismatches"] == []
    assert len(w9_replay["drink_steps"]) == 4


def test_w9_drink_ids_and_labels(w9_replay) -> None:
    steps = w9_replay["drink_steps"]
    assert [s["drink"] for s in steps] == [
        "pdrink_00-3-001", "pdrink_00-2-010", "pdrink_00-2-010", "pdrink_00-2-009",
    ]
    # 实机 auto-drink-confirm labels 权威文本逐字核对。
    protein = steps[0]["label"]["labels"]
    assert any("技能卡使用数追加" in str(l) for l in protein)
    soda = steps[1]["label"]["labels"]
    soda_text = " ".join(str(l) for l in soda)
    assert "得分上升量增加" in soda_text and "技能卡抽取" in soda_text
    assert "体力消耗" in soda_text and "回合开始后" in soda_text
    herbal = steps[3]["label"]["labels"]
    herbal_text = " ".join(str(l) for l in herbal)
    assert "偶像固有技能卡" in herbal_text and "消耗体力减少" in herbal_text


def test_w9_drink_deltas_match_sim(w9_replay) -> None:
    """引擎 oracle 喝一瓶前后状态增量 ↔ sim 饮料效果引擎逐效果配对。"""
    if not DRINKS_JSON.is_file():
        pytest.skip("缺少 drinks.json")
    cat = get_catalog()
    for step in w9_replay["drink_steps"]:
        spec = cat.spec_for(step["drink"])
        assert spec is not None
        before, after = step["before"], step["after"]
        d_score = after["score"] - before["score"]
        d_stamina = after["stamina"] - before["stamina"]
        d_focus = after["focus"] - before["focus"]
        d_plays = after["extra_plays"] - before["extra_plays"]
        d_hand = len(after["hand"]) - len(before["hand"])
        # 用 sim 在相同前置状态下喝同一瓶，比对增量。
        sim = LessonSim(
            [CardSpec("占位", 0, 0)] * 6,
            LessonConfig(turns=12, stamina=before["stamina"], target_clear=1,
                         stamina_max=35, drinks=(spec,), hand_size=3),
            rng_seed=0,
        )
        sim.extra_plays = before["extra_plays"]
        sim.buffs.focus = before["focus"]
        sim.use_drink(0)
        # W9 四瓶都不直接加分（score_buff 是倍率、不是直接分）：d_score == 0。
        assert sim.score == d_score, (step["drink"], "score", d_score)
        assert sim.buffs.focus - before["focus"] == d_focus, (step["drink"], "focus")
        assert sim.extra_plays - before["extra_plays"] == d_plays, (step["drink"], "plays")
        # 体力增量：stamina_cost 段（苏打 -2）；sim 饮料 cost=0 + stamina_cost 段。
        expected_stamina = sum(
            -e.value for e in spec.effects if e.implemented and e.kind == "stamina_cost"
        ) + sum(e.value for e in spec.effects if e.implemented and e.kind == "stamina")
        assert d_stamina == expected_stamina, (step["drink"], "stamina", d_stamina)
        # 立即抽牌张数（苏打 +2；汉方 search_move +1）。
        expected_draw = sum(
            e.value for e in spec.effects if e.implemented and e.kind in ("draw", "search_move")
        )
        assert d_hand == expected_draw, (step["drink"], "hand", d_hand)


def test_w7_replay_no_drinks_regression(w7_replay) -> None:
    """W7（0 饮料使用）回归：终分 655,198 不变，逐决策 0 mismatch。

    W7 loadout 携带饮料但实机一瓶没喝（drink_steps=0）——纯机制对照场。
    """
    assert w7_replay["final_score"] == 655198
    assert w7_replay["expect_score"] == 655198
    assert w7_replay["decision_mismatches"] == []
    assert len(w7_replay["drink_steps"]) == 0
    assert w7_replay["opening_rng_match"] is True


# --------------------------------------------------------------------- local_bench 注入
def _local_bench_module():
    import importlib.util

    path = ROOT / "scripts" / "local_bench.py"
    spec = importlib.util.spec_from_file_location("local_bench_drinks_test", path)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses 注解解析要查 sys.modules[cls.__module__]，必须先注册再 exec。
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_local_bench_drinks_opt_in() -> None:
    """--drinks 默认 off 逐位不变；auto 按 loadout.drink_ids 注入槽位（不去重）。"""
    problems = ROOT / "data" / "bench_local" / "problems_hif.json"
    if not problems.is_file() or not DRINKS_JSON.is_file():
        pytest.skip("缺少题集或 drinks.json")
    lb = _local_bench_module()
    raw = lb.load_problems(problems)[0]
    rows, index, refs = lb.load_card_table()
    default = lb.build_problem(raw, rows, index, refs)
    off = lb.build_problem(raw, rows, index, refs, drinks_mode="off")
    auto = lb.build_problem(raw, rows, index, refs, drinks_mode="auto")
    assert default.config.drinks == ()
    assert off.config.drinks == ()
    assert off.drink_stats.mode == "off" and off.drink_stats.ids == 0
    assert auto.drink_stats.mode == "auto"
    loadout = (raw.get("archive") or {}).get("loadout") or {}
    ids = [str(x) for x in (loadout.get("drink_ids") or []) if x]
    assert auto.drink_stats.ids == len(ids)
    assert len(auto.config.drinks) == auto.drink_stats.slots
    assert auto.drink_stats.slots <= len(ids)  # 未知 id 不注入但显式上报
    assert auto.drink_stats.known + len(auto.drink_stats.unknown) >= auto.drink_stats.slots
