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
    "unknown_score_fallback": frozenset({"cheapest", "skip"}),
    "plan": frozenset(VALID_PLANS),
    "engine": frozenset({"rules", "expectimax", "uinet"}),
}


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
        # uinet=GKMSUINet 神经网络（ONNX，UIObs v1）。后两者异常/状态不完整/
        # 模型缺失时都自动退回 rules。
        "engine": "rules",
        # expectimax 的 anytime 预算与 V_leaf σ；规则模式不读。
        "expectimax_budget_ms": 800.0,
        "expectimax_sigma": 80.0,
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
    ) -> None:
        self.buffs = buffs or BuffLibrary.load()
        self.plans = plans or default_plan_library()
        self.params = self._resolve_params(params, params_path)
        # 显式 plan 参数优先级最高；未知值按需求退回 sense，不抛异常。
        if plan is not None:
            self.params["plan"] = normalize_plan(plan) or DEFAULT_PLAN
        # 显式 engine 参数优先级最高；未知值退回 rules（保持旧行为）
        if engine is not None:
            self.params["engine"] = engine if engine in _ALLOWED_VALUES["engine"] else "rules"
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
        """当前出牌引擎：``rules``（默认）/ ``expectimax`` / ``uinet``。"""
        return str(self.params.get("engine") or "rules")

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

    def decide(self, state: LessonState, *, allow_skip: bool = True) -> LessonAction:
        """按 ``engine`` 选择规则 / expectimax / UINet；异常或局面不完整退回规则。

        默认 ``engine="rules"``，行为与旧版逐位一致；``policy.json`` 的
        ``lesson.engine`` 或构造参数 ``engine="expectimax"`` / ``engine="uinet"``
        才启用搜索 / 神经网络。
        """
        self._sync_turn(state.turns_left)
        rules_action = self._decide_rules(state, allow_skip=allow_skip)
        if self.engine == "expectimax":
            override = self._try_expectimax(state, allow_skip=allow_skip)
            return override if override is not None else rules_action
        if self.engine == "uinet":
            override = self._try_uinet(state, allow_skip=allow_skip)
            return override if override is not None else rules_action
        return rules_action

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
            if (
                self.params["unknown_score_fallback"] == "skip"
                and allow_skip
                and not below_perfect
            ):
                return LessonAction(
                    "skip",
                    point=state.skip_point,
                    reason="没有值得打的牌，按配置跳过本回合",
                )
            # 分数一个都没读到 ≠ 这些牌没用：读不到数字时打最便宜的，别浪费回合（跳课=不涨属性）
            fallback = self._cheapest_unknown(affordable)
            if fallback is not None:
                return LessonAction(
                    "card",
                    index=fallback.index,
                    point=fallback.point,
                    card=fallback,
                    expected=0.0,
                    reason=f"分数没读到，先打最便宜的「{fallback.name or '卡'}」保成长",
                )
            if not allow_skip:
                return self._must_play(affordable, values, "考试不允许 SKIP，硬打一张")
            if below_perfect:
                # 还没到 PERFECT 线：哪怕这张牌的收益低于 min_gain，也要继续推进，
                # 不能像以前那样"打够 CLEAR 就收手"。
                return self._must_play(
                    affordable, values, "还没到 PERFECT 线，继续打一张"
                )
            return LessonAction(
                "skip",
                point=state.skip_point,
                reason="剩下的牌都不值体力",
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
    def _try_expectimax(
        self, state: LessonState, *, allow_skip: bool
    ) -> LessonAction | None:
        """用真机 ``LessonState`` 构造模拟状态并跑回合内 expectimax。

        只映射读屏能确认的字段（手牌/体力/剩余回合/分数/CLEAR 基准）；卡表能补
        费用与效果。读不到总回合数时用剩余回合兜底；身份不明的牌/异常一律返回
        ``None``，调用方退回规则，绝不让出牌退化。
        """
        try:
            if not state.cards:
                return None
            gauge = state.gauge
            turns_left = state.turns_left
            stamina = state.stamina
            # 用户要求：禁用规则回退。读不到 CLEAR 基准时用经验默认值（250），
            # 只保留"手牌为空 / 体力未知 / 回合未知"这类无法决策的硬性回退。
            if gauge is None or gauge <= 0:
                gauge = int(self.params.get("default_clear_gauge") or 250)
            if turns_left is None or turns_left <= 0:
                return None
            if stamina is None:
                return None
            from gkagent.sim.expectimax import (
                AnalyticLeafValue,
                ExpectState,
                expectimax_with_stats,
            )
            from gkagent.sim.play_choice import specs_from_hand

            play_cards = specs_from_hand(state.cards, table=self._card_table())
            if not play_cards:
                return None
            perfect = math.ceil(
                float(gauge) * float(self.params["perfect_target_multiplier"])
            )
            sim_state = ExpectState(
                hand=tuple(card.spec for card in play_cards),
                stamina=max(int(stamina), 0),
                score=max(int(state.score or 0), 0),
                turns_left=max(int(turns_left), 1),
                total_turns=max(int(state.total_turns or turns_left), 1),
                plays_used=max(int(self._plays_this_turn), 0),
                play_limit=3,
                clear=int(gauge),
                perfect=max(int(perfect), int(gauge)),
                hand_size=len(play_cards),
            )
            # 叶子：有拟合模型就用 ensemble（analytic + learned 平均），否则纯解析式。
            # 真机默认走 ensemble —— 本地评测里它比任一单模型都强（+13.2% 配对几何）。
            leaf = AnalyticLeafValue(sigma=float(self.params["expectimax_sigma"]))
            try:
                from pathlib import Path as _Path

                v_leaf_path = _Path("data/knowledge/v_leaf.json")
                if v_leaf_path.exists():
                    from gkagent.sim.v_leaf import EnsembleLeafValue, LinearLeafValue

                    leaf = EnsembleLeafValue(
                        primary=leaf,
                        secondary=LinearLeafValue.load(v_leaf_path),
                        weight=0.5,
                    )
            except Exception:  # noqa: BLE001 - 模型坏了退回解析式，不能让出牌崩
                pass
            result = expectimax_with_stats(
                sim_state,
                leaf,
                time_budget_ms=float(self.params["expectimax_budget_ms"]),
            )
            if result.card is None:
                if not allow_skip:
                    return None
                return LessonAction(
                    "skip",
                    point=state.skip_point,
                    reason=(
                        f"expectimax: SKIP（档位期望 {result.utility:.2f}，"
                        f"{result.elapsed_ms:.0f}ms）"
                    ),
                )
            picked = next(
                (card for card in play_cards if card.spec == result.card), None
            )
            if picked is None:
                return None
            original = next(
                (card for card in state.cards if card.index == picked.index),
                state.cards[picked.index],
            )
            return LessonAction(
                "card",
                index=picked.index,
                point=picked.point,
                card=original,
                expected=result.utility,
                reason=(
                    f"expectimax: {picked.name}（档位期望 {result.utility:.2f}，"
                    f"{result.nodes} 节点，{result.elapsed_ms:.0f}ms）"
                ),
            )
        except Exception:  # noqa: BLE001 - 搜索绝不能让出牌退化
            return None

    def _try_uinet(
        self, state: LessonState, *, allow_skip: bool
    ) -> LessonAction | None:
        """把真机 ``LessonState`` 转 UIObs v1，交给 GKMSUINet 选一张牌。

        只映射**读屏能确认**的字段（手牌/体力/剩余回合/分数），其余按
        :mod:`gkagent.sim.uiobs` 的保守默认值补。模型/主数据缺失、包没装、
        ONNX 报错、动作越界、体力其实不够……一律返回 ``None`` 退回规则，
        绝不让出牌崩掉或点出非法动作。
        """
        try:
            if not state.cards or state.stamina is None:
                return None
            from gkagent.sim import uinet
            from gkagent.sim.uiobs import to_uiobs

            obs = to_uiobs(
                state,
                table=self._card_table(),
                plan=self.plan,
                allow_skip=allow_skip,
                plays=self._plays_this_turn,
            )
            legal = {tuple(item) for item in obs["legal"]}
            if not any(item[0] == "play" for item in legal):
                return None
            result = uinet.predict(obs)
            action = result.action
            if not action:
                return None
            kind = str(action[0])
            if kind == "play":
                index = int(action[1])
                if ["play", index] not in obs["legal"]:
                    return None
                card = state.cards[index]
                cost = card.cost
                if cost is None:
                    cost = self._card_table().cost(card.name)
                if cost is not None and cost > state.stamina:
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
            if kind == "end":
                if not allow_skip:
                    return None
                top_prob = max(result.probs) if result.probs else 0.0
                return LessonAction(
                    "skip",
                    point=state.skip_point,
                    reason=f"uinet: 结束回合（概率 {top_prob:.2f}，{result.elapsed_ms:.0f}ms）",
                )
            # 饮料等真机还没有对应操作：退回规则。
            return None
        except Exception:  # noqa: BLE001 - 神经网络绝不能让出牌退化
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
        """PERFECT 线 = 屏幕 CLEAR 基准 × ``perfect_target_multiplier``。

        ``LessonState.gauge`` 是课程界面上读到的 CLEAR 基准；没有它（试镜/OCR
        没读到）时返回 None，策略退回原来的"性价比优先"。
        """
        gauge = state.gauge
        if gauge is None or gauge <= 0:
            return None
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

