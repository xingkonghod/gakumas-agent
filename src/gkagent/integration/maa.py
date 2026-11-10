"""把 MaaGakumasu / MaaFramework 的识别结果转成 GDE 契约。

这里不 import maa，保持纯函数、可单测；真正的 custom_action 在
docs/MAA_INTEGRATION.md 里给出。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from gkagent.contract.models import Action, ActionKind, Card, Observation, Phase


@dataclass(frozen=True)
class MaaCardHit:
    """MAA 识别结果里的一张手牌框。"""

    label: str
    box: tuple[int, int, int, int]  # x, y, w, h
    score: float = 0.0


def box_center(box: tuple[int, int, int, int]) -> tuple[int, int]:
    x, y, w, h = box
    return x + w // 2, y + h // 2


def observation_from_maa(
    hits: Iterable[MaaCardHit],
    *,
    frame_id: int = 0,
    ts_ms: int = 0,
    screen: str = "produce_card",
    phase: Phase = Phase.PRODUCE,
    extra: dict[str, Any] | None = None,
) -> Observation:
    """把 MAA 的 cards/suggestions/useless 框转成 Observation。

    L1 阶段没有卡 ID，只用 label 做粗分类；L2 再接卡图分类器补 card_id/cost。
    """
    hand: list[Card] = []
    boxes: list[list[int]] = []
    scores: list[float] = []
    for i, hit in enumerate(hits):
        hand.append(
            Card(
                card_id=f"maa_{i}",
                name=None,
                cost=None,
                kind=hit.label,
                playable=hit.label != "useless",
            )
        )
        boxes.append(list(hit.box))
        scores.append(hit.score)

    raw = {"boxes": boxes, "scores": scores}
    if extra:
        raw.update(extra)
    return Observation(
        frame_id=frame_id,
        ts_ms=ts_ms,
        screen=screen,
        phase=phase,
        hand=hand,
        confidence=max(scores, default=0.0),
        raw=raw,
    )


def action_to_card_index(action: Action) -> int | None:
    if action.kind == ActionKind.PLAY_CARD:
        return action.index
    return None


def action_to_point(action: Action, obs: Observation) -> tuple[int, int] | None:
    """把 Action 映射成点击坐标；没有对应 box 时返回 None。"""
    if action.kind not in (ActionKind.PLAY_CARD, ActionKind.CHOOSE):
        return None
    if action.index is None:
        return None
    boxes = obs.raw.get("boxes") or []
    if action.index >= len(boxes):
        return None
    box = boxes[action.index]
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    return box_center(tuple(int(v) for v in box))
