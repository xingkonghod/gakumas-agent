"""P 道具（被动道具）建模：只做"事件 -> 增量"的纯函数，不碰 ``LessonSim`` 内部状态。

真机课程右上角的 P 道具是**被动**的：满足条件自动触发，不需要玩家动作，但会影响
分数 / 体力 / 层数 / 当回合可出牌次数。数据来自 ``data/knowledge/p_items.json``
（由 ``scripts/build_p_items.py`` 解析 ``ProduceItem.json`` + gakumasu-diff 的
``ProduceItem.yaml`` 生成）；真实对局带哪些 P 道具由
``gkagent.data.p_items_db`` 从 loadout 的 ``produce_item_ids`` 解析（T5③
2026-11-22 接入：gkbench 505 题模板共 83 个唯一 id，72 个在 2026-09-16 主数据
快照里，未知 id 显式上报、不猜）。

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
TURN_END = "turn_end"
CARD_PLAY = "card_play"  # 出牌：同时覆盖"技能卡使用时/使用后"两种触发
STATUS_GAIN = "status_gain"  # 直接效果让某个状态增加（好印象/集中/干劲…）
# 训练/考试开始时（e_trigger-exam_start_exam / start_exam_play 等）；
# 由 LessonSim 在开局（抽第一手牌前）结算一次。gkbench 起点体力偏差就是这类道具
# （如 pitem_02-3-293-0「训练开始时，最大体力的80%数值变为体力消耗」）。
EXAM_START = "exam_start"

# ---- 效果类型 -> 结算目标 --------------------------------------------------
# 语义确定的：分数 / 体力 / 层数（元气、好印象、集中、干劲、全力值）/
# 当回合额外可出牌次数（ExamPlayableValueAdd，与卡效果同口径）
SCORE_EFFECTS = frozenset({"ExamLesson"})
STAMINA_EFFECTS = frozenset({"ExamStaminaRecoverFix"})
EXTRA_PLAY_EFFECTS = frozenset({"ExamPlayableValueAdd"})
STACK_EFFECTS = {
    "ExamBlock": "vitality",
    "ExamReview": "impression",
    "ExamLessonBuff": "focus",
    "ExamCardPlayAggressive": "aggressive",
    "ExamFullPowerPoint": "full_power_point",
}

# ---- 已实现的触发时机 ------------------------------------------------------
SUPPORTED_TRIGGERS = frozenset(
    {TURN_START, TURN_END, CARD_PLAY, "card_played", "card_play_interval", STATUS_GAIN, EXAM_START}
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
    item_id: str = ""
    rarity: str = ""
    label: str = ""  # effect_type 的中文名（打分/元气/…）
    interval: int = 0  # card_play_interval：每 N 次
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

    @property
    def target(self) -> str:
        """这条效果结算到哪儿："score" / "stamina" / "extra_plays" / 层数 key / ""（不支持）。"""
        if self.effect_type in SCORE_EFFECTS:
            return "score"
        if self.effect_type in STAMINA_EFFECTS:
            return "stamina"
        if self.effect_type in EXTRA_PLAY_EFFECTS:
            return "extra_plays"
        return STACK_EFFECTS.get(self.effect_type, "")

    @property
    def implemented(self) -> bool:
        return self.trigger in SUPPORTED_TRIGGERS and bool(self.target) and self.value > 0


@dataclass(frozen=True)
class PassiveEvent:
    """触发事件。``kind`` 只用 TURN_START / TURN_END / CARD_PLAY / STATUS_GAIN / EXAM_START。"""

    kind: str
    card_category: str = ""  # 打出的卡类别：ActiveSkill / MentalSkill / IdolUnique
    cards_played_this_turn: int = 0
    cards_played_total: int = 0
    status: str = ""  # status_gain：增加的是哪个状态（stacks 的 key）
    amount: int = 0  # status_gain：增加了多少层


@dataclass(frozen=True)
class PassiveState:
    """模拟器侧传进来的简单状态（只读）。

    ``turns_left`` / ``is_final_turn`` / ``lesson_type`` / ``uses`` 等字段留空表示
    "模拟器不知道"，此时依赖这些信息的道具**不触发**（保守）。
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
    uses: Mapping[str, int] | None = None  # item_id -> 已经触发次数

    def stack(self, key: str) -> int:
        return int(self.stacks.get(key, 0))


