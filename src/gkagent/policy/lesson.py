"""课程/试镜出牌策略：用界面上的分数预览 + 体力，做"像人一样"的取舍。

规则（按优先级）：

1. 只用分数预览判断收益——那是游戏自己算好的值，含好调/集中/属性倍率；
2. 按 ``分数 ÷ 体力`` 选牌；0 费牌按 1 费算，避免被"1 分 0 费"骗；
3. 每个回合的体力预算 ≈ ``体力 / 剩余回合``，先给后面的回合留饭；
4. 剩余回合 ≥2 且本回合还没上过 buff 时，先铺一张便宜的 好调/集中（后续牌吃倍率）；
5. 没有正收益的牌就 **SKIP 结束回合**，不要瞎点卡面空转；
6. 已经过了审查基准、剩下的牌又不值几分时，也别再烧体力。

数值参数全部外置到 ``data/knowledge/policy.json``：模拟器扫出来的参数写回文件后，
真机下一次构造 ``LessonPolicy`` 就生效；``describe()`` 返回当前生效参数，便于日志对比。

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
from gkagent.vision.lesson import LessonCard, LessonState, card_value

# 默认参数文件：真机与模拟器共用。模拟器也可以先写 policy_sim.json 再通过 params_path 传进来。
DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "policy.json"

# 字符串型参数的合法取值；文件里写错就回退默认值，不让策略崩。
_ALLOWED_VALUES: dict[str, frozenset[str]] = {
    "unknown_score_fallback": frozenset({"cheapest", "skip"}),
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
    }

    def __init__(
        self,
        *,
        buffs: BuffLibrary | None = None,
        buff_first: bool | None = None,
        min_gain: float | None = None,
        params: dict | None = None,
        params_path: str | Path | None = None,
    ) -> None:
        self.buffs = buffs or BuffLibrary.load()
        self.params = self._resolve_params(params, params_path)
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

    # ------------------------------------------------------------------ 参数
    @property
    def buff_first(self) -> bool:
        return bool(self.params["buff_first"])

    @buff_first.setter
    def buff_first(self, value: bool) -> None:
        self.params["buff_first"] = bool(value)

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

    @classmethod
    def _resolve_params(
        cls, params: dict | None, params_path: str | Path | None
    ) -> dict[str, Any]:
        values = dict(cls.DEFAULT_PARAMS)
        # 不传 params_path 时尝试默认文件；显式传路径则只认那个路径（缺失=默认值）。
        path = Path(params_path) if params_path is not None else DEFAULT_POLICY_PATH
        values.update(cls._read_overrides(path, values))
        if params:
            values.update(cls._coerce(params, values))
        return values

    @classmethod
    def _read_overrides(cls, path: Path, base: dict[str, Any]) -> dict[str, Any]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return cls._coerce(raw, base)

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
        self._plays_this_turn += 1
        if card is not None and card.buff:
            self._buff_played_this_turn = True

    def decide(self, state: LessonState, *, allow_skip: bool = True) -> LessonAction:
        """``allow_skip=False``（考试/试镜）：绝不返回 ``skip``，必须每回合出一张牌。

        F#17：考试页被当成课程时，体力门/「剩下的牌都不值体力」会连续 SKIP 白送回合
        （真机期中 4th/228Pt 直接不合格）。考试里 SKIP 没有任何收益，所以禁掉三个
        SKIP 出口，退化为「硬打一张最值的」/「等下一帧交给兜底选牌」。
        """
        self._sync_turn(state.turns_left)
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

        # 2) 性价比最高的牌
        best = self._best_score_card(affordable, values, budget, turns)
        if best is None:
            if self.params["unknown_score_fallback"] == "skip" and allow_skip:
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
        buffs = [card for card in affordable if card.buff]
        if not buffs:
            return None
        # 知识库给每种 buff 定了出牌顺序（好调/集中先铺，元气/干劲后置），同序再比费用
        buffs.sort(
            key=lambda card: (
                self.buffs.play_order(card.text),
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
            (values.get(card.index, 0.0) for card in affordable if not card.buff),
            default=0.0,
        )
        # 手里没有能打分的牌时，铺 buff 完全无效（打了也吃不到倍率）——2026-11-15 用户实测反馈
        if best_score <= 0.0:
            return None
        if candidate.text:
            buff_value = estimate_value(candidate.text, turns_left=turns).score
        else:
            buff_value = float(self.params["buff_value_fallback"])
        guard = float(self.params["buff_score_guard"])
        # 早期回合（剩余回合数 ≥ buff_early_turns）buff 优先：层数 buff 越早铺收益越大，
        # 这时只有「能一击清 CLEAR」的分数牌才压过 buff（turn_gain_expected>0 保留原语义）。
        early_turns = int(self.params.get("buff_early_turns", 3) or 0)
        early = turns is not None and turns >= early_turns > 0
        if not early and best_score >= guard * max(buff_value, 1.0) and turn_gain_expected(best_score) > 0:
            return None
        return LessonAction(
            "card",
            index=candidate.index,
            point=candidate.point,
            card=candidate,
            expected=buff_value,
            reason=(
                f"先上 buff：{candidate.name or '卡'}（体力 {candidate.cost}，"
                f"等效 {buff_value:.1f}，剩余 {turns} 回合）"
            ),
        )

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

    def _sync_turn(self, turns: int | None) -> None:
        if turns is None:
            return
        if self._last_turns is None:
            self._last_turns = turns
            return
        if turns != self._last_turns:
            self._last_turns = turns
            self._plays_this_turn = 0
            self._buff_played_this_turn = False


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

