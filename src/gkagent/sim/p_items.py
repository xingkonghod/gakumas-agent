"""P 道具（被动道具）建模：只做"事件 -> 增量"的纯函数，不碰 ``LessonSim`` 内部状态。

真机课程右上角的 P 道具是**被动**的：满足条件自动触发，不需要玩家动作，但会影响
分数 / 体力 / 层数 / 当回合可出牌次数。数据来自 ``data/knowledge/p_items.json``
（由 ``scripts/build_p_items.py`` 解析 ``masterTrans/ProduceItem.json`` + gakumasu-diff
的 ``ProduceItem.yaml`` 生成，**1115 件**：本地中文 master 1068 件 + 上游新增 47 件）。
真实对局带哪些 P 道具由 ``gkagent.data.p_items_db`` 从 loadout 的
``produce_item_ids`` 解析（B7 起 catalog 覆盖到上游 1115 件，gkbench 505 题模板
的 83 个唯一 id 全部已知；上游新增 47 件的描述/中文触发句缺失 → 卡名用仓库自译表、
描述日文、条件未知的保守不触发，见 ``PItemSpec.condition_known``）。

设计边界（有意保守）：

* ``apply_passive`` 是**纯函数**：接收 ``PItemSpec`` 列表 + 一个事件 + 一份简单状态，
  返回 ``PItemDelta``（分数 / 体力 / 层数 / 当回合额外可出牌次数的增量），不读也不写
  模拟器内部状态。
* 只实现"语义确定"的效果；其余 ``effect_type`` 一律 no-op（不抛异常），
  由 ``unsupported_effect_types`` / ``summarize`` 统计出来。
* 条件（``condition``）只认几个能确定语义的写法（层数阈值、体力百分比、回合数）；
  认不出的条件**不触发**（宁可少算，也不瞎算）。
* ``state.uses`` 给出时才按 ``max_uses`` 封顶（次数上限，卡面「（N次）」）。
* 触发时机：``turn_start`` / ``turn_end`` / ``card_play``（含使用后/每 N 次）/
  ``status_gain`` / ``exam_start``（训练·考试开始时，由 ``LessonSim`` 构造时结算一次）。

用法::

    from gkagent.sim.p_items import (PassiveEvent, PassiveState, apply_passive, load_p_items)

    specs = load_p_items()
    delta = apply_passive(specs, PassiveEvent(kind="card_play", cards_played_this_turn=2), PassiveState(turn=1))
    delta.score, delta.stamina, delta.extra_plays, delta.stacks
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

# ---- 事件种类（apply_passive 认的事件）------------------------------------
TURN_START = "turn_start"
TURN_START_AFTER = "turn_start_after"  # 回合开始后（B8：start_play-remaining_turn-N）
TURN_INTERVAL = "turn_interval"  # 每 N 回合（B8：exam_turn_interval-N）
TURN_END = "turn_end"
CARD_PLAY = "card_play"  # 出牌：同时覆盖"技能卡使用时/使用后"两种触发
STATUS_GAIN = "status_gain"  # 直接效果让某个状态增加（好印象/集中/干劲…）
STATUS_GAIN_INTERVAL = "status_gain_interval"  # 状态累计增加 N 次时（B8）
STANCE_CHANGE = "stance_change"  # 指針变化时（B8：强气/温存/全力）
STAMINA_REDUCE = "stamina_reduce"  # 体力减少时（B8：支付牌费等）
# 训练/考试开始时（e_trigger-exam_start_exam / start_exam_play 等）；
# 由 LessonSim 在开局（抽第一手牌前）结算一次。gkbench 起点体力偏差就是这类道具
# （如 pitem_02-3-293-0「训练开始时，最大体力的80%数值变为体力消耗」）。
EXAM_START = "exam_start"

# ---- 效果类型 -> 结算目标 --------------------------------------------------
# 语义确定的：分数 / 体力 / 层数（元气、好印象、集中、干劲、全力值）/
# 当回合额外可出牌次数（ExamPlayableValueAdd，与卡效果同口径）
SCORE_EFFECTS = frozenset({"ExamLesson"})
STAMINA_GAIN_EFFECTS = frozenset({"ExamStaminaRecoverFix"})
STAMINA_LOSS_EFFECTS = frozenset({"ExamStaminaReduceFix"})  # B8：固定体力消耗（含最大体力%）
STAMINA_EFFECTS = STAMINA_GAIN_EFFECTS | STAMINA_LOSS_EFFECTS
EXTRA_PLAY_EFFECTS = frozenset({"ExamPlayableValueAdd"})
STACK_EFFECTS = {
    "ExamBlock": "vitality",
    "ExamReview": "impression",
    "ExamLessonBuff": "focus",
    "ExamCardPlayAggressive": "aggressive",
    "ExamFullPowerPoint": "full_power_point",
    "ExamParameterBuff": "parameter_buff",
    # B9：固定元气（固定Genki，不吃干劲加成，直接进元气）
    "ExamBlockFix": "vitality",
}

# ---- B9（2026-11-22）：持久倍率 / modifier 类效果 ---------------------------
# 语义来源：gakumas-tools 参考引擎（BSD-3）
#   * ``Executor/resolvers.js::resolveScore`` f/g：score *= (1 + Σ scoreBuff)，
#     再 *= max(1 − Σ scoreDebuff, 0)；
#   * ``BuffManager.js``：``setScoreBuff(amount, turns)`` 等按 (amount, turns)
#     入列表、回合末倒计时（turns=None 永久）；
#   * ``p_items.csv`` 的 DSL（``setScoreBuff(0.5,1)`` / ``setStance(preservation)`` /
#     ``costReduction+=N`` 等）。
# 这里只做「PItemSpec.target 分类 + PItemDelta 增量」；生命周期与结算在
# ``sim/lesson.py`` / ``sim/expectimax.py`` 里镜像。
SCORE_BUFF_EFFECTS = frozenset({"ExamLessonValueMultiple"})  # 打分上升量增加
SCORE_DEBUFF_EFFECTS = frozenset({"ExamLessonValueMultipleDown"})  # 打分上升量减少
REVIEW_MULTIPLE_EFFECTS = frozenset({"ExamReviewMultiple"})  # 好印象强化
REVIEW_TIMES_EFFECTS = frozenset({"ExamReviewCountAdd"})  # 好印象追加发动
ENTHUSIASM_MULTIPLE_EFFECTS = frozenset({"ExamEnthusiasticMultiple"})  # 热意增加
ENTHUSIASM_BONUS_EFFECTS = frozenset({"ExamEnthusiasticAdditive"})  # 热意追加
CONCENTRATION_EFFECT_EFFECTS = frozenset({"ExamLessonBuffMultiple"})  # 集中强化
CONCENTRATION_GAIN_EFFECTS = frozenset({"ExamLessonBuffAdditive"})  # 集中增加量增加
IMPRESSION_GAIN_EFFECTS = frozenset({"ExamReviewAdditive"})  # 好印象增加量增加
MOTIVATION_GAIN_EFFECTS = frozenset({"ExamAggressiveAdditive"})  # 干劲增加量增加
FULL_POWER_CHARGE_EFFECTS = frozenset({"ExamFullPowerPointAdditive"})  # 全力值增加量增加
PERFECT_CONDITION_EFFECTS = frozenset({"ExamParameterBuffMultiplePerTurn"})  # 绝好调
POOR_CONDITION_EFFECTS = frozenset({"ExamGimmickParameterDebuff"})  # 不调
EXTRA_TURN_EFFECTS = frozenset({"ExamExtraTurn"})  # 回合追加
COST_REDUCTION_EFFECTS = frozenset({"ExamStaminaConsumptionDownFix"})  # 削减消耗体力
COST_INCREASE_EFFECTS = frozenset({"ExamStaminaConsumptionAddFix"})  # 消耗体力追加
HALF_COST_EFFECTS = frozenset({"ExamStaminaConsumptionDown"})  # 消耗体力减少（回合）
DOUBLE_COST_EFFECTS = frozenset({"ExamStaminaConsumptionAdd"})  # 消耗体力增加（回合）
IMPRESSION_REDUCE_EFFECTS = frozenset({"ExamReviewReduce"})  # 好印象减少
STANCE_EFFECT_TARGETS = {
    "ExamPreservation": "stance_preservation",
    "ExamConcentration": "stance_concentration",
}

#: effect_type -> 新目标（不含需要看文本才能判定的指針直给式）。
TARGET_BY_EFFECT: dict[str, str] = {
    **{effect: "score_buff" for effect in SCORE_BUFF_EFFECTS},
    **{effect: "score_debuff" for effect in SCORE_DEBUFF_EFFECTS},
    **{effect: "review_multiple" for effect in REVIEW_MULTIPLE_EFFECTS},
    **{effect: "review_times" for effect in REVIEW_TIMES_EFFECTS},
    **{effect: "enthusiasm_multiple" for effect in ENTHUSIASM_MULTIPLE_EFFECTS},
    **{effect: "enthusiasm_bonus" for effect in ENTHUSIASM_BONUS_EFFECTS},
    **{effect: "concentration_effect" for effect in CONCENTRATION_EFFECT_EFFECTS},
    **{effect: "concentration_gain" for effect in CONCENTRATION_GAIN_EFFECTS},
    **{effect: "impression_gain" for effect in IMPRESSION_GAIN_EFFECTS},
    **{effect: "motivation_gain" for effect in MOTIVATION_GAIN_EFFECTS},
    **{effect: "full_power_charge" for effect in FULL_POWER_CHARGE_EFFECTS},
    **{effect: "perfect_condition_turns" for effect in PERFECT_CONDITION_EFFECTS},
    **{effect: "poor_condition_turns" for effect in POOR_CONDITION_EFFECTS},
    **{effect: "extra_turn" for effect in EXTRA_TURN_EFFECTS},
    **{effect: "cost_reduction" for effect in COST_REDUCTION_EFFECTS},
    **{effect: "cost_increase" for effect in COST_INCREASE_EFFECTS},
    **{effect: "half_cost_turns" for effect in HALF_COST_EFFECTS},
    **{effect: "double_cost_turns" for effect in DOUBLE_COST_EFFECTS},
    **{effect: "impression_reduce" for effect in IMPRESSION_REDUCE_EFFECTS},
}

#: 百分比类目标：effect.values.percent1 是「人类百分比」（50 = +50%），
#: spec.value 统一存千分比（500），与卡表 ``review_multiple`` 渠道一致。
PERCENT_TARGETS = frozenset(
    {
        "score_buff",
        "score_debuff",
        "review_multiple",
        "enthusiasm_multiple",
        "concentration_effect",
        "concentration_gain",
        "impression_gain",
        "motivation_gain",
        "full_power_charge",
    }
)
#: 持续回合数取自 ``values.turn`` 的目标（0/缺 = 永久，与参考引擎 turns=None 同义）。
DURATION_TARGETS = frozenset(
    {
        "score_buff",
        "score_debuff",
        "review_multiple",
        "review_times",
        "enthusiasm_multiple",
        "enthusiasm_bonus",
        "concentration_effect",
        "concentration_gain",
        "impression_gain",
        "motivation_gain",
        "full_power_charge",
        "half_cost_turns",
        "double_cost_turns",
        "perfect_condition_turns",
        "poor_condition_turns",
    }
)
#: 纯标记类目标（数值固定 1 / 只看触发时机）。
FLAG_TARGETS = frozenset({"extra_turn", "stance_preservation", "stance_concentration"})
#: 新目标的全部集合（供 summarize / implemented 判定）。
MODIFIER_TARGETS = frozenset(
    set(TARGET_BY_EFFECT.values()) | set(STANCE_EFFECT_TARGETS.values())
)

# ---- 已实现的触发时机 ------------------------------------------------------
SUPPORTED_TRIGGERS = frozenset(
    {
        TURN_START,
        TURN_START_AFTER,
        TURN_INTERVAL,
        TURN_END,
        CARD_PLAY,
        "card_played",
        "card_play_interval",
        STATUS_GAIN,
        STATUS_GAIN_INTERVAL,
        STANCE_CHANGE,
        STAMINA_REDUCE,
        EXAM_START,
    }
)

# 条件里的状态中文名 -> stacks 的 key
STATUS_NAMES = {
    "元气": "vitality",
    "好印象": "impression",
    "集中": "focus",
    "好调": "parameter_buff",
    "干劲": "aggressive",
    "全力值": "full_power_point",
    "强气": "stance_concentration",
    "温存": "stance_preservation",
    "全力": "stance_full_power",
    # B9：条件里的「消耗体力减少状态」= halfCostTurns>0（P 道具/卡效果给的
    # 消耗体力减少回合数），用伪 stack key 表达"是否在状态中"。
    "消耗体力减少": "half_cost_state",
}

# 能拿来做"层数阈值"比较的状态：都是纯层数。好调（parameter_buff）在模拟器里是
# 千分比／剩余回合数，量纲不一样，所以不做阈值比较（返回 None = 不知道）。
THRESHOLD_KEYS = frozenset(
    {
        "vitality",
        "impression",
        "focus",
        "aggressive",
        "full_power_point",
        "stance_concentration",
        "stance_preservation",
        "stance_full_power",
    }
)

_RE_STATUS_GE = re.compile(r"^(?P<name>[^，]+?)在(?P<value>\d+)以上(?:的时候)?$")
_RE_STATUS_LE = re.compile(r"^(?P<name>[^，]+?)在(?P<value>\d+)以下(?:的时候)?$")
_RE_STATUS_EQ = re.compile(r"^(?P<name>[^，]+?)为(?P<value>\d+)(?:的时候)?$")
_RE_STAMINA_PCT = re.compile(r"^体力在(?P<value>\d+)%(?P<op>以上|以下)(?:的时候)?$")
_RE_REMAINING = re.compile(r"^剩余(?P<value>\d+)回合内(?:的时候)?$")
_RE_PRESENT = re.compile(r"^(?P<name>[^，]+?)(?:状态)?的时候$")
_RE_TURN = re.compile(r"^第(?P<value>\d+)回合(?:开始时|结束时)?$")
# B8：新语法 id 解析出的条件（好调按「剩余回合数」；累计全力值看本场累计）
_RE_PARAM_BUFF_TURNS = re.compile(r"^好调在(?P<value>\d+)回合以上(?:的时候)?$")
_RE_FULL_POWER_TOTAL = re.compile(
    r"^(?:这个训练中的|本场累计的)?累计全力值在(?P<value>\d+)以上(?:的时候)?$"
)


@dataclass(frozen=True)
class PItemSpec:
    """一条 P 道具被动效果（= 道具 × 一个 effect_type）。

    字段按交付要求给足 name / trigger / effect_type / value / condition，
    其余是数据层解析出来的触发参数，手写构造时可以全部留空。
    """

    name: str
    trigger: str
    effect_type: str
    value: int = 0
    condition: str = ""
    # 条件是否已知：新增道具的新触发 id 没有中文触发句时 = False（条件没解析出来），
    # apply_passive 会保守跳过（宁可不触发，也不把带条件的道具当无条件结算）。
    condition_known: bool = True
    # B8：触发条件里是否含「指定卡名 / 手牌指定卡张数」这类还没有卡名→id 映射的限定；
    # False 时同样保守跳过（否则会在任意卡上误触发）。
    trigger_known: bool = True
    item_id: str = ""
    rarity: str = ""
    label: str = ""  # effect_type 的中文名（打分/元气/…）
    # B9（2026-11-22）：持久倍率 / modifier 类效果的显式目标（覆盖按 effect_type
    # 推导的 target）；duration 是持续回合数（0 = 永久，参考引擎 turns=None）。
    target_kind: str = ""
    duration: int = 0
    # B9：效果段自己的文本（指針直给式/随机手牌限定的判定要用它；数据层写入）。
    effect_text: str = ""
    interval: int = 0  # card_play_interval：每 N 次；status_gain_interval：每 N 次状态增加
    interval_scope: str = "turn"  # turn = 回合内累计，exam = 整场累计
    status: str = ""  # status_gain：触发它的状态 key
    status_min: int = 0  # status_gain：「增加 N 以上后」的门槛，0 = 不限
    turn: int | None = None  # 仅第 N 回合
    remaining_turns: int | None = None  # 仅剩余 N 回合内
    final_turn: bool = False  # 仅最终回合
    card_filter: str = ""  # ActiveSkill / MentalSkill / IdolUnique
    lesson_filter: str = ""  # vocal / dance / visual / sp
    max_uses: int = 0  # 次数上限，0 = 不限
    text: str = ""  # 中文描述（调试用）
    # B8：依赖换算（「X 的 N% 数值变为 Y」）/ 最大体力百分比 / 「X 变为 0」/ 每 N 回合。
    depends_on: str = ""  # 源层数 key（vitality/impression/focus/aggressive/full_power_point/…）
    percent: int = 0  # 依赖换算百分比：目标增量 = int(源层数 × percent / 100)
    percent_max: int = 0  # 体力类效果：按最大体力百分比结算
    every: int = 0  # turn_interval：每 N 回合
    zero_stack: str = ""  # 「X 变为 0」：结算时把该层数清零

    @property
    def target(self) -> str:
        """这条效果结算到哪儿："score" / "stamina" / "extra_plays" / 层数 key /
        B9 的持久倍率目标（score_buff / review_multiple / …）/ ""（不支持）。"""
        if self.target_kind:
            return self.target_kind
        # 手写 spec 没带 target_kind 时按 effect_type（+ 效果段文本）推导；
        # 数据层 record_to_specs 会显式写入 target_kind（含指針直给式的文本判定）。
        modifier = classify_effect_target(
            self.effect_type, self.effect_text or self.text
        )
        if modifier:
            return modifier
        if self.effect_type in SCORE_EFFECTS:
            return "score"
        if self.effect_type in STAMINA_EFFECTS:
            return "stamina"
        if self.effect_type in EXTRA_PLAY_EFFECTS:
            return "extra_plays"
        return STACK_EFFECTS.get(self.effect_type, "")

    @property
    def implemented(self) -> bool:
        if self.trigger not in SUPPORTED_TRIGGERS:
            return False
        if self.zero_stack:
            return True
        if self.depends_on and self.percent > 0:
            return True
        if self.percent_max > 0 and self.target == "stamina":
            return True
        target = self.target
        if target in PERCENT_TARGETS:
            # 百分比类：value 是千分比（>0 才算有数值）
            return self.value > 0
        if target in FLAG_TARGETS:
            return True
        if target in ("review_times", "cost_reduction", "cost_increase", "impression_reduce"):
            return self.value > 0
        if target in (
            "half_cost_turns",
            "double_cost_turns",
            "perfect_condition_turns",
            "poor_condition_turns",
        ):
            return self.duration > 0 or self.value > 0
        return bool(target) and self.value > 0


@dataclass(frozen=True)
class PassiveEvent:
    """触发事件。``kind`` 只用 TURN_START / TURN_START_AFTER / TURN_INTERVAL / TURN_END /
    CARD_PLAY / STATUS_GAIN / STATUS_GAIN_INTERVAL / STANCE_CHANGE / STAMINA_REDUCE / EXAM_START。"""

    kind: str
    card_category: str = ""  # 打出的卡类别：ActiveSkill / MentalSkill / IdolUnique
    cards_played_this_turn: int = 0
    cards_played_total: int = 0
    status: str = ""  # status_gain：增加的是哪个状态（stacks 的 key）
    amount: int = 0  # status_gain：增加了多少层
    status_total: int = 0  # status_gain：累计增加次数（含本次；status_gain_interval 用）
    stamina_delta: int = 0  # stamina_reduce：这次减少了多少体力（正数）


@dataclass(frozen=True)
class PassiveState:
    """模拟器侧传进来的简单状态（只读）。

    ``turns_left`` / ``is_final_turn`` / ``lesson_type`` / ``uses`` 等字段留空表示
    "模拟器不知道"，此时依赖这些信息的道具**不触发**（保守）。

    ``stacks`` 除真实层数外，还投影两个 B8 用的伪 key（依赖换算的源）：
    ``full_power_point_total``（本场累计全力值）与 ``consumed_stamina_total``（本场累计
    消耗体力）。``status_counts`` 是各状态**累计增加次数**（status_gain_interval 用）。
    """

    turn: int = 0
    turns_left: int | None = None
    is_final_turn: bool = False
    stamina: int = 0
    stamina_max: int = 0
    score: int = 0
    lesson_type: str = ""  # vocal / dance / visual
    is_sp: bool = False
    stacks: Mapping[str, int] = field(default_factory=dict)
    status_counts: Mapping[str, int] = field(default_factory=dict)
    uses: Mapping[str, int] | None = None  # item_id -> 已经触发次数

    def stack(self, key: str) -> int:
        return int(self.stacks.get(key, 0))

    def status_count(self, key: str) -> int:
        return int(self.status_counts.get(key, 0))


@dataclass
class PItemDelta:
    """一次事件里所有 P 道具带来的增量（纯数据）。"""

    score: int = 0
    stamina: int = 0
    stamina_consumed: int = 0  # B8：其中「固定体力消耗」扣掉的量（正数，累计消耗体力用）
    extra_plays: int = 0  # 当回合额外可出牌次数（ExamPlayableValueAdd）
    stacks: dict[str, int] = field(default_factory=dict)
    zero_stacks: list[str] = field(default_factory=list)  # B8：「X 变为 0」
    applied: list[str] = field(default_factory=list)  # 触发了哪些道具（item_id 或 name）
    # ---- B9（2026-11-22）：持久倍率 / modifier 增量 -------------------------
    # 分数倍率是**列表**（参考引擎同类 buff 按 turns 分组、amount 加算）；元素
    # (千分比, 剩余回合)，remaining=-1 = 永久。
    score_buffs: list[tuple[int, int]] = field(default_factory=list)
    score_debuffs: list[tuple[int, int]] = field(default_factory=list)
    # 其它持久倍率：key -> (千分比/数值, 剩余回合)。key 见 MODIFIER_TARGETS。
    modifiers: list[tuple[str, int, int]] = field(default_factory=list)
    # 固定/百分比费用修正（永久，整场累计）；half/double 是「接下来 N 回合」计数器
    cost_reduction: int = 0
    cost_increase: int = 0
    half_cost_turns: int = 0
    double_cost_turns: int = 0
    # 回合追加（ExamExtraTurn）：累积到本回合结束再加到剩余回合数
    extra_turns: int = 0
    # 指針直给（ExamPreservation/ExamConcentration 的「温存变更/强气变更」）
    stances: list[str] = field(default_factory=list)
    # 绝好调 / 不调 回合数（ExamParameterBuffMultiplePerTurn / ExamGimmickParameterDebuff）
    perfect_condition_turns: int = 0
    poor_condition_turns: int = 0

    def add_stack(self, key: str, amount: int) -> None:
        if amount:
            self.stacks[key] = self.stacks.get(key, 0) + amount

    def is_zero(self) -> bool:
        return not (
            self.score
            or self.stamina
            or self.stamina_consumed
            or self.extra_plays
            or self.zero_stacks
            or self.score_buffs
            or self.score_debuffs
            or self.modifiers
            or self.cost_reduction
            or self.cost_increase
            or self.half_cost_turns
            or self.double_cost_turns
            or self.extra_turns
            or self.stances
            or self.perfect_condition_turns
            or self.poor_condition_turns
            or any(self.stacks.values())
        )

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "stamina": self.stamina,
            "stamina_consumed": self.stamina_consumed,
            "extra_plays": self.extra_plays,
            "stacks": dict(self.stacks),
            "zero_stacks": list(self.zero_stacks),
            "score_buffs": list(self.score_buffs),
            "score_debuffs": list(self.score_debuffs),
            "modifiers": list(self.modifiers),
        }

    def __iadd__(self, other: PItemDelta) -> Self:
        self.score += other.score
        self.stamina += other.stamina
        self.stamina_consumed += other.stamina_consumed
        self.extra_plays += other.extra_plays
        for key, amount in other.stacks.items():
            self.add_stack(key, amount)
        self.zero_stacks.extend(other.zero_stacks)
        self.applied.extend(other.applied)
        self.score_buffs.extend(other.score_buffs)
        self.score_debuffs.extend(other.score_debuffs)
        self.modifiers.extend(other.modifiers)
        self.cost_reduction += other.cost_reduction
        self.cost_increase += other.cost_increase
        self.half_cost_turns += other.half_cost_turns
        self.double_cost_turns += other.double_cost_turns
        self.extra_turns += other.extra_turns
        self.stances.extend(other.stances)
        self.perfect_condition_turns += other.perfect_condition_turns
        self.poor_condition_turns += other.poor_condition_turns
        return self

    def __add__(self, other: PItemDelta) -> PItemDelta:
        merged = PItemDelta(
            score=self.score,
            stamina=self.stamina,
            stamina_consumed=self.stamina_consumed,
            extra_plays=self.extra_plays,
            stacks=dict(self.stacks),
            zero_stacks=list(self.zero_stacks),
            applied=list(self.applied),
            score_buffs=list(self.score_buffs),
            score_debuffs=list(self.score_debuffs),
            modifiers=list(self.modifiers),
            cost_reduction=self.cost_reduction,
            cost_increase=self.cost_increase,
            half_cost_turns=self.half_cost_turns,
            double_cost_turns=self.double_cost_turns,
            extra_turns=self.extra_turns,
            stances=list(self.stances),
            perfect_condition_turns=self.perfect_condition_turns,
            poor_condition_turns=self.poor_condition_turns,
        )
        merged += other
        return merged


# ---- B9：定时倍率列表的纯函数（参考引擎 BuffManager.setBuff/decrementBuffTurns）----
# 列表元素 ``(amount, turns)``：``turns`` = 剩余回合数，-1 = 永久（参考引擎 None）。
# 同 ``turns`` 的条目按参考引擎 ``setBuff`` 合并（amount 相加）；回合末
# ``tick_timed`` 把 turns>0 的 -1、到 0 移除、永久保持。
TimedAmounts = tuple[tuple[int, int], ...]
PERMANENT_TURNS = -1


def normalize_turns(turns: int) -> int:
    """0/None 表示永久 → -1；负数原样返回（-1 = 永久）。"""
    if isinstance(turns, bool) or not isinstance(turns, int):
        raise TypeError(f"turns 必须是 int：{turns!r}")
    if turns <= 0:
        return PERMANENT_TURNS
    return turns


def add_timed(entries: TimedAmounts, amount: int, turns: int) -> TimedAmounts:
    """按参考引擎 ``setBuff`` 口径加入一条 (amount, turns)：同 turns 合并加算。"""
    if not amount:
        return entries
    turns = normalize_turns(turns)
    merged: list[tuple[int, int]] = []
    found = False
    for old_amount, old_turns in entries:
        if old_turns == turns:
            merged.append((old_amount + amount, old_turns))
            found = True
        else:
            merged.append((old_amount, old_turns))
    if not found:
        merged.append((amount, turns))
    return tuple(merged)


def total_timed(entries: TimedAmounts) -> int:
    """当前生效的合计值（参考引擎 ``reduce((acc, cur) => acc + cur.amount, 0/1)``）。"""
    return sum(amount for amount, _ in entries)


def tick_timed(entries: TimedAmounts) -> TimedAmounts:
    """回合末倒计时：turns>0 的 -1、到 0 移除，-1（永久）保持。"""
    ticked: list[tuple[int, int]] = []
    for amount, turns in entries:
        if turns == PERMANENT_TURNS:
            ticked.append((amount, turns))
            continue
        next_turns = turns - 1
        if next_turns > 0:
            ticked.append((amount, next_turns))
    return tuple(ticked)


def timed_dict_add(
    table: Mapping[str, TimedAmounts], key: str, amount: int, turns: int
) -> dict[str, TimedAmounts]:
    """``{key: timed 列表}`` 的 copy-on-write 加入（modifier 渠道共用）。"""
    merged = dict(table)
    merged[key] = add_timed(merged.get(key, ()), amount, turns)
    return merged


def timed_dict_tick(table: Mapping[str, TimedAmounts]) -> dict[str, TimedAmounts]:
    ticked: dict[str, TimedAmounts] = {}
    for key, entries in table.items():
        after = tick_timed(entries)
        if after:
            ticked[key] = after
    return ticked


def timed_dict_total(table: Mapping[str, TimedAmounts], key: str) -> int:
    return total_timed(table.get(key, ()))


def _permil(percent: int) -> int:
    """人类百分比 → 千分比（与卡表 review_multiple 等渠道同口径）。"""
    return int(percent) * 10


def classify_effect_target(effect_type: str, text: str = "") -> str:
    """B9：effect_type（+ 中文/日文效果文本）→ 持久倍率目标；认不出返回 ""。

    指針直给式（``ExamPreservation``/``ExamConcentration``）要看文本：卡名/卡类
    强化段（「温存效果的技能卡的…」「强气效果的技能卡的打分值增加…」）**不是**
    指針变更，不能当直给式结算（保守 no-op）；只有「温存变更 / 温存阶段变更 /
    温存に変更 / 强气变更 / 強気変更」才是 ``setStance``。
    """
    if effect_type in STANCE_EFFECT_TARGETS:
        head = (text or "").strip()
        if effect_type == "ExamPreservation":
            if head.startswith(("温存变更", "温存阶段变更", "温存に変更")):
                return "stance_preservation"
            return ""
        if head.startswith(("强气变更", "强気変更", "強気変更", "强气に変更")):
            return "stance_concentration"
        return ""
    kind = TARGET_BY_EFFECT.get(effect_type, "")
    if kind and "随机" in (text or ""):
        # 「削减消耗体力随机1张手牌在…」这类效果只作用于随机 1 张手牌：
        # 没有手牌定位就不能当全局费用削减结算（保守 no-op）。
        return ""
    return kind


def effect_target(effect: Mapping) -> str:
    """一条 effect 段的 B9 目标（数据里带 ``target`` 时优先，旧数据按类型推导）。"""
    explicit = str(effect.get("target") or "")
    if explicit:
        return explicit
    return classify_effect_target(str(effect.get("type") or ""), str(effect.get("text") or ""))


def effect_value(effect: Mapping, target: str | None = None) -> int:
    """一条 effect 段结算用的数值（B9 口径；旧类型仍取 value1/count）。

    * 百分比类目标：``percent1``（人类百分比）→ 千分比；
    * 回合数类目标（持续回合/绝好调/消耗体力减少回合）：``turn``；
    * 其余：``value1``（``ExamPlayableValueAdd`` 优先 ``count``，B6 口径）。
    """
    kind = target if target is not None else effect_target(effect)
    values = effect.get("values") or {}
    if kind in PERCENT_TARGETS:
        return _permil(int(values.get("percent1") or 0))
    if kind in (
        "half_cost_turns",
        "double_cost_turns",
        "perfect_condition_turns",
        "poor_condition_turns",
    ):
        return int(values.get("turn") or 0)
    if effect.get("type") == "ExamPlayableValueAdd":
        return int(values.get("count") or values.get("value1") or 0)
    return int(values.get("value1") or 0)


def effect_duration(effect: Mapping, target: str | None = None) -> int:
    """持续回合数（B9）：``values.turn``；0 = 永久（参考引擎 turns=None）。"""
    kind = target if target is not None else effect_target(effect)
    values = effect.get("values") or {}
    if kind in ("half_cost_turns", "double_cost_turns"):
        # 「消耗体力减少/增加 N 回合」的 N 就是持续回合数
        return int(values.get("turn") or 0)
    if kind in DURATION_TARGETS or kind in (
        "perfect_condition_turns",
        "poor_condition_turns",
    ):
        return int(values.get("turn") or 0)
    return 0


def evaluate_condition(condition: str, state: PassiveState) -> bool | None:
    """条件求值：True / False / None（认不出 = 不知道，调用方应当不触发）。"""
    text = (condition or "").strip()
    if not text:
        return True

    match = _RE_STAMINA_PCT.match(text)
    if match:
        if state.stamina_max <= 0:
            return None
        percent = state.stamina * 100 / state.stamina_max
        value = int(match.group("value"))
        return percent >= value if match.group("op") == "以上" else percent <= value

    match = _RE_REMAINING.match(text)
    if match:
        if state.turns_left is None:
            return None
        return state.turns_left <= int(match.group("value"))

    # B8：好调按「剩余回合数」比较；累计全力值看本场累计（伪 stack key）。
    match = _RE_PARAM_BUFF_TURNS.match(text)
    if match:
        return state.stack("parameter_buff") >= int(match.group("value"))

    match = _RE_FULL_POWER_TOTAL.match(text)
    if match:
        return state.stack("full_power_point_total") >= int(match.group("value"))

    match = _RE_TURN.match(text)
    if match:
        return state.turn == int(match.group("value"))

    match = _RE_STATUS_GE.match(text) or _RE_STATUS_LE.match(text) or _RE_STATUS_EQ.match(text)
    if match:
        key = STATUS_NAMES.get(match.group("name"))
        if key is None or key not in THRESHOLD_KEYS:
            return None
        current = state.stack(key)
        value = int(match.group("value"))
        if _RE_STATUS_GE.match(text):
            return current >= value
        if _RE_STATUS_LE.match(text):
            return current <= value
        return current == value

    match = _RE_PRESENT.match(text)
    if match:
        key = STATUS_NAMES.get(match.group("name"))
        if key is None:
            return None
        return state.stack(key) > 0

    return None


def _turn_params_match(spec: PItemSpec, state: PassiveState) -> bool:
    """回合类触发共用的参数（第 N 回合 / 剩余 N 回合 / 最终回合 / 每 N 回合）。"""
    if spec.turn is not None and state.turn != spec.turn:
        return False
    if spec.remaining_turns is not None and (
        state.turns_left is None or state.turns_left > spec.remaining_turns
    ):
        return False
    if spec.final_turn and not state.is_final_turn:
        return False
    return not (spec.every and (spec.every <= 0 or state.turn % spec.every))


def _trigger_matches(spec: PItemSpec, event: PassiveEvent, state: PassiveState) -> bool:
    """触发时机 + 触发参数是否对得上（不含 condition 求值）。"""
    trigger = spec.trigger
    if trigger == EXAM_START:
        # 训练/考试开始：一次性的开局事件，没有回合参数可对（条件仍会在
        # evaluate_condition 里按开局状态判断）。
        if event.kind != EXAM_START:
            return False
    elif trigger in (TURN_START, TURN_START_AFTER, TURN_END):
        if event.kind != trigger:
            return False
        if not _turn_params_match(spec, state):
            return False
    elif trigger == TURN_INTERVAL:
        if event.kind != TURN_INTERVAL or spec.every <= 0:
            return False
        if not _turn_params_match(spec, state):
            return False
    elif trigger in (CARD_PLAY, "card_played"):
        if event.kind != CARD_PLAY:
            return False
        if spec.card_filter and event.card_category != spec.card_filter:
            return False
    elif trigger == "card_play_interval":
        if event.kind != CARD_PLAY or spec.interval <= 0:
            return False
        if spec.card_filter and event.card_category != spec.card_filter:
            return False
        played = (
            event.cards_played_this_turn
            if spec.interval_scope != "exam"
            else event.cards_played_total
        )
        if played <= 0 or played % spec.interval:
            return False
    elif trigger == STATUS_GAIN:
        if event.kind != STATUS_GAIN:
            return False
        if not spec.status or spec.status != event.status:
            return False
        if spec.status_min and event.amount < spec.status_min:
            return False
    elif trigger == STATUS_GAIN_INTERVAL:
        # 「状态累计增加 N 次时」：用累计次数（含本次）判断有没有跨过 N 的整数倍。
        if event.kind != STATUS_GAIN or spec.interval <= 0:
            return False
        if spec.status and spec.status != event.status:
            return False
        total = event.status_total or state.status_count(event.status)
        before = total - event.amount
        if total // spec.interval <= before // spec.interval:
            return False
    elif trigger == STANCE_CHANGE:
        if event.kind != STANCE_CHANGE:
            return False
    elif trigger == STAMINA_REDUCE:
        if event.kind != STAMINA_REDUCE:
            return False
    else:
        return False

    if spec.lesson_filter:
        if spec.lesson_filter == "sp":
            if not state.is_sp:
                return False
        elif state.lesson_type != spec.lesson_filter:
            return False

    if spec.max_uses and state.uses is not None:
        key = spec.item_id or spec.name
        return state.uses.get(key, 0) < spec.max_uses
    return True


def apply_passive(
    items: Iterable[PItemSpec],
    event: PassiveEvent,
    state: PassiveState,
) -> PItemDelta:
    """把一次事件（训练/考试开始/回合开始/回合结束/出牌/状态增加）过一遍 P 道具，
    返回增量。

    纯函数：同样的 (items, event, state) 永远得到同样的结果；不抛异常
    （不支持的 effect_type / 认不出的条件一律跳过）。

    计数口径：``card_play_interval`` 的「每 N 张」用
    ``event.cards_played_this_turn`` / ``cards_played_total``，**要包含刚打出的这张**
    （打出第 2 张时传 2）；``turn`` / ``turns_left`` / ``is_final_turn`` 等留空表示
    "模拟器不知道"，依赖它们的道具不触发。
    """
    delta = PItemDelta()
    for spec in items:
        if not _trigger_matches(spec, event, state):
            continue
        if not spec.condition_known or not spec.trigger_known:
            # 条件/触发限定没解析出来：保守不触发（见 condition_known / trigger_known）
            continue
        if evaluate_condition(spec.condition, state) is not True:
            continue
        target = spec.target
        applied = False
        # B8：依赖换算「X 的 N% 数值变为 Y」——目标增量 = int(源层数 × N / 100)。
        if spec.depends_on and spec.percent > 0:
            amount = int(state.stack(spec.depends_on) * spec.percent / 100)
            if amount > 0:
                if target == "score":
                    delta.score += amount
                elif target and target not in ("stamina", "extra_plays"):
                    delta.add_stack(target, amount)
                applied = True
        # B8：「X 变为 0」——把对应层数清零（不算增量，但要记一次触发）。
        elif spec.zero_stack:
            delta.zero_stacks.append(spec.zero_stack)
            applied = True
        # B8：固定体力消耗/回复（value1 固定值 或 最大体力的 percent_max%）。
        elif target == "stamina":
            amount = spec.value
            if amount <= 0 and spec.percent_max > 0 and state.stamina_max > 0:
                amount = int(state.stamina_max * spec.percent_max / 100)
            if amount > 0:
                if spec.effect_type in STAMINA_LOSS_EFFECTS:
                    delta.stamina -= amount
                    delta.stamina_consumed += amount
                else:
                    delta.stamina += amount
                applied = True
        # ---- B9（2026-11-22）：持久倍率 / modifier 目标 -------------------
        elif target in MODIFIER_TARGETS:
            applied = _apply_modifier_target(spec, target, delta)
        elif not target or spec.value <= 0:
            continue  # 未实现的 effect_type：no-op
        else:
            if target == "score":
                delta.score += spec.value
            elif target == "extra_plays":
                delta.extra_plays += spec.value
            else:
                delta.add_stack(target, spec.value)
            applied = True
        if applied:
            delta.applied.append(spec.item_id or spec.name)
    return delta


def _apply_modifier_target(spec: PItemSpec, target: str, delta: PItemDelta) -> bool:
    """B9：把一条持久倍率/modifier 目标写进 ``delta``；返回是否真的触发。"""
    turns = spec.duration  # 0 = 永久
    if target in ("score_buff", "score_debuff"):
        if spec.value <= 0:
            return False
        entry = (spec.value, normalize_turns(turns))
        if target == "score_buff":
            delta.score_buffs.append(entry)
        else:
            delta.score_debuffs.append(entry)
        return True
    if target in PERCENT_TARGETS:  # review_multiple / enthusiasm_multiple / 增益倍率…
        if spec.value <= 0:
            return False
        delta.modifiers.append((target, spec.value, normalize_turns(turns)))
        return True
    if target == "review_times":
        if spec.value <= 0:
            return False
        delta.modifiers.append((target, spec.value, normalize_turns(turns)))
        return True
    if target == "half_cost_turns":
        amount = spec.duration or spec.value
        if amount <= 0:
            return False
        delta.half_cost_turns += amount
        return True
    if target == "double_cost_turns":
        amount = spec.duration or spec.value
        if amount <= 0:
            return False
        delta.double_cost_turns += amount
        return True
    if target == "cost_reduction":
        if spec.value <= 0:
            return False
        delta.cost_reduction += spec.value
        return True
    if target == "cost_increase":
        if spec.value <= 0:
            return False
        delta.cost_increase += spec.value
        return True
    if target == "perfect_condition_turns":
        amount = spec.duration or spec.value
        if amount <= 0:
            return False
        delta.perfect_condition_turns += amount
        return True
    if target == "poor_condition_turns":
        amount = spec.duration or spec.value
        if amount <= 0:
            return False
        delta.poor_condition_turns += amount
        return True
    if target == "extra_turn":
        delta.extra_turns += max(spec.value, 1)
        return True
    if target == "stance_preservation":
        delta.stances.append("preservation")
        return True
    if target == "stance_concentration":
        delta.stances.append("concentration")
        return True
    if target == "impression_reduce":
        # 「好印象减少」：层数减少（结算时夹到 ≥0）
        if spec.value <= 0:
            return False
        delta.add_stack("impression", -spec.value)
        return True
    return False


# ---- 数据加载 -------------------------------------------------------------


def _effect_value(effect: Mapping) -> int:
    """一条效果段的数值（``values`` 里取哪一列）。

    - 默认 ``value1``（分数/体力/层数类都是这个）；
    - ``ExamPlayableValueAdd``（技能卡使用数追加）的 N 在 ``count`` 列
      （46/50 条这样；个别同时带 value1/percent1 的仍以 count 为准）。
    """
    values = effect.get("values") or {}
    if effect.get("type") == "ExamPlayableValueAdd":
        return int(values.get("count") or values.get("value1") or 0)
    return int(values.get("value1") or 0)


def record_to_specs(record: Mapping) -> list[PItemSpec]:
    """把 p_items.json 的一条记录展开成若干条 PItemSpec（一个 effect 一条）。

    不支持的 effect_type 也保留（``implemented=False``），这样
    ``apply_passive`` 会走到 no-op 分支而不是漏掉数据。
    """
    params = record.get("trigger_params") or {}
    effects = record.get("effects") or []
    common = {
        "name": record.get("name", ""),
        "trigger": record.get("trigger", ""),
        "condition": record.get("condition", ""),
        "condition_known": bool(record.get("condition_known", True)),
        "trigger_known": bool(record.get("trigger_known", True)),
        "item_id": record.get("id", ""),
        "rarity": record.get("rarity", ""),
        "interval": int(params.get("interval") or 0),
        "interval_scope": params.get("interval_scope", "turn"),
        "status": params.get("status", ""),
        "status_min": int(params.get("status_min") or 0),
        "turn": params.get("turn"),
        "remaining_turns": params.get("remaining_turns"),
        "final_turn": bool(params.get("final_turn")),
        "card_filter": params.get("card_filter", ""),
        "lesson_filter": params.get("lesson_filter", ""),
        "every": int(params.get("every") or 0),
        "text": record.get("text_zh") or record.get("text_ja", ""),
    }
    if not effects:
        return [
            PItemSpec(
                effect_type="unknown",
                label="",
                value=0,
                max_uses=int(record.get("max_uses") or 0),
                **common,
            )
        ]
    specs = []
    for effect in effects:
        values = effect.get("values") or {}
        target_kind = effect_target(effect)
        value = effect_value(effect, target_kind)
        if target_kind in ("perfect_condition_turns", "poor_condition_turns"):
            # 这两类没有独立数值列，duration 才是回合数（value 也存一份便于实现判定）
            value = effect_value(effect, target_kind)
        specs.append(
            PItemSpec(
                effect_type=effect.get("type", "unknown"),
                label=effect.get("label", ""),
                value=value,
                target_kind=target_kind if target_kind in MODIFIER_TARGETS else "",
                duration=effect_duration(effect, target_kind),
                effect_text=str(effect.get("text") or ""),
                max_uses=int(effect.get("max_uses") or record.get("max_uses") or 0),
                depends_on=effect.get("depends_on", ""),
                percent=int(values.get("percent1") or 0) if effect.get("depends_on") else 0,
                percent_max=int(effect.get("percent_max") or 0),
                zero_stack=effect.get("zero_stack", ""),
                **common,
            )
        )
    return specs


def load_p_items(path: str | Path | None = None) -> list[PItemSpec]:
    """读 data/knowledge/p_items.json 并展开成 PItemSpec 列表。"""
    if path is None:
        path = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "p_items.json"
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    specs: list[PItemSpec] = []
    for record in payload.get("items", []):
        specs.extend(record_to_specs(record))
    return specs


def _probe_state() -> PassiveState:
    """一个"啥都知道"的假状态，只用来判断条件能不能解析（不关心真假）。"""
    return PassiveState(
        turn=1,
        turns_left=1,
        is_final_turn=False,
        stamina=50,
        stamina_max=100,
        lesson_type="vocal",
        is_sp=True,
        stacks={
            **{key: 1 for key in STATUS_NAMES.values()},
            "full_power_point_total": 1,
            "consumed_stamina_total": 1,
        },
        status_counts={key: 1 for key in STATUS_NAMES.values()},
    )


def summarize(items: Sequence[PItemSpec]) -> dict:
    """统计"实现了 / no-op"的分布（给报告和自检用）。"""
    implemented = [spec for spec in items if spec.implemented]
    noop = [spec for spec in items if not spec.implemented]
    noop_reasons: dict[str, int] = {}
    for spec in noop:
        if not spec.trigger_known:
            reason = "trigger_unknown"
        elif not spec.target:
            reason = "effect_type_unsupported"
        elif spec.trigger not in SUPPORTED_TRIGGERS:
            reason = "trigger_unsupported"
        else:
            reason = "no_value"
        noop_reasons[reason] = noop_reasons.get(reason, 0) + 1
    probe = _probe_state()
    unparsed = [spec for spec in implemented if evaluate_condition(spec.condition, probe) is None]
    return {
        "specs": len(items),
        "implemented": len(implemented),
        "noop": len(noop),
        # B7：条件未知（新增道具的新触发 id 没有中文触发句）——这些 spec 不会触发，
        # 单独计数，不混进 implemented/noop 口径里假装建模完成。
        "condition_unknown": sum(1 for spec in items if not spec.condition_known),
        # B8：触发限定未知（指定卡名 / 手牌指定卡张数）——同样单独计数、保守跳过。
        "trigger_unknown": sum(1 for spec in items if not spec.trigger_known),
        # B8：依赖换算 / 最大体力百分比 / 归零段 的实现计数（数据层语义）。
        "depends_on_specs": sum(1 for spec in items if spec.depends_on and spec.percent > 0),
        "percent_max_specs": sum(1 for spec in items if spec.percent_max > 0),
        "zero_stack_specs": sum(1 for spec in items if spec.zero_stack),
        "noop_reasons": noop_reasons,
        "implemented_with_unparsed_condition": len(unparsed),
        "implemented_effect_types": _count(spec.effect_type for spec in implemented),
        "implemented_triggers": _count(spec.trigger for spec in implemented),
        "noop_effect_types": _count(spec.effect_type for spec in noop),
        # B9：持久倍率 / modifier 类（score_buff / review_multiple / 费用修正 / …）
        "implemented_modifier_specs": sum(
            1 for spec in implemented if spec.target in MODIFIER_TARGETS
        ),
        "implemented_modifier_targets": _count(
            spec.target for spec in implemented if spec.target in MODIFIER_TARGETS
        ),
    }


def _count(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def unsupported_effect_types(items: Sequence[PItemSpec]) -> list[str]:
    """没实现的 effect_type（no-op），按出现次数降序。"""
    return list(summarize(items)["noop_effect_types"])


__all__ = [
    "CARD_PLAY",
    "DURATION_TARGETS",
    "EXAM_START",
    "EXTRA_PLAY_EFFECTS",
    "FLAG_TARGETS",
    "MODIFIER_TARGETS",
    "PERCENT_TARGETS",
    "PERMANENT_TURNS",
    "SCORE_BUFF_EFFECTS",
    "SCORE_DEBUFF_EFFECTS",
    "SCORE_EFFECTS",
    "STACK_EFFECTS",
    "STAMINA_EFFECTS",
    "STAMINA_GAIN_EFFECTS",
    "STAMINA_LOSS_EFFECTS",
    "STAMINA_REDUCE",
    "STANCE_CHANGE",
    "STATUS_GAIN",
    "STATUS_GAIN_INTERVAL",
    "STATUS_NAMES",
    "SUPPORTED_TRIGGERS",
    "THRESHOLD_KEYS",
    "TURN_END",
    "TURN_INTERVAL",
    "TURN_START",
    "TURN_START_AFTER",
    "PItemDelta",
    "PItemSpec",
    "PassiveEvent",
    "PassiveState",
    "TimedAmounts",
    "add_timed",
    "apply_passive",
    "classify_effect_target",
    "effect_duration",
    "effect_target",
    "effect_value",
    "evaluate_condition",
    "load_p_items",
    "normalize_turns",
    "record_to_specs",
    "summarize",
    "tick_timed",
    "timed_dict_add",
    "timed_dict_tick",
    "timed_dict_total",
    "total_timed",
    "unsupported_effect_types",
]
