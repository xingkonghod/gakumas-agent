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
    # 33 段语义确定已实现，18 段显式 no-op（不猜）。
    assert catalog_payload["segments_implemented"] == 33
    drinks = catalog_payload["drinks"]
    assert len(drinks) == 29
    assert sum(d["total"] for d in drinks) == 51
    assert sum(d["implemented"] for d in drinks) == 33


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
    assert len(unknown) == 18
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
