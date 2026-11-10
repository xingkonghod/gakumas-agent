"""L1 出牌策略：规则版，先保证教练模式能给出稳定建议。"""

from __future__ import annotations

from dataclasses import dataclass

from gkagent.contract.models import Observation


@dataclass(frozen=True)
class Recommendation:
    index: int
    confidence: float
    reason: str


class RuleCardPolicy:
    """系统推荐优先；否则在可用牌里选识别分数最高的一张。"""

    def recommend(self, obs: Observation) -> Recommendation | None:
        playable = [(i, card) for i, card in enumerate(obs.hand) if card.playable]
        if not playable:
            return None

        suggestions = [(i, card) for i, card in playable if card.kind == "suggestions"]
        if suggestions:
            index, _ = suggestions[0]
            return Recommendation(index=index, confidence=0.9, reason="系统推荐")

        scores = obs.raw.get("scores") or []
        index, _ = max(
            playable,
            key=lambda item: scores[item[0]] if item[0] < len(scores) else 0.0,
        )
        return Recommendation(index=index, confidence=0.5, reason="识别分数最高")
