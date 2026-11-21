"""F#17：考试/试镜模式——顶部排名条命中后禁止一切 SKIP。

真机 ep-sup1：考试页被当成课程，体力门 / 同屏兜底 /「剩下的牌都不值体力」轮番按
SKIP，白送回合；期中 4th / 228Pt（1st=597）直接不合格。考试里 SKIP 没有任何收益，
所以先用排名条（1st..6th）识别，再把所有 SKIP 出口禁掉，强制每回合出一张牌。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gkagent.policy.lesson import LessonPolicy
from gkagent.policy.lesson_pick import decide_lesson_pick
from gkagent.tasks.produce_ui import (
    LessonPlayGuard,
    ProduceDriver,
    is_exam_rank_text,
    lesson_stamina_gate,
)
from gkagent.vision.lesson import LessonCard, LessonState

DATA = Path(__file__).resolve().parents[1] / "data"


def _card(
    index: int = 0,
    *,
    cost: int = 4,
    score: int = 9,
    name: str = "卡",
    buff: bool = False,
) -> LessonCard:
    return LessonCard(
        index=index,
        box=(40 + index * 200, 890, 180, 220),
        point=(140 + index * 200, 1000),
        name=name,
        score=score,
        cost=cost,
        buff=buff,
    )


def _state(cards, *, stamina: int | None = 20, turns: int = 6) -> LessonState:
    return LessonState(kind="audition", turns_left=turns, stamina=stamina, cards=tuple(cards))


def test_exam_rank_text_detection() -> None:
    assert is_exam_rank_text("1st 2nd 3rd 4th")
    assert is_exam_rank_text("2ND")
    assert is_exam_rank_text("剩余回合 7 3rd 104")
    assert not is_exam_rank_text("剩余回合 7")
    assert not is_exam_rank_text("CLEAR PERFECT")
    assert not is_exam_rank_text("")


def test_exam_rank_roi_on_real_frame() -> None:
    """真机考试页截图排名条必须命中；回忆照片结算页不能误判成考试。"""
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2

    exam_path = DATA / "exam_rank_frame.png"
    if not exam_path.exists():
        pytest.skip("缺少考试页实拍 data/exam_rank_frame.png")
    driver = ProduceDriver(sleep=lambda _seconds: None)
    image = cv2.imread(str(exam_path))
    assert image is not None
    assert driver.exam_mode(image) is True

    other_path = DATA / "settlement_photo_select.png"
    if other_path.exists():
        other = cv2.imread(str(other_path))
        assert other is not None
        assert driver.exam_mode(other) is False


def test_stamina_gate_never_skips_in_exam() -> None:
    """体力 0 + 最低费用 6：课程要 SKIP，考试必须放行（不点 SKIP）。"""
    state = _state([_card(cost=6)], stamina=0)
    gate = lesson_stamina_gate(state)
    assert gate is not None
    assert gate[0] == state.skip_point
    assert lesson_stamina_gate(state, exam=True) is None


def test_policy_never_returns_skip_in_exam() -> None:
    policy = LessonPolicy()
    state = _state([_card(score=0, cost=4)])
    # 2026-11-21 用户规则：读不到/分数低不算跳过理由，还有体力就硬打
    assert policy.decide(state).kind == "card"
    action = policy.decide(state, allow_skip=False)
    assert action.kind == "card"
    assert action.point == (140, 1000)


def test_policy_no_affordable_card_waits_in_exam() -> None:
    """考试没有付得起的牌也不 SKIP：返回 wait 交给兜底换牌。"""
    policy = LessonPolicy()
    state = _state([_card(cost=9)], stamina=1)
    assert policy.decide(state).kind == "skip"
    assert policy.decide(state, allow_skip=False).kind == "wait"


def test_decide_lesson_pick_never_clicks_skip_in_exam() -> None:
    policy = LessonPolicy()
    state = _state([_card(score=0)], stamina=20)
    clicks: list[tuple[int, int]] = []

    def click(x: int, y: int) -> bool:
        clicks.append((x, y))
        return True

    pick, done = decide_lesson_pick(
        None, None, policy, state=state, click=click, allow_skip=False
    )
    assert clicks == []  # 考试绝不点 SKIP
    assert done is False
    assert pick is not None and pick.point == (140, 1000)

    # 2026-11-21 用户规则：普通课程里读不到分数也不点 SKIP（只有真没体力才跳过）
    pick2, done2 = decide_lesson_pick(None, None, policy, state=state, click=click)
    assert pick2 is not None
    assert done2 is False
    assert clicks == []


def test_lesson_guard_never_skips_in_exam() -> None:
    exam_guard = LessonPlayGuard()
    for _ in range(5):
        exam_guard.picked((120, 1000), "卡")
        exam_guard.confirm_clicked()
        action, _point = exam_guard.observe(True, progressed=False, allow_skip=False)
        assert action != "skip"

    # 普通课程：同一坐标连续 3 次没推进会走 SKIP（考试除外）
    normal_guard = LessonPlayGuard()
    outcomes = []
    for _ in range(5):
        normal_guard.picked((120, 1000), "卡")
        normal_guard.confirm_clicked()
        outcomes.append(normal_guard.observe(True, progressed=False)[0])
    assert "skip" in outcomes
