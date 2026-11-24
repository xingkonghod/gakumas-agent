"""P1-3（2026-11-24）：hold（保留）区的纯规则 + 逐卡证据表。

参考引擎（BSD-3 ``surisuririsu/gakumas-tools``，本地 ``data/dl/gt/gakumas-tools-master``）：

- ``CardManager.hold``：把牌推进 ``heldCards``（按卡索引幂等——再演翻倍
  ``holdThisCard`` 时同一张牌不会重复进区）；
- ``CardManager.enforceHoldLimit``：**保留区上限 2**，超限把最旧（``shift()``）
  的牌推进弃牌堆；
- ``CardManager.holdThisCard``：把刚打出的牌（``usedCard``）保留——``useCard``
  末尾 ``thisCardHeld`` 为真时该牌**不进弃牌堆/除外区**；
- ``CardManager.holdSelectedByTarget``：按目标规则从指定区选牌保留（玩家策略选牌，
  参考 ``HeuristicStrategy.pickCardsToHold`` 按「全新全力状态预览分」降序）；
- ``CardManager.moveHeldCardsToHand``：保留区全部弹回手牌（``pop()`` = **LIFO**，
  无手牌上限检查）；全力回合的 ``FULL_POWER_CHANGED_EFFECTS`` 调用它（P1-1 已接）；
- ``TurnManager.endTurn`` 只弃手牌（``discardHand``）——**保留区跨回合保留**。

主数据里卡的保留效果是 ``ExamCardMove``（``values`` 恒空，目标区/张数不编码），
语义按 BSD-3 ``packages/gakumas-data/csv/skill_cards.csv`` 的 DSL **逐卡交叉验证**
（日文卡名 ↔ 中文卡名用 ``data/knowledge/card_meta.json`` 别名表核对），
与 P1-1 ``stance.LEISURE_RESERVE_SOURCES`` 同一口径。表外的 ``ExamCardMove`` 卡
（全力值消耗/``holdSelectedUpto``/``target:held`` 成长/干扰卡计数条件等交互未建模）
**保留旧的 +1 抽牌近似**，不猜。

本模块只做数值推演与证据表，不读卡表、不依赖模拟器；全部纯函数。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 避免与 lesson.py 循环导入（运行时只按 .score 鸭子类型）
    from gkagent.sim.lesson import CardSpec

__all__ = [
    "HOLD_LIMIT",
    "HOLD_SELECT_ZONES",
    "HOLD_SOURCES",
    "HoldSource",
    "hold_pick",
    "hold_source_for",
]

#: 保留区上限（参考 ``CardManager.enforceHoldLimit``：``heldCards.length > 2``
#: 时最旧的进弃牌堆）。
HOLD_LIMIT = 2

#: ``CardSpec.hold_select_zones`` 的键 → 模拟器 tracked 区（参考 CARD_PILES
#: 顺序 deck 在前；``deck_grave`` = 牌堆或弃牌，``deck`` = 仅牌堆）。
HOLD_SELECT_ZONES: dict[str, tuple[str, ...]] = {
    "hand": ("hand",),
    "deck": ("deck",),
    "deck_grave": ("deck", "discard"),
}


@dataclass(frozen=True)
class HoldSource:
    """一张卡的保留语义（逐卡证据表条目）。

    ``mode``：``this`` = holdThisCard（保留自身）；``select`` = holdSelected
    （从 ``zones`` 选 ``count`` 张）；``move_hand`` = moveHeldCardsToHand
    （保留区全部回手，卡效果版，参考 わずかずつの歩み）。
    ``when_save``：仅温存中触发（参考 ``if:isPreservation { holdThisCard }``，
    主数据 trigger ``e_trigger-none-preservation_up`` 交叉）。
    """

    mode: str
    zones: tuple[str, ...] = ()
    count: int = 1
    when_save: bool = False


#: 卡 base id → 保留语义。BSD-3 skill_cards.csv 行号逐卡交叉（中文卡名 ↔ 日文卡名
#: 用 card_meta 别名核对）；主数据卡面文本（data/master/produce_cards.json）佐证：
#:   372/373 スパート（冲刺）: if:isPreservation { holdThisCard }
#:   388/389 積み重ね（积累）: if:isPreservation { holdThisCard }
#:   416/417 潜在能力: holdSelected[hand],1
#:   688/689 レスポンスの基本（互动的基础）: holdSelected[hand],1
#:   424/425 切磋琢磨: holdSelected[deck | discarded]（+ lockStanceTurns+=1，
#:           主数据 StanceLock turn=1，见 CardSpec.lock_stance_turns）
#:   444/445 覚悟（觉悟）: holdSelected[deck | discarded],1
#:   486/487 新たなステージ（新的舞台）: holdSelected[deck | discarded]
#:           （+ 变体的 target:held g.score+=5 是保留区卡成长，未建模，见 RULES §5.6）
#:   492/493 がんばった、よ（努力了，哦）: holdSelected[deck | discarded]
#:   526/527 あの日、この場所で（那一天，在这里）: holdSelected[deck | discarded],1
#:           / + 变体 (2)（主数据 ++/+++ 卡面文本同为「2张」→ count=2，见 hold_source_for）
#:   528/529 対戦お願いします！（对战请多指教！）: holdSelected[deck | discarded]
#:   847/848 星を散らせ（让群星散落吧）: holdSelected[deck | discarded]
#:   498/499 愛情レインボー（爱意彩虹）: holdSelected[deck],1
#:           （整卡使用条件 if:isPreservation 未建模——本模型卡总是可打出，既有口径）
#:   917/918 わずかずつの歩み（一点一滴的进步）: moveHeldCardsToHand
#: 表外（保留旧 +1 抽牌近似，交互未建模不猜）：
#:   550/551 トレンドリーダー（潮流领袖）: holdThisCard 但伴随 fullPowerCharge-=2
#:           （全力值消耗未建模）；
#:   779/780 羽ばたけ！（展翅高飞！）: if:cumulativeFullPowerCharge>=5 + charge-=4；
#:   753/754 本領発揮（发挥本领）: holdSelectedUpto（可选张数）+ target:held 成长
#:           + charge-=2；
#:   700/701 ノンストップ（决不停歇）: if:countCards[!removed & T]>=2（干扰卡计数，
#:           本模型无干扰卡）；
#:   夏夜绽放的回忆/天赋才能/尝尝味道如何/得到的答案/过分帅气的偶像/启明星（Legend）
#:           等：参考 DSL 无对应行或语义含未建模交互。
HOLD_SOURCES: dict[str, HoldSource] = {
    "p_card-03-act-0_021": HoldSource("this", when_save=True),
    "p_card-03-act-1_042": HoldSource("this", when_save=True),
    "p_card-03-men-2_064": HoldSource("select", ("hand",)),
    "p_card-03-men-0_050": HoldSource("select", ("hand",)),
    "p_card-03-men-2_079": HoldSource("select", ("deck", "discard")),
    "p_card-03-men-3_063": HoldSource("select", ("deck", "discard")),
    "p_card-03-ido-3_107": HoldSource("select", ("deck", "discard")),
    "p_card-03-ido-3_112": HoldSource("select", ("deck", "discard")),
    "p_card-03-ido-3_117": HoldSource("select", ("deck", "discard")),
    "p_card-03-sup-3_126": HoldSource("select", ("deck", "discard")),
    "p_card-03-ido-3_238": HoldSource("select", ("deck", "discard")),
    "p_card-03-sup-2_093": HoldSource("select", ("deck",)),
    "p_card-03-ido-3_219": HoldSource("move_hand"),
}


def hold_source_for(card_id: str, upgrade: int = 0) -> HoldSource | None:
    """卡 base id（+强化等级）→ 保留语义；表外返回 ``None``（调用方保留旧近似）。

    「那一天，在这里」+ / ++ / +++ 保留 2 张：参考 DSL 527 ``holdSelected[deck |
    discarded](2)``，主数据 ++/+++ 卡面文本同为「选择牌堆或弃牌中的2张技能卡」。
    """
    source = HOLD_SOURCES.get(str(card_id))
    if source is None:
        return None
    if card_id == "p_card-03-ido-3_117" and int(upgrade) >= 1:
        return replace(source, count=2)
    return source


def hold_pick(candidates: Sequence[CardSpec], num: int) -> list[CardSpec]:
    """确定性选牌（保留区选牌是**玩家选择**，参考引擎由策略决定）。

    参考 ``HeuristicStrategy.pickCardsToHold`` 按「全新全力状态预览分」降序选牌；
    全新状态下集中/好印象/元气/干劲/全力值都是 0，依赖分与折算分恒 0，预览分
    ≈ 白值 × 全力倍率 × 回合倍率（对所有候选相同）→ **排序等价于卡面白值分降序**。
    本模型按白值分降序、稳定排序（同分保持传入的区/位置顺序，deck 在前）。
    """
    ranked = sorted(candidates, key=lambda card: -card.score)
    return ranked[: max(int(num), 0)]
