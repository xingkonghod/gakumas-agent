"""P1-1（2026-11-24）全力回合 +1 出牌/保留牌回手 + のんびり指針 回归测试。

覆盖五块：

1. 纯规则：leisure 倍率 ×0（分数/费用）、setStance 守卫（全力禁切/のんびり禁温存）、
   解除收益 4 元组（温存→のんびり不触发；のんびり→全力 = 全体卡打分成长 +10）；
2. LessonSim：全力回合 +1 出牌（连续全力每回合都有）、保留牌回手、全力期间指針守卫、
   のんびり预约（回合开始条件触发/次数扣减）、解除熱意/固定元気/次数、成长加进白值；
3. ExpectState 双镜：end_turn_state / apply_card / fire_p_items / 快照往返 / canonical；
4. 解析层：sim_produce / play_choice 的 ExamOverPreservation 预约字段（BSD-3
   skill_cards.csv 逐卡证据表）、评测牌组组成不变；
5. P 道具：ExamOverPreservation → stance_leisure 直给（数据层 2 件标注 + delta）。

证据（BSD-3 gakumas-tools）：
- ``constants.js`` FULL_POWER_EFFECTS / FULL_POWER_CHANGED_EFFECTS /
  STANCE_CHANGED_EFFECTS（のんびり三条）；
- ``TurnManager.startTurn``（抽牌后 FULL_POWER_CHANGED_EFFECTS）；
- ``BuffManager.setStance``（全力/のんびり守卫）；
- ``Executor/resolvers.js`` resolveScore/resolveCost（leisure ×0）；
- ``CardManager.moveHeldCardsToHand`` / ``targeting.js`` target:all（全体卡成长）；
- ``skill_cards.csv`` 540-545/834（のんびり预约条件/次数，card_meta 别名交叉）。
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.sim.enthusiasm import (
    LEISURE_TO_FULL_SCORE_GROWTH,
    release_on_stance_change,
)
from gkagent.sim.expectimax import (
    ExpectState,
    apply_card,
    end_turn_state,
    fire_p_items,
    sim_from_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    CARD_PLAY,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    apply_passive,
    classify_effect_target,
    load_p_items,
)
from gkagent.sim.play_choice import spec_from_name
from gkagent.sim.stance import (
    Stance,
    StanceState,
    leisure_reserve_for,
    score_multiplier,
    stamina_cost_multiplier,
    stance_change_allowed,
)


def _config(**kwargs) -> LessonConfig:
    base = {
        "turns": 3,
        "stamina": 30,
        "target_clear": 1,
        "hand_size": 3,
        "plays_per_turn": 1,
    }
    base.update(kwargs)
    return LessonConfig(**base)


def _sim(deck: list[CardSpec], hand: list[CardSpec], **config) -> LessonSim:
    sim = LessonSim(deck, _config(**config), rng_seed=0)
    sim.hand = list(hand)
    sim.deck = []
    sim.discard = []
    return sim


def _leisure_state(**kwargs) -> StanceState:
    return StanceState(stance=Stance.LEISURE, **kwargs)


# ---------------------------------------------------------------- 纯规则


def test_leisure_multipliers_are_zero() -> None:
    """のんびり：分数 ×0、费用 ×0（resolveScore / resolveCost）。"""
    leisure = _leisure_state()
    assert score_multiplier(leisure) == 0.0
    assert stamina_cost_multiplier(leisure) == 0.0
    # 其它指針不受影响
    assert score_multiplier(StanceState(stance="full")) == 3.0
    assert stamina_cost_multiplier(StanceState(stance="save", save_level=1)) == 0.5


def test_stance_change_guards_match_set_stance() -> None:
    """全力期间禁切指針；のんびり期间禁温存（BuffManager.setStance）。"""
    full = StanceState(stance=Stance.FULL)
    leisure = _leisure_state()
    normal = StanceState()
    for kind in ("preservation", "concentration", "leisure"):
        assert stance_change_allowed(full, kind) is False
    assert stance_change_allowed(leisure, "preservation") is False
    assert stance_change_allowed(leisure, "concentration") is True
    assert stance_change_allowed(leisure, "leisure") is True
    for kind in ("preservation", "concentration", "leisure"):
        assert stance_change_allowed(normal, kind) is True


def test_save_release_suppressed_when_going_to_leisure() -> None:
    """温存→のんびり 不触发温存解除（STANCE_CHANGED_EFFECTS 的 stance!=leisure）。"""
    save1 = StanceState(stance="save", save_level=1)
    save2 = StanceState(stance="save", save_level=2)
    leisure = _leisure_state()
    assert release_on_stance_change(save1, leisure) == (0, 0, 0, 0)
    assert release_on_stance_change(save2, leisure) == (0, 0, 0, 0)
    # 温存→其它仍触发（P1-1 后末位成长恒 0）
    strong = StanceState(stance="strong1")
    assert release_on_stance_change(save1, strong) == (5, 0, 1, 0)


def test_leisure_release_to_non_full() -> None:
    """のんびり→非全力：熱意基础 10 + 固定元気 5 + 次数 1（无成长）。"""
    leisure = _leisure_state()
    for target in (StanceState(), StanceState(stance="strong1"), StanceState(stance="save", save_level=1)):
        assert release_on_stance_change(leisure, target) == (10, 5, 1, 0)
    assert release_on_stance_change(leisure, leisure) == (0, 0, 0, 0)


def test_leisure_release_to_full_is_card_growth() -> None:
    """のんびり→全力：target:all g.score+=10（全体卡成长），不是熱意/即时分。"""
    leisure = _leisure_state()
    full = StanceState(stance=Stance.FULL)
    assert release_on_stance_change(leisure, full) == (0, 5, 1, LEISURE_TO_FULL_SCORE_GROWTH)
    assert LEISURE_TO_FULL_SCORE_GROWTH == 10


def test_leisure_reserve_evidence_table() -> None:
    """4 族来源卡的条件/次数（skill_cards.csv 交叉）；未知 id 保守 no-op。"""
    assert leisure_reserve_for("p_card-03-ido-1_054") == (-1, True)  # のんびり屋さん
    assert leisure_reserve_for("p_card-03-ido-2_084") == (-1, True)  # 休み休み、前へ
    assert leisure_reserve_for("p_card-03-ido-3_077") == (-1, True)  # 屋上からの景色
    assert leisure_reserve_for("p_card-03-ido-100_047") == (3, False)  # 星々を見下ろす一番星
    assert leisure_reserve_for("p_card-unknown") == (0, True)


# ---------------------------------------------------------------- LessonSim 全力


def test_full_power_turn_grants_extra_play() -> None:
    """全力回合基础 1 + FULL_POWER_CHANGED_EFFECTS 1 = 2 次出牌。"""
    charge = CardSpec("攒点", 0, 0, full_power_point=10)
    hit = CardSpec("打分", 1, 10)
    sim = _sim([charge, hit, hit], [charge, hit, hit], turns=2)
    sim.step(0)  # 攒满 10 → 自动结束回合 → 下一回合全力
    assert sim.stance.stance == Stance.FULL
    assert sim.extra_plays == 1
    assert sim.plays_per_turn + sim.extra_plays == 2
    sim.step(0)
    assert sim.plays_this_turn == 1
    sim.step(0)  # 第 2 张（全力 +1）
    assert sim.plays_this_turn == 2


def test_consecutive_full_power_turns_each_grant_extra_play() -> None:
    """连续全力回合每回合都 +1（参考 fullPower→none→fullPower 后仍检查 stance）。"""
    charge = CardSpec("攒点", 0, 0, full_power_point=10)
    filler = CardSpec("占位", 0, 0)
    sim = _sim([charge, charge, filler, filler], [charge, charge, filler, filler], turns=3, plays_per_turn=2)
    sim.step(0)  # 回合 1：攒 10
    sim.step(0)  # 再攒 10（共 20）→ 回合末消耗 10 → 全力
    assert sim.stance.stance == Stance.FULL
    assert sim.stance.full_power_point == 10
    assert sim.extra_plays == 1  # 回合 2 全力 +1
    sim.step(0)  # 回合 2 打占位
    sim.step(0)  # 回合 2 第 2 张 → 回合末再消耗 10 → 连续全力
    assert sim.stance.stance == Stance.FULL
    assert sim.extra_plays == 1  # 回合 3 仍 +1


def test_full_power_moves_held_cards_to_hand() -> None:
    """全力回合 moveHeldCardsToHand：保留区全部回手（来源留 P1-3，钩子先验）。"""
    charge = CardSpec("攒点", 0, 0, full_power_point=10)
    held_card = CardSpec("保留牌", 1, 5)
    sim = _sim([charge], [charge], turns=2)
    sim.held.append(held_card)
    sim.step(0)
    assert sim.stance.stance == Stance.FULL
    assert sim.held == []
    assert held_card in sim.hand


def test_full_power_blocks_stance_changes_but_not_charge() -> None:
    """全力期间打温存/強気牌不改指針（setStance 守卫）；全力值仍累计。"""
    charge = CardSpec("攒点", 0, 0, full_power_point=10)
    filler = CardSpec("占位", 0, 0)
    save = CardSpec("温存", 0, 0, preservation=1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    more = CardSpec("再攒", 0, 0, full_power_point=3)
    sim = _sim(
        [charge, filler, save, strong, more],
        [charge, filler, save, strong, more],
        turns=2,
        plays_per_turn=2,
    )
    sim.step(0)  # 回合 1：攒满 10
    sim.step(0)  # 占位 → 回合末全力（新回合基础 2 + 全力 1 = 3 次）
    assert sim.stance.stance == Stance.FULL
    sim.step(0)  # 温存牌：被守卫挡下
    assert sim.stance.stance == Stance.FULL
    assert sim.enthusiasm == 0  # 没有解除收益
    sim.step(0)  # 強気牌：同样挡下
    assert sim.stance.stance == Stance.FULL
    sim.step(0)  # 全力值牌：不受守卫影响
    assert sim.stance.full_power_point == 3


# ---------------------------------------------------------------- LessonSim のんびり


def test_leisure_reservation_fires_at_turn_start() -> None:
    """走走停停（温存+预约）：本回合温存，下一回合开始自动 のんびり。"""
    card = CardSpec("走走停停", 3, 0, preservation=1, leisure_reserve=-1, leisure_reserve_when_save=True)
    filler = CardSpec("占位", 1, 0)
    sim = _sim([card, filler], [card, filler], turns=2, plays_per_turn=2)
    sim.step(0)
    assert sim.stance.stance == Stance.SAVE
    assert sim.leisure_reserves == [(-1, True)]
    sim.step(0)  # 回合结束 → 预约触发
    assert sim.stance.stance == Stance.LEISURE
    assert sim.leisure_reserves == [(-1, True)]  # 永久不扣


def test_leisure_turn_zero_score_zero_cost() -> None:
    """のんびり回合：出牌分 ×0、费用 ×0（resolveScore/resolveCost）。"""
    reserve = CardSpec("预约", 0, 0, leisure_reserve=-1, leisure_reserve_when_save=False)
    hit = CardSpec("大牌", 5, 20)
    sim = _sim([reserve, hit], [reserve, hit], turns=2, stamina=10)
    sim.step(0)  # 非温存预约 → 下回合 のんびり
    assert sim.stance.stance == Stance.LEISURE
    sim.hand = [hit]  # 控制手牌（避免预约卡洗回）
    sim.deck = []
    sim.discard = []
    stamina_before = sim.stamina
    sim.step(0)  # 打 20 分大牌
    assert sim.score == 0  # ×0
    assert sim.stamina == stamina_before  # 费用 ×0


def test_leisure_release_via_strong_card() -> None:
    """のんびり→強気：熱意 +10、固定元気 +5、次数 +1；后续牌吃熱意。"""
    reserve = CardSpec("预约", 0, 0, leisure_reserve=-1, leisure_reserve_when_save=False)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    hit = CardSpec("打分", 1, 10)
    sim = _sim([reserve, strong, hit], [reserve], turns=2, plays_per_turn=1)
    sim.step(0)  # 回合 1 打预约 → 回合 2 のんびり
    assert sim.stance.stance == Stance.LEISURE
    sim.hand = [strong, hit]
    sim.deck = []
    sim.discard = []
    sim.step(0)  # 強気解除
    assert sim.stance.stance == Stance.STRONG1
    assert sim.enthusiasm == 10
    assert sim.vitality == 5
    assert sim.extra_plays == 1
    sim.step(0)  # 打分牌：(10 + 熱意10) × 強気2 = 40
    assert sim.score == 40


def test_leisure_release_enthusiasm_buffs_apply() -> None:
    """のんびり解除熱意也吃 熱意追加/増加 buff（wiki：N=のんびり10）。"""
    reserve = CardSpec("预约", 0, 0, leisure_reserve=-1, leisure_reserve_when_save=False)
    buff = CardSpec("熱意増加", 0, 0, enthusiasm_multiple=500, enthusiasm_multiple_turns=-1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    sim = _sim([reserve, buff, strong], [reserve], turns=3, plays_per_turn=1)
    sim.step(0)  # 回合 1 预约 → 回合 2 のんびり
    sim.hand = [buff]
    sim.deck = []
    sim.discard = []
    sim.step(0)  # のんびり中打熱意増加 +50%（永久）→ 回合 3 仍 のんびり
    assert sim.buffs.enthusiasm_multiple == 500
    assert sim.stance.stance == Stance.LEISURE
    sim.hand = [strong, CardSpec("占位", 0, 0)]  # 留占位牌避免打空自动结束回合
    sim.deck = []
    sim.discard = []
    sim.step(0)  # 強気解除：ceil(10 × 1.5) = 15
    assert sim.enthusiasm == 15


def test_leisure_to_full_boundary_grants_growth() -> None:
    """のんびり→全力（回合边界）：元気+5、次数 2（解除1+全力1）、全体卡成长+10。"""
    reserve = CardSpec("预约", 0, 0, leisure_reserve=-1, leisure_reserve_when_save=False)
    charge = CardSpec("攒点", 0, 0, full_power_point=10)
    hit = CardSpec("打分", 1, 10)
    sim = _sim([reserve, charge, hit], [reserve], turns=3, plays_per_turn=1)
    sim.step(0)  # 回合 1 预约 → 回合 2 のんびり
    assert sim.stance.stance == Stance.LEISURE
    sim.hand = [charge]
    sim.deck = []
    sim.discard = []
    sim.step(0)  # のんびり中攒满 10（费用 ×0）→ 回合末全力
    assert sim.stance.stance == Stance.FULL
    assert sim.vitality == 5
    assert sim.enthusiasm == 0  # →全力 给成长不给熱意
    assert sim.extra_plays == 2
    assert sim.score_growth_all == 10
    sim.hand = [hit]
    sim.deck = []
    sim.discard = []
    sim.step(0)  # 打分牌：(10 + 成长10) × 全力3 = 60
    assert sim.score == 60


def test_leisure_blocks_preservation_card() -> None:
    """のんびり期间温存牌被守卫挡下（leisure && preservation → return）。"""
    reserve = CardSpec("预约", 0, 0, leisure_reserve=-1, leisure_reserve_when_save=False)
    save = CardSpec("温存", 0, 0, preservation=1)
    sim = _sim([reserve, save], [reserve], turns=2, plays_per_turn=1)
    sim.step(0)
    assert sim.stance.stance == Stance.LEISURE
    sim.hand = [save]
    sim.deck = []
    sim.discard = []
    sim.step(0)
    assert sim.stance.stance == Stance.LEISURE


def test_leisure_reserve_limit_variant_decrements() -> None:
    """俯瞰群星的启明星变体：非温存触发、limit 3，触发 3 次后失效。"""
    reserve = CardSpec("启明星", 0, 0, leisure_reserve=3, leisure_reserve_when_save=False)
    filler = CardSpec("占位", 0, 0)
    sim = _sim([reserve, filler], [reserve, filler], turns=5, plays_per_turn=2)
    sim.step(0)  # 登记 limit 3
    assert sim.leisure_reserves == [(3, False)]
    sim.step(0)  # 回合末：非温存触发 → のんびり；3 → 2
    assert sim.stance.stance == Stance.LEISURE
    assert sim.leisure_reserves == [(2, False)]
    for expected in (1, 0):
        # 控制手牌（避免预约卡洗回）；のんびり中打占位 → 回合末预约仍触发
        # （のんびり ≠ 温存，条件成立；setStance 同指針不变但次数照扣）
        sim.hand = [filler]
        sim.deck = []
        sim.discard = []
        sim.step(0)
        assert sim.stance.stance == Stance.LEISURE
        assert sim.leisure_reserves == ([(expected, False)] if expected else [])


def test_leisure_reserve_condition_unmet_no_decrement() -> None:
    """温存中触发的预约：条件不成立时不触发也不扣次数（永久 -1 本就不扣）。"""
    reserve = CardSpec("预约", 0, 0, leisure_reserve=2, leisure_reserve_when_save=True)
    filler = CardSpec("占位", 0, 0)
    sim = _sim([reserve, filler, filler], [reserve, filler, filler], turns=3, plays_per_turn=2)
    sim.step(0)  # 登记（当前 normal，非温存）
    sim.step(0)  # 回合结束：条件不成立 → 不触发、不扣
    assert sim.stance.stance == Stance.NORMAL
    assert sim.leisure_reserves == [(2, True)]


def test_save_to_leisure_grants_no_save_release() -> None:
    """温存→のんびり（预约）：无温存解除收益（熱意/元気/次数都 0）。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    reserve = CardSpec("预约", 0, 0, leisure_reserve=-1, leisure_reserve_when_save=True)
    filler = CardSpec("占位", 0, 0)
    sim = _sim([save, reserve, filler], [save, reserve, filler], turns=2, plays_per_turn=3)
    sim.step(0)  # 温存
    sim.step(0)  # 登记预约（仍温存）
    sim.step(0)  # 回合结束 → 预约：温存→のんびり
    assert sim.stance.stance == Stance.LEISURE
    assert sim.enthusiasm == 0
    assert sim.vitality == 0
    assert sim.extra_plays == 0