@dataclass
class PItemDelta:
    """一次事件里所有 P 道具带来的增量（纯数据）。"""

    score: int = 0
    stamina: int = 0
    extra_plays: int = 0  # 当回合额外可出牌次数（ExamPlayableValueAdd）
    stacks: dict[str, int] = field(default_factory=dict)
    applied: list[str] = field(default_factory=list)  # 触发了哪些道具（item_id 或 name）

    def add_stack(self, key: str, amount: int) -> None:
        if amount:
            self.stacks[key] = self.stacks.get(key, 0) + amount

    def is_zero(self) -> bool:
        return not (self.score or self.stamina or self.extra_plays or any(self.stacks.values()))

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "stamina": self.stamina,
            "extra_plays": self.extra_plays,
            "stacks": dict(self.stacks),
        }

    def __iadd__(self, other: PItemDelta) -> Self:
        self.score += other.score
        self.stamina += other.stamina
        self.extra_plays += other.extra_plays
        for key, amount in other.stacks.items():
            self.add_stack(key, amount)
        self.applied.extend(other.applied)
        return self

    def __add__(self, other: PItemDelta) -> PItemDelta:
        merged = PItemDelta(
            score=self.score,
            stamina=self.stamina,
            extra_plays=self.extra_plays,
            stacks=dict(self.stacks),
            applied=list(self.applied),
        )
        merged += other
        return merged


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


def _trigger_matches(spec: PItemSpec, event: PassiveEvent, state: PassiveState) -> bool:
    """触发时机 + 触发参数是否对得上（不含 condition 求值）。"""
    trigger = spec.trigger
    if trigger == EXAM_START:
        # 训练/考试开始：一次性的开局事件，没有回合参数可对（条件仍会在
        # evaluate_condition 里按开局状态判断）。
        if event.kind != EXAM_START:
            return False
    elif trigger in (TURN_START, TURN_END):
        if event.kind != trigger:
            return False
        if spec.turn is not None and state.turn != spec.turn:
            return False
        if spec.remaining_turns is not None and (
            state.turns_left is None or state.turns_left > spec.remaining_turns
        ):
            return False
        if spec.final_turn and not state.is_final_turn:
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
        played = event.cards_played_this_turn if spec.interval_scope != "exam" else event.cards_played_total
        if played <= 0 or played % spec.interval:
            return False
    elif trigger == STATUS_GAIN:
        if event.kind != STATUS_GAIN:
            return False
        if not spec.status or spec.status != event.status:
            return False
        if spec.status_min and event.amount < spec.status_min:
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
        if evaluate_condition(spec.condition, state) is not True:
            continue
        target = spec.target
        if not target or spec.value <= 0:
            continue  # 未实现的 effect_type：no-op
        if target == "score":
            delta.score += spec.value
        elif target == "stamina":
            delta.stamina += spec.value
        elif target == "extra_plays":
            delta.extra_plays += spec.value
        else:
            delta.add_stack(target, spec.value)
        delta.applied.append(spec.item_id or spec.name)
    return delta


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
        "text": record.get("text_zh", ""),
    }
    if not effects:
        return [PItemSpec(effect_type="unknown", label="", value=0, max_uses=int(record.get("max_uses") or 0), **common)]
    specs = []
    for effect in effects:
        specs.append(
            PItemSpec(
                effect_type=effect.get("type", "unknown"),
                label=effect.get("label", ""),
                value=_effect_value(effect),
                max_uses=int(effect.get("max_uses") or record.get("max_uses") or 0),
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
        stacks={key: 1 for key in STATUS_NAMES.values()},
    )


def summarize(items: Sequence[PItemSpec]) -> dict:
    """统计"实现了 / no-op"的分布（给报告和自检用）。"""
    implemented = [spec for spec in items if spec.implemented]
    noop = [spec for spec in items if not spec.implemented]
    noop_reasons: dict[str, int] = {}
    for spec in noop:
        if not spec.target:
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
        "noop_reasons": noop_reasons,
        "implemented_with_unparsed_condition": len(unparsed),
        "implemented_effect_types": _count(spec.effect_type for spec in implemented),
        "implemented_triggers": _count(spec.trigger for spec in implemented),
        "noop_effect_types": _count(spec.effect_type for spec in noop),
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
    "EXAM_START",
    "EXTRA_PLAY_EFFECTS",
    "SCORE_EFFECTS",
    "STACK_EFFECTS",
    "STAMINA_EFFECTS",
    "STATUS_GAIN",
    "STATUS_NAMES",
    "SUPPORTED_TRIGGERS",
    "THRESHOLD_KEYS",
    "TURN_END",
    "TURN_START",
    "PItemDelta",
    "PItemSpec",
    "PassiveEvent",
    "PassiveState",
    "apply_passive",
    "evaluate_condition",
    "load_p_items",
    "record_to_specs",
    "summarize",
    "unsupported_effect_types",
]
