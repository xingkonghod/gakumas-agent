"""把"读屏 + 出牌策略"接进老的自动跑图脚本。

老路径是 ``pick_hand_card``（读卡名→查卡库→选分数最高的），它看不到界面上的
分数预览和体力，属于"闭着眼睛打"。这里换成 ``LessonReader`` + ``LessonPolicy``。

用户规则（2026-11-21）：**bot 不许回退 rules**。``LessonPolicy`` 走搜索引擎时，
这里不再调用 ``fallback`` 老规则路径；引擎没产出可执行动作就返回 ``(None, False)``
让调用方等下一帧重读，动作/状态异常则抛 :class:`RuleFallbackBlocked`（真机入口
记 ``[engine][BLOCKED]`` 并中止本局）。
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from gkagent.policy.lesson import LessonPolicy, RuleFallbackBlocked
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
    allow_skip: bool = True,
) -> tuple[HandPick | None, bool]:
    """返回 ``(要点的卡, 是否已经处理完这个回合)``。

    - ``(HandPick, False)``：点这张卡（两段式的第一段）；
    - ``(None, True)``：已经点了 SKIP，本回合不要再点卡；
    - ``(None, False)``：没读到手牌/引擎等下一帧，交给调用方处理。

    ``state`` 已经读过时直接传进来，避免同一帧 OCR 两遍。
    ``allow_skip=False``（考试/试镜，F#17）：策略不许 SKIP、这里也绝不点 SKIP。

    搜索引擎（``engine != "rules"``）禁止静默回退 ``fallback`` 老规则路径；
    只有显式 ``engine="rules"`` 或 ``allow_rule_fallback=True`` 才保留旧行为。
    """
    if state is None:
        kind = "audition" if _looks_like_audition(image, reader) else "lesson"
        state = reader.read(image, kind=kind)
    if stamina is not None and state.stamina is None:
        state = _with_stamina(state, stamina)
    strict = policy.forbids_rule_fallback
    if not state.cards and not strict:
        return (fallback() if fallback is not None else None), False

    action = policy.decide(state, allow_skip=allow_skip)
    if action.kind == "card" and action.point is not None and action.card is not None:
        card = action.card
        if exclude and card.name in exclude:
            if strict:
                raise RuleFallbackBlocked(
                    f"引擎选中的卡「{card.name}」已判定打不出去（禁止回退 rules 另选）"
                )
            return (fallback() if fallback is not None else None), False
        policy.note_play(card)
        return (
            HandPick(point=action.point, index=action.index or 0, name=card.name, value=action.expected),
            False,
        )
    if action.kind == "skip" and action.point is not None and click is not None:
        if not allow_skip:
            # 考试：策略不该返回 skip（decide 已禁），这里再兜一层，绝不点 SKIP
            if strict:
                raise RuleFallbackBlocked("考试模式收到 SKIP 动作（禁止点 SKIP/回退 rules）")
            return (fallback() if fallback is not None else None), False
        clicked = click(*action.point)
        policy.reset_turn()
        return None, bool(clicked is not False)
    if action.kind == "skip":
        # 调用方没给 click 回调：把 SKIP 交回给调用方处理。
        if not strict and fallback is not None:
            return fallback(), False
        return None, False
    if action.kind == "wait":
        if strict:
            # 状态没读全/搜索超时：等下一帧重读，绝不接老规则路径。
            return None, False
        return (fallback() if fallback is not None else None), False
    if strict:
        raise RuleFallbackBlocked(f"引擎返回无法执行的动作：{action.kind}")
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
