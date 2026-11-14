"""把"读屏 + 出牌策略"接进老的自动跑图脚本。

老路径是 ``pick_hand_card``（读卡名→查卡库→选分数最高的），它看不到界面上的
分数预览和体力，属于"闭着眼睛打"。这里换成 ``LessonReader`` + ``LessonPolicy``，
读不到手牌时再退回老路径，保证不会比现在更差。
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from gkagent.policy.lesson import LessonPolicy
from gkagent.vision.hand_names import HandPick
from gkagent.vision.lesson import LessonReader

SKIP_NAME = "__skip__"


def decide_lesson_pick(
    image: np.ndarray,
    reader: LessonReader,
    policy: LessonPolicy,
    *,
    stamina: int | None = None,
    exclude: set[str] | None = None,
    click: Callable[..., bool] | None = None,
    fallback: Callable[[], HandPick | None] | None = None,
    state=None,
) -> tuple[HandPick | None, bool]:
    """返回 ``(要点的卡, 是否已经处理完这个回合)``。

    - ``(HandPick, False)``：点这张卡（两段式的第一段）；
    - ``(None, True)``：已经点了 SKIP，本回合不要再点卡；
    - ``(None, False)``：没读到手牌，交给调用方兜底。

    ``state`` 已经读过时直接传进来，避免同一帧 OCR 两遍。
    """
    if state is None:
        kind = "audition" if _looks_like_audition(image, reader) else "lesson"
        state = reader.read(image, kind=kind)
    if stamina is not None and state.stamina is None:
        state = _with_stamina(state, stamina)
    if not state.cards:
        return (fallback() if fallback is not None else None), False

    action = policy.decide(state)
    if action.kind == "card" and action.point is not None and action.card is not None:
        card = action.card
        if exclude and card.name in exclude:
            return (fallback() if fallback is not None else None), False
        policy.note_play(card)
        return (
            HandPick(point=action.point, index=action.index or 0, name=card.name, value=action.expected),
            False,
        )
    if action.kind == "skip" and action.point is not None and click is not None:
        clicked = click(*action.point)
        policy.reset_turn()
        return None, bool(clicked is not False)
    return (fallback() if fallback is not None else None), False


def _with_stamina(state, stamina: int):
    from dataclasses import replace

    return replace(state, stamina=int(stamina))


def _looks_like_audition(image: np.ndarray, reader: LessonReader) -> bool:
    """试镜界面左上角有「属性 + N%」，课程界面是「剩余回合数 + CLEAR」。"""
    try:
        line = reader.engine.line(image, (96, 44, 150, 50), digits_only=False)
    except Exception:  # noqa: BLE001
        return False
    if line is None:
        return False
    return any(word in line.text for word in ("歌唱", "舞蹈", "视觉", "%"))
