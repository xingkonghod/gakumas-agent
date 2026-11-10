"""出牌搜索策略。

目标：在每个可出牌上做一次很短的贪心/搜索打分，输出 Recommendation。

与 sim 的关系
-------------
``gkagent.sim`` 目前只有抽象 ``Env``，没有“把当前 Observation 塞回环境再展开”的接口，
所以这里用一个很薄的 ``CardScorer`` 适配层：未来的竞赛/培育模拟器只要实现
``score_hand(obs) -> Sequence[float]``（每张手牌的期望收益），SearchPolicy 就会优先用
模拟分数；没有模拟器时退回确定性启发式：**推荐标签 + 费用效率 + 二步贪心**。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from gkagent.contract.models import Card, Observation
from gkagent.policy.router import Recommendation

DEFAULT_KIND_VALUES: dict[str, float] = {
    "attack": 3.0,
    "buff": 2.4,
    "debuff": 2.2,
    "heal": 2.0,
    "status": 1.2,
    "cards": 2.0,
    "suggestions": 2.0,
    "recommended": 2.0,
    "recommend": 2.0,
}

SUGGESTION_KINDS = frozenset({"suggestions", "recommended", "recommend"})


class CardScorer(Protocol):
    """模拟器适配层：返回每张手牌的期望收益。"""

    def score_hand(self, obs: Observation) -> Sequence[float] | None:
        ...


ScoreFn = Callable[[Observation], Sequence[float] | None]


@dataclass(frozen=True)
class SearchConfig:
    suggestion_bonus: float = 2.0
    playable_bonus: float = 0.25
    unknown_cost: float = 1.0
    lookahead: int = 2
    default_value: float = 2.0


@dataclass(frozen=True)
class _Entry:
    index: int
    card: Card
    value: float
    cost: float
    playable: bool
    suggested: bool


@dataclass(frozen=True)
class _Plan:
    value: float
    cost: float
    indices: tuple[int, ...]


class SearchPolicy:
    """确定性出牌推荐：模拟器打分优先，其次贪心费用效率。"""

    def __init__(
        self,
        scorer: CardScorer | ScoreFn | None = None,
        *,
        config: SearchConfig | None = None,
        kind_values: dict[str, float] | None = None,
    ) -> None:
        self.scorer = scorer
        self.config = config or SearchConfig()
        self.kind_values = dict(DEFAULT_KIND_VALUES)
        if kind_values:
            self.kind_values.update(kind_values)

    # ------------------------------------------------------------------ 公共
    def recommend(self, obs: Observation) -> Recommendation | None:
        entries = self._entries(obs)
        playable = [entry for entry in entries if entry.playable]
        if not playable:
            return None

        sim_scores = self._sim_scores(obs)
        if sim_scores is not None:
            scored = [
                (sim_scores[entry.index] + self.config.suggestion_bonus * entry.suggested, entry)
                for entry in playable
            ]
            scored.sort(key=lambda item: (item[0], -item[1].index), reverse=True)
            best_score, best = scored[0]
            second = scored[1][0] if len(scored) > 1 else None
            confidence = self._confidence(best_score, second, base=0.70, span=0.27)
            reason = f"模拟打分最高({sim_scores[best.index]:.2f})"
            return Recommendation(index=best.index, confidence=confidence, reason=reason)

        suggestions = [entry for entry in playable if entry.suggested]
        if suggestions:
            best = max(suggestions, key=lambda entry: (entry.value / entry.cost, -entry.index))
            return Recommendation(index=best.index, confidence=0.9, reason="系统推荐")

        ap = self._ap(obs)
        plans: list[tuple[_Entry, _Plan, float]] = []
        for entry in playable:
            plan = self._greedy_plan(playable, entry, ap)
            score = plan.value / max(plan.cost, 0.5)
            plans.append((entry, plan, score))
        plans.sort(key=lambda item: (item[2], item[1].value, -item[0].index), reverse=True)
        best_entry, best_plan, best_score = plans[0]
        second_score = plans[1][2] if len(plans) > 1 else None
        confidence = self._confidence(best_score, second_score, base=0.50, span=0.35)
        if len(best_plan.indices) > 1:
            reason = (
                f"贪心二步: 期望 {best_plan.value:.2f} / {best_plan.cost:.1f} 费，"
                f"先出第 {best_entry.index} 张"
            )
        else:
            reason = (
                f"费用效率: {best_entry.value:.2f} / {best_entry.cost:.1f} 费，"
                f"第 {best_entry.index} 张"
            )
        return Recommendation(index=best_entry.index, confidence=confidence, reason=reason)

    def rank(self, obs: Observation) -> list[tuple[int, float, str]]:
        """返回 [(index, score, reason)]，按分数从高到低；用于调试/复盘。"""
        entries = self._entries(obs)
        playable = [entry for entry in entries if entry.playable]
        if not playable:
            return []
        sim_scores = self._sim_scores(obs)
        if sim_scores is not None:
            ranked = [
                (entry.index, float(sim_scores[entry.index]), "模拟打分")
                for entry in playable
            ]
            ranked.sort(key=lambda item: (item[1], -item[0]), reverse=True)
            return ranked

        ap = self._ap(obs)
        ranked = []
        for entry in playable:
            plan = self._greedy_plan(playable, entry, ap)
            score = plan.value / max(plan.cost, 0.5)
            reason = "贪心二步" if len(plan.indices) > 1 else "费用效率"
            ranked.append((entry.index, score, reason))
        ranked.sort(key=lambda item: (item[1], -item[0]), reverse=True)
        return ranked

    # ------------------------------------------------------------------ 特征
    def _entries(self, obs: Observation) -> list[_Entry]:
        ap = self._ap(obs)
        suggested_flags = obs.raw.get("suggested") if obs.raw else None
        flags: Sequence[bool] = (
            suggested_flags
            if isinstance(suggested_flags, (list, tuple))
            and len(suggested_flags) == len(obs.hand)
            else ()
        )
        entries: list[_Entry] = []
        for index, card in enumerate(obs.hand):
            kind = (card.kind or "").lower()
            suggested = kind in SUGGESTION_KINDS or (bool(flags[index]) if flags else False)
            cost = float(card.cost) if card.cost is not None else None
            playable = card.playable and kind != "useless"
            if ap is not None and cost is not None and cost > ap:
                playable = False
            value = self.kind_values.get(kind, self.config.default_value)
            if suggested:
                value += self.config.suggestion_bonus
            value += self.config.playable_bonus
            effective_cost = (
                self.config.unknown_cost if cost is None else max(cost, 0.5)
            )
            entries.append(
                _Entry(
                    index=index,
                    card=card,
                    value=float(value),
                    cost=float(effective_cost),
                    playable=playable,
                    suggested=suggested,
                )
            )
        return entries

    def _greedy_plan(
        self, playable: Sequence[_Entry], first: _Entry, ap: float | None
    ) -> _Plan:
        value = first.value
        cost = first.cost
        indices = [first.index]
        if ap is None or self.config.lookahead <= 1:
            return _Plan(value=value, cost=cost, indices=tuple(indices))

        remaining = ap - first.cost
        used = {first.index}
        while len(indices) < self.config.lookahead:
            options = [
                entry
                for entry in playable
                if entry.index not in used and entry.cost <= remaining + 1e-9
            ]
            if not options:
                break
            nxt = max(options, key=lambda entry: (entry.value / entry.cost, -entry.index))
            indices.append(nxt.index)
            used.add(nxt.index)
            value += nxt.value
            cost += nxt.cost
            remaining -= nxt.cost
        return _Plan(value=value, cost=cost, indices=tuple(indices))

    def _sim_scores(self, obs: Observation) -> list[float] | None:
        if self.scorer is None:
            return None
        try:
            score_hand = getattr(self.scorer, "score_hand", None)
            raw = score_hand(obs) if callable(score_hand) else self.scorer(obs)  # type: ignore[operator]
        except Exception:  # noqa: BLE001 - 模拟器异常一律回退启发式，不能阻断出牌
            return None
        if raw is None or isinstance(raw, (str, bytes)):
            return None
        try:
            scores = [float(value) for value in raw]
        except (TypeError, ValueError):
            return None
        if len(scores) != len(obs.hand) or not all(math.isfinite(v) for v in scores):
            return None
        return scores

    @staticmethod
    def _ap(obs: Observation) -> float | None:
        if not obs.raw:
            return None
        for key in ("ap", "ap_left", "action_points"):
            value = obs.raw.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                return float(value)
        return None

    @staticmethod
    def _confidence(best: float, second: float | None, *, base: float, span: float) -> float:
        if second is None:
            return _clamp(base + span)
        margin = (best - second) / max(abs(best), abs(second), 1e-6)
        return _clamp(base + span * max(0.0, min(1.0, margin)))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
