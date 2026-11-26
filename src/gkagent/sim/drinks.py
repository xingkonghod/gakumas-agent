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
  * 饮料特有的三类（立即抽牌 / timed 回合开始抽牌 / zone search move 偶像固有）
    由 ``LessonSim.use_drink`` / ``expectimax.use_drink_state`` 直接结算。

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

from gkagent.sim.p_items import PItemDelta

__all__ = [
    "DRINK_EFFECT_KINDS",
    "DrinkEffect",
    "classify_drink_effect",
    "effects_to_delta",
    "rng_caliber",
    "legacy_effect",
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
    "unknown": "未建模（RNG/交互/依赖换算），显式 no-op",
}

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
    }
)
#: 由 use_drink / use_drink_state 直接结算的 kind（需要牌区/抽牌交互）。
DIRECT_KINDS = frozenset({"draw", "turn_start_draw", "search_move"})


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
    inner: list[dict] | None = None,
    label: str = "",
) -> DrinkEffect:
    """主数据效果本体 → :class:`DrinkEffect`（语义确定的实现，其余 unknown）。

    ``values`` 是效果本体字段（effectValue1/effectValue2/effectCount/effectTurn）；
    ``search``/``move_to`` 来自 produceCardSearchId/movePositionType；``inner`` 是
    附魔内层效果段列表（``[{"type","values","trigger"}]``）。
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
        return mk("unknown", 0)
    if et in ("ExamCardCreateId", "ExamCardCreateSearch"):
        # 青汁：随机卡池生成 SSR → RNG 消费入口，真机流未知 → 显式 unknown。
        return mk("unknown", 0, rng="create_random_unknown")
    # 其余（ExamCardUpgrade 交互强化 / ExamConcentration/ExamPreservation 指針直给 /
    # ExamForcePlayCardSearch / ExamSearchPlayCardStaminaConsumptionChange /
    # ExamCardSearchEffectPlayCountBuff / ExamHandGraveCountCardDraw /
    # ExamLessonDependExamReview 依赖换算）：语义未定或需交互/RNG → 显式 no-op。
    rng = "none"
    if et in (
        "ExamForcePlayCardSearch",
        "ExamSearchPlayCardStaminaConsumptionChange",
        "ExamCardSearchEffectPlayCountBuff",
    ):
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
    return delta


def rng_caliber(effects: tuple[DrinkEffect, ...] | list[DrinkEffect]) -> dict[str, Any]:
    """一瓶饮料的 RNG 消费口径汇总（m1-rng ``rng_graph`` 的饮料 hook）。

    返回 ``{"deterministic": bool, "entries": [口径标签…], "unknown": [effect_type…]}``：
      * ``none`` 段不消费随机数；
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
