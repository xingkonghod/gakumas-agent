"""WorkTask 的离线测试：模板自匹配、中文主页真实截图、状态机推进/失败提示。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from gkagent.tasks import work
from gkagent.tasks.work import WorkTask
from gkagent.vision.matcher import Match, TemplateMatcher

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
REAL_SCREENSHOTS = Path(r"D:\Games\MaaGakumasu\debug\on_error")

NEW_TEMPLATES = (
    "work_entry",
    "work_finish",
    "work_choose_show",
    "work_choose_live",
    "work_choose_idol",
    "work_sure",
    "work_start",
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(work.time, "sleep", lambda *_args, **_kwargs: None)


def _screen(*placements: tuple[str, int, int]) -> np.ndarray:
    """白底 720x1280，把模板贴到指定坐标，模拟一个界面。"""
    image = np.full((1280, 720, 3), 245, dtype=np.uint8)
    for name, x, y in placements:
        template = cv2.imread(str(TEMPLATES / f"{name}.png"))
        assert template is not None, name
        h, w = template.shape[:2]
        image[y : y + h, x : x + w] = template
    return image


def _home(with_entry: bool = True) -> np.ndarray:
    items: list[tuple[str, int, int]] = [("home", 235, 963)]
    if with_entry:
        items.append(("work_entry", 49, 722))
    return _screen(*items)


def _type_screen() -> np.ndarray:
    return _screen(
        ("work_choose_show", 80, 650),
        ("work_choose_live", 390, 650),
    )


def _idol_screen() -> np.ndarray:
    return _screen(("work_choose_idol", 255, 1120))


def _time_screen() -> np.ndarray:
    return _screen(("work_sure", 255, 1120))


def _start_screen() -> np.ndarray:
    return _screen(("work_start", 255, 1120))


class FakeAgent:
    """按脚本逐屏推进的 Agent：click 一次就换到下一屏。"""

    def __init__(self, screens: list[np.ndarray]) -> None:
        self.matcher = TemplateMatcher(TEMPLATES)
        self.screens = screens
        self.index = 0
        self.clicks: list[tuple[str, tuple[int, int]]] = []

    @property
    def current(self) -> np.ndarray:
        return self.screens[min(self.index, len(self.screens) - 1)]

    def shot(self) -> np.ndarray:
        return self.current

    def find(self, name: str, image=None, roi=None, threshold=None) -> Match | None:
        target = self.current if image is None else image
        return self.matcher.find(name, target, roi=roi, threshold=threshold)

    def click(self, match: Match) -> None:
        self.clicks.append((match.name, match.center))
        if self.index < len(self.screens) - 1:
            self.index += 1

    def ensure_home(self, attempts: int = 4) -> bool:
        for _ in range(attempts):
            image = self.shot()
            if self.matcher.find("home", image, threshold=0.85) is not None:
                return True
            tab = self.matcher.find("home_tab", image, threshold=0.9)
            if tab is None:
                return False
            self.click(tab)
            work.time.sleep(1.2)
        return False

    def close_popup(self, image=None) -> bool:
        target = self.shot() if image is None else image
        for name in ("close", "decide"):
            match = self.matcher.find(name, target, threshold=0.85)
            if match is not None:
                self.click(match)
                work.time.sleep(0.8)
                return True
        return False


@pytest.mark.parametrize("name", NEW_TEMPLATES)
def test_work_templates_self_match(name: str) -> None:
    matcher = TemplateMatcher(TEMPLATES)
    image = cv2.imread(str(TEMPLATES / f"{name}.png"))
    assert image is not None
    match = matcher.find(name, image)
    assert match is not None
    assert match.score > 0.99
    assert match.box[:2] == (0, 0)


@pytest.mark.parametrize(
    "filename",
    [
        "2026.11.09-23.17.54.753_WorkHomeFlag.png",
        "2026.11.10-17.10.16.217_StartUpHomeFlag.png",
        "2026.11.10-16.37.07.368_StartUpHomeFlag.png",
    ],
)
def test_work_entry_matches_real_chinese_home(filename: str) -> None:
    path = REAL_SCREENSHOTS / filename
    if not path.exists():
        pytest.skip(f"真实截图不存在: {path}")
    image = cv2.imread(str(path))
    assert image is not None
    match = TemplateMatcher(TEMPLATES).find(
        "work_entry",
        image,
        roi=WorkTask.work_entry_roi,
        threshold=WorkTask.work_entry_threshold,
    )
    assert match is not None
    assert match.center == (71, 733)
    assert match.score >= WorkTask.work_entry_threshold


def test_work_starts_and_returns_home() -> None:
    agent = FakeAgent(
        [
            _home(),
            _type_screen(),
            _idol_screen(),
            _time_screen(),
            _start_screen(),
            _home(),
        ]
    )

    result = WorkTask().run(agent)

    assert result.ok is True
    assert result.message == "工作已开始，已回到主页"
    assert [name for name, _ in agent.clicks] == [
        "work_entry",
        "work_choose_show",
        "work_choose_idol",
        "work_sure",
        "work_start",
    ]


def test_work_reward_is_claimed_and_returns_home() -> None:
    agent = FakeAgent(
        [
            _home(),
            _screen(("work_finish", 250, 1120)),
            _screen(("decide", 250, 1120)),
            _home(),
        ]
    )

    result = WorkTask().run(agent)

    assert result.ok is True
    assert result.message == "工作奖励已领取，已回到主页"
    assert [name for name, _ in agent.clicks] == ["work_entry", "work_finish", "decide"]


def test_start_then_close_work_page_returns_home() -> None:
    agent = FakeAgent(
        [
            _home(),
            _type_screen(),
            _idol_screen(),
            _time_screen(),
            _start_screen(),
            _screen(("close", 20, 120)),
            _home(),
        ]
    )

    result = WorkTask().run(agent)

    assert result.ok is True
    assert result.message == "工作已开始，已回到主页"
    assert [name for name, _ in agent.clicks][-2:] == ["work_start", "close"]


def test_start_with_home_tab_left_over_returns_home() -> None:
    agent = FakeAgent(
        [
            _home(),
            _type_screen(),
            _idol_screen(),
            _time_screen(),
            _start_screen(),
            _screen(
                ("work_choose_show", 80, 650),
                ("work_choose_live", 390, 650),
                ("home_tab", 300, 1160),
            ),
            _home(),
        ]
    )

    result = WorkTask().run(agent)

    assert result.ok is True
    assert result.message == "工作已开始，已回到主页"
    assert [name for name, _ in agent.clicks][-2:] == ["work_start", "home_tab"]


def test_missing_work_entry_fails_with_step() -> None:
    agent = FakeAgent([_home(with_entry=False)])

    result = WorkTask().run(agent)

    assert result.ok is False
    assert "工作入口" in result.message


def test_not_home_fails_before_entry() -> None:
    agent = FakeAgent([_screen()])

    result = WorkTask().run(agent)

    assert result.ok is False
    assert "不在主页" in result.message


def test_stuck_at_time_selection_reports_step() -> None:
    agent = FakeAgent(
        [
            _home(),
            _type_screen(),
            _idol_screen(),
            _time_screen(),
            _screen(),
        ]
    )

    result = WorkTask().run(agent)

    assert result.ok is False
    assert "确认时长" in result.message
    assert [name for name, _ in agent.clicks][-1] == "work_sure"


def test_popup_on_home_is_closed_before_entry() -> None:
    agent = FakeAgent(
        [
            _screen(("home", 235, 963), ("close", 250, 1120)),
            _home(),
            _type_screen(),
            _idol_screen(),
            _time_screen(),
            _start_screen(),
            _home(),
        ]
    )

    result = WorkTask().run(agent)

    assert result.ok is True
    assert [name for name, _ in agent.clicks][:2] == ["close", "work_entry"]
