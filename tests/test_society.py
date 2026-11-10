"""SocietyTask 的离线测试：模板自匹配、MAA 失败截图、状态机推进与防卡死。

真实截图路径是 MaaGakumasu 的 debug 目录；换机器时不存在会自动 skip，
不会影响 `uv run pytest tests/test_society.py -q`。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from gkagent.tasks import society
from gkagent.tasks.society import SocietyTask
from gkagent.vision.matcher import Match, TemplateMatcher

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
REAL_SCREENSHOTS = Path(r"D:\Games\MaaGakumasu\debug\on_error")

NEW_TEMPLATES = (
    "society_menu",
    "society_entry",
    "society_commit",
    "society_commit_already",
    "society_requests",
    "society_requests_already",
    "society_requests_get",
    "society_next",
    "society_close_menu",
    "society_close_icon",
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """状态机里的等待不拖慢测试。"""
    monkeypatch.setattr(society.time, "sleep", lambda *_args, **_kwargs: None)


# ------------------------------------------------------------------ 测试工具


def _task() -> SocietyTask:
    return SocietyTask(settle_timeout=0.0, poll_interval=0.0, click_delay=0.0)


def _load_template(name: str) -> np.ndarray:
    """按 TemplateMatcher 的规则把 RGBA 模板压到白底上。"""
    image = cv2.imread(str(TEMPLATES / f"{name}.png"), cv2.IMREAD_UNCHANGED)
    assert image is not None, f"missing template: {name}"
    if image.ndim == 3 and image.shape[2] == 4:
        alpha = image[:, :, 3:4].astype(np.float32) / 255.0
        image = (image[:, :, :3].astype(np.float32) * alpha + 255.0 * (1.0 - alpha)).astype(
            np.uint8
        )
    return image


def _screen(*placements: tuple[str, int, int]) -> np.ndarray:
    """白底 720x1280，把模板贴到指定坐标，模拟一个界面。"""
    image = np.full((1280, 720, 3), 245, dtype=np.uint8)
    for name, x, y in placements:
        template = _load_template(name)
        h, w = template.shape[:2]
        assert x + w <= 720 and y + h <= 1280, f"{name} at ({x},{y}) out of screen"
        image[y : y + h, x : x + w] = template
    return image


def _home() -> np.ndarray:
    return _screen(("home", 235, 963), ("society_menu", 618, 1179))


def _menu() -> np.ndarray:
    return _screen(("society_entry", 566, 349))


def _menu_with_close() -> np.ndarray:
    return _screen(("society_entry", 566, 349), ("society_close_menu", 587, 1175))


def _menu_without_entry() -> np.ndarray:
    return _screen(("society_close_menu", 587, 1175))


def _club_ready() -> np.ndarray:
    return _screen(("society_commit", 493, 920), ("society_requests", 245, 1057))


def _club_done() -> np.ndarray:
    return _screen(("society_commit_already", 493, 920), ("society_requests", 245, 1057))


def _club_done_requesting() -> np.ndarray:
    return _screen(
        ("society_commit_already", 493, 920),
        ("society_requests_already", 245, 1057),
    )


def _real(name: str) -> np.ndarray:
    path = REAL_SCREENSHOTS / name
    if not path.exists():
        pytest.skip(f"真实截图不存在: {path}")
    image = cv2.imread(str(path))
    assert image is not None
    return image


class FakeAgent:
    """按脚本逐屏推进的 Agent：click/swipe 一次就换到下一屏。"""

    def __init__(self, screens: list[np.ndarray]) -> None:
        self.matcher = TemplateMatcher(TEMPLATES)
        self.screens = screens
        self.index = 0
        self.clicks: list[tuple[str, tuple[int, int]]] = []
        self.swipes: list[tuple[int, int, int, int, int]] = []
        # SocietyTask 只用 agent.device.swipe 做翻页。
        self.device = self

    @property
    def current(self) -> np.ndarray:
        return self.screens[min(self.index, len(self.screens) - 1)]

    def shot(self) -> np.ndarray:
        return self.current

    def find(self, name: str, image=None, roi=None, threshold=None) -> Match | None:
        target = self.current if image is None else image
        return self.matcher.find(name, target, roi=roi, threshold=threshold)

    def _advance(self) -> None:
        if self.index < len(self.screens) - 1:
            self.index += 1

    def click(self, match: Match) -> None:
        self.clicks.append((match.name, match.center))
        self._advance()

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.swipes.append((x1, y1, x2, y2, duration_ms))
        self._advance()

    def ensure_home(self, attempts: int = 4) -> bool:
        for _ in range(attempts):
            if self.matcher.find("home", self.current, threshold=0.85) is not None:
                return True
            tab = self.matcher.find("home_tab", self.current, threshold=0.9)
            if tab is None:
                return False
            self.click(tab)
        return False


# ------------------------------------------------------------------ 模板


@pytest.mark.parametrize("name", NEW_TEMPLATES)
def test_society_templates_self_match(name: str) -> None:
    matcher = TemplateMatcher(TEMPLATES)
    image = _load_template(name)
    match = matcher.find(name, image)
    assert match is not None
    assert match.score > 0.99
    assert match.box[:2] == (0, 0)


def test_task_contract() -> None:
    task = SocietyTask()
    assert task.name == "society"
    assert hasattr(task, "run")
    assert hasattr(task, "classify")
    assert hasattr(task, "donation_state")
    assert hasattr(task, "request_state")


# ------------------------------------------------ MAA 失败截图（真实中文 UI）


def test_real_commit_already_screenshot_is_recognized() -> None:
    """17:16 的失败现场：MAA 的 RGBCount 只有 0.798，我们的 CCOEFF 是 1.0。"""
    image = _real("2026.11.10-17.16.07.306_ReturnHome.png")
    agent = FakeAgent([image])
    task = _task()
    matcher = TemplateMatcher(TEMPLATES)

    assert task.classify(agent, image) == "society"
    assert task.donation_state(agent, image) == "already"
    assert task.request_state(agent, image) == "open"

    match = matcher.find(
        "society_commit_already",
        image,
        roi=SocietyTask.donation_roi,
        threshold=SocietyTask.button_threshold,
    )
    assert match is not None
    assert match.score > 0.95
    # 不能把「已捐赠」误认成「捐赠」，否则会重复点捐赠。
    assert (
        matcher.find(
            "society_commit",
            image,
            roi=SocietyTask.donation_roi,
            threshold=SocietyTask.button_threshold,
        )
        is None
    )


def test_real_commit_ready_screenshot_is_recognized() -> None:
    """16:38 的失败现场：还显示「捐赠」，应该走捐赠而不是已捐赠。"""
    image = _real("2026.11.10-16.38.29.311_SocietyDonation.png")
    agent = FakeAgent([image])
    task = _task()
    matcher = TemplateMatcher(TEMPLATES)

    assert task.classify(agent, image) == "society"
    assert task.donation_state(agent, image) == "ready"
    assert task.request_state(agent, image) == "open"

    match = matcher.find(
        "society_commit",
        image,
        roi=SocietyTask.donation_roi,
        threshold=SocietyTask.button_threshold,
    )
    assert match is not None
    assert match.score > 0.95
    # 反过来也不能把「捐赠」误认成「已捐赠」，否则会跳过捐赠。
    assert (
        matcher.find(
            "society_commit_already",
            image,
            roi=SocietyTask.donation_roi,
            threshold=SocietyTask.button_threshold,
        )
        is None
    )


def test_real_menu_entry_screenshot_is_recognized() -> None:
    """23:37 的失败现场：菜单已打开、停在「社团」入口前。"""
    image = _real("2026.11.09-23.37.57.404_SocietyDonation.png")
    agent = FakeAgent([image])
    task = _task()

    assert task.classify(agent, image) == "menu"
    match = TemplateMatcher(TEMPLATES).find(
        "society_entry",
        image,
        threshold=SocietyTask.entry_threshold,
    )
    assert match is not None
    assert match.score > 0.9


def test_real_home_menu_is_recognized() -> None:
    image = _real("2026.11.10-17.10.16.217_StartUpHomeFlag.png")
    agent = FakeAgent([image])
    task = _task()

    assert task.classify(agent, image) == "home"
    match = TemplateMatcher(TEMPLATES).find(
        "society_menu",
        image,
        roi=SocietyTask.menu_roi,
        threshold=SocietyTask.menu_threshold,
    )
    assert match is not None
    assert match.score > 0.70


# ------------------------------------------------------------------ 状态判断


def test_classify_screens() -> None:
    task = _task()
    assert task.classify(FakeAgent([_home()]), _home()) == "home"
    assert task.classify(FakeAgent([_menu()]), _menu()) == "menu"
    assert task.classify(FakeAgent([_club_ready()]), _club_ready()) == "society"
    assert task.classify(FakeAgent([_screen()]), _screen()) == "unknown"


def test_donation_state() -> None:
    task = _task()
    ready = _club_ready()
    done = _club_done()
    blank = _screen()
    assert task.donation_state(FakeAgent([ready]), ready) == "ready"
    assert task.donation_state(FakeAgent([done]), done) == "already"
    assert task.donation_state(FakeAgent([blank]), blank) == "unknown"


def test_request_state() -> None:
    task = _task()
    open_screen = _club_ready()
    already_screen = _club_done_requesting()
    blank = _screen()
    assert task.request_state(FakeAgent([open_screen]), open_screen) == "open"
    assert task.request_state(FakeAgent([already_screen]), already_screen) == "already"
    assert task.request_state(FakeAgent([blank]), blank) == "unknown"


# ------------------------------------------------------------------ 完整流程


def test_donate_then_request_then_home() -> None:
    agent = FakeAgent(
        [
            _home(),
            _menu(),
            _club_ready(),
            _screen(("society_next", 15, 808)),
            _screen(("decide", 250, 1120)),
            _club_done(),
            _screen(("society_requests_get", 200, 400)),
            _screen(("close", 250, 1120)),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert result.message == "社团捐赠已完成；已打开并关闭募集页；已回到主页"
    assert [name for name, _ in agent.clicks] == [
        "society_menu",
        "society_entry",
        "society_commit",
        "decide",
        "society_requests",
        "society_requests_get",
        "close",
    ]
    assert agent.swipes == [(490, 855, 182, 855, 300)]


def test_already_donated_skips_donation_and_requests() -> None:
    agent = FakeAgent(
        [
            _home(),
            _menu(),
            _club_done(),
            _screen(("society_requests_get", 200, 400)),
            _screen(("close", 250, 1120)),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert result.message == "社团今日已捐赠，已跳过捐赠；已打开并关闭募集页；已回到主页"
    assert [name for name, _ in agent.clicks] == [
        "society_menu",
        "society_entry",
        "society_requests",
        "society_requests_get",
        "close",
    ]
    assert "society_commit" not in [name for name, _ in agent.clicks]


def test_requesting_state_is_not_requested_again() -> None:
    agent = FakeAgent(
        [
            _home(),
            _menu(),
            _club_done_requesting(),
            _screen(("close", 250, 1120)),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert result.message == "社团今日已捐赠，已跳过捐赠；募集已在处理中；已回到主页"
    assert [name for name, _ in agent.clicks] == [
        "society_menu",
        "society_entry",
        "society_requests_already",
        "close",
    ]


def test_request_popup_close_icon_is_used() -> None:
    """请求弹窗只有右上角圆 X 时也要能关掉，不能卡在弹窗里。"""
    agent = FakeAgent(
        [
            _home(),
            _menu(),
            _club_done(),
            _screen(("society_close_icon", 650, 800)),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert result.message == "社团今日已捐赠，已跳过捐赠；已打开并关闭募集页；已回到主页"
    assert [name for name, _ in agent.clicks] == [
        "society_menu",
        "society_entry",
        "society_requests",
        "society_close_icon",
    ]


def test_start_from_society_page_does_not_fail_at_home() -> None:
    """MAA 把游戏留在社团页后，下一次运行应该还能继续，而不是“不在主页”。"""
    agent = FakeAgent(
        [
            _club_done(),
            _screen(("close", 250, 1120)),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert "已回到主页" in result.message
    assert agent.clicks[0][0] == "society_requests"


# ------------------------------------------------------------------ 防卡死


def test_missing_requests_reports_instead_of_hanging() -> None:
    """社团页没有募集入口，也没有主页入口：必须有界返回而不是反复重试。"""
    agent = FakeAgent([_screen(("society_commit_already", 493, 920))])

    result = _task().run(agent)

    assert result.ok is False
    assert result.message == "社团今日已捐赠，已跳过捐赠；未找到募集入口；回主页未确认（可能仍在社团页）"
    assert agent.clicks == []


def test_real_stuck_club_screenshot_does_not_hang() -> None:
    """把 17:16 的卡死截图直接喂给状态机：只点一次募集就返回，不再反复重试。"""
    image = _real("2026.11.10-17.16.07.306_ReturnHome.png")
    agent = FakeAgent([image])

    result = _task().run(agent)

    assert result.ok is False
    assert result.message == (
        "社团今日已捐赠，已跳过捐赠；已打开募集页；回主页未确认（可能仍在社团页）"
    )
    assert [name for name, _ in agent.clicks] == ["society_requests"]


def test_menu_without_entry_is_closed_and_fails() -> None:
    agent = FakeAgent([_home(), _menu_without_entry(), _home()])

    result = _task().run(agent)

    assert result.ok is False
    assert "进入社团失败" in result.message
    assert [name for name, _ in agent.clicks] == ["society_menu", "society_close_menu"]


def test_home_popup_is_closed_before_menu() -> None:
    agent = FakeAgent(
        [
            _screen(("home", 235, 963), ("close", 250, 1120)),
            _home(),
            _menu(),
            _club_ready(),
        ]
    )

    assert _task()._open_society(agent) is True
    assert [name for name, _ in agent.clicks] == [
        "close",
        "society_menu",
        "society_entry",
    ]


def test_club_popup_after_entry_is_closed() -> None:
    agent = FakeAgent(
        [
            _home(),
            _menu(),
            _screen(("close", 250, 1120)),
            _club_done(),
            _screen(("close", 250, 1120)),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert result.message == "社团今日已捐赠，已跳过捐赠；已打开并关闭募集页；已回到主页"
    assert [name for name, _ in agent.clicks] == [
        "society_menu",
        "society_entry",
        "close",
        "society_requests",
        "close",
    ]


def test_donation_panel_without_progress_fails() -> None:
    agent = FakeAgent([_club_ready(), _screen()])

    result = _task().run(agent)

    assert result.ok is False
    assert "社团捐赠未完成" in result.message
    assert [name for name, _ in agent.clicks] == ["society_commit"]


def test_return_home_from_open_menu_uses_close_button() -> None:
    agent = FakeAgent([_menu_with_close(), _home()])
    task = _task()

    assert task._return_home(agent) is True
    assert [name for name, _ in agent.clicks] == ["society_close_menu"]
