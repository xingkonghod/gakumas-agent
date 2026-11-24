"""P1-3（2026-11-24）hold 保留区建模 + lockStanceTurns 指針固定 回归测试。

覆盖六块：

1. 纯规则：hold 上限 2 / 逐卡证据表 / 确定性选牌 / setStance 固定守卫 /
   全力进入门（lockStanceTurns==0）；
2. LessonSim：holdThisCard（温存条件）/ holdSelected（hand/deck/deck_grave，
   张数）/ moveHeldCardsToHand 卡效果 / 保留区跨回合保留 / 超限最旧进弃牌堆 /
   全力回手 LIFO（真实卡冲刺验证 P1-1 钩子）/ 指針固定（fresh 保护锁下一回合）；
3. ExpectState 双镜：apply_card / sample_apply_card / end_turn_state /
   canonical / 快照往返 / known_draw・discard_order 同步 / 叶子快照对齐；
4. P 道具：hold 区张数条件（实现的觉悟 countCards[held]>=1）/ hotfix
   （咲季营养餐・改 每回合第 2 张）/ 温存 2 段階直给（preservation2）；
5. 数据层：parse_card_search hold 区映射 / period810_hotfix 非限定标记 /
   触发未知 3→0；
6. 解析层：sim_produce / play_choice 的 ExamCardMove・StanceLock 字段
   （BSD-3 skill_cards.csv 逐卡证据表）；表外卡保留旧 +1 抽牌近似。

证据（BSD-3 gakumas-tools）：
- ``CardManager/index.js`` hold/enforceHoldLimit/holdCard/holdThisCard/
  holdSelectedByTarget/moveHeldCardsToHand（:959-1102）+ useCard thisCardHeld（:639）；
- ``TurnManager.js`` endTurn 只弃手牌（held 跨回合保留）/ startTurn
  FULL_POWER_EFFECTS（lockStanceTurns==0 门）+ FULL_POWER_CHANGED_EFFECTS；
- ``constants.js`` EOT_DECREMENT_FIELDS（lockStanceTurns）/ FULL_POWER_EFFECTS；
- ``BuffManager.js`` setStance（:262 lockStanceTurns 守卫）/ decrementBuffTurns
  （freshBuffs 位）；``Executor/index.js``（:271-279 fresh 保护）；
- ``HeuristicStrategy.js`` pickCardsToHold（全力预览分排序 ≈ 白值分排序）；
- ``skill_cards.csv`` 372/373/388/389/416/417/424/425/444/445/486/487/492/493/
  526/527/528/529/498/499/847/848/917/918（逐卡交叉，card_meta 别名核对）；
- ``p_items.csv`` 212/213（叶える覚悟 = 实现的觉悟，countCards[held]>=1 +
  setStance(preservation/preservation2)）/ 404（咲季の完全食・改 = 咲季营养餐・改，
  turnCardsUsed%2==1 无卡过滤）。
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
    apply_card,
    end_turn_state,
    legal_cards,
    sample_apply_card,
    sim_from_state,
    state_from_sim,
)
from gkagent.sim.hold import (
    HOLD_LIMIT,
    HOLD_SOURCES,
    hold_pick,
    hold_source_for,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    CARD_PLAY,
    PassiveEvent,
    PassiveState,
    apply_passive,
    load_p_items,
)
from gkagent.sim.play_choice import spec_from_name
from gkagent.sim.stance import (
    Stance,
    StanceState,
    end_turn,
    stance_change_allowed,
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


def _card(name: str, score: float = 10, cost: int = 1, **kwargs) -> CardSpec:
    return CardSpec(name=name, cost=cost, score=score, **kwargs)


def _sim(deck: list[CardSpec], hand: list[CardSpec], **config) -> LessonSim:
    sim = LessonSim(deck, _config(**config), rng_seed=0)
    sim.hand = list(hand)
    sim.deck = list(deck)
    sim.discard = []
    return sim


def _real(name: str) -> CardSpec:
    spec = spec_from_name(name)
    assert spec is not None, name
    return spec


def _item_specs(item_id: str) -> tuple:
    return tuple(spec for spec in load_p_items() if spec.item_id == item_id)


# ---------------------------------------------------------------- 1. 纯规则


def test_hold_limit_and_evidence_table() -> None:
    """上限 2（enforceHoldLimit）；证据表 13 族卡；表外 → None（保守）。"""
    assert HOLD_LIMIT == 2
    assert len(HOLD_SOURCES) == 13
    assert hold_source_for("p_card-03-act-0_021") is not None  # 冲刺
    assert hold_source_for("p_card-03-men-2_079") is not None  # 切磋琢磨
    assert hold_source_for("p_card-99-xxx-9_999") is None


def test_hold_source_that_day_variants() -> None:
    """那一天，在这里：base 1 张；+/++/+++ 2 张（DSL 527 (2) + 主数据卡面文本）。"""
    assert hold_source_for("p_card-03-ido-3_117", 0).count == 1
    for upgrade in (1, 2, 3):
        assert hold_source_for("p_card-03-ido-3_117", upgrade).count == 2


def test_hold_pick_ranks_by_score_desc_stable() -> None:
    """确定性选牌：白值分降序（参考全力预览分排序等价）；同分保持传入顺序。"""
    low = _card("low", score=5)
    high = _card("high", score=30)
    mid = _card("mid", score=20)
    tie = _card("tie", score=20)
    assert hold_pick([low, high, mid, tie], 2) == [high, mid]
    assert hold_pick([low, high], 0) == []
    assert hold_pick([], 1) == []


def test_stance_change_allowed_locked() -> None:
    """lockStanceTurns>0 禁切指針（参考 setStance :262）；默认 False 旧行为。"""
    normal = StanceState()
    assert stance_change_allowed(normal, "preservation") is True
    assert stance_change_allowed(normal, "preservation", locked=True) is False
    assert stance_change_allowed(normal, "concentration", locked=True) is False
    assert stance_change_allowed(normal, "leisure", locked=True) is False
    # 全力期间仍只允许 none（不走本函数）；固定不改变全力守卫
    full = StanceState(stance=Stance.FULL)
    assert stance_change_allowed(full, "preservation", locked=False) is False


def test_end_turn_locked_blocks_full_entry_keeps_charge() -> None:
    """固定期间全力进入门不满足：charge>=10 也不进全力、不消耗（FULL_POWER_EFFECTS）。"""
    state = StanceState(stance=Stance.SAVE, save_level=1, full_power_point=12)
    after = end_turn(state, locked=True)
    assert after.stance == Stance.SAVE
    assert after.full_power_point == 12  # 不消耗
    # 解锁后照常进入全力
    after2 = end_turn(state, locked=False)
    assert after2.stance == Stance.FULL
    assert after2.full_power_point == 2


def test_end_turn_locked_does_not_block_full_exit() -> None:
    """全力解除 = setStance(none)，参考 fullPower 分支不受 lock 守卫。"""
    state = StanceState(stance=Stance.FULL, full_power_point=0)
    after = end_turn(state, locked=True)
    assert after.stance == Stance.NORMAL


# ---------------------------------------------------------------- 2. LessonSim


def test_hold_this_card_unconditional() -> None:
    """holdThisCard：本牌进保留区，不进弃牌堆（useCard thisCardHeld）。"""
    card = _card("holder", hold_this=1)
    sim = _sim([_card("d1"), _card("d2")], [card, _card("other")])
    sim.step(0)
    assert sim.held == [card]
    assert card not in sim.discard
    assert card not in sim.excluded


def test_hold_this_when_save_real_card() -> None:
    """冲刺（真实卡）：温存中保留自身；非温存正常弃牌（if:isPreservation）。"""
    sprint = _real("冲刺")
    assert sprint.hold_this == 1 and sprint.hold_this_when_save
    # 温存中 → 保留
    sim = _sim([_card("d1"), _card("d2")], [sprint, _card("other")])
    sim.stance = StanceState(stance=Stance.SAVE, save_level=1)
    sim.step(0)
    assert sim.held == [sprint]
    # 非温存 → 弃牌（plays_per_turn=2 + 多张手牌：不让回合结束/重洗消耗弃牌堆）
    sim2 = _sim([_card("d1"), _card("d2")], [sprint, _card("other")], plays_per_turn=2)
    sim2.step(0)
    assert sim2.held == []
    assert sprint in sim2.discard


def test_hold_limit_evicts_oldest_to_discard() -> None:
    """保留区上限 2：第 3 张进区时最旧的进弃牌堆（enforceHoldLimit shift）。"""
    a, b, c = _card("a", hold_this=1), _card("b", hold_this=1), _card("c", hold_this=1)
    sim = _sim([_card("d1"), _card("d2"), _card("d3")], [a, b, c], plays_per_turn=3)
    sim.step(0)
    sim.step(0)
    sim.step(0)
    assert sim.held == [b, c]
    assert a in sim.discard


def test_held_persists_across_turns() -> None:
    """保留区跨回合保留（endTurn 只弃手牌，参考 discardHand）。"""
    holder = _card("holder", hold_this=1)
    sim = _sim([_card("d1"), _card("d2"), _card("d3")], [holder, _card("x")])
    sim.step(0)  # 保留 holder，自动结束回合
    assert sim.held == [holder]
    sim.step(None)  # SKIP 一回合
    assert sim.held == [holder]  # 仍在保留区
    assert holder not in sim.discard


def test_hold_select_from_hand_real_card() -> None:
    """潜在能力（真实卡）：holdSelected[hand],1 —— 选剩余手牌白值最高者。"""
    ability = _real("潜在能力")
    assert ability.hold_select_zones == "hand"
    low = _card("low", score=5)
    high = _card("high", score=40)
    sim = _sim([_card("d1"), _card("d2")], [ability, low, high])
    sim.step(0)  # 打出潜在能力（已离手），从 [low, high] 选 high
    assert sim.held == [high]
    assert high not in sim.hand
    assert low in sim.hand or low in sim.discard  # 回合结束弃手牌


def test_hold_select_from_deck_grave_real_card() -> None:
    """切磋琢磨（真实卡）：holdSelected[deck|discarded] —— 牌堆+弃牌堆里选。"""
    card = _real("切磋琢磨")
    assert card.hold_select_zones == "deck_grave"
    deck_low = _card("deck_low", score=5)
    grave_high = _card("grave_high", score=50)
    sim = _sim([deck_low, _card("d2")], [card])
    sim.discard = [grave_high]
    sim.step(0)
    assert sim.held == [grave_high]
    assert grave_high not in sim.discard


def test_hold_select_deck_only_real_card() -> None:
    """爱意彩虹（真实卡）：holdSelected[deck],1 —— 只从牌堆选（弃牌堆高分不选）。"""
    card = _real("爱意彩虹")
    assert card.hold_select_zones == "deck"
    deck_mid = _card("deck_mid", score=20)
    grave_high = _card("grave_high", score=90)
    sim = _sim([deck_mid, _card("d2")], [card, _card("x")], plays_per_turn=2)
    sim.discard = [grave_high]
    sim.step(0)
    assert sim.held == [deck_mid]
    assert grave_high in sim.discard


def test_hold_select_count_two_real_card() -> None:
    """那一天，在这里+（真实卡）：holdSelected[deck|discarded](2) —— 选 2 张。"""
    card = _real("那一天，在这里+")
    assert card.hold_select_count == 2
    a, b, c = _card("a", score=30), _card("b", score=20), _card("c", score=10)
    # plays_per_turn=2 + 留一张手牌：本牌全力值+10 会进全力回手，这里只测选牌张数
    sim = _sim([a, b, c], [card, _card("x")], plays_per_turn=2)
    sim.step(0)
    assert sim.held == [a, b]
    assert sim.deck == [c]


def test_move_held_to_hand_card_effect_real_card() -> None:
    """一点一滴的进步（真实卡）：moveHeldCardsToHand 卡效果版，LIFO 回手。"""
    card = _real("一点一滴的进步")
    assert card.hold_move_to_hand
    h1, h2 = _card("h1"), _card("h2")
    sim = _sim([_card("d1"), _card("d2"), _card("d3")], [card], plays_per_turn=2)
    sim.held = [h1, h2]
    sim.step(0)
    # LIFO：h2 先回手（参考 pop()）；本牌仍占一次，extra_play+3 回合继续
    assert sim.hand[:2] == [h2, h1]
    assert sim.held == []


def test_full_power_returns_held_lifo_real_card() -> None:
    """真实卡验证 P1-1 全力回手钩子：冲刺温存中保留 → 攒满 10 → 全力回合回手 +1。"""
    sprint = _real("冲刺")
    sim = _sim([_card("d1"), _card("d2"), _card("d3")], [sprint, _card("x")])
    sim.stance = StanceState(stance=Stance.SAVE, save_level=1, full_power_point=9)
    sim.step(0)  # 冲刺 +1 全力值 → 10；保留自身；自动结束回合 → 进全力
    assert sim.stance.stance == Stance.FULL
    assert sim.held == []
    assert sprint in sim.hand  # 回手钩子用真实卡验证
    # 温存→全力边界：解除 +1 次数 +5 熱意，全力回合再 +1 次数 = 2 次额外
    assert sim.extra_plays == 2
    assert sim.enthusiasm == 5


def test_full_power_held_lifo_order() -> None:
    """全力回手 LIFO：保留区 [h1, h2] → 下一手 [h2, h1] 在前（参考 pop）。"""
    h1, h2 = _card("h1"), _card("h2")
    sim = _sim([_card("d1"), _card("d2"), _card("d3")], [_card("x")])
    sim.held = [h1, h2]
    sim.stance = StanceState(full_power_point=10)
    sim.step(None)  # SKIP → 回合末进全力 → 回手（抽牌之后追加，LIFO）
    assert sim.stance.stance == Stance.FULL
    assert sim.hand[-2:] == [h2, h1]
    assert sim.held == []


def test_hold_this_precedes_once_exclusion() -> None:
    """holdThisCard 优先于 once 除外（参考 thisCardHeld 分支在 limit 判定前）。"""
    card = _card("holder", hold_this=1, once=True)
    sim = _sim([_card("d1"), _card("d2")], [card])
    sim.step(0)
    assert sim.held == [card]
    assert sim.excluded == []


def test_encore_does_not_double_hold() -> None:
    """再演不翻倍 hold（参考 hold 按卡索引幂等）；lockStanceTurns 是直接效果翻倍。"""
    card = _card("holder", hold_this=1, encore=True)
    sim = _sim([_card("d1"), _card("d2")], [card])
    sim.step(0)
    assert sim.held == [card]  # 只一张


def test_held_cards_not_playable() -> None:
    """保留区的牌不可直接打出（不在手牌；参考 heldCards 非 handCards）。"""
    holder = _card("holder", score=99)
    sim = _sim([_card("d1"), _card("d2")], [_card("x")])
    sim.held = [holder]
    assert all(sim.hand[i] != holder for i in sim.legal_actions() if i is not None)
    state = state_from_sim(sim)
    assert holder not in legal_cards(state)


# ---------------------------------------------------------------- 指針固定


def test_lock_stance_gain_real_card() -> None:
    """切磋琢磨（真实卡）：StanceLock turn=1 → lock_stance_turns=1 + fresh。"""
    card = _real("切磋琢磨")
    assert card.lock_stance_turns == 1
    # 留一张手牌 + plays_per_turn=2：回合不结束，fresh 标记仍在
    sim = _sim([_card("d1"), _card("d2")], [card, _card("x")], plays_per_turn=2)
    sim.step(0)
    assert sim.lock_stance_turns == 1
    assert sim._lock_stance_fresh is True


def test_lock_blocks_stance_change_mid_turn() -> None:
    """固定期间打温存牌不切指針（setStance 守卫）。"""
    lock_card = _real("切磋琢磨")
    save_card = _card("save", preservation=1)
    sim = _sim([_card("d1"), _card("d2"), _card("d3")], [lock_card, save_card],
               plays_per_turn=2)
    sim.step(0)  # 切磋琢磨 → lock=1（extra_play+1 回合继续）
    sim.step(0)  # 温存牌 → 被固定守卫挡住
    assert sim.stance.stance != Stance.SAVE


def test_lock_blocks_full_entry_next_turn_fresh() -> None:
    """fresh 保护：获得当回合末不扣 → 锁下一回合的全力进入（全力值不消耗）。"""
    lock_card = _real("切磋琢磨")
    sim = _sim([_card("d1"), _card("d2"), _card("d3"), _card("d4")],
               [lock_card, _card("x")], plays_per_turn=2)
    sim.stance = StanceState(full_power_point=8)  # +2 → 10
    sim.step(0)  # 打出 → lock=1 fresh；extra_play+1，回合继续
    sim.step(None)  # SKIP 结束回合：fresh 跳过递减 → lock 仍 1；全力门被锁
    assert sim.lock_stance_turns == 1
    assert sim.stance.stance != Stance.FULL
    assert sim.stance.full_power_point == 10  # 未消耗


def test_lock_expires_after_next_turn() -> None:
    """第二个回合末 lock -1 → 0；之后全力进入恢复。"""
    lock_card = _real("切磋琢磨")
    sim = _sim([_card(f"d{i}") for i in range(8)],
               [lock_card, _card("x")], plays_per_turn=2)
    sim.stance = StanceState(full_power_point=8)
    sim.step(0)  # 打出 → lock=1 fresh，回合继续
    sim.step(None)  # T1 末：fresh 跳过
    assert sim.lock_stance_turns == 1
    sim.step(None)  # T2 末：-1 → 0；全力门解锁 → 进全力
    assert sim.lock_stance_turns == 0
    assert sim.stance.stance == Stance.FULL
    assert sim.stance.full_power_point == 0


def test_lock_does_not_block_full_exit() -> None:
    """全力期间获得固定（合成）：全力照常解除（setStance(none) 不受 lock 守卫）。"""
    sim = _sim([_card("d1"), _card("d2")], [_card("x")])
    sim.stance = StanceState(stance=Stance.FULL)
    sim.lock_stance_turns = 1
    sim.step(None)
    assert sim.stance.stance == Stance.NORMAL


def test_lock_stance_encore_doubles() -> None:
    """lockStanceTurns 是直接效果：再演翻倍（参考 doubleCardEffectCards 重执行）。"""
    card = _card("locker", lock_stance_turns=1, encore=True)
    sim = _sim([_card("d1"), _card("d2")], [card])
    sim.step(0)
    assert sim.lock_stance_turns == 2


# ---------------------------------------------------------------- 3. ExpectState 双镜


def test_apply_card_hold_this_mirror() -> None:
    """apply_card：holdThisCard 进保留区、不弃牌（与 LessonSim 同口径）。"""
    card = _card("holder", hold_this=1)
    state = ExpectState(
        hand=(card, _card("other")),
        deck=(_card("d1"), _card("d2")),
        stamina=30,
        turns_left=3,
        total_turns=4,
    )
    outcomes = apply_card(state, card)
    assert len(outcomes) == 1
    after = outcomes[0][1]
    assert after.held == (card,)
    assert card not in after.discard
    assert card not in after.hand


def test_apply_card_hold_select_mirror() -> None:
    """apply_card：holdSelected[deck_grave] 选白值最高（与 LessonSim 同口径）。"""
    card = _card("picker", hold_select_zones="deck_grave")
    grave_high = _card("grave_high", score=50)
    deck_low = _card("deck_low", score=5)
    state = ExpectState(
        hand=(card,),
        deck=(deck_low,),
        discard=(grave_high,),
        stamina=30,
        turns_left=3,
        total_turns=4,
    )
    after = apply_card(state, card)[0][1]
    assert after.held == (grave_high,)
    assert grave_high not in after.discard


def test_sample_apply_card_hold_mirror() -> None:
    """sample_apply_card（beam 用）：hold 同口径。"""
    card = _card("holder", hold_this=1)
    state = ExpectState(
        hand=(card,), deck=(_card("d1"),), stamina=30, turns_left=3, total_turns=4
    )
    after = sample_apply_card(state, card, random.Random(0))
    assert after.held == (card,)
    assert card not in after.discard


def test_end_turn_state_lock_fresh_and_held_lifo() -> None:
    """end_turn_state：lock fresh 跳过递减 + 全力回手 LIFO（与 LessonSim 对齐）。"""
    h1, h2 = _card("h1"), _card("h2")
    state = ExpectState(
        hand=(_card("x"),),
        deck=(_card("d1"), _card("d2"), _card("d3")),
        held=(h1, h2),
        stamina=30,
        turns_left=3,
        total_turns=4,
        stance=("normal", 0, 0, 10),
        lock_stance_turns=1,
        lock_stance_fresh=True,
    )
    after = end_turn_state(state)
    # fresh 跳过递减 → lock 仍 1 → 全力门被锁（charge 10 不消耗）
    assert after.lock_stance_turns == 1
    assert after.lock_stance_fresh is False
    assert after.stance[0] != Stance.FULL
    assert after.stance[3] == 10
    assert after.held == (h1, h2)  # 未进全力 → 不回手
    # 解锁版本：进全力 → 回手 LIFO
    unlocked = replace(state, lock_stance_turns=0, lock_stance_fresh=False)
    after2 = end_turn_state(unlocked)
    assert after2.stance[0] == Stance.FULL
    assert after2.hand[:2] == (h2, h1)
    assert after2.held == ()


def test_canonical_includes_lock() -> None:
    """canonical 含 lock_stance_turns/fresh（影响后续价值/合法性）。"""
    base = ExpectState(hand=(_card("x"),), stamina=30, turns_left=3)
    locked = replace(base, lock_stance_turns=1)
    fresh = replace(base, lock_stance_turns=1, lock_stance_fresh=True)
    assert base.canonical() != locked.canonical()
    assert locked.canonical() != fresh.canonical()


def test_state_roundtrip_lock_and_held() -> None:
    """state_from_sim / sim_from_state：lock + held 往返不丢。"""
    sim = _sim([_card("d1"), _card("d2")], [_card("x")])
    sim.held = [_card("h1"), _card("h2")]
    sim.lock_stance_turns = 2
    sim._lock_stance_fresh = True
    state = state_from_sim(sim)
    assert state.lock_stance_turns == 2
    assert state.lock_stance_fresh is True
    assert len(state.held) == 2
    rebuilt = sim_from_state(state)
    assert rebuilt.lock_stance_turns == 2
    assert rebuilt._lock_stance_fresh is True
    assert rebuilt.held == sim.held


def test_hold_select_syncs_known_draw() -> None:
    """holdSelected 从牌堆移牌 → known_draw 同步（牌堆顺序 = reversed(known_draw)）。"""
    a, b, c = _card("a", score=10), _card("b", score=30), _card("c", score=20)
    picker = _card("picker", hold_select_zones="deck_grave")
    state = ExpectState(
        hand=(picker,),
        deck=(a, b, c),
        known_draw=(c, b, a),  # reversed(deck)
        stamina=30,
        turns_left=3,
        total_turns=4,
    )
    after = apply_card(state, picker)[0][1]
    assert after.held == (b,)
    assert after.deck == (a, c)
    assert after.known_draw == (c, a)  # b 移除


def test_hold_select_syncs_discard_order_and_limit() -> None:
    """holdSelected 从弃牌堆移牌 + 超限驱逐 → discard_order 同步。"""
    g1, g2 = _card("g1", score=40), _card("g2", score=30)
    picker = _card("picker", hold_select_zones="deck_grave", hold_select_count=2)
    old = _card("old")
    state = ExpectState(
        hand=(picker,),
        deck=(),
        discard=(g1, g2),
        discard_order=(g1, g2),
        held=(old,),
        stamina=30,
        turns_left=3,
        total_turns=4,
    )
    after = apply_card(state, picker)[0][1]
    # 选 g1,g2 → held [old,g1,g2] → 超限驱逐 old → 弃牌堆；打出的 picker 随后也弃牌
    assert after.held == (g1, g2)
    assert after.discard == (old, picker)
    assert after.discard_order == (old, picker)


def test_leaf_snapshot_full_boundary_held_lifo() -> None:
    """叶子快照（leaf_data）：全力边界回手 LIFO + extra_plays（与 end_turn_state 对齐）。"""
    from gkagent.sim.leaf_data import RecordingLessonSim

    sprint = _real("冲刺")
    rec = RecordingLessonSim(
        [_card("d1"), _card("d2"), _card("d3")], _config(), rng_seed=0
    )
    rec.hand = [sprint, _card("x")]
    rec.deck = [_card("d1"), _card("d2"), _card("d3")]
    rec.stance = StanceState(stance=Stance.SAVE, save_level=1, full_power_point=9)
    rec.step(0)  # 冲刺保留 → 全力 → 回手
    assert rec.leaf_states
    leaf = rec.leaf_states[-1]
    assert sprint in leaf.hand
    assert leaf.held == ()
    assert leaf.extra_plays >= 1


# ---------------------------------------------------------------- 4. P 道具


def test_zone_count_hold_condition_real_item() -> None:
    """实现的觉悟（真实数据）：魅力刚刚好使用后 + held>=1 → 温存变更 + 全力值+2。"""
    specs = _item_specs("pitem_03-3-078-0")
    assert specs and all(s.trigger_known for s in specs)
    event = PassiveEvent(
        kind=CARD_PLAY, card_name="魅力刚刚好", cards_played_this_turn=1
    )
    # held 有牌 → 触发
    state = PassiveState(held=("冲刺",), zones_known=True, stamina=30, stamina_max=30)
    delta = apply_passive(specs, event, state)
    assert "preservation" in delta.stances
    assert delta.stacks.get("full_power_point") == 2
    # held 空 → 不触发（countCards[held]>=1 不满足）
    empty = PassiveState(held=(), zones_known=True, stamina=30, stamina_max=30)
    assert apply_passive(specs, event, empty).is_zero()
    # 其它卡 → play_filter 不满足
    other = PassiveEvent(kind=CARD_PLAY, card_name="冲刺", cards_played_this_turn=1)
    assert apply_passive(specs, other, state).is_zero()


def test_hotfix_item_fires_on_second_card_per_turn() -> None:
    """咲季营养餐・改（真实数据）：回合内第 2 张 → 好印象+2 / 好印象强化+25%；limit 1。"""
    specs = _item_specs("pitem_02-3-309-0")
    assert specs and all(s.trigger_known for s in specs)
    state = PassiveState(zones_known=True, stamina=30, stamina_max=30)
    # 第 1 张 → 不触发
    first = PassiveEvent(kind=CARD_PLAY, card_name="冲刺", cards_played_this_turn=1)
    assert apply_passive(specs, first, state).is_zero()
    # 第 2 张 → 触发（任意卡，无卡过滤 —— 参考 turnCardsUsed%2==1）
    second = PassiveEvent(kind=CARD_PLAY, card_name="魅力的基础", cards_played_this_turn=2)
    delta = apply_passive(specs, second, state)
    assert delta.stacks.get("impression") == 2
    assert any(key == "review_multiple" and value == 250 for key, value, _ in delta.modifiers)
    # limit 1（训练内1次）：已用 1 次 → 不再触发
    used = PassiveState(zones_known=True, stamina=30, stamina_max=30,
                        uses={"pitem_02-3-309-0": 1})
    assert apply_passive(specs, second, used).is_zero()


def test_preservation2_direct_stance_real_item() -> None:
    """实现的觉悟+（真实数据）：温存阶段变更 → preservation2（直给 2 段階）。"""
    specs = _item_specs("pitem_03-3-078-1")
    event = PassiveEvent(
        kind=CARD_PLAY, card_name="魅力刚刚好", cards_played_this_turn=1
    )
    state = PassiveState(held=("冲刺",), zones_known=True, stamina=30, stamina_max=30)
    delta = apply_passive(specs, event, state)
    assert "preservation2" in delta.stances
    assert delta.stacks.get("full_power_point") == 4
    # LessonSim 直给：从普通指針直接到温存 2 段階
    sim = _sim([_card("d1")], [_card("x")])
    sim._apply_direct_stances(["preservation2"])
    assert sim.stance.stance == Stance.SAVE
    assert sim.stance.save_level == 2


def test_preservation2_blocked_by_lock() -> None:
    """温存 2 段階直给也过固定守卫（lockStanceTurns>0 禁切）。"""
    sim = _sim([_card("d1")], [_card("x")])
    sim.lock_stance_turns = 1
    sim._apply_direct_stances(["preservation2"])
    assert sim.stance.stance != Stance.SAVE


def test_lesson_sim_hold_zone_count_item_fires() -> None:
    """LessonSim 集成：held 有牌时打出魅力刚刚好 → 实现的觉悟触发温存+全力值。"""
    specs = _item_specs("pitem_03-3-078-0")
    just = _real("魅力刚刚好")
    sim = _sim([_card("d1"), _card("d2")], [just], p_items=specs)
    sim.held = [_card("held_card")]
    sim.step(0)
    assert sim.stance.stance == Stance.SAVE
    # 魅力刚刚好自身全力值+2，道具再+2 = 4
    assert sim.stance.full_power_point == 4


# ---------------------------------------------------------------- 5. 数据层


def test_build_p_items_hold_zone_and_hotfix_parsed() -> None:
    """parse_card_search：hold → zones ["held"]；period810_hotfix 非限定标记。"""
    import build_p_items

    play_filter, zone_count, unresolved = build_p_items.parse_card_search(
        "e_trigger-exam_card_play_after-card_search_count_up-1-p_card_search-hold-"
        "p_card_search-target-1-p_card-03-act-1_038-0_1"
    )
    assert unresolved is False
    assert zone_count["zones"] == ["held"] and zone_count["min"] == 1
    assert play_filter["card_id"] == "p_card-03-act-1_038"
    _, _, unresolved2 = build_p_items.parse_card_search(
        "e_trigger-exam_play_turn_count_interval-2-p_card_search-target-period810_hotfix"
    )
    assert unresolved2 is False


def test_catalog_trigger_unknown_zero() -> None:
    """B10 遗留 trigger_unknown 3 件/6 段 → P1-3 清零；P1-4 implemented 1056→1067。"""
    from gkagent.data.p_items_db import catalog_coverage, get_catalog

    cov = catalog_coverage(get_catalog())
    assert cov["trigger_unknown"] == 0
    assert cov["condition_unknown"] == 0
    assert cov["implemented"] == 1067
    assert cov["specs"] == 1849


# ---------------------------------------------------------------- 6. 解析层


def test_sim_produce_hold_parse_real_cards() -> None:
    """sim_produce：13 族真实卡 → hold/lock 字段（41 元组末 6 位）。"""
    import json

    import sim_produce as sp

    table = json.loads(
        (ROOT / "data" / "knowledge" / "card_table.json").read_text(encoding="utf-8")
    )["cards"]
    expectations = {
        "冲刺": (1, True, "", 1, False, 0),
        "积累": (1, True, "", 1, False, 0),
        "切磋琢磨": (0, False, "deck_grave", 1, False, 1),
        "潜在能力": (0, False, "hand", 1, False, 0),
        "互动的基础": (0, False, "hand", 1, False, 0),
        "觉悟": (0, False, "deck_grave", 1, False, 0),
        "新的舞台": (0, False, "deck_grave", 1, False, 0),
        "努力了，哦": (0, False, "deck_grave", 1, False, 0),
        "那一天，在这里": (0, False, "deck_grave", 1, False, 0),
        "那一天，在这里+": (0, False, "deck_grave", 2, False, 0),
        "对战请多指教！": (0, False, "deck_grave", 1, False, 0),
        "让群星散落吧": (0, False, "deck_grave", 1, False, 0),
        "爱意彩虹": (0, False, "deck", 1, False, 0),
        "一点一滴的进步": (0, False, "", 1, True, 0),
    }
    for name, expected in expectations.items():
        fields = sp._effect_fields(table[name])
        assert len(fields) == 41
        assert fields[35:41] == expected, name
        # 已建模 hold 卡不再加 +1 抽牌近似（对战请多指教！自带 ExamCardDraw 抽 1）
        if name == "对战请多指教！":
            assert fields[3] == 1, name  # 真实抽牌效果（DSL drawCard），非近似
        else:
            assert fields[3] == 0, name


def test_play_choice_hold_parse_parity() -> None:
    """play_choice（生产卡表路径）：与 sim_produce 同口径。"""
    for name in ("冲刺", "切磋琢磨", "潜在能力", "那一天，在这里+", "一点一滴的进步"):
        spec = _real(name)
        row = spec_from_name(name)
        assert row is not None
        assert (spec.hold_this, spec.hold_select_zones, spec.hold_select_count,
                spec.hold_move_to_hand, spec.lock_stance_turns) == (
            row.hold_this, row.hold_select_zones, row.hold_select_count,
            row.hold_move_to_hand, row.lock_stance_turns)
    assert _real("切磋琢磨").lock_stance_turns == 1
    assert _real("冲刺").hold_this_when_save is True


def test_unverified_cards_keep_approx_draw() -> None:
    """表外 ExamCardMove 卡（交互未建模）保留旧 +1 抽牌近似，hold 字段空。"""
    import json

    import sim_produce as sp

    table = json.loads(
        (ROOT / "data" / "knowledge" / "card_table.json").read_text(encoding="utf-8")
    )["cards"]
    for name in ("潮流领袖", "展翅高飞！", "发挥本领", "决不停歇"):
        fields = sp._effect_fields(table[name])
        assert fields[35:41] == (0, False, "", 1, False, 0), name
    # 决不停歇：无 extra_play → 旧近似 draw=1 保持
    assert sp._effect_fields(table["决不停歇"])[3] == 1


def test_pool_hold_cards_fields() -> None:
    """奖励池：冲刺/积累 hold_this=1 + draw=0（旧近似移除）；表外卡不变。"""
    import sim_produce as sp

    pool = {row.name: row for row in sp.build_pool(rich=True)}
    for name in ("冲刺", "冲刺+", "积累", "积累+"):
        assert pool[name].hold_this == 1
        assert pool[name].draw == 0
    assert pool["决不停歇"].hold_this == 0
    assert pool["决不停歇"].draw == 1