# ---------------------------------------------------------------- P 道具 のんびり


def test_classify_exam_over_preservation() -> None:
    """ExamOverPreservation + 悠闲变更/のんびりに変更 → stance_leisure；其它文本 no-op。"""
    assert classify_effect_target("ExamOverPreservation", "悠闲变更") == "stance_leisure"
    assert classify_effect_target("ExamOverPreservation", "のんびりに変更") == "stance_leisure"
    assert classify_effect_target("ExamOverPreservation", "温存效果的技能卡") == ""


def test_catalog_leisure_items_target_annotated() -> None:
    """夜空を従える花（pitem_03-3-303-0/1）的悠闲变更段已标注 stance_leisure。

    触发时机 card_play_interval_after 仍是 B8 遗留未支持触发（保守 no-op，
    见 test_p_items.py::test_unsupported_trigger_is_noop）→ 道具整体暂不触发，
    目标机制本身就绪（ synthetic CARD_PLAY spec 测试覆盖）。
    """
    items = load_p_items()
    for item_id in ("pitem_03-3-303-0", "pitem_03-3-303-1"):
        specs = [spec for spec in items if spec.item_id == item_id]
        leisure = [spec for spec in specs if spec.target_kind == "stance_leisure"]
        assert len(leisure) == 1, item_id
        assert leisure[0].trigger == "card_play_interval_after"
        assert leisure[0].implemented is False  # 触发未支持，保守 no-op


