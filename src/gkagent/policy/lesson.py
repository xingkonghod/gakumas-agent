"""课程/试镜出牌策略：用界面上的分数预览 + 体力，做"像人一样"的取舍。

规则（按优先级）：

1. 只用分数预览判断收益——那是游戏自己算好的值，含好调/集中/属性倍率；
2. 按 ``分数 ÷ 体力`` 选牌；0 费牌按 1 费算，避免被"1 分 0 费"骗；
3. 每个回合的体力预算 ≈ ``体力 / 剩余回合``，先给后面的回合留饭；
4. 铺 buff 的顺序**按方案（プラン）**：感性 好调→集中、理性 好印象→やる気、
   非凡 温存优先（最后 1-2 回合留给全力/大分牌），数据在
   ``data/knowledge/plans.json``；
5. 剩余回合 ≥ ``early_buff_turns`` 且本回合还没上过 buff 时，先铺一张便宜的
   方案优先 buff（后续牌吃倍率）；
6. 目标函数按 **PERFECT** 而不是 CLEAR：``LessonState.gauge`` 是屏幕 CLEAR
   基准，PERFECT 线 = gauge × 2；没到线时按"总分最大"补缺口、不因低于
   ``min_gain`` 而 SKIP（真机只打 CLEAR 只拿半档属性）；
7. 没有正收益的牌就 **SKIP 结束回合**，不要瞎点卡面空转；
8. 已经到 PERFECT 线、剩下的牌又不值几分时，也别再烧体力。

数值参数全部外置到 ``data/knowledge/policy.json``：模拟器扫出来的参数写回文件后，
真机下一次构造 ``LessonPolicy`` 就生效；``describe()`` 返回当前生效参数，便于日志对比。
当前方案读 ``policy.json`` 的 ``produce.plan``（缺省/未知一律退回 ``sense``）。

策略只产出"点哪里"，不负责点击的时序（两段式确认由调用方处理）。
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from gkagent.data.buffs import BuffLibrary
from gkagent.data.card_effects import estimate_value
from gkagent.data.plans import (
    DEFAULT_PLAN,
    VALID_PLANS,
    Plan,
    PlanLibrary,
    default_plan_library,
    normalize_plan,
)
from gkagent.vision.lesson import LessonCard, LessonState, card_value

# 默认参数文件：真机与模拟器共用。模拟器也可以先写 policy_sim.json 再通过 params_path 传进来。
DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "policy.json"

# 字符串型参数的合法取值；文件里写错就回退默认值，不让策略崩。
_ALLOWED_VALUES: dict[str, frozenset[str]] = {
    # 2026-11-21 用户规则：读不到分数不是跳过理由（未知≈OCR 问题，不是 0 分）。
    # 旧的 "skip" 取值废弃：即使配置写 skip 也按 cheapest 处理。
    "unknown_score_fallback": frozenset({"cheapest"}),
    "plan": frozenset(VALID_PLANS),
    "engine": frozenset({"rules", "expectimax", "uinet", "beam"}),
}


class RuleFallbackBlocked(RuntimeError):
    """搜索引擎无法决策时禁止静默回退 rules（用户规则，2026-11-21）。

    真机入口（``scripts/auto_produce.py``）捕获后写 ``[engine][BLOCKED]`` 并中止
    本局：宁可停下暴露 OCR/卡表问题，也不许 bot 悄悄改用 rules 引擎打。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class LessonAction:
    kind: str  # card / skip / wait
    index: int | None = None
    point: tuple[int, int] | None = None
    reason: str = ""
    expected: float = 0.0
    card: LessonCard | None = None


