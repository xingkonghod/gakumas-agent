"""B10（2026-11-23）T5 剩余机制①②：生成卡 + 指定卡名/手牌张数映射 回归测试。

覆盖五块：

1. 数据层 ``parse_card_search``：指定卡名 / 偶像固有 / 效果组 / 费用 / 类别 /
   稀有度 / 区域张数（含 negate）/ hold 与未知词保守不解析；
2. ``card_meta`` 索引：idol_unique 判据（与参考引擎 pIdol 交叉验证）、效果组、
   日文别名、(id, upgrade) → 卡名；
3. ``sim/p_items`` 触发限定求值：play_filter / zone_count（真数据 spec + 真卡名）；
4. 生成卡（``ExamCardCreateId`` 确定式）：LessonSim / ExpectState 双镜落牌
   （手牌≥5 不生成 / 牌堆顶 / 弃牌堆）、exam_start_after 时机、随机式保持 no-op；
5. 次数上限按道具计（同事件多效果段只记 1 次，B10 口径修正）。

语义来源：masterTrans/ProduceCardSearch.json + 主数据 ProduceCard.effectGroupIds /
originIdolCardId / originCharacterId + BSD-3 参考引擎 gakumas-tools（usedCardBaseId /
countCards / addCardTo* / limit:N）。参考 csv 在 data/dl/（gitignore），缺失时跳过交叉验证。
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_p_items

from gkagent.data.card_meta import CardMetaIndex, card_meta_index
from gkagent.sim.expectimax import ExpectState, fire_p_items, state_from_sim
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    CARD_PLAY,
    EXAM_START_AFTER,
    STATUS_GAIN,
    TURN_START_AFTER,
    CardFilter,
    CreateCard,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    ZoneCount,
    apply_passive,
    load_p_items,
)
from gkagent.sim.play_choice import spec_from_name

ITEMS = load_p_items()
REF_CSV = ROOT / "data/dl/gt/gakumas-tools-master/packages/gakumas-data/csv"


def _specs(item_id: str) -> list[PItemSpec]:
    return [spec for spec in ITEMS if spec.item_id == item_id]


def _spec(item_id: str, effect_type: str) -> PItemSpec:
    for spec in _specs(item_id):
        if spec.effect_type == effect_type:
            return spec
    raise AssertionError(f"{item_id} 没有 {effect_type} 段")


def _config(**kwargs) -> LessonConfig:
    base = {"turns": 2, "stamina": 30, "target_clear": 1, "hand_size": 3, "plays_per_turn": 1}
    base.update(kwargs)
    return LessonConfig(**base)


def _state(**kwargs) -> PassiveState:
    base = {"turn": 1, "turns_left": 2, "stamina": 30, "stamina_max": 30, "zones_known": True}
    base.update(kwargs)
    return PassiveState(**base)


# ---- 1. 数据层：parse_card_search -------------------------------------------


def test_parse_specific_card_play_filter() -> None:
    play, zone, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play-p_card_search-playing-p_card-01-ido-1_058-0_1"
    )
    assert unresolved is False and zone is None
    assert play == {"kind": "card", "card_id": "p_card-01-ido-1_058", "upgrade": 0, "count": 1}


def test_parse_specific_card_target_filter() -> None:
    play, zone, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play_after-p_card_search-target-1-p_card-01-act-1_002-0_1"
    )
    assert unresolved is False and zone is None
    assert play["kind"] == "card" and play["card_id"] == "p_card-01-act-1_002"


def test_parse_idol_unique_and_effect_group_and_cost() -> None:
    play, _, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play-p_card_search-playing-idol-unique-0_1"
    )
    assert unresolved is False and play == {"kind": "idol_unique"}
    play, _, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play-p_card_search-playing-effect_group-visible-exam_lesson_buff-000-0_1"
    )
    assert unresolved is False
    assert play == {"kind": "effect_group", "group": "effect_group-visible-exam_lesson_buff-000"}
    play, _, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play-p_card_search-playing-min_max-4_99-0_1"
    )
    assert unresolved is False
    assert play == {"kind": "cost", "cost_min": 4, "cost_max": 99}


def test_parse_category_and_rarity_filters() -> None:
    play, _, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play-p_card_search-active_skill-playing-0_1"
    )
    assert unresolved is False
    assert play == {"kind": "category", "category": "ActiveSkill"}
    play, _, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play-remaining_turn-3-p_card_search-ssr-playing-0_1"
    )
    assert unresolved is False and play == {"rarities": ["SSR"]}


def test_parse_any_card_filter_is_none() -> None:
    """playing-0_1 = 任意技能卡 → 无额外限定（None），不是 kind=any 的假限定。"""
    play, zone, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play-p_card_search-playing-0_1"
    )
    assert (play, zone, unresolved) == (None, None, False)


def test_parse_zone_counts() -> None:
    play, zone, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_start_turn-card_search_count_up-7-p_card_search-trouble-deck_grave"
    )
    assert unresolved is False and play is None
    assert zone == {
        "zones": ["deck", "discard"],
        "min": 7,
        "negate": False,
        "filter": {"trouble": True},
    }
    _, zone, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_end_turn_interval-2-not-card_search_count_up-9-p_card_search-lost"
    )
    assert unresolved is False
    assert zone["zones"] == ["excluded"] and zone["min"] == 9 and zone["negate"] is True
    _, zone, _ = build_p_items.parse_card_search(
        "e_trigger-exam_start_exam-card_search_count_up-21-p_card_search-r-sr-ssr-legend-deck_all"
    )
    assert zone["zones"] == ["deck", "hand", "discard", "excluded"]
    assert zone["filter"] == {"rarities": ["R", "SR", "SSR", "LEGEND"]}


def test_parse_hand_specific_card_count() -> None:
    play, zone, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play_after-card_search_count_up-1-p_card_search-hand-p_card-00-acc-0_002-p_card_search-target-0_1"
    )
    assert unresolved is False
    assert zone["zones"] == ["hand"] and zone["min"] == 1
    assert zone["filter"]["card_id"] == "p_card-00-acc-0_002"
    assert play is None  # target-0_1 = 任意卡


def test_hold_zone_parsed_and_unknown_token_stays_unresolved() -> None:
    """P1-3：hold 保留区已建模 → 张数条件结构化解析（zones=["held"]）；
    period810_hotfix 证实为非限定标记（masterTrans 描述表无此目标 + 参考 DSL
    无卡过滤 + 中文触发句无卡限定）→ 解析通过；真正未知词仍保守跳过。"""
    trigger_id = (
        "e_trigger-exam_card_play_after-card_search_count_up-1-p_card_search-hold-"
        "p_card_search-target-1-p_card-03-act-1_038-0_1"
    )
    assert build_p_items.trigger_id_has_unparsed_condition(trigger_id) is False
    play_filter, zone_count, unresolved = build_p_items.parse_card_search(trigger_id)
    assert unresolved is False
    assert zone_count == {"zones": ["held"], "min": 1, "negate": False, "filter": None}
    assert play_filter == {
        "kind": "card", "card_id": "p_card-03-act-1_038", "upgrade": 0, "count": 1,
    }
    assert build_p_items.trigger_id_has_unparsed_condition(
        "e_trigger-exam_play_turn_count_interval-2-p_card_search-target-period810_hotfix"
    ) is False
    assert build_p_items.trigger_id_has_unparsed_condition(
        "e_trigger-exam_card_play_after-p_card_search-target-some_unknown_token"
    ) is True


def test_produce_domain_search_target_not_unresolved() -> None:
    """育成期「获得技能卡」的搜索目标不是考试限定 → 不算 unresolved。"""
    assert build_p_items.trigger_id_has_unparsed_condition(
        "p_trigger-get_produce_card-0000_0000-p_card_search-deck_all-effect_group-visible-exam_block-000"
    ) is False


def test_real_catalog_b10_stats() -> None:
    payload = json.loads((ROOT / "data/knowledge/p_items.json").read_text(encoding="utf-8-sig"))
    stats = payload["stats"]
    # P1-3：hold 保留区 2 件 + period810_hotfix 1 件解析 → 触发未知 3→0
    assert stats["items_trigger_unknown"] == 0
    assert stats["items_condition_unknown"] == 0
    assert stats["items_play_filter"] >= 100
    assert stats["items_zone_count"] >= 20
    assert stats["effects_create_card"] == 11
    assert stats["effects_create_random"] == 6
    # 偶像固有触发不再带旧 IdolUnique 类别标签（卡表 category 词表没有它）。
    for record in payload["items"]:
        pf = record["trigger_params"].get("play_filter") or {}
        if pf.get("kind") == "idol_unique":
            assert "card_filter" not in record["trigger_params"], record["id"]


def test_real_create_annotations() -> None:
    payload = json.loads((ROOT / "data/knowledge/p_items.json").read_text(encoding="utf-8-sig"))
    records = {r["id"]: r for r in payload["items"]}
    assert records["pitem_01-3-127-0"]["effects"][0]["create"] == {
        "card_id": "p_card-01-men-2_035", "upgrade": 1, "zone": "hand", "count": 1,
    }
    assert records["pitem_02-3-128-0"]["effects"][0]["create"]["card_id"] == "p_card-02-men-2_054"
    assert records["pitem_03-3-129-0"]["effects"][0]["create"]["card_id"] == "p_card-03-men-2_066"
    goddess = records["pitem_01-3-131-0"]["effects"]
    assert goddess[2]["create"] == {
        "card_id": "p_card-00-acc-0_002", "upgrade": 0, "zone": "deck_top", "count": 1,
    }
    tower = records["pitem_tower_001-exam_review-1-stage_022"]["effects"][0]
    assert tower["create"]["zone"] == "discard"
    cheer = records["pitem_01-3-266-0"]["effects"][0]
    assert cheer["create_random"] == {"kind": "basic_to_deck_count", "deck_target": 22}
    assert "create" not in cheer


# ---- 2. card_meta 索引 -------------------------------------------------------


def test_card_meta_basic_lookup() -> None:
    index = card_meta_index()
    meta = index.meta("轻快步伐")
    assert meta is not None
    assert meta.card_id == "p_card-01-act-1_002" and meta.category == "ActiveSkill"
    assert meta.cost == 4 and meta.rarity == "R"
    assert index.meta("不存在的卡") is None


def test_card_meta_idol_unique() -> None:
    index = card_meta_index()
    assert index.meta("初次的褒奖").idol_unique is True  # originIdolCardId
    assert index.meta("星光").idol_unique is False
    assert index.meta("睡意").idol_unique is False


def test_card_meta_effect_groups() -> None:
    index = card_meta_index()
    assert "effect_group-visible-exam_concentration-000" in index.meta("星光").effect_groups
    assert index.meta("睡意").effect_groups == ()


def test_card_meta_ja_aliases_and_reverse() -> None:
    index = card_meta_index()
    assert index.resolve("静かな意志+") == "沉静意志+"
    assert index.resolve("眠気") == "睡意"
    assert index.name_of("p_card-01-men-2_035", 1) == "沉静意志+"
    assert index.name_of("p_card-00-acc-0_002", 0) == "睡意"
    assert index.name_of("p_card-no-such", 0) is None


def test_card_meta_reference_cross_check() -> None:
    """idol_unique 判据与参考 pIdol 交叉验证（340/342、0 误报）；参考缺失跳过。"""
    if not (REF_CSV / "skill_cards.csv").is_file():
        pytest.skip("参考引擎 csv 不在 data/dl/（gitignore）")
    payload = json.loads((ROOT / "data/knowledge/card_meta.json").read_text(encoding="utf-8"))
    ref = payload["stats"].get("reference_cross_check")
    assert ref is not None, "card_meta.json 构建时参考在，应含交叉验证"
    assert ref["matched"] == 340 and ref["in_snapshot"] == 342
    assert ref["false_positives"] == []


def test_card_meta_missing_file_degrades() -> None:
    index = CardMetaIndex(meta_path=ROOT / "data/knowledge/no_such_meta.json")
    assert index.meta_available is False
    meta = index.meta("星光")
    assert meta is not None and meta.has_meta is False
    # 元数据缺失 → 偶像固有/效果组限定不可判（None），id/rarity 仍可用。
    assert meta.card_id == "p_card-03-act-1_040"


# ---- 3. sim 触发限定求值（真数据 spec + 真卡名）------------------------------


def test_specific_card_filter_matches_base_id_any_upgrade() -> None:
    """加油鼓劲使用时（体力≥50%）：base id 命中，强化变体也算（参考 usedCardBaseId）。"""
    specs = _specs("pitem_02-3-076-0")
    event = PassiveEvent(kind=CARD_PLAY, card_name="加油鼓劲", cards_played_this_turn=1)
    delta = apply_passive(specs, event, _state(stamina=20, stamina_max=30))
    assert delta.stacks.get("aggressive", 0) == 2
    assert delta.extra_plays == 1
    assert delta.stamina == -4  # 最大体力 30 的 15% = int(4.5) = 4
    # 别的卡不触发
    other = apply_passive(specs, PassiveEvent(kind=CARD_PLAY, card_name="星光"), _state(stamina=20, stamina_max=30))
    assert other.is_zero()


def test_idol_unique_filter() -> None:
    spec = _spec("pitem_02-0-002-0-008", "ExamReview")
    idol = apply_passive([spec], PassiveEvent(kind=CARD_PLAY, card_name="初次的褒奖"), _state())
    assert idol.stacks.get("impression", 0) == 8
    non_idol = apply_passive([spec], PassiveEvent(kind=CARD_PLAY, card_name="星光"), _state())
    assert non_idol.is_zero()


def test_effect_group_filter() -> None:
    spec = _spec("pitem_01-3-157-1", "ExamStaminaConsumptionDown")
    # 集中效果组 = effect_group-visible-exam_lesson_buff-000（沉静意志有；星光是强气组）。
    hit = apply_passive([spec], PassiveEvent(kind=CARD_PLAY, card_name="沉静意志+"), _state())
    assert hit.half_cost_turns == 2
    miss = apply_passive([spec], PassiveEvent(kind=CARD_PLAY, card_name="睡意"), _state())
    assert miss.is_zero()


def test_cost_min_max_filter() -> None:
    specs = _specs("pitem_tower_001-exam_review-1-stage_021")
    hit = apply_passive(specs, PassiveEvent(kind=CARD_PLAY, card_name="星光"), _state())  # cost 6
    assert hit.stamina == -6 and hit.score_buffs == [(50, -1)]
    miss = apply_passive(specs, PassiveEvent(kind=CARD_PLAY, card_name="睡意"), _state())  # cost 0
    assert miss.is_zero()


def test_unknown_card_name_is_conservative() -> None:
    spec = _spec("pitem_02-0-002-0-008", "ExamReview")
    delta = apply_passive([spec], PassiveEvent(kind=CARD_PLAY, card_name="合成卡不在卡表"), _state())
    assert delta.is_zero()


def test_zone_count_deck_grave_all_cards() -> None:
    spec = PItemSpec(
        name="牌堆弃牌≥2", trigger="turn_start", effect_type="ExamLesson", value=5,
        zone_count=ZoneCount(zones=("deck", "discard"), minimum=2),
    )
    state = _state(deck=("星光", "睡意"), discard=())
    assert apply_passive([spec], PassiveEvent(kind="turn_start"), state).score == 5
    assert apply_passive([spec], PassiveEvent(kind="turn_start"), _state(deck=("星光",))).is_zero()
    # 区域信息没给 → 保守不触发
    assert apply_passive([spec], PassiveEvent(kind="turn_start"), PassiveState(turn=1)).is_zero()


def test_zone_count_trouble_and_rarity() -> None:
    trouble = PItemSpec(
        name="干扰≥2", trigger="turn_start", effect_type="ExamLesson", value=3,
        zone_count=ZoneCount(zones=("deck", "discard"), minimum=2, filter=CardFilter(trouble=True)),
    )
    state = _state(deck=("睡意", "星光"), discard=("睡意",))
    assert apply_passive([trouble], PassiveEvent(kind="turn_start"), state).score == 3
    rarity = PItemSpec(
        name="R以上≥2", trigger="exam_start", effect_type="ExamLesson", value=4,
        zone_count=ZoneCount(
            zones=("deck", "hand", "discard", "excluded"), minimum=2,
            filter=CardFilter(rarities=("R", "SR", "SSR", "LEGEND")),
        ),
    )
    assert apply_passive([rarity], PassiveEvent(kind="exam_start"), _state(deck=("星光", "沉静意志+"))).score == 4
    assert apply_passive([rarity], PassiveEvent(kind="exam_start"), _state(deck=("睡意", "睡意"))).is_zero()


def test_zone_count_negate_lost() -> None:
    spec = PItemSpec(
        name="除外≤8", trigger="turn_end", effect_type="ExamLesson", value=2,
        zone_count=ZoneCount(zones=("excluded",), minimum=9, negate=True),
    )
    assert apply_passive([spec], PassiveEvent(kind="turn_end"), _state(excluded=("睡意",))).score == 2
    nine = _state(excluded=tuple(["睡意"] * 9))
    assert apply_passive([spec], PassiveEvent(kind="turn_end"), nine).is_zero()


def test_zone_count_unknown_card_conservative() -> None:
    spec = PItemSpec(
        name="干扰≥1", trigger="turn_start", effect_type="ExamLesson", value=1,
        zone_count=ZoneCount(zones=("deck",), minimum=1, filter=CardFilter(trouble=True)),
    )
    assert apply_passive([spec], PassiveEvent(kind="turn_start"), _state(deck=("合成卡",))).is_zero()


# ---- 4. 生成卡（ExamCardCreateId 确定式）-------------------------------------


def test_create_card_into_hand_at_exam_start_after() -> None:
    """将胜利握在手中：训练开始后（抽完第一手牌）生成沉静意志+到手牌（3+1=4）。"""
    specs = tuple(_specs("pitem_01-3-127-0"))
    sim = LessonSim([CardSpec("占位", 0, 0)] * 6, _config(p_items=specs), rng_seed=0)
    assert len(sim.hand) == 4
    assert sim.hand[-1].name == "沉静意志+"
    assert sim.hand[-1].cost == 4 and sim.hand[-1].condition == 4  # 卡表真值（好调4回合）
    assert sim.p_item_uses.get("pitem_01-3-127-0") == 1


def test_create_card_to_deck_top() -> None:
    """雨后的女神：回合开始后生成睡意到牌堆顶（下一张抽到），同时 +1 出牌 +5 元气。"""
    specs = tuple(_specs("pitem_01-3-131-0"))
    sim = LessonSim([CardSpec("占位", 0, 0)] * 8, _config(p_items=specs), rng_seed=0)
    assert sim.deck[-1].name == "睡意"
    assert sim.extra_plays >= 1 and sim.vitality >= 5
    assert sim.p_item_uses.get("pitem_01-3-131-0") == 1  # 多段同事件只记 1 次


def test_create_card_to_discard_on_status_gain() -> None:
    specs = tuple(_specs("pitem_tower_001-exam_review-1-stage_022"))
    sim = LessonSim([CardSpec("占位", 0, 0)] * 6, _config(p_items=specs), rng_seed=0)
    sim._fire_p_items(STATUS_GAIN, status="impression", amount=2)
    assert [card.name for card in sim.discard] == ["睡意"]


def test_create_card_hand_cap_five() -> None:
    """参考 addCardToHand：手牌≥5 不生成。"""
    spec = PItemSpec(
        name="生成睡意", trigger=EXAM_START_AFTER, effect_type="ExamCardCreateId",
        create_card=CreateCard("p_card-00-acc-0_002", 0, "hand"),
    )
    sim = LessonSim([CardSpec("占位", 0, 0)] * 6, _config(p_items=(spec,)), rng_seed=0)
    assert len(sim.hand) == 4  # 3 + 1
    sim._fire_p_items(EXAM_START_AFTER)
    sim._fire_p_items(EXAM_START_AFTER)
    assert len(sim.hand) == 5  # 封顶 5，第三次不生成


def test_create_card_unknown_id_is_noop() -> None:
    spec = PItemSpec(
        name="生成未知卡", trigger=EXAM_START_AFTER, effect_type="ExamCardCreateId",
        create_card=CreateCard("p_card-no-such-0_000", 0, "hand"),
    )
    sim = LessonSim([CardSpec("占位", 0, 0)] * 6, _config(p_items=(spec,)), rng_seed=0)
    assert len(sim.hand) == 3


def test_random_basic_create_stays_noop() -> None:
    """H.I.F应援棒：随机基础卡是考试 RNG 入口、真机流未知 → 保持 no-op（不猜）。"""
    specs = _specs("pitem_01-3-266-0")
    assert all(spec.implemented is False for spec in specs)
    assert specs[0].create_random == "basic_to_deck_count"
    sim = LessonSim([CardSpec("占位", 0, 0)] * 6, _config(p_items=tuple(specs)), rng_seed=0)
    assert len(sim.deck) == 3  # 6 张抽 3 张起手；应援棒不补牌
    delta = apply_passive(specs, PassiveEvent(kind="exam_start"), _state(deck=tuple(["占位"] * 3)))
    assert delta.is_zero()


def test_expectimax_create_card_mirror() -> None:
    hand_spec = PItemSpec(
        name="生成手牌", trigger=EXAM_START_AFTER, effect_type="ExamCardCreateId",
        create_card=CreateCard("p_card-00-acc-0_002", 0, "hand"),
    )
    deck_spec = PItemSpec(
        name="生成牌堆顶", trigger=TURN_START_AFTER, effect_type="ExamCardCreateId",
        create_card=CreateCard("p_card-00-acc-0_002", 0, "deck_top"),
    )
    discard_spec = PItemSpec(
        name="生成弃牌", trigger=STATUS_GAIN, effect_type="ExamCardCreateId", status="impression",
        create_card=CreateCard("p_card-00-acc-0_002", 0, "discard"),
    )
    state = ExpectState(
        hand=(CardSpec("占位", 0, 0),) * 3,
        deck=(CardSpec("占位", 0, 0),) * 4,
        known_draw=(CardSpec("占位", 0, 0),) * 4,
        discard_order=(),
        stamina=30, stamina_max=30, turns_left=2,
        p_items=(hand_spec, deck_spec, discard_spec),
    )
    state = fire_p_items(state, EXAM_START_AFTER)
    assert len(state.hand) == 4 and state.hand[-1].name == "睡意"
    state = fire_p_items(state, TURN_START_AFTER)
    assert state.deck[-1].name == "睡意"
    assert state.known_draw[0].name == "睡意"  # 全知牌序同步：下一张抽到
    assert len(state.deck) == len(state.known_draw)
    state = fire_p_items(state, STATUS_GAIN, status="impression", amount=1)
    assert state.discard[-1].name == "睡意"
    assert state.discard_order[-1].name == "睡意"


def test_create_card_sim_expect_parity() -> None:
    """LessonSim 与 ExpectState 生成卡后区域组成逐位一致。"""
    specs = tuple(_specs("pitem_01-3-127-0"))
    sim = LessonSim([CardSpec("占位", 0, 0)] * 6, _config(p_items=specs), rng_seed=0)
    state = state_from_sim(sim)
    assert tuple(card.name for card in state.hand) == tuple(card.name for card in sim.hand)
    assert state.hand[-1].name == "沉静意志+"


def test_spec_from_name() -> None:
    spec = spec_from_name("沉静意志+")
    assert spec is not None and spec.name == "沉静意志+"
    assert spec.category == "MentalSkill" and spec.cost == 4 and spec.condition == 4
    assert spec_from_name("不存在的卡") is None
    assert spec_from_name("") is None


# ---- 5. 次数上限按道具计（B10 口径修正）--------------------------------------


def test_max_uses_counts_item_not_segments() -> None:
    """雨后的女神 3 效果段、limit 5：触发 5 次后用完（旧口径按段累计会 2 次就用完）。"""
    specs = tuple(_specs("pitem_01-3-131-0"))
    sim = LessonSim([CardSpec("占位", 0, 0)] * 30, _config(turns=8, p_items=specs), rng_seed=0)
    for _ in range(7):
        sim._fire_p_items(TURN_START_AFTER)
    assert sim.p_item_uses.get("pitem_01-3-131-0") == 5
    # 第 6 次起不再生成睡意
    deck_before = len(sim.deck)
    sim._fire_p_items(TURN_START_AFTER)
    assert len(sim.deck) == deck_before


def test_max_uses_expectimax_parity() -> None:
    specs = tuple(_specs("pitem_01-3-131-0"))
    state = ExpectState(
        deck=(CardSpec("占位", 0, 0),) * 30,
        stamina=30, stamina_max=30, turns_left=8,
        p_items=specs,
    )
    for _ in range(7):
        state = fire_p_items(state, TURN_START_AFTER)
    assert dict(state.p_item_uses).get("pitem_01-3-131-0") == 5


# ---- 6. 参考引擎生成卡交叉验证（data/dl 缺失跳过）----------------------------


@pytest.mark.skipif(not (REF_CSV / "p_items.csv").is_file(), reason="参考引擎 csv 不在 data/dl/")
def test_reference_generation_cards_match() -> None:
    """参考 DSL addCardToHand(111/131/421)/addCardToTopOfDeck(23) 的卡名与我们解析一致。"""
    skill_names: dict[str, str] = {}
    with (REF_CSV / "skill_cards.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            skill_names[row["id"]] = row["name"]
    expected = {
        "pitem_01-3-127-0": ("111", "hand"),
        "pitem_02-3-128-0": ("131", "hand"),
        "pitem_03-3-129-0": ("421", "hand"),
        "pitem_01-3-131-0": ("23", "deck_top"),
    }
    index = card_meta_index()
    payload = json.loads((ROOT / "data/knowledge/p_items.json").read_text(encoding="utf-8-sig"))
    records = {r["id"]: r for r in payload["items"]}
    for item_id, (ref_id, zone) in expected.items():
        ja_name = skill_names[ref_id]
        zh_name = index.resolve(ja_name)
        assert zh_name is not None, (item_id, ja_name)
        meta = index.meta(zh_name)
        create = next(e["create"] for e in records[item_id]["effects"] if e.get("create"))
        assert create["card_id"] == meta.card_id, item_id
        assert create["upgrade"] == meta.upgrade, item_id
        assert create["zone"] == zone, item_id