def test_apply_passive_leisure_delta() -> None:
    """stance_leisure 直给 → delta.stances=["leisure"]。"""
    spec = PItemSpec(
        name="悠闲道具",
        trigger=CARD_PLAY,
        effect_type="ExamOverPreservation",
        target_kind="stance_leisure",
        effect_text="悠闲变更",
    )
    delta = apply_passive(
        [spec], PassiveEvent(kind=CARD_PLAY), PassiveState(stacks={})
    )
    assert delta.stances == ["leisure"]


def test_lesson_sim_p_item_leisure_direct_and_release() -> None:
    """P 道具直给 のんびり：从温存切过来无解除收益；之后強気牌解除拿熱意。"""
    spec = PItemSpec(
        name="悠闲道具",
        trigger=CARD_PLAY,
        effect_type="ExamOverPreservation",
        target_kind="stance_leisure",
        effect_text="悠闲变更",
        item_id="test-leisure",
        max_uses=1,  # 只触发一次（真实道具是「每 3 次强气卡后」，这里简化成一次性）
    )
    save = CardSpec("温存", 0, 0, preservation=1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    filler = CardSpec("占位", 0, 0)
    sim = LessonSim(
        [save, strong, filler],
        _config(turns=2, plays_per_turn=3, p_items=(spec,)),
        rng_seed=0,
    )
    sim.hand = [save, strong, filler]
    sim.deck = []
    sim.step(0)  # 温存；出牌触发 P 道具 → のんびり（温存→のんびり无收益）
    assert sim.stance.stance == Stance.LEISURE
    assert sim.enthusiasm == 0
    sim.step(0)  # 強気解除（道具次数已用完不再切回）：熱意 10 / 元気 5 / 次数 1
    assert sim.stance.stance == Stance.STRONG1
    assert sim.enthusiasm == 10
    assert sim.vitality == 5


# ---------------------------------------------------------------- ExpectState 双镜


def test_end_turn_state_full_entry_extra_play_and_held() -> None:
    """end_turn_state：进全力 +1 次数、保留牌进下一手（held 清空）。"""
    held_card = CardSpec("保留牌", 1, 5)
    state = ExpectState(
        stamina=10,
        turns_left=2,
        total_turns=2,
        stance=("save", 0, 1, 10),
        held=(held_card,),
    )
    nxt = end_turn_state(state)
    assert nxt.stance[0] == Stance.FULL
    assert nxt.extra_plays == 2  # 温存解除 1 + 全力 1
    assert nxt.hand == (held_card,)
    assert nxt.held == ()
    assert nxt.enthusiasm == 5


def test_end_turn_state_leisure_to_full_growth() -> None:
    """end_turn_state：のんびり→全力 = 元気5/次数2/成长10（无熱意）。"""
    state = ExpectState(
        stamina=10,
        turns_left=2,
        total_turns=2,
        stance=(Stance.LEISURE, 0, 0, 10),
    )
    nxt = end_turn_state(state)
    assert nxt.stance[0] == Stance.FULL
    assert nxt.vitality == 5
    assert nxt.enthusiasm == 0
    assert nxt.extra_plays == 2
    assert nxt.score_growth_all == 10


def test_leisure_reserves_state_mirror() -> None:
    """_apply_leisure_reserves_state（经 end_turn_state）：温存→のんびり + limit 扣减。"""
    state = ExpectState(
        stamina=10,
        turns_left=2,
        total_turns=2,
        stance=("save", 0, 1, 0),
        leisure_reserves=((2, True),),
    )
    nxt = end_turn_state(state)
    assert nxt.stance[0] == Stance.LEISURE
    assert nxt.leisure_reserves == ((1, True),)
    assert nxt.enthusiasm == 0  # 温存→のんびり 无解除


def test_state_roundtrip_new_fields() -> None:
    """state_from_sim / sim_from_state：held / 预约 / 成长逐字段往返。"""
    sim = _sim([], [], turns=2)
    sim.held = [CardSpec("保留", 1, 3)]
    sim.leisure_reserves = [(3, False), (-1, True)]
    sim.score_growth_all = 10
    sim.stance = _leisure_state()
    state = state_from_sim(sim)
    assert state.held == tuple(sim.held)
    assert state.leisure_reserves == ((3, False), (-1, True))
    assert state.score_growth_all == 10
    assert state.stance[0] == Stance.LEISURE
    back = sim_from_state(state)
    assert back.held == sim.held
    assert back.leisure_reserves == sim.leisure_reserves
    assert back.score_growth_all == 10
    assert back.stance == sim.stance


def test_canonical_includes_new_fields() -> None:
    """canonical 记忆化键含新字段（不同值 → 不同键）。"""
    base = ExpectState(stamina=10, turns_left=2)
    assert base.canonical() != replace(base, score_growth_all=10).canonical()
    assert base.canonical() != replace(base, leisure_reserves=((3, False),)).canonical()
    assert base.canonical() != replace(base, held=(CardSpec("保留", 1, 3),)).canonical()


def test_apply_card_full_guard_and_leisure_cost() -> None:
    """apply_card：全力守卫 / のんびり 费用×0 分数×0（与 LessonSim 同口径）。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    full = ExpectState(
        stamina=10, turns_left=1, stance=(Stance.FULL, 0, 0, 0), extra_plays=2, hand=(save,)
    )
    outcomes = apply_card(full, save)
    assert outcomes
    assert max(outcomes, key=lambda item: item[0])[1].stance[0] == Stance.FULL

    hit = CardSpec("大牌", 5, 20)
    leisure = ExpectState(stamina=10, turns_left=1, stance=(Stance.LEISURE, 0, 0, 0), hand=(hit,))
    outcomes = apply_card(leisure, hit)
    assert outcomes
    nxt = max(outcomes, key=lambda item: item[0])[1]
    assert nxt.score == 0
    assert nxt.stamina == 10


def test_expect_award_includes_growth_all() -> None:
    """ExpectState 算分：score_growth_all 加进白值（与 LessonSim 同口径）。"""
    hit = CardSpec("打分", 1, 10)
    state = ExpectState(
        stamina=10,
        turns_left=1,
        stance=(Stance.FULL, 0, 0, 0),
        score_growth_all=10,
        hand=(hit,),
    )
    outcomes = apply_card(state, hit)
    nxt = max(outcomes, key=lambda item: item[0])[1]
    assert nxt.score == 60  # (10 + 10) × 3


def test_fire_p_items_leisure_mirror() -> None:
    """fire_p_items：stance_leisure 直给 + 守卫（与 LessonSim._apply_direct_stances 同口径）。"""
    spec = PItemSpec(
        name="悠闲道具",
        trigger=CARD_PLAY,
        effect_type="ExamOverPreservation",
        target_kind="stance_leisure",
        effect_text="悠闲变更",
        item_id="test-leisure",
    )
    state = ExpectState(stamina=10, turns_left=1, p_items=(spec,))
    nxt = fire_p_items(state, CARD_PLAY)
    assert nxt.stance[0] == Stance.LEISURE
    # 全力期间直给也被守卫挡下
    full = replace(state, stance=(Stance.FULL, 0, 0, 0))
    nxt = fire_p_items(full, CARD_PLAY)
    assert nxt.stance[0] == Stance.FULL


# ---------------------------------------------------------------- 解析层


def test_sim_produce_leisure_parse_real_cards() -> None:
    """sim_produce：4 族卡解析出预约字段；未知 id 的 ExamOverPreservation 保守 no-op。"""
    import json

    import sim_produce as sp

    table = json.loads(
        (ROOT / "data/knowledge/card_table.json").read_text(encoding="utf-8")
    )["cards"]
    for name in ("悠闲自在的人", "走走停停，继续前进", "从天台看到的景色"):
        fields = sp._effect_fields(table[name])
        assert fields[31] == -1, name
        assert fields[32] is True, name
    fields = sp._effect_fields(table["俯瞰群星的启明星"])
    assert (fields[31], fields[32]) == (3, False)
    # 未知 id：不登记预约
    unknown = sp._effect_fields(
        {"id": "p_card-unknown", "effects": [{"type": "ExamOverPreservation", "values": []}]}
    )
    assert unknown[31] == 0
    # CardRow → CardSpec 透传
    row = sp.CardRow("预约", 0, 0, 0, 0, leisure_reserve=-1, leisure_reserve_when_save=False)
    spec = sp._spec_from_row(row)
    assert (spec.leisure_reserve, spec.leisure_reserve_when_save) == (-1, False)


def test_play_choice_leisure_spec() -> None:
    """生产卡表：悠闲自在的人 = のんびり预约（旧 preservation 误映射已移除）。"""
    spec = spec_from_name("悠闲自在的人")
    assert spec is not None
    assert spec.leisure_reserve == -1
    assert spec.leisure_reserve_when_save is True
    assert spec.preservation == 0  # 不是温存牌
    assert spec.full_power_point == 1
    spec2 = spec_from_name("走走停停，继续前进")
    assert spec2 is not None
    assert (spec2.preservation, spec2.leisure_reserve) == (1, -1)
    spec3 = spec_from_name("俯瞰群星的启明星")
    assert spec3 is not None
    assert (spec3.leisure_reserve, spec3.leisure_reserve_when_save) == (3, False)


def test_eval_deck_composition_unchanged() -> None:
    """规则接入不改评测牌组：のんびり来源卡都不在 small/large 牌组（score 0/SSR/Legend）。"""
    import eval_expectimax as ee

    leisure_names = {"悠闲自在的人", "走走停停，继续前进", "从天台看到的景色", "俯瞰群星的启明星"}
    for scenario, size in (("small", 14), ("large", 31)):
        deck = ee.build_deck(scenario)
        assert len(deck) == size
        names = {card.name for card in deck}
        assert not (names & leisure_names), scenario
        assert all(card.leisure_reserve == 0 for card in deck)
    # 牌组里的指針/全力卡仍在（规则有可触达来源）
    large = {card.name: card for card in ee.build_deck("large")}
    assert large["冲刺"].full_power_point == 1
    assert large["猛烈地"].strong_level == 1


def test_pool_excludes_leisure_cards() -> None:
    """build_pool(rich=True) 不收のんびり来源卡（score<=0 或 SSR/Legend）→ 牌组不变。"""
    import sim_produce as sp

    pool = sp.build_pool(rich=True)
    names = {row.name for row in pool}
    for family in ("悠闲自在的人", "走走停停，继续前进", "从天台看到的景色", "俯瞰群星的启明星"):
        assert family not in names


# ---------------------------------------------------------------- 叶子快照双镜


def test_leaf_snapshot_full_boundary_held_and_extra() -> None:
    """RecordingLessonSim 叶子：全力边界 +1 次数 / 保留牌回手（与 end_turn_state 对齐）。"""
    from gkagent.sim.leaf_data import RecordingLessonSim

    charge = CardSpec("攒点", 0, 0, full_power_point=10)
    sim = RecordingLessonSim([charge], _config(turns=2), rng_seed=0)
    sim.hand = [charge]
    sim.deck = []
    sim.held = [CardSpec("保留牌", 1, 5)]
    sim.stance = StanceState(stance=Stance.SAVE, save_level=1, full_power_point=0)
    sim.step(0)  # 攒满 → 回合末全力；叶子快照在 _draw_hand 入口
    assert sim.leaf_states
    leaf = sim.leaf_states[0]
    assert leaf.extra_plays == 2  # 温存解除 1 + 全力 1
    assert leaf.enthusiasm == 5
    assert len(leaf.hand) == 1 and leaf.hand[0].name == "保留牌"
    assert leaf.held == ()
    # 与搜索侧 end_turn_state 同口径
    pre = ExpectState(
        stamina=sim.stamina,
        turns_left=2,
        total_turns=2,
        stance=("save", 0, 1, 10),
        held=(CardSpec("保留牌", 1, 5),),
    )
    expected = end_turn_state(pre)
    assert leaf.extra_plays == expected.extra_plays
    assert leaf.score_growth_all == expected.score_growth_all