class LessonPolicy:
    """有状态的出牌策略：跟踪"本回合打了几张、有没有上过 buff"。

    参数优先级（低 → 高）：``DEFAULT_PARAMS`` → ``params_path``/默认
    ``data/knowledge/policy.json`` → ``params`` → 显式关键字参数。
    文件缺失、JSON 损坏、字段类型不对时都只用默认值，绝不抛异常。
    """

    DEFAULT_PARAMS: ClassVar[dict[str, Any]] = {
        # 方案（プラン）：sense=感性 / logic=理性 / anomaly=非凡；未知值退回 sense
        "plan": DEFAULT_PLAN,
        # 保留给后续回合的体力下限：每剩 1 回合至少留这么多
        "reserve_per_turn": 2.0,
        # 分数预览 ≤ 这个值（且不是 buff）被视为"没用"
        "negligible": 0.5,
        # 低于这个期望收益的牌不打（最后一回合同样生效）
        "min_gain": 1.0,
        # 是否先铺 buff（好调/集中等）
        "buff_first": True,
        # 前 N 个回合（剩余回合数 ≥ N）buff 牌优先于分数牌：层数类 buff 会滚雪球，
        # 越早越值钱（2026-11-15 用户打法：先攒倍率，再打分数）
        "buff_early_turns": 3,
        # 铺 buff 的费用上限 = 本回合预算 × ratio，且不低于 buff_min_budget
        "buff_max_cost_ratio": 1.0,
        "buff_min_budget": 2.0,
        # 场上已有分数 ≥ guard × buff 等效分时，先打分数牌而不是 buff
        # （8 → 12：让 buff 更强势；只有明显更高才压过 buff）
        "buff_score_guard": 12.0,
        # buff 文本估不出分时的兜底等效分
        "buff_value_fallback": 6.0,
        # 最后一回合按"总分最大"而不是"性价比"选牌
        "last_turn_max_total": True,
        # 分数完全没读到时：cheapest=打最便宜的保成长，skip=跳过
        "unknown_score_fallback": "cheapest",
        # 分数是卡表兜底估出来的（屏幕宝石没读到）时按这个系数轻微降权：
        # 不把它当 0 分卡跳过，但也别完全信任估值。
        "estimated_score_weight": 0.9,
        # PERFECT 线 = 屏幕 CLEAR 基准（LessonState.gauge）× 该倍率。
        # 目标函数按 PERFECT 而不是 CLEAR：没到线就不收手（真机 CLEAR 只拿半档属性）。
        "perfect_target_multiplier": 2.0,
        # 出牌引擎：rules=固定优先级规则（默认，行为不变）；expectimax=回合内搜索；
        # uinet=GKMSUINet 神经网络（ONNX，UIObs v1）；beam=跨回合 beam 规划
        # （需要 ExamDrawPlan 给 known_draw 才有意义，没有全知数据时改用回合内搜索）。
        # 用户规则（2026-11-21）：**bot 不许回退 rules**——搜索异常/状态不读全时
        # 只会 wait 重读或抛 RuleFallbackBlocked，绝不静默改用规则引擎。
        "engine": "rules",
        # expectimax 的 anytime 预算与 V_leaf σ；规则模式不读。
        "expectimax_budget_ms": 800.0,
        "expectimax_sigma": 80.0,
        # beam（跨回合规划）：宽度 + 单次决策预算（本地评测均值 ~100ms/回合）。
        "beam_width": 4,
        "beam_deadline_ms": 250.0,
        # B2 学习型叶子（默认 None = 保持历史行为）。设置后 expectimax/beam 的叶子
        # 变成 EnsembleLeafValue(analytic, learned, weight)；T2 真机 A/B 再决定打开。
        "leaf_model": None,
        "leaf_model_weight": 0.5,
    }

    def __init__(
        self,
        *,
        buffs: BuffLibrary | None = None,
        plans: PlanLibrary | None = None,
        plan: str | None = None,
        buff_first: bool | None = None,
        min_gain: float | None = None,
        params: dict | None = None,
        params_path: str | Path | None = None,
        engine: str | None = None,
        draw_plan=None,
        allow_rule_fallback: bool = False,
    ) -> None:
        self.buffs = buffs or BuffLibrary.load()
        self.plans = plans or default_plan_library()
        self.params = self._resolve_params(params, params_path)
        # 显式 plan 参数优先级最高；未知值按需求退回 sense，不抛异常。
        if plan is not None:
            self.params["plan"] = normalize_plan(plan) or DEFAULT_PLAN
        # 用户规则（2026-11-21）：**bot 不许回退 rules**。显式 engine 写错时大声
        # 报错（否则真机 bot 会静默变成 rules 在打）；只有调试/旧评测脚本才允许
        # 显式打开 allow_rule_fallback。
        self.allow_rule_fallback = bool(allow_rule_fallback)
        if engine is not None:
            normalized = str(engine).strip().lower()
            if normalized not in _ALLOWED_VALUES["engine"]:
                raise ValueError(
                    f"未知出牌引擎 {engine!r}（可选："
                    f"{', '.join(sorted(_ALLOWED_VALUES['engine']))}）"
                    "；用户规则禁止静默回退 rules"
                )
            self.params["engine"] = normalized
        # 兼容旧的显式关键字参数（优先级最高）
        if buff_first is not None:
            self.params["buff_first"] = bool(buff_first)
        if min_gain is not None:
            parsed = _as_float(min_gain)
            if parsed is not None:
                self.params["min_gain"] = parsed
        self._last_turns: int | None = None
        self._plays_this_turn = 0
        self._buff_played_this_turn = False
        # 读不到回合数时 `_sync_turn` 无法判断新回合；用「上一手是 SKIP」和
        # 「手牌整体换了一批」两个信号兜底重置，避免计数器卡死导致满体力一直 SKIP。
        self._await_turn_reset = False
        self._last_hand_sig: tuple[str, ...] = ()
        # 考试牌序计划（可空）：给了就把 known_draw / discard_order / 重洗钩子
        # 喂进搜索（见 gkagent.sim.exam_plan.ExamDrawPlan）。
        self.draw_plan = None
        self._plan_turn_key: tuple[int | None, int | None] | None = None
        self._plan_hand: list[str] = []
        self._plan_played: list[str] = []
        self._plan_reverse: dict[tuple[str, int], str] = {}
        # 决策可观测性（真机日志用）：最近一次决策用的引擎 / 搜索回退原因
        self.last_decision: dict[str, Any] = {}
        self.last_fallback_reason = ""
        # 最近一次搜索用的考试属性倍率（屏幕读数；None = 非考试/没读到）
        self._last_coefficient: float | None = None
        if draw_plan is not None:
            self.attach_draw_plan(draw_plan)

    # ------------------------------------------------------------------ 参数
    @property
    def plan(self) -> str:
        """当前方案 key（``sense`` / ``logic`` / ``anomaly``）。"""
        return normalize_plan(self.params.get("plan")) or DEFAULT_PLAN

    @property
    def plan_config(self) -> Plan:
        """当前方案的完整配置（buff 优先级 / 前期回合数 / 是否先铺后打）。"""
        return self.plans.get(self.plan)

    @property
    def buff_priority(self) -> tuple[str, ...]:
        """按方案决定的 buff 出牌顺序。"""
        return self.plan_config.buff_priority

    @property
    def early_buff_turns(self) -> int:
        """前 N 个回合（剩余回合数 ≥ N）buff 优先，按方案取值。"""
        return self.plan_config.early_buff_turns

    @property
    def buff_first(self) -> bool:
        return bool(self.params["buff_first"])

    @buff_first.setter
    def buff_first(self, value: bool) -> None:
        self.params["buff_first"] = bool(value)

    @property
    def engine(self) -> str:
        """当前出牌引擎：``rules``（默认）/ ``expectimax`` / ``uinet`` / ``beam``。"""
        return str(self.params.get("engine") or "rules")

    @property
    def forbids_rule_fallback(self) -> bool:
        """搜索引擎是否禁止回退 rules（用户规则：bot 不许回退 rules）。"""
        return self.engine != "rules" and not self.allow_rule_fallback

    def attach_draw_plan(self, plan) -> None:
        """挂上考试牌序计划（``gkagent.sim.exam_plan.ExamDrawPlan`` 或 None）。

        计划激活时，``expectimax`` / ``beam`` 会把 ``known_draw`` / ``discard_order``
        与确定性重洗钩子并进搜索；计划没激活（没采到数据 / 核对失败）时行为不变。
        """
        self.draw_plan = plan
        self._plan_turn_key = None
        self._plan_hand = []
        self._plan_played = []
        if plan is not None:
            start = getattr(plan, "start", None)
            if callable(start):
                try:
                    start()
                except Exception as exc:  # noqa: BLE001 - 计划起不来就当没有
                    logging.getLogger(__name__).warning("考试牌序计划启动失败：%s", exc)
                    self.draw_plan = None

    @property
    def min_gain(self) -> float:
        return float(self.params["min_gain"])

    @min_gain.setter
    def min_gain(self, value: float) -> None:
        parsed = _as_float(value)
        if parsed is not None:
            self.params["min_gain"] = parsed

    def describe(self) -> dict[str, Any]:
        """当前生效的规则参数（拷贝，供日志/评测对比）。"""
        return dict(self.params)

    def describe_plan(self) -> dict[str, Any]:
        """当前方案的配置（方案名 / buff 顺序 / early_buff_turns / notes）。"""
        return self.plan_config.as_dict()

    @classmethod
    def _resolve_params(
        cls, params: dict | None, params_path: str | Path | None
    ) -> dict[str, Any]:
        values = dict(cls.DEFAULT_PARAMS)
        # 不传 params_path 时尝试默认文件；显式传路径则只认那个路径（缺失=默认值）。
        path = Path(params_path) if params_path is not None else DEFAULT_POLICY_PATH
        raw = cls._read_json(path)
        if raw is not None:
            values.update(cls._coerce(raw, values))
            # produce.plan 是唯一从 produce 段读进 lesson 策略的字段（默认 sense）。
            file_plan = cls._read_plan(raw)
            if file_plan is not None:
                values["plan"] = file_plan
        if params:
            values.update(cls._coerce(params, values))
            if "plan" in params:
                values["plan"] = normalize_plan(params["plan"]) or DEFAULT_PLAN
        return values

    @staticmethod
    def _read_json(path: Path) -> object | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _read_plan(raw: object) -> str | None:
        """从 policy.json 的 ``produce.plan``（兼容顶层 ``plan``）读方案。"""
        if not isinstance(raw, dict):
            return None
        produce = raw.get("produce")
        candidate = produce.get("plan") if isinstance(produce, dict) else None
        if candidate is None:
            candidate = raw.get("plan")
        return normalize_plan(candidate)

    @classmethod
    def _coerce(cls, raw: object, base: dict[str, Any]) -> dict[str, Any]:
        """只采纳类型正确的已知字段；未知字段/坏值忽略。"""
        source = cls._lesson_section(raw)
        out: dict[str, Any] = {}
        for key, default in base.items():
            if key not in source:
                continue
            value = source[key]
            if isinstance(default, bool):
                parsed_bool = _as_bool(value)
                if parsed_bool is not None:
                    out[key] = parsed_bool
            elif isinstance(default, float):
                parsed_float = _as_float(value)
                if parsed_float is not None:
                    out[key] = parsed_float
            elif isinstance(default, int):
                parsed_float = _as_float(value)
                if parsed_float is not None and parsed_float >= 0:
                    out[key] = int(parsed_float)
            elif isinstance(default, str):
                allowed = _ALLOWED_VALUES.get(key, frozenset())
                if isinstance(value, str) and value in allowed:
                    out[key] = value
            elif default is None and (value is None or (isinstance(value, str) and value)):
                # 可选字段（默认 None）：接受 None 或非空字符串（如 B2 leaf_model 路径）。
                out[key] = value
        return out

    @staticmethod
    def _lesson_section(raw: object) -> dict[str, Any]:
        """兼容 ``{"lesson": {...}}`` 整份文件和扁平 dict 两种写法。"""
        if not isinstance(raw, dict):
            return {}
        lesson = raw.get("lesson")
        if isinstance(lesson, dict):
            return lesson
        return raw

    # ------------------------------------------------------------------ 公共
    def reset(self) -> None:
        self._last_turns = None
        self._plays_this_turn = 0
        self._buff_played_this_turn = False

    def reset_turn(self) -> None:
        """SKIP 之后调用：本回合的计数清零（回合号要等下一帧再同步）。"""
        self._plays_this_turn = 0
        self._buff_played_this_turn = False

    def note_play(self, card: LessonCard | None = None) -> None:
        """调用方真正点出去之后告知，用于回合内计数。"""
        if card is None:
            # SKIP 结束本回合：下一帧决策前重置出牌计数
            self._await_turn_reset = True
            return
        self._plays_this_turn += 1
        if card.buff:
            self._buff_played_this_turn = True
        plan = getattr(self, "draw_plan", None)
        if plan is not None and getattr(plan, "active", False):
            name = card.name or ""
            if name:
                self._plan_played.append(name)
                try:
                    plan.note_play(name)
                except Exception as exc:  # noqa: BLE001 - 台账坏了不能影响出牌
                    logging.getLogger(__name__).warning("draw_plan.note_play 失败：%s", exc)

    def decide(self, state: LessonState, *, allow_skip: bool = True) -> LessonAction:
        """按 ``engine`` 决策；**搜索引擎绝不回退 rules**（用户规则，2026-11-21）。

        - ``engine="rules"``：显式规则引擎（A/B 对照 / 离线脚本），行为与旧版一致；
        - ``expectimax`` / ``beam`` / ``uinet``：搜索/规划/神经网络决策。搜索建议
          SKIP 但还有付得起的牌时，按**搜索结果自己的动作价值**硬打一张（不是规则）；
          状态没读全时返回 ``wait`` 等下一帧重读；搜索异常/结果失配抛
          :class:`RuleFallbackBlocked`，由真机入口记 ``[engine][BLOCKED]`` 并中止
          本局——去修 OCR/卡表，不许用 rules 兜底。只有调试/旧评测显式传
          ``allow_rule_fallback=True`` 时才保留旧回退。

        挂了 ``draw_plan``（``ExamDrawPlan``）时先把当前手牌喂给计划：新回合做一次
        牌序核对，核对通过后搜索用 ``known_draw`` / ``discard_order``（完全信息）。

        决策可观测性：每次返回前把「实际用哪个引擎、为什么没产出动作」记到
        ``last_decision`` / ``last_fallback_reason``，真机日志用 :meth:`decision_note`
        打出来。
        """
        self.last_fallback_reason = ""
        self._last_coefficient = None
        self._sync_turn(state.turns_left)
        self._sync_exam_plan(state)
        if self.engine == "rules":
            action = self._decide_rules(state, allow_skip=allow_skip)
        else:
            action = self._decide_search(state, allow_skip=allow_skip)
        # 用户规则：只有"所有牌都付不起（真没体力）"才允许 SKIP。搜索引擎若仍返回
        # SKIP 而手里有付得起的牌（正常已被 _decide_search 拦截），说明决策链路有
        # bug——宁可暴露也不许悄悄执行跳过。
        if action.kind == "skip" and state.cards:
            stamina = state.stamina
            affordable = [
                card
                for card in state.cards
                if stamina is None or card.cost is None or card.cost <= stamina
            ]
            if affordable:
                raise RuleFallbackBlocked(
                    "SKIP 被拦截：还有付得起的牌，但没有引擎给出可打的牌"
                )
        self.last_decision = {
            "engine": self.engine,
            "kind": action.kind,
            "reason": action.reason,
            "fallback": self.last_fallback_reason,
        }
        if self._last_coefficient is not None:
            # 考试属性倍率（屏幕「舞蹈 207%」= 2.07）：真机日志能看出搜索用的倍率
            self.last_decision["attr_multiplier"] = self._last_coefficient
        return action

    def _decide_search(self, state: LessonState, *, allow_skip: bool) -> LessonAction:
        """搜索引擎决策；失败时不回退 rules（见 :meth:`decide`）。"""
        if self.engine == "expectimax":
            action = self._try_expectimax(state, allow_skip=allow_skip)
        elif self.engine == "beam":
            action = self._try_beam(state, allow_skip=allow_skip)
        else:
            action = self._try_uinet(state, allow_skip=allow_skip)
        if action is not None:
            return action
        reason = self.last_fallback_reason or "搜索未产出动作"
        if self.allow_rule_fallback:
            # 仅调试/旧评测：显式打开才允许旧行为（真机入口永远不传 True）。
            self.last_fallback_reason = f"{reason}（调试开关 allow_rule_fallback）"
            logging.getLogger(__name__).warning(
                "allow_rule_fallback=True，退回 rules：%s", reason
            )
            return self._decide_rules(state, allow_skip=allow_skip)
        raise RuleFallbackBlocked(f"engine={self.engine} 无法决策：{reason}")

    def _wait_action(self, reason: str) -> LessonAction:
        """状态没读全/搜索超时：等下一帧重读，绝不改成规则决策。"""
        self.last_fallback_reason = f"等待重读：{reason}（不回退 rules）"
        return LessonAction("wait", reason=f"{reason}：等下一帧重读（禁止回退 rules）")

    def decision_note(self) -> str:
        """最近一次决策的紧凑说明（真机日志用）：``eng=expectimax attr=2.07 fallback=…``。"""
        info = self.last_decision or {}
        engine = str(info.get("engine") or self.engine)
        fallback = str(info.get("fallback") or "")
        note = f"eng={engine}"
        coefficient = info.get("attr_multiplier")
        if coefficient is not None:
            note += f" attr={float(coefficient):.2f}"
        return note + (f" fallback={fallback}" if fallback else "")

    def _decide_rules(
        self, state: LessonState, *, allow_skip: bool = True
    ) -> LessonAction:
        """固定优先级规则（旧版 ``decide`` 的实现，行为不变）。

        考试模式（``allow_skip=False``）绝不返回 SKIP：没有付得起的牌也比白送回合好，
        退回 `"硬打一张最值的"`/`"等下一帧"`。
        """
        self._sync_turn(state.turns_left)
        perfect_target = self._perfect_target(state)
        below_perfect = (
            perfect_target is not None
            and state.score is not None
            and state.score < perfect_target
        )
        cards = [card for card in state.cards if card.name or card.score is not None]
        if not cards:
            return LessonAction("wait", reason="没读到手牌")

        stamina = state.stamina
        turns = state.turns_left
        affordable = [
            card
            for card in cards
            if stamina is None or card.cost is None or card.cost <= stamina
        ]
        if not affordable:
            if not allow_skip:
                # 考试：没有付得起的牌也不 SKIP，交给调用方兜底换牌/等下一帧
                return LessonAction(
                    "wait", reason=f"考试模式：没有付得起的牌（体力 {stamina}），不 SKIP"
                )
            return LessonAction(
                "skip",
                point=state.skip_point,
                reason=f"没有付得起的牌（体力 {stamina}）",
            )

        values = {card.index: self._value(card, turns) for card in affordable}
        budget = self._budget(stamina, turns)

        # 0) 游戏高亮（金框/推荐）无条件优先：机制上就是提示「先把倍率铺起来」
        highlighted = [card for card in affordable if card.highlight]
        if highlighted:
            pick = max(
                highlighted,
                key=lambda card: (
                    card.buff,
                    values.get(card.index, 0.0),
                    -(card.cost if card.cost is not None else 9),
                    -card.index,
                ),
            )
            return LessonAction(
                "card",
                index=pick.index,
                point=pick.point,
                card=pick,
                expected=values.get(pick.index, 0.0),
                reason=f"游戏高亮优先：{pick.name or '卡'}",
            )

        # 1) 先铺 buff
        buff_action = self._maybe_buff(state, affordable, values, budget)
        if buff_action is not None:
            return buff_action

        # 2) 性价比最高的牌（没到 PERFECT 线时改为"总分最大"，先把缺口补上）
        best = self._best_score_card(
            affordable, values, budget, turns, prefer_total=below_perfect
        )
        if best is None:
            # 用户规则（2026-11-21）：**只有真没体力/真没付得起的牌才允许 SKIP**。
            # 读不到分数、分数太低都不是跳过理由——未知分只说明 OCR 有问题，
            # 跳课 = 白丢一回合属性（真机 ep-finish7 连续 lesson-skip 就是这么来的）。
            fallback = self._cheapest_unknown(affordable)
            if fallback is not None:
                return LessonAction(
                    "card",
                    index=fallback.index,
                    point=fallback.point,
                    card=fallback,
                    expected=0.0,
                    reason=f"分数没读到/太低，禁止跳过——硬打「{fallback.name or '卡'}」",
                )
            return self._must_play(
                affordable, values, "禁止因读不到价值跳过，硬打一张"
            )

        card, value = best
        efficiency = value / max(card.cost or 3, 1)
        estimate_note = "（卡表估）" if card.score_estimated else ""
        return LessonAction(
            "card",
            index=card.index,
            point=card.point,
            card=card,
            expected=value,
            reason=(
                f"{card.name or '卡'} 分数{int(value)}{estimate_note} / "
                f"体力{card.cost if card.cost is not None else '?'}"
                f"（性价比 {efficiency:.1f}，预算 {budget:.0f}）"
            ),
        )

    # ------------------------------------------------------------------ 内部
    def _sync_exam_plan(self, state: LessonState) -> None:
        """把当前手牌喂给 ``ExamDrawPlan``：新回合核对 + 回合内抽牌跟踪。"""
        plan = getattr(self, "draw_plan", None)
        if plan is None or not getattr(plan, "active", False):
            return
        names = [card.name for card in state.cards if card.name]
        if not names:
            return
        key = (state.turns_left, state.total_turns)
        try:
            if key != self._plan_turn_key:
                if self._plan_hand:
                    plan.end_turn(_remove_played(self._plan_hand, self._plan_played))
                self._plan_turn_key = key
                self._plan_hand = list(names)
                self._plan_played = []
                from gkagent.sim.exam_plan import PARAMETER_TYPES

                parameter = PARAMETER_TYPES.get(state.attribute or "")
                plan.begin_turn(list(names), parameter)
            elif names != self._plan_hand:
                plan.observe_hand(list(names))
                self._plan_hand = list(names)
        except Exception as exc:  # noqa: BLE001 - 牌序计划坏了不能影响出牌
            logging.getLogger(__name__).warning("考试牌序计划同步失败，已停用：%s", exc)
            self.draw_plan = None
            self._plan_turn_key = None

    def _plan_card_specs(self, cards):
        """牌序里的 ``(id, upgrade)`` → 搜索用 ``CardSpec``（借卡表补卡面数值）。"""
        from gkagent.sim.lesson import CardSpec
        from gkagent.sim.play_choice import specs_from_hand

        table = self._card_table()
        lesson_cards = [
            LessonCard(
                index=index,
                box=(0, 0, 0, 0),
                point=(0, 0),
                name=table.name_of(card[0], card[1]) or card[0],
            )
            for index, card in enumerate(cards)
        ]
        play_cards = specs_from_hand(lesson_cards, table=table)
        if len(play_cards) != len(cards):
            return [CardSpec(name=card[0], cost=1, score=10) for card in cards]
        return [item.spec for item in play_cards]

    def _search_state(self, state: LessonState):
        """``LessonState`` → ``(ExpectState, play_cards, reshuffle)``；不可用返回 None。

        只映射读屏能确认的字段（手牌/体力/剩余回合/分数/CLEAR 基准）；卡表能补费用
        与效果。挂了激活的 ``draw_plan`` 时把 known_draw / discard_order / 确定性
        重洗钩子一并喂进搜索（完全信息搜索）。
        """
        from gkagent.sim.expectimax import ExpectState
        from gkagent.sim.play_choice import specs_from_hand

        if not state.cards:
            self.last_fallback_reason = "手牌为空"
            return None
        stamina = state.stamina
        if stamina is None:
            self.last_fallback_reason = "体力未知"
            return None
        turns_left = state.turns_left
        if turns_left is None or turns_left <= 0:
            self.last_fallback_reason = "剩余回合未知"
            return None
        gauge = state.gauge
        # 用户要求：禁用规则回退。读不到 CLEAR 基准时用经验默认值（250），
        # 只保留"手牌为空 / 体力未知 / 回合未知"这类无法决策的硬性回退。
        if gauge is None or gauge <= 0:
            gauge = int(self.params.get("default_clear_gauge") or 250)
        play_cards = specs_from_hand(state.cards, table=self._card_table())
        if not play_cards:
            self.last_fallback_reason = "手牌无法转成卡表规格"
            return None
        perfect = state.perfect if (state.perfect or 0) > 0 else None
        if perfect is None:
            # 由过关线反推满分线：档位表（追い込み 90→360、165→600）优先，缺省 2×。
            from gkagent.sim.hajime_data import perfect_target

            perfect = int(perfect_target(int(gauge)))
        kwargs: dict = {}
        reshuffle = None
        plan = getattr(self, "draw_plan", None)
        if plan is not None and getattr(plan, "active", False):
            try:
                kwargs = plan.expect_state_kwargs(to_specs=self._plan_card_specs)
                if kwargs:
                    hook = getattr(plan, "reshuffle_hook", None)
                    reshuffle = hook() if callable(hook) else None
            except Exception as exc:  # noqa: BLE001 - 全知数据注入失败退回期望搜索
                logging.getLogger(__name__).warning("known_draw 注入失败：%s", exc)
                kwargs, reshuffle = {}, None
        coefficient = audition_coefficient(state)
        if coefficient is not None:
            # 考试真实属性倍率（读屏「舞蹈 207%」）：同回合内排序基本不变，但 beam
            # 跨回合与叶子绝对分估值要吃真实倍率（T5 2026-11-22）。读不到不加参数，
            # 保持 ExpectState 默认 1.0（旧行为）。
            kwargs["attribute_coefficient"] = coefficient
            self._last_coefficient = coefficient
        sim_state = ExpectState(
            hand=tuple(card.spec for card in play_cards),
            stamina=max(int(stamina), 0),
            score=max(int(state.score or 0), 0),
            turns_left=max(int(turns_left), 1),
            total_turns=max(int(state.total_turns or turns_left), 1),
            # 游戏规则（2026-11-22 实拍 + 考试逐回合日志 + 社区核对）：**每回合默认
            # 只能出 1 张牌**（一手 3 张是"选 1 张"；额外出牌次数来自卡效果/P 道具）。
            # 旧实现写死 3（"手牌 3 张"的误读）会让搜索以为一回合能连打 3 张：于是
            # "先铺 buff 再补两刀"永远比直接出分牌划算，每回合都先打 buff → 整节课 0 分
            # FAILED（F#42）。
            # 这里每次决策只建模"现在打 1 张"，打完下一帧重新读屏再决策；额外出牌时游戏
            # 会继续问策略（`_plays_this_turn` 记账继续加），所以不把本回合已出牌数喂给搜索，
            # 否则会出现 plays_left=0 的假死（模拟器 A/B 里表现为 RuleFallbackBlocked）。
            plays_used=0,
            play_limit=1,
            clear=int(gauge),
            perfect=max(int(perfect), int(gauge)),
            hand_size=len(play_cards),
            **kwargs,
        )
        return sim_state, play_cards, reshuffle

    def _leaf_value(self):
        """叶子估值（带缓存）：解析式；可叠加学习模型（ensemble）。

        优先级（低 → 高）：

        1. ``AnalyticLeafValue``（永远作为 primary）；
        2. 历史行为：``data/knowledge/v_leaf.json`` 存在时叠 35 维线性叶子（weight 0.5）；
        3. B2 显式配置：``leaf_model`` 指向 ``leaf_mlp.MLPLeafValue`` JSON 时用 MLP 叶子
           （或其它 v_leaf JSON）；权重 ``leaf_model_weight``。**默认 None = 行为不变**，
           T2 真机 A/B 后再决定是否打开（B2 离线结果见 docs/EXPECTIMAX.md）。
        """
        cached = getattr(self, "_leaf_cache", None)
        if cached is not None:
            return cached
        leaf = self._build_leaf_value()
        self._leaf_cache = leaf
        return leaf

    def _build_leaf_value(self):
        """构造叶子估值（只在首次 ``_leaf_value`` 时跑一次，避免每决策重读 JSON）。"""
        from gkagent.sim.expectimax import AnalyticLeafValue

        logger = logging.getLogger(__name__)
        leaf = AnalyticLeafValue(sigma=float(self.params["expectimax_sigma"]))
        weight = float(self.params.get("leaf_model_weight", 0.5) or 0.5)
        explicit = self.params.get("leaf_model")
        if explicit:
            try:
                path = Path(str(explicit))
                if not path.is_absolute():
                    path = Path.cwd() / path
                doc = json.loads(path.read_text(encoding="utf-8"))
                from gkagent.sim.v_leaf import EnsembleLeafValue

                if doc.get("format") == "gkagent.mlp_leaf.v1":
                    from gkagent.sim.leaf_mlp import MLPLeafValue

                    learned = MLPLeafValue.load(path)
                else:
                    from gkagent.sim.v_leaf import LinearLeafValue

                    learned = LinearLeafValue.load(path)
                return EnsembleLeafValue(primary=leaf, secondary=learned, weight=weight)
            except Exception as exc:  # noqa: BLE001 - 模型坏了退回解析式，不能让出牌崩
                logger.warning("B2 leaf_model 加载失败，退回解析式叶子: %s", exc)
        try:
            v_leaf_path = Path("data/knowledge/v_leaf.json")
            if v_leaf_path.exists():
                from gkagent.sim.v_leaf import EnsembleLeafValue, LinearLeafValue

                leaf = EnsembleLeafValue(
                    primary=leaf,
                    secondary=LinearLeafValue.load(v_leaf_path),
                    weight=0.5,
                )
        except Exception as exc:  # noqa: BLE001 - 模型坏了退回解析式，不能让出牌崩
            logger.warning("v_leaf 加载失败，退回解析式叶子: %s", exc)
        return leaf

    @staticmethod
    def _search_action(
        state: LessonState,
        play_cards,
        card,
        *,
        allow_skip: bool,
        reason: str,
        expected: float,
    ) -> LessonAction | None:
        """把搜索结果（``CardSpec``）映射回 ``LessonAction``（原手牌对象/坐标）。"""
        if card is None:
            if not allow_skip:
                return None
            return LessonAction("skip", point=state.skip_point, reason=reason)
        picked = next((item for item in play_cards if item.spec == card), None)
        if picked is None:
            return None
        original = next(
            (item for item in state.cards if item.index == picked.index),
            state.cards[picked.index],
        )
        return LessonAction(
            "card",
            index=picked.index,
            point=picked.point,
            card=original,
            expected=expected,
            reason=reason,
        )

    def _resolve_search_skip(
        self,
        state: LessonState,
        play_cards,
        *,
        actions,
        complete: bool,
        elapsed_ms: float,
        nodes: int,
        allow_skip: bool,
        engine_name: str,
    ) -> LessonAction | None:
        """搜索建议 SKIP 时的处理：有付得起的牌就按**搜索结果自己的动作价值**硬打。

        用户规则（2026-11-21）：读不到价值/搜索建议都不是跳过理由，只有所有牌都
        付不起才允许 SKIP。这里绝不回退 rules——硬打的依据必须是引擎给出的动作
        排序；真没动作时返回 ``None``（调用方按失败处理）或 ``wait``（考试）。

        用户现场 F#42（2026-11-22）：禁跳规则下的"硬打"**必须保证得分**——搜索
        在"反正到不了 CLEAR"的回合会把所有动作打成平手（值都是 0.00），若照原排序
        硬打会挑中 buff 牌（表情的基础之类，0 分）→ 整节课 0 分 FAILED。所以这里
        先筛"屏幕分数预览 > 0"的牌，按（搜索价值, 屏幕分）排序硬打；一张正分牌都
        没有时才退回原排序（hand 全是 buff/防御牌时打什么都一样）。
        """
        affordable = [
            card
            for card in state.cards
            if state.stamina is None or card.cost is None or card.cost <= state.stamina
        ]
        ranked = sorted(
            (item for item in actions if item),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        if affordable:
            preview = self._preview_by_name(state, play_cards)
            scored = [
                (name, value) for name, value in ranked if preview.get(name, 0.0) > 0.0
            ]
            if scored:
                ranked = sorted(
                    scored,
                    key=lambda item: (float(item[1]), preview.get(item[0], 0.0)),
                    reverse=True,
                )
            for name, value in ranked:
                spec = next(
                    (item.spec for item in play_cards if item.spec.name == name), None
                )
                if spec is None:
                    continue
                forced = self._search_action(
                    state,
                    play_cards,
                    spec,
                    allow_skip=False,
                    reason=(
                        f"{engine_name} 建议 SKIP 被用户规则拦截 → 按搜索动作价值硬打 "
                        f"{name}（{float(value):.2f}，{nodes} 节点，{elapsed_ms:.0f}ms）"
                    ),
                    expected=float(value),
                )
                if forced is not None:
                    self.last_fallback_reason = (
                        "搜索建议 SKIP → 按搜索排名硬打（不回退 rules）"
                    )
                    return forced
            if not complete:
                return self._wait_action(
                    f"{engine_name} 超时且没给出动作（{nodes} 节点，{elapsed_ms:.0f}ms）"
                )
            self.last_fallback_reason = (
                f"{engine_name} 建议 SKIP 且没有可打动作"
                f"（complete={complete}，nodes={nodes}，{elapsed_ms:.0f}ms）"
            )
            return None
        if not allow_skip:
            return self._wait_action(f"考试没有付得起的牌（体力 {state.stamina}）")
        self.last_fallback_reason = "所有牌都付不起（真没体力）→ 允许 SKIP"
        return LessonAction(
            "skip",
            point=state.skip_point,
            reason=f"所有牌都付不起（体力 {state.stamina}），允许 SKIP",
        )

    @staticmethod
    def _preview_by_name(state: LessonState, play_cards) -> dict[str, float]:
        """搜索动作名 → 屏幕分数预览（这张牌当下能打多少分；buff 牌不算）。

        卡表认出是 buff（``LessonCard.buff``）的一律记 0：buff 牌不产生课程分，
        F#42 的"硬打必须得分"就是不让它以 0 分占掉最后一回合。
        """
        preview: dict[str, float] = {}
        for item in play_cards:
            index = int(getattr(item, "index", -1))
            card = state.cards[index] if 0 <= index < len(state.cards) else None
            score = 0.0
            if card is not None and not card.buff:
                score = float(card.total_score)
            name = str(getattr(item.spec, "name", "") or "")
            if name:
                preview[name] = max(preview.get(name, 0.0), score)
        return preview

    def _try_expectimax(
        self, state: LessonState, *, allow_skip: bool
    ) -> LessonAction | None:
        """用真机 ``LessonState`` 构造模拟状态并跑回合内 expectimax。

        返回 card / wait / skip；返回 ``None`` 表示搜索彻底失败——调用方按用户
        规则抛 :class:`RuleFallbackBlocked`，**绝不退回 rules**。

        挂了激活的 ``draw_plan``（``ExamDrawPlan``）时，``known_draw`` 让抽牌机会
        节点退化成确定分支；``discard_order`` + 重洗钩子让弃牌堆重洗后也能全知。
        """
        try:
            prepared = self._search_state(state)
            if prepared is None:
                return self._wait_action(self.last_fallback_reason or "状态未读全")
            sim_state, play_cards, reshuffle = prepared
            from gkagent.sim.expectimax import expectimax_with_stats

            result = expectimax_with_stats(
                sim_state,
                self._leaf_value(),
                time_budget_ms=float(self.params["expectimax_budget_ms"]),
                reshuffle=reshuffle,
                # 真机出牌链路没有"喝饮料"动作（auto_produce 单独处理饮料）：
                # 否则搜索选中饮料时 card=None，会被误当成 SKIP。
                allow_drinks=False,
            )
            if result.card is None:
                return self._resolve_search_skip(
                    state,
                    play_cards,
                    actions=result.actions,
                    complete=bool(result.complete),
                    elapsed_ms=float(result.elapsed_ms),
                    nodes=int(result.nodes),
                    allow_skip=allow_skip,
                    engine_name="expectimax",
                )
            reason = (
                f"expectimax: {result.card.name}（档位期望 {result.utility:.2f}，"
                f"{result.nodes} 节点，{result.elapsed_ms:.0f}ms）"
            )
            action = self._search_action(
                state,
                play_cards,
                result.card,
                allow_skip=allow_skip,
                reason=reason,
                expected=result.utility,
            )
            if action is None:
                self.last_fallback_reason = "搜索结果不在手牌（CardSpec 失配）"
                logging.getLogger(__name__).warning(
                    "expectimax 搜索结果不在手牌（禁止回退 rules）：%s", result.card
                )
                return None
            return action
        except RuleFallbackBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 - 搜索失败要暴露，不许退回 rules
            self.last_fallback_reason = f"expectimax 异常: {exc!r}"
            logging.getLogger(__name__).warning(
                "expectimax 失败（禁止回退 rules）：%s", exc
            )
            return None

    def _try_beam(self, state: LessonState, *, allow_skip: bool) -> LessonAction | None:
        """跨回合 beam（``engine="beam"``）：按 V_leaf 规划整段，出计划首牌。

        必须有 ``draw_plan`` 给的 known_draw 才有意义（知道后面几张真实好牌，
        才谈得上替它保留体力/出牌位）；没有全知数据时改用回合内 expectimax
        （不是 rules）。beam 自己建议 SKIP 时，优先执行它根回合计划的真实首牌，
        再退回合内搜索；仍无动作才算失败（调用方抛 blocked，绝不回退 rules）。
        """
        try:
            prepared = self._search_state(state)
            if prepared is None:
                return self._wait_action(self.last_fallback_reason or "状态未读全")
            sim_state, play_cards, reshuffle = prepared
            if not sim_state.known_draw:
                self.last_fallback_reason = (
                    "beam 无 known_draw，改用回合内 expectimax（不回退 rules）"
                )
                return self._try_expectimax(state, allow_skip=allow_skip)
            from gkagent.sim.expectimax import search_beam

            result = search_beam(
                sim_state,
                self._leaf_value(),
                width=max(int(self.params["beam_width"]), 1),
                deadline_ms=float(self.params["beam_deadline_ms"]),
                reshuffle=reshuffle,
            )
            if result.card is None:
                forced = self._force_from_beam_sequence(state, play_cards, result)
                if forced is not None:
                    return forced
                self.last_fallback_reason = (
                    "beam 建议 SKIP → 改回合内 expectimax 硬打（不回退 rules）"
                )
                fallback = self._try_expectimax(state, allow_skip=allow_skip)
                if fallback is not None:
                    return fallback
                return self._resolve_search_skip(
                    state,
                    play_cards,
                    actions=(),
                    complete=bool(result.complete),
                    elapsed_ms=float(result.elapsed_ms),
                    nodes=0,
                    allow_skip=allow_skip,
                    engine_name="beam",
                )
            reason = (
                f"beam: {result.card.name}（V {result.utility:.2f}，宽 {result.width}，"
                f"深 {result.depth_reached}/{sim_state.turns_left}，"
                f"{result.elapsed_ms:.0f}ms）"
            )
            action = self._search_action(
                state,
                play_cards,
                result.card,
                allow_skip=allow_skip,
                reason=reason,
                expected=result.utility,
            )
            if action is None:
                self.last_fallback_reason = "beam 结果不在手牌（CardSpec 失配）"
                logging.getLogger(__name__).warning(
                    "beam 结果不在手牌（禁止回退 rules）：%s", result.card
                )
            return action
        except RuleFallbackBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 - 搜索失败要暴露，不许退回 rules
            self.last_fallback_reason = f"beam 异常: {exc!r}"
            logging.getLogger(__name__).warning("beam 失败（禁止回退 rules）：%s", exc)
            return None

    def _force_from_beam_sequence(
        self, state: LessonState, play_cards, result
    ) -> LessonAction | None:
        """beam 建议 SKIP 但根回合计划里有首牌：按 beam 自己的计划硬打（不是 rules）。"""
        sequence = getattr(result, "sequence", ()) or ()
        if not sequence:
            return None
        name = str(sequence[0])
        spec = next((item.spec for item in play_cards if item.spec.name == name), None)
        if spec is None:
            return None
        self.last_fallback_reason = "beam 建议 SKIP → 按 beam 计划首牌硬打（不回退 rules）"
        return self._search_action(
            state,
            play_cards,
            spec,
            allow_skip=False,
            reason=(
                f"beam 建议 SKIP 被用户规则拦截 → 按 beam 根回合计划首牌硬打 {name}"
                f"（V {result.utility:.2f}，{result.elapsed_ms:.0f}ms）"
            ),
            expected=float(result.utility),
        )

    def _try_uinet(
        self, state: LessonState, *, allow_skip: bool
    ) -> LessonAction | None:
        """把真机 ``LessonState`` 转 UIObs v1，交给 GKMSUINet 选一张牌。

        只映射**读屏能确认**的字段（手牌/体力/剩余回合/分数），其余按
        :mod:`gkagent.sim.uiobs` 的保守默认值补。UINet 说「结束回合/饮料」时按它
        自己的合法动作概率硬打一张（用户规则：有牌就不许跳过）；模型/主数据缺失、
        ONNX 报错、动作越界都返回 ``None``（调用方抛 blocked，**不回退 rules**）。
        """
        try:
            if not state.cards:
                return self._wait_action("手牌为空")
            if state.stamina is None:
                return self._wait_action("体力未知")
            from gkagent.sim import uinet
            from gkagent.sim.uiobs import to_uiobs

            obs = to_uiobs(
                state,
                table=self._card_table(),
                plan=self.plan,
                allow_skip=allow_skip,
                plays=self._plays_this_turn,
            )
            legal = [tuple(item) for item in obs["legal"]]
            if not any(item and item[0] == "play" for item in legal):
                if not allow_skip:
                    return self._wait_action("考试没有付得起的牌")
                self.last_fallback_reason = "所有牌都付不起（真没体力）→ 允许 SKIP"
                return LessonAction(
                    "skip",
                    point=state.skip_point,
                    reason=f"所有牌都付不起（体力 {state.stamina}），允许 SKIP",
                )
            result = uinet.predict(obs)
            action = result.action
            if not action:
                self.last_fallback_reason = "uinet 无动作"
                return None
            kind = str(action[0])
            if kind == "play":
                index = int(action[1])
                if ["play", index] not in obs["legal"]:
                    self.last_fallback_reason = f"uinet 动作越界：play {index}"
                    return None
                card = state.cards[index]
                cost = card.cost
                if cost is None:
                    cost = self._card_table().cost(card.name)
                if cost is not None and cost > state.stamina:
                    self.last_fallback_reason = "uinet 选了付不起的牌"
                    return None
                top_prob = max(result.probs) if result.probs else 0.0
                return LessonAction(
                    "card",
                    index=card.index,
                    point=card.point,
                    card=card,
                    expected=0.0,
                    reason=(
                        f"uinet: {card.name or '卡'}（概率 {top_prob:.2f}，"
                        f"{result.elapsed_ms:.0f}ms）"
                    ),
                )
            # 结束回合/饮料/其他：用户规则禁止"有牌却跳过"，按 UINet 自己的概率硬打。
            forced = self._uinet_forced_card(state, obs, result)
            if forced is not None:
                return forced
            if allow_skip:
                return LessonAction(
                    "skip",
                    point=state.skip_point,
                    reason=f"uinet: {kind}，没有付得起的牌，允许 SKIP",
                )
            return self._wait_action(f"uinet 返回 {kind}，考试没有可打的牌")
        except RuleFallbackBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 - 模型失败要暴露，不许退回 rules
            self.last_fallback_reason = f"uinet 异常: {exc!r}"
            logging.getLogger(__name__).warning(
                "uinet 失败（禁止回退 rules）：%s", exc
            )
            return None

    def _uinet_forced_card(self, state: LessonState, obs, result) -> LessonAction | None:
        """UINet 说结束/饮料时，按它自己的合法动作概率挑一张牌（不是 rules）。"""
        plays = [
            int(item[1])
            for item in (tuple(entry) for entry in obs["legal"])
            if item and item[0] == "play"
        ]
        if not plays:
            return None
        probs = list(result.probs or [])

        def probability(index: int) -> float:
            return float(probs[index]) if index < len(probs) else 0.0

        for index in sorted(plays, key=probability, reverse=True):
            card = state.cards[index]
            cost = card.cost
            if cost is None:
                cost = self._card_table().cost(card.name)
            if cost is not None and state.stamina is not None and cost > state.stamina:
                continue
            self.last_fallback_reason = (
                "uinet 建议结束 → 按合法动作概率硬打（不回退 rules）"
            )
            return LessonAction(
                "card",
                index=card.index,
                point=card.point,
                card=card,
                expected=0.0,
                reason=(
                    f"uinet 建议结束/饮料被用户规则拦截 → 按概率硬打 "
                    f"{card.name or '卡'}（p={probability(index):.2f}）"
                ),
            )
        return None

    def _card_table(self):
        """懒加载卡表；测试可以替换 ``self._table`` 注入 FakeTable。"""
        table = getattr(self, "_table", None)
        if table is None:
            from gkagent.data.card_table import CardTable

            table = CardTable()
            self._table = table
        return table

    def _value(self, card: LessonCard, turns: int | None) -> float:
        # 纯 buff 牌不走"分数"通道，只由 _maybe_buff 决定要不要先铺
        if card.buff:
            return 0.0
        value = card_value(card, turns_left=turns)
        if value <= 0 and card.text:
            value = estimate_value(card.text, turns_left=turns).score
        if card.score_estimated:
            # 屏幕宝石没读到、按卡表兜底的分数：轻微降权，别完全信任；
            # 但降权不能把本来够 min_gain 的牌压到门槛下（否则又变成"跳过"）。
            weight = float(self.params["estimated_score_weight"])
            value = max(value * weight, min(value, float(self.params["min_gain"])))
        return value

    def _perfect_target(self, state: LessonState) -> int | None:
        """PERFECT（满分）线：真机读屏已经算出来的优先（``state.perfect``）。

        读屏口径见 ``vision.lesson.LessonReader``：圆环「CLEAR截止 / PERFECT截止 N」
        给的是还差分，换算后得到过关线/满分线，都在 ``LessonState`` 里。
        没有真机换算值时按档位表（``sim.hajime_data``）由过关线反推，最后退 2×。
        """
        if state.perfect is not None and int(state.perfect) > 0:
            return int(state.perfect)
        gauge = state.gauge
        if gauge is None or gauge <= 0:
            return None
        try:
            from gkagent.sim.hajime_data import lesson_by_clear, perfect_target

            tier = lesson_by_clear(int(gauge), int(state.turns_left) if state.turns_left else None)
            if tier is None:
                tier = lesson_by_clear(int(gauge))
            if tier is not None:
                return int(tier.full)
            return int(perfect_target(int(gauge)))
        except Exception:  # noqa: BLE001 - 查表失败就用经验倍率，不能影响出牌
            return math.ceil(gauge * float(self.params["perfect_target_multiplier"]))

    def _budget(self, stamina: int | None, turns: int | None) -> float:
        if stamina is None:
            return 99.0
        if not turns or turns <= 1:
            return float(stamina)
        reserve = float(self.params["reserve_per_turn"]) * (turns - 1)
        return max(float(stamina) - reserve, float(stamina) / max(turns, 1))

    def _maybe_buff(
        self,
        state: LessonState,
        affordable: list[LessonCard],
        values: dict[int, float],
        budget: float,
    ) -> LessonAction | None:
        if not self.params["buff_first"] or self._buff_played_this_turn:
            return None
        turns = state.turns_left
        if turns is not None and turns <= 1:
            return None
        buffs = [card for card in affordable if self._is_buff_candidate(card)]
        if not buffs:
            return None
        # 方案（プラン）决定 buff 顺序：感性 好调→集中、理性 好印象→やる気、
        # 非凡 温存→強気→全力；同序再比费用。
        buffs.sort(
            key=lambda card: (
                self.buffs.plan_rank(card.text, self.buff_priority),
                card.cost if card.cost is not None else 9,
                card.index,
            )
        )
        # 默认 ratio=1.0 + min_budget=2.0 等价于老的 ``cost <= max(budget, 2.0)``
        cost_limit = max(
            budget * float(self.params["buff_max_cost_ratio"]),
            float(self.params["buff_min_budget"]),
        )
        candidate = None
        for card in buffs:
            cost = card.cost if card.cost is not None else 9
            if cost <= cost_limit:
                candidate = card
                break
        if candidate is None:
            return None
        # 本回合已经打过牌并且有高收益牌在，就别再上 buff 了
        if self._plays_this_turn > 0:
            return None
        best_score = max(
            (
                values.get(card.index, 0.0)
                for card in affordable
                if not self._is_buff_candidate(card)
            ),
            default=0.0,
        )
        # 手里没有能打分的牌时，铺 buff 完全无效（打了也吃不到倍率）——2026-11-15 用户实测反馈
        if best_score <= 0.0:
            return None
        if candidate.text:
            buff_value = estimate_value(candidate.text, turns_left=turns).score
        else:
            buff_value = float(self.params["buff_value_fallback"])
        plan = self.plan_config
        candidate_rank = self.buffs.plan_rank(candidate.text, self.buff_priority)[0]
        if not plan.score_after_buff:
            # 非凡（アノマリー）：不在早期无脑铺 buff。温存（优先级第一）先铺，
            # 用来攒全力值；最后 1-2 回合不再铺，把回合留给全力/大分牌兑现。
            if turns is not None and turns <= 2:
                return None
            if candidate_rank > 0:
                return None
        else:
            # 早期回合（剩余回合数 ≥ 方案 early_buff_turns）buff 优先：层数 buff
            # 越早铺收益越大，这时只有「能一击清 CLEAR」的分数牌才压过 buff。
            early_turns = self.early_buff_turns
            early = turns is not None and turns >= early_turns > 0
            guard = float(self.params["buff_score_guard"])
            if (
                not early
                and best_score >= guard * max(buff_value, 1.0)
                and turn_gain_expected(best_score) > 0
            ):
                return None
        if plan.score_after_buff:
            reason = (
                f"先上 buff（{plan.cn}）：{candidate.name or '卡'}（体力 {candidate.cost}，"
                f"等效 {buff_value:.1f}，剩余 {turns} 回合）"
            )
        else:
            reason = (
                f"非凡温存优先：{candidate.name or '卡'}（体力 {candidate.cost}，"
                f"等效 {buff_value:.1f}，剩余 {turns} 回合）"
            )
        return LessonAction(
            "card",
            index=candidate.index,
            point=candidate.point,
            card=candidate,
            expected=buff_value,
            reason=reason,
        )

    def _is_buff_candidate(self, card: LessonCard) -> bool:
        """这张牌能不能按"铺 buff"处理。

        - 感性/理性沿用旧口径：只认读屏打上的 ``card.buff`` 标记；
        - 非凡的指針牌（温存/強気/全力）在真机上不一定被 ``is_buff_text``
          认成 buff，所以再按方案优先级匹配一次卡面文本（带打分的牌除外）。
        """
        if card.buff:
            return True
        if self.plan_config.score_after_buff:
            return False
        text = card.text or ""
        if not text or any(word in text for word in ("打分", "得分", "分数", "スコア")):
            return False
        return any(self.buffs.matches(text, name) for name in self.buff_priority)

    @staticmethod
    def _must_play(
        affordable: list[LessonCard], values: dict[int, float], reason: str
    ) -> LessonAction:
        """考试模式：即使收益低于门槛也硬打一张（分数最高、其次最便宜）。"""
        if not affordable:
            return LessonAction("wait", reason=reason)
        card = max(
            affordable,
            key=lambda item: (
                values.get(item.index, 0.0),
                -(item.cost if item.cost is not None else 9),
            ),
        )
        return LessonAction(
            "card",
            index=card.index,
            point=card.point,
            card=card,
            expected=values.get(card.index, 0.0),
            reason=f"{reason}：{card.name or '卡'}",
        )

    @staticmethod
    def _cheapest_unknown(affordable: list[LessonCard]) -> LessonCard | None:
        """分数没读到的牌里挑最便宜的一张（至少让这回合产生成长）。"""
        unknown = [
            card
            for card in affordable
            if card.score is None or card.score_unread
        ]
        if not unknown:
            return None
        # 有条件的牌最后才用（条件不满足时点不动，白费一步）
        unknown.sort(
            key=lambda card: (
                card.conditional,
                card.cost if card.cost is not None else 9,
                card.index,
            )
        )
        return unknown[0]

    def _best_score_card(
        self,
        affordable: list[LessonCard],
        values: dict[int, float],
        budget: float,
        turns: int | None = None,
        *,
        prefer_total: bool = False,
    ) -> tuple[LessonCard, float] | None:
        scored = [
            (card, values.get(card.index, 0.0))
            for card in affordable
            if values.get(card.index, 0.0) > float(self.params["negligible"])
        ]
        if not scored:
            return None
        # 最后一回合：体力不用就是浪费，按总分最大挑（而不是性价比）
        last_turn = (
            bool(self.params["last_turn_max_total"])
            and turns is not None
            and turns <= 1
        )
        min_gain = float(self.params["min_gain"])
        if last_turn:
            scored.sort(key=lambda item: (item[1], -item[0].index), reverse=True)
            card, value = scored[0]
            return (card, value) if value >= min_gain else None
        in_budget = [
            item for item in scored if (item[0].cost or 0) <= budget or item[0].cost is None
        ]
        pool = in_budget or scored
        if prefer_total:
            # 还没到 PERFECT 线：优先把单张总分最高的打出去（而不是性价比），
            # 同时不再用 min_gain 卡掉"分数不大但能把缺口补上"的牌。
            pool.sort(
                key=lambda item: (
                    item[1],
                    -item[0].cost if item[0].cost is not None else 0,
                    -item[0].index,
                ),
                reverse=True,
            )
            return pool[0]
        pool.sort(
            key=lambda item: (
                item[1] / max(item[0].cost or 3, 1),
                item[1],
                -item[0].index,
            ),
            reverse=True,
        )
        card, value = pool[0]
        if value < min_gain:
            return None
        return card, value

    def _reset_turn_counters(self) -> None:
        self._plays_this_turn = 0
        self._buff_played_this_turn = False
        self._await_turn_reset = False

    def _sync_turn(self, turns: int | None) -> None:
        # 读不到回合数时不能直接 return：否则 `_plays_this_turn` 永不归零，
        # 会在下一回合（甚至同一屏）一直判「次数用完」而满体力 SKIP。
        if self._await_turn_reset:
            self._reset_turn_counters()
        if turns is None:
            return
        if self._last_turns is None:
            self._last_turns = turns
            return
        if turns != self._last_turns:
            self._last_turns = turns
            self._reset_turn_counters()


def turn_gain_expected(score: float) -> float:
    """留个钩子：以后按"还差多少分"判断值不值，现在只是把 0 分挡掉。"""
    return float(score)


# 考试/舞台的读屏 kind（与 ``sim/play_choice.AUDITION_KINDS`` 同口径）
AUDITION_KINDS = frozenset({"audition", "exam", "stage"})


def audition_coefficient(state) -> float | None:
    """``LessonState`` → 考试/舞台属性倍率系数（屏幕「舞蹈 207%」= 2.07）。

    T5 2026-11-22：真机考试每回合顶部显示的倍率就是本回合的**真实**属性倍率
    （主数据分段曲线 × 审查基准联动惩罚算出来的值；见 ``sim/exam_multiplier.py``）。
    读到就喂给搜索；不是考试/读不到返回 None（保持旧行为，不猜、不设默认 4.11）。
    ``LessonReader`` 只接受 10~999 的读数，这里再夹一次合理区间。
    """
    kind = str(getattr(state, "kind", "") or "").strip().lower()
    if kind not in AUDITION_KINDS:
        return None
    raw = getattr(state, "multiplier", None)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    coefficient = value / 100.0
    if not 0.1 <= coefficient <= 9.99:
        return None
    return coefficient


def _remove_played(hand: list[str], played: list[str]) -> list[str]:
    """手牌里扣掉本回合打出的牌（同名多张只扣一张），保持手牌顺序。

    ``ExamDrawPlan.end_turn(leftover)`` 要的是「回合末剩下的手牌顺序」——
    客户端就是按这个顺序把剩余手牌 append 进弃牌堆的。
    """
    remaining = list(hand)
    for name in played:
        try:
            remaining.remove(name)
        except ValueError:
            continue
    return remaining


def _as_float(value: object) -> float | None:
    """把配置文件里的数字/数字字符串转成有限 float；坏值返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
    else:
        return None
    return parsed if math.isfinite(parsed) else None


def _as_bool(value: object) -> bool | None:
    """宽容地解析布尔值；认不出来返回 None（由调用方保留默认值）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value) if value in (0, 1) else None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return None

