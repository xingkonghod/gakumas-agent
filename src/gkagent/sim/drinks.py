"""M6 饮料效果建模（2026-11-26）：把 ``ProduceDrinkEffect`` 主数据的效果段映射成
模拟器可结算的增量，**未知效果显式 no-op（不猜）**。

数据来源（``scripts/build_drinks.py`` 解析，产出 ``data/knowledge/drinks.json``）：
  * ``ProduceDrink.yaml`` → 饮料 id / 名 / 稀有度 / ``produceDrinkEffectIds``；
  * ``ProduceDrinkEffect.yaml`` → ``p_drink_effect-*`` → ``e_effect-*``；
  * ``ProduceExamEffect.yaml`` → 效果本体（effectType / effectValue1 / effectTurn /
    effectCount / produceCardSearchId / movePositionType / 附魔 id）；
  * ``ProduceExamStatusEnchant.yaml`` → 附魔内层效果（回合开始抽牌等）。

设计边界（与 ``sim/p_items.py`` 同纪律）：
  * 只实现「语义确定」的效果段；其余 ``kind="unknown"``、``implemented=False``，
    结算时整段跳过（不抛异常、不静默当成有用饮料），由 catalog 统计如实报数。
  * 能复用 P 道具增量渠道（``PItemDelta``）的效果（打分/体力/层数/extra_plays/
    timed 分数倍率/费用修正/回合追加…）走 :func:`effects_to_delta`，与
    ``LessonSim._apply_p_delta`` / ``expectimax._apply_p_delta_state`` 双镜共用。
  * 饮料特有的直接结算类（立即抽牌 / timed 回合开始抽牌 / zone search move 偶像固有 /
    阶段1.5 的回合边界附魔 buff、search hold、温存指針直给）由
    ``LessonSim.use_drink`` / ``expectimax.use_drink_state`` 结算。
  * **阶段1.5（2026-11-26）确定式增量批**：4 种严选初星 ExamStatusEnchant
    （回合结束集中/好印象/干劲 +1、回合开始全力值 +1，effectTurn=-1 永久）→
    ``turn_enchants`` 渠道（(kind, value, turns) 三元组，双镜新字段）；
    热绿茶 ExamCardMove deck_grave→hold（pickRangeType=Select 玩家选牌，
    引擎 select_policy 不掷点）+ ExamPreservation 温存 2 段階直给（走
    PItemDelta.stances，与 p_items P1-3 同渠道）。引擎 oracle 逐瓶配对
    rng_advances=0（data/_drinks_probe5.py，不提交）。

**饮料 RNG 消费入口**（M6 划给饮料侧，与 m1-rng 的 ``rng_graph`` 留 hook）：
  * ``extra_plays`` / ``score_buff`` / ``half_cost`` / ``stamina_cost`` 等纯数值段
    **0 次** xorshift32 消费（W9 实机 oracle 验证：蛋白粉 rng_advances=0）；
  * ``search_move``（``ExamCardMove`` 搜索偶像固有）= type9 roll 口径：候选 >1 时
    引擎掷点选 1（W9 汉方 rng_advances=3，含搜索排序+选取）；本模块用
    ``rng.choice`` 建模选取，精确消费数由 :func:`rng_caliber` 标注、引擎 oracle 配对；
  * ``draw``（立即抽牌）本身不掷点，但**入手牌触发支援强化掷点**（W9 苏打
    rng_advances=4 = 2 张 × 2 张本回合属性合格支援）——支援强化属考试 RNG 图
    （m1-rng），本模块只标 ``draw_support`` 口径、不在课程 sim 里复现支援掷点；
  * ``create_random``（青汁 ``ExamCardCreateId``/``ExamCardCreateSearch`` 随机 SSR
    生成）= 随机卡池掷点，真机流未知 → **显式 unknown**（同 p_items.create_random）。

用法::

    from gkagent.sim.drinks import DrinkEffect, classify_drink_effect, effects_to_delta
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gkagent.sim.p_items import PERMANENT_TURNS, PItemDelta, normalize_turns

__all__ = [
    "DRINK_EFFECT_KINDS",
    "SAFE_KINDS",
    "TURN_ENCHANT_KINDS",
    "DrinkEffect",
    "add_turn_enchant",
    "classify_drink_effect",
    "drink_is_safe",
    "effects_to_delta",
    "rng_caliber",
    "legacy_effect",
    "tick_turn_enchants",
]

# ---- 效果段目标分类（语义确定的才实现）------------------------------------
#: kind -> 说明。``unknown`` = 未建模（RNG/交互/依赖换算），结算整段跳过。
DRINK_EFFECT_KINDS: dict[str, str] = {
    "stamina": "体力回复（ExamStaminaRecoverFix，封顶 stamina_max）",
    "stamina_cost": "固定体力消耗（ExamStaminaReduceFix，喝这瓶扣的体力）",
    "focus": "集中 +N（ExamLessonBuff）",
    "condition": "好调 N 回合（ExamParameterBuff）",
    "score": "直接加 N 分（ExamLesson，不吃倍率）",
    "vitality": "元气 +N（ExamBlock/ExamBlockFix）",
    "impression": "好印象 +N（ExamReview）",
    "aggressive": "干劲 +N（ExamCardPlayAggressive）",
    "full_power_point": "全力值 +N（ExamFullPowerPoint）",
    "extra_plays": "本回合可出牌次数 +N（ExamPlayableValueAdd）",
    "score_buff": "timed 分数上升量倍率（ExamLessonValueMultiple，千分比）",
    "half_cost": "timed 消耗体力减少（ExamStaminaConsumptionDown，回合）",
    "double_cost": "timed 消耗体力增加（ExamStaminaConsumptionAdd，回合）",
    "cost_reduction": "永久削减消耗体力（ExamStaminaConsumptionDownFix）",
    "perfect_condition": "绝好调 N 回合（ExamParameterBuffMultiplePerTurn）",
    "extra_turn": "回合追加（ExamExtraTurn）",
    "draw": "立即抽 N 张（ExamCardDraw）",
    "turn_start_draw": "timed 回合开始后抽 N 张（ExamStatusEnchant 内层 ExamCardDraw）",
    "search_move": "zone search move 偶像固有（ExamCardMove deck_grave→hand）",
    # ---- 阶段1.5（2026-11-26）：确定式增量批（引擎 oracle 逐瓶配对，rng=none）----
    "turn_end_focus": "回合结束时集中 +N（ExamStatusEnchant 内层 ExamLessonBuff，trigger=exam_end_turn）",
    "turn_end_impression": "回合结束时好印象 +N（ExamStatusEnchant 内层 ExamReview，trigger=exam_end_turn）",
    "turn_end_aggressive": "回合结束时干劲 +N（ExamStatusEnchant 内层 ExamCardPlayAggressive，trigger=exam_end_turn）",
    "turn_start_full_power": "回合开始时全力值 +N（ExamStatusEnchant 内层 ExamFullPowerPoint，trigger=exam_start_turn）",
    "search_hold": "zone search move 到保留区（ExamCardMove deck_grave→hold，Select 玩家选牌，rng=none）",
    "preservation": "温存指針直给（ExamPreservation value1=1/2 → setStance(preservation/preservation2)）",
    # ---- 阶段2 batch2（2026-11-26）：probe6 引擎 oracle 逐瓶配对，rng=none ----
    "concentration": "强气指針直给（ExamConcentration value1=1/2 → setStance(concentration/concentration2)）",
    "select_move_hand": "zone search move 到手牌（ExamCardMove deck_grave→hand，Select 玩家选牌，rng=none）",
    "zero_cost": "接下来 N 张正费牌体力消耗变为 0（ExamSearchPlayCardStaminaConsumptionChange v1=0，count=N；0 费牌不耗次数）",
    "encore_active": "下一张主动技能卡直接效果再发动 1 次（ExamCardSearchEffectPlayCountBuff v1=1/count=1/turn=1；1 次，喝回合+下一回合有效）",
    "unknown": "未建模（RNG/交互/依赖换算），显式 no-op",
}

#: sim 侧搜索/生产决策的 SAFE kind 集合（纯数值段：不改牌堆/手牌/RNG/回合数）。
#: **引擎侧全饮料保留**（gnrpa-spec a86ffdc 实锤：限制 SAFE 反而 −897k）；本集合
#: 只用于我们自己的 sim 搜索/生产 allow_drinks 决策与锁定前 worlds 保守口径。
#: encore_active 排除：再发动可能放大抽牌类卡效果（改手牌）；select_move_hand/
#: search_hold/search_move/draw/turn_start_draw/extra_turn 改牌区/回合数；
#: unknown 段保守排除（语义未定）。
SAFE_KINDS = frozenset(
    {
        "stamina", "stamina_cost", "focus", "condition", "score", "vitality",
        "impression", "aggressive", "full_power_point", "extra_plays",
        "score_buff", "half_cost", "double_cost", "cost_reduction",
        "perfect_condition", "preservation", "concentration", "zero_cost",
        "turn_end_focus", "turn_end_impression", "turn_end_aggressive",
        "turn_start_full_power",
    }
)

#: 回合边界附魔 buff 渠道（turn_enchants 字段，(kind, value, turns) 三元组）。
TURN_ENCHANT_KINDS = frozenset(
    {
        "turn_end_focus",
        "turn_end_impression",
        "turn_end_aggressive",
        "turn_start_full_power",
    }
)

#: 走 PItemDelta 渠道的 kind（effects_to_delta 表达）；其余由 use_drink 直接结算。
DELTA_KINDS = frozenset(
    {
        "stamina",
        "stamina_cost",
        "focus",
        "condition",
        "score",
        "vitality",
        "impression",
        "aggressive",
        "full_power_point",
        "extra_plays",
        "score_buff",
        "half_cost",
        "double_cost",
        "cost_reduction",
        "perfect_condition",
        "extra_turn",
        # 阶段1.5：温存指針直给走 PItemDelta.stances（与 P 道具 setStance 同渠道）。
        "preservation",
        # 阶段2 batch2：强气指針直给同渠道。
        "concentration",
    }
)
#: 由 use_drink / use_drink_state 直接结算的 kind（需要牌区/抽牌/回合边界交互）。
DIRECT_KINDS = frozenset(
    {"draw", "turn_start_draw", "search_move", "search_hold",
     "select_move_hand", "zero_cost", "encore_active"} | TURN_ENCHANT_KINDS
)


@dataclass(frozen=True)
class DrinkEffect:
    """一瓶饮料的一个效果段（= ProduceDrinkEffect × 一个 effect_type）。

    ``kind`` 见 :data:`DRINK_EFFECT_KINDS`；``value`` 是结算数值（千分比/层数/张数/
    回合数，按 kind）；``turns`` 是持续回合（0 = 立即/永久，-1 = 永久，>0 = timed）；
    ``trigger`` 仅 timed 回合开始类（``turn_start_after``）；``search``/``move_to``
    仅 search_move（``deck_grave-idol-unique`` / ``hand``）。``implemented=False``
    的段结算时整段跳过。``rng`` 是 RNG 消费口径标签（见 :func:`rng_caliber`）。
    """

    kind: str
    value: int = 0
    turns: int = 0
    trigger: str = ""
    search: str = ""
    move_to: str = ""
    effect_type: str = ""
    implemented: bool = True
    rng: str = "none"
    label: str = ""

    def __post_init__(self) -> None:
        if self.kind not in DRINK_EFFECT_KINDS:
            raise ValueError(f"未知饮料效果 kind：{self.kind!r}")


def legacy_effect(effect_type: str, value: int) -> DrinkEffect:
    """旧 ``DrinkSpec(effect_type, value)`` 单效果 → 一个效果段（保持旧行为）。"""
    kind = effect_type if effect_type in ("stamina", "focus", "condition", "score") else "unknown"
    return DrinkEffect(
        kind=kind,
        value=int(value),
        effect_type=f"legacy:{effect_type}",
        implemented=kind != "unknown",
    )


def _as_int(value: Any) -> int:
    try:
        return int(str(value or 0))
    except (TypeError, ValueError):
        return 0


def classify_drink_effect(
    effect_type: str,
    values: dict[str, Any] | None = None,
    *,
    search: str = "",
    move_to: str = "",
    pick: str = "",
    inner: list[dict] | None = None,
    label: str = "",
) -> DrinkEffect:
    """主数据效果本体 → :class:`DrinkEffect`（语义确定的实现，其余 unknown）。

    ``values`` 是效果本体字段（effectValue1/effectValue2/effectCount/effectTurn）；
    ``search``/``move_to``/``pick`` 来自 produceCardSearchId/movePositionType/
    pickRangeType；``inner`` 是附魔内层效果段列表（``[{"type","values","trigger"}]``）。
    """
    values = values or {}
    v1 = _as_int(values.get("effectValue1") or values.get("value1"))
    count = _as_int(values.get("effectCount") or values.get("count"))
    turn = _as_int(values.get("effectTurn") or values.get("turn"))
    et = effect_type.replace("ProduceExamEffectType_", "")

    def mk(kind: str, value: int, turns: int = 0, **kw: Any) -> DrinkEffect:
        return DrinkEffect(
            kind=kind, value=value, turns=turns, effect_type=et, label=label,
            implemented=(kind != "unknown"), **kw
        )

    if et == "ExamStaminaRecoverFix":
        return mk("stamina", v1)
    if et == "ExamStaminaReduceFix":
        return mk("stamina_cost", v1)
    if et == "ExamLessonBuff":
        return mk("focus", v1)
    if et == "ExamParameterBuff":
        return mk("condition", v1 or turn)
    if et == "ExamLesson":
        return mk("score", v1)
    if et in ("ExamBlock", "ExamBlockFix"):
        return mk("vitality", v1)
    if et == "ExamReview":
        return mk("impression", v1)
    if et == "ExamCardPlayAggressive":
        return mk("aggressive", v1)
    if et == "ExamFullPowerPoint":
        return mk("full_power_point", v1)
    if et == "ExamPlayableValueAdd":
        return mk("extra_plays", count or v1)
    if et == "ExamLessonValueMultiple":
        # effectValue1 是千分比（100 = +10%，W9 苏打引擎 score_mult 1.0→1.1 核实）。
        return mk("score_buff", v1, turn, rng="none")
    if et == "ExamStaminaConsumptionDown":
        return mk("half_cost", turn, turn)
    if et == "ExamStaminaConsumptionAdd":
        return mk("double_cost", turn, turn)
    if et == "ExamStaminaConsumptionDownFix":
        return mk("cost_reduction", v1)
    if et == "ExamParameterBuffMultiplePerTurn":
        return mk("perfect_condition", turn, turn)
    if et == "ExamExtraTurn":
        return mk("extra_turn", 1)
    if et == "ExamCardDraw":
        return mk("draw", v1, rng="draw_support")
    if et == "ExamCardMove":
        # 只实现「牌堆/弃牌中搜索偶像固有 → 手牌」（W9 汉方）；其余搜索目标 unknown。
        if "idol-unique" in search and move_to == "hand":
            return mk(
                "search_move", 1, search=search, move_to=move_to, rng="type9_search"
            )
        # 阶段1.5：热绿茶「牌堆/弃牌选 1 张 → 保留」（pickRangeType=Select 玩家选牌，
        # 引擎走 select_policy 不掷点，oracle rng_advances=0 实测）。其余变体 unknown。
        if move_to == "hold" and pick == "Select" and search == "p_card_search-deck_grave":
            return mk("search_hold", 1, search=search, move_to=move_to, rng="none")
        # 阶段2 batch2：黑醋汁「牌堆/弃牌选 1 张 → 手牌」（Select 玩家选牌，
        # probe6 oracle rng_advances=0 + greedy_select_policy 选牌事件实测）。
        if move_to == "hand" and pick == "Select" and search == "p_card_search-deck_grave":
            return mk("select_move_hand", 1, search=search, move_to=move_to, rng="none")
        return mk("unknown", 0, rng="type9_search")
    if et == "ExamStatusEnchant":
        # 附魔：内层是「回合开始后抽 N 张」（trigger=start_play）→ timed 回合开始抽牌。
        for child in inner or []:
            ctype = str(child.get("type") or "").replace("ProduceExamEffectType_", "")
            cvals = child.get("values") or {}
            ctrigger = str(child.get("trigger") or "")
            if ctype == "ExamCardDraw" and "start_play" in ctrigger:
                n = _as_int(cvals.get("effectValue1") or cvals.get("value1"))
                return mk(
                    "turn_start_draw", n, turn, trigger="turn_start_after", rng="draw_support"
                )
            # 阶段1.5：严选初星系列「以后，回合结束/开始时 +N」（effectTurn=-1 永久）。
            # 内层效果类型 × 触发时机语义确定才实现；其余内层仍 unknown。
            n = _as_int(cvals.get("effectValue1") or cvals.get("value1"))
            if "exam_end_turn" in ctrigger:
                if ctype == "ExamLessonBuff":
                    return mk("turn_end_focus", n, turn, trigger="turn_end", rng="none")
                if ctype == "ExamReview":
                    return mk("turn_end_impression", n, turn, trigger="turn_end", rng="none")
                if ctype == "ExamCardPlayAggressive":
                    return mk("turn_end_aggressive", n, turn, trigger="turn_end", rng="none")
            if "exam_start_turn" in ctrigger and ctype == "ExamFullPowerPoint":
                return mk("turn_start_full_power", n, turn, trigger="turn_start", rng="none")
        return mk("unknown", 0)
    if et == "ExamPreservation":
        # 阶段1.5：温存指針直给（value1=1「温存变更」/ 2「温存阶段变更」↔
        # setStance(preservation/preservation2)，与 p_items P1-3 同渠道同口径）。
        if v1 in (1, 2):
            return mk("preservation", v1, rng="none")
        return mk("unknown", 0)
    if et == "ExamConcentration":
        # 阶段2 batch2：强气指針直给（姜汁汽水 v1=1 / 超级苏打 v1=2，probe6
        # oracle stance Concentration step1/2 + rng=0 实测；同温存渠道）。
        if v1 in (1, 2):
            return mk("concentration", v1, rng="none")
        return mk("unknown", 0)
    if et == "ExamSearchPlayCardStaminaConsumptionChange":
        # 阶段2 batch2：黑醋汁「接下来 count 张正费牌体力消耗变为 0」（v1=0，
        # effectTurn=-1 永久直到次数耗尽；probe6 实测前 2 张正费牌 stamina/block
        # 整费归零、0 费牌不耗次数、第 3 张正费牌恢复）。v1≠0 语义未定 → unknown。
        if v1 == 0 and count > 0:
            return mk("zero_cost", count, rng="none")
        return mk("unknown", 0, rng="search_unknown")
    if et == "ExamCardSearchEffectPlayCountBuff":
        # 阶段2 batch2：特制精华「下一张主动卡直接效果再发动 1 次」（v1=1/count=1/
        # turn=1；probe6 纯分卡 1244=2×622 实测，第 2 张正常、喝回合+下一回合有效
        # （effectTurn=1 + fresh 保护 = sim 倒计时 2），过期正常）。其余值未定。
        if v1 == 1 and count == 1 and turn == 1:
            return mk("encore_active", 1, turn, rng="none")
        return mk("unknown", 0, rng="search_unknown")
    if et in ("ExamCardCreateId", "ExamCardCreateSearch"):
        # 青汁：随机卡池生成 SSR → RNG 消费入口，真机流未知 → 显式 unknown。
        return mk("unknown", 0, rng="create_random_unknown")
    # 其余（ExamCardUpgrade 交互强化 / ExamForcePlayCardSearch /
    # ExamHandGraveCountCardDraw / ExamLessonDependExamReview 依赖换算）：
    # 语义未定或需交互/RNG → 显式 no-op。
    rng = "none"
    if et == "ExamForcePlayCardSearch":
        rng = "search_unknown"
    return mk("unknown", 0, rng=rng)


def effects_to_delta(effects: tuple[DrinkEffect, ...] | list[DrinkEffect]) -> PItemDelta:
    """把走 PItemDelta 渠道的效果段聚合成一份增量（双镜共用）。

    立即抽牌 / timed 回合开始抽牌 / search_move 不在这里（由 use_drink 直接结算）。
    ``stamina_cost`` 表达成负体力 + 累计消耗（与 ExamStaminaReduceFix 同口径）。
    """
    delta = PItemDelta()
    for eff in effects:
        if not eff.implemented or eff.kind not in DELTA_KINDS:
            continue
        kind, value = eff.kind, int(eff.value)
        if kind == "stamina":
            delta.stamina += value
        elif kind == "stamina_cost":
            delta.stamina -= value
            delta.stamina_consumed += value
        elif kind == "focus":
            delta.add_stack("focus", value)
        elif kind == "condition":
            delta.add_stack("parameter_buff", value)
        elif kind == "score":
            delta.score += value
        elif kind == "vitality":
            delta.add_stack("vitality", value)
        elif kind == "impression":
            delta.add_stack("impression", value)
        elif kind == "aggressive":
            delta.add_stack("aggressive", value)
        elif kind == "full_power_point":
            delta.add_stack("full_power_point", value)
        elif kind == "extra_plays":
            delta.extra_plays += value
        elif kind == "score_buff":
            delta.score_buffs.append((value, eff.turns))
        elif kind == "half_cost":
            delta.half_cost_turns += value
        elif kind == "double_cost":
            delta.double_cost_turns += value
        elif kind == "cost_reduction":
            delta.cost_reduction += value
        elif kind == "perfect_condition":
            delta.perfect_condition_turns += value
        elif kind == "extra_turn":
            delta.extra_turns += value
        elif kind == "preservation":
            # 阶段1.5：温存指針直给走 PItemDelta.stances（双镜 _apply_p_delta /
            # _apply_p_delta_state 已实现守卫/解除，与 P 道具 setStance 同口径）。
            delta.stances.append("preservation2" if value >= 2 else "preservation")
        elif kind == "concentration":
            # 阶段2 batch2：强气指針直给同渠道（concentration2 = 2 段階直给）。
            delta.stances.append("concentration2" if value >= 2 else "concentration")
    return delta


def drink_is_safe(effects: tuple[DrinkEffect, ...] | list[DrinkEffect]) -> bool:
    """sim 侧 SAFE 判定：全部效果段已实现且 kind ⊆ :data:`SAFE_KINDS`。

    用于我们自己的搜索/生产 allow_drinks 决策（引擎侧全饮料保留，gnrpa-spec
    实锤）。含 unknown 段 / 改牌区 / 改回合数 / 再发动类 → False（保守不喝）。
    空效果段（旧单效果路径）→ False（调用方走 legacy 口径）。
    """
    if not effects:
        return False
    return all(eff.implemented and eff.kind in SAFE_KINDS for eff in effects)


def add_turn_enchant(
    entries: tuple[tuple[str, int, int], ...], kind: str, value: int, turns: int
) -> tuple[tuple[str, int, int], ...]:
    """登记一条回合边界附魔 buff（ ``(kind, value, turns)``，同 kind+turns 合并加算）。

    与 :func:`p_items.add_timed` 同口径：``turns<=0`` 归一为永久（-1）。
    严选初星系列 effectTurn=-1（「以后」= 永久）；timed 变体留接口。
    """
    if not value:
        return entries
    turns = normalize_turns(turns)
    merged: list[tuple[str, int, int]] = []
    found = False
    for old_kind, old_value, old_turns in entries:
        if old_kind == kind and old_turns == turns:
            merged.append((old_kind, old_value + value, old_turns))
            found = True
        else:
            merged.append((old_kind, old_value, old_turns))
    if not found:
        merged.append((kind, value, turns))
    return tuple(merged)


def tick_turn_enchants(
    entries: tuple[tuple[str, int, int], ...],
) -> tuple[tuple[str, int, int], ...]:
    """回合末倒计时：turns>0 的 -1、到 0 移除，永久（-1）保持（同 tick_timed）。"""
    ticked: list[tuple[str, int, int]] = []
    for kind, value, turns in entries:
        if turns == PERMANENT_TURNS:
            ticked.append((kind, value, turns))
            continue
        next_turns = turns - 1
        if next_turns > 0:
            ticked.append((kind, value, next_turns))
    return tuple(ticked)


def rng_caliber(effects: tuple[DrinkEffect, ...] | list[DrinkEffect]) -> dict[str, Any]:
    """一瓶饮料的 RNG 消费口径汇总（m1-rng ``rng_graph`` 的饮料 hook）。

    返回 ``{"deterministic": bool, "entries": [口径标签…], "unknown": [effect_type…]}``：
      * ``none`` 段不消费随机数（含阶段1.5 的 Select 玩家选牌 search_hold /
        指針直给 / 回合边界附魔 buff，引擎 oracle rng_advances=0 实测）；
      * ``type9_search`` 段按搜索候选掷点（精确消费数需引擎 oracle 配对）；
      * ``draw_support`` 段抽牌本身不掷点、入手触发支援强化（考试 RNG 图侧）；
      * ``create_random_unknown`` / ``search_unknown`` 真机流未知 → 显式 unknown。
    课程 sim 不復现支援强化掷点；本函数只供消费图标注与引擎配对，不猜精确次数。
    """
    entries: list[str] = []
    unknown: list[str] = []
    for eff in effects:
        if not eff.implemented:
            if eff.rng.endswith("unknown") or eff.rng == "search_unknown":
                unknown.append(eff.effect_type or eff.kind)
            continue
        if eff.rng and eff.rng != "none":
            entries.append(eff.rng)
    return {
        "deterministic": not entries and not unknown,
        "entries": sorted(set(entries)),
        "unknown": sorted(set(unknown)),
    }
