"""ChallengeTask 的离线测试：模板自匹配、真实截图、状态机推进、次数用完弹窗收尾。

所有界面由 templates/ 里的模板拼出来，不需要游戏窗口；真实截图存在时额外校验
主页入口/竞技场入口页，截图不存在则跳过。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from gkagent.tasks.challenge import ChallengeAction, ChallengeScreen, ChallengeTask
from gkagent.vision.matcher import Match, TemplateMatcher

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
REAL_SCREENSHOTS = Path(r"D:\Games\MaaGakumasu\debug\on_error")

HOME_SCREENSHOT = REAL_SCREENSHOTS / "2026.11.10-17.10.16.217_StartUpHomeFlag.png"
ARENA_SCREENSHOT = REAL_SCREENSHOTS / "2026.11.09-23.38.19.866_ChallengeClick.png"

CHALLENGE_TEMPLATES = (
    "challenge",
    "challenge_battle_total",
    "challenge_start",
    "challenge_skip",
    "challenge_next",
    "challenge_finish",
    "challenge_runout",
    "challenge_award",
    "challenge_homeflag_black",
)


def _load(name: str) -> np.ndarray:
    """按 matcher 的方式读模板：带 alpha 的图先铺白底。"""
    image = cv2.imread(str(TEMPLATES / f"{name}.png"), cv2.IMREAD_UNCHANGED)
    assert image is not None, name
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
        template = _load(name)
        h, w = template.shape[:2]
        image[y : y + h, x : x + w] = template
    return image


def _home() -> np.ndarray:
    return _screen(("home", 235, 963), ("challenge", 451, 1104))


def _arena() -> np.ndarray:
    # 竞技场入口页：主页 banner 消失，底部「主页」是未选中态。
    return _screen(("challenge_homeflag_black", 333, 1121))


def _selector() -> np.ndarray:
    return _screen(
        ("challenge_battle_total", 76, 797),
        ("challenge_start", 260, 1053),
        ("challenge_homeflag_black", 333, 1121),
    )


def _battle() -> np.ndarray:
    return _screen(
        ("challenge_skip", 516, 1033),
        ("challenge_homeflag_black", 333, 1121),
    )


def _result_next() -> np.ndarray:
    return _screen(("challenge_next", 189, 1091))


def _result_finish() -> np.ndarray:
    return _screen(("challenge_finish", 250, 1053))


def _runout() -> np.ndarray:
    return _screen(
        ("challenge_runout", 247, 560),
        ("decide", 250, 900),
        ("challenge_homeflag_black", 333, 1121),
    )


def _runout_close() -> np.ndarray:
    return _screen(
        ("challenge_runout", 247, 560),
        ("close", 250, 900),
        ("challenge_homeflag_black", 333, 1121),
    )


def _runout_over_home() -> np.ndarray:
    """主页被「已耗尽今天的挑战权」弹窗压住：home.png 被遮住，ensure_home 认不出主页。"""
    image = _home()
    runout = _load("challenge_runout")
    decide = _load("decide")
    image[860 : 860 + runout.shape[0], 247 : 247 + runout.shape[1]] = runout
    image[960 : 960 + decide.shape[0], 250 : 250 + decide.shape[1]] = decide
    return image


SCREENS = {
    "home": _home,
    "arena": _arena,
    "arena_plain": lambda: _screen(),
    "selector": _selector,
    "battle": _battle,
    "next": _result_next,
    "finish": _result_finish,
    "runout": _runout,
    "runout_close": _runout_close,
    "runout_home": _runout_over_home,
    "blank": lambda: _screen(),
}


class ImageAgent:
    """只有一帧截图的 Agent，用来跑 observe()/真实截图。"""

    def __init__(self, image: np.ndarray) -> None:
        self.image = image
        self.matcher = TemplateMatcher(TEMPLATES)

    def shot(self) -> np.ndarray:
        return self.image

    def find(self, name: str, image=None, roi=None, threshold=None) -> Match | None:
        target = self.image if image is None else image
        return self.matcher.find(name, target, roi=roi, threshold=threshold)


class FakeDevice:
    def __init__(self, agent: FakeAgent) -> None:
        self._agent = agent

    def click(self, x: int, y: int) -> None:
        self._agent.device_clicks.append((x, y))
        if (x, y) == ChallengeTask.arena_entry_point and self._agent.arena_point_works:
            self._agent.state = "selector"
        elif (x, y) == ChallengeTask.home_tab_point and self._agent.home_tab_works:
            self._agent.state = "home"

    def swipe(self, *args, **kwargs) -> None:  # pragma: no cover - 本任务不用滑动
        pass


class FakeAgent:
    """带状态迁移的 Agent：点击某个模板后切到下一屏，用来测循环/收尾。"""

    def __init__(
        self,
        *,
        initial: str = "home",
        rounds_until_runout: int = 1,
        arena_page: bool = True,
        after_decide: str = "home",
        skip_advances: bool = True,
        arena_point_works: bool = True,
        home_tab_works: bool = True,
    ) -> None:
        self.matcher = TemplateMatcher(TEMPLATES)
        self.state = initial
        self.rounds_until_runout = rounds_until_runout
        self.arena_page = arena_page
        self.after_decide = after_decide
        self.skip_advances = skip_advances
        self.arena_point_works = arena_point_works
        self.home_tab_works = home_tab_works
        self.battles_done = 0
        self.clicks: list[str] = []
        self.device_clicks: list[tuple[int, int]] = []
        self.device = FakeDevice(self)
        self._screens = {name: make() for name, make in SCREENS.items()}

    @property
    def image(self) -> np.ndarray:
        return self._screens[self.state]

    def shot(self) -> np.ndarray:
        return self.image

    def find(self, name: str, image=None, roi=None, threshold=None) -> Match | None:
        target = self.image if image is None else image
        return self.matcher.find(name, target, roi=roi, threshold=threshold)

    def click(self, match: Match) -> None:
        self.clicks.append(match.name)
        self._advance(match.name)

    def ensure_home(self, attempts: int = 4) -> bool:
        for _ in range(attempts):
            if self.matcher.find("home", self.image, threshold=0.85) is not None:
                return True
            tab = self.matcher.find("home_tab", self.image, threshold=0.9)
            if tab is None:
                return False
            self.click(tab)
        return False

    def close_popup(self, image=None) -> bool:
        target = self.image if image is None else image
        for name in ("close", "decide"):
            match = self.matcher.find(name, target, threshold=0.85)
            if match is not None:
                self.click(match)
                return True
        return False

    def _advance(self, name: str) -> None:
        if name == "challenge":
            self.state = "arena" if self.arena_page else "selector"
        elif name == "challenge_battle_total":
            return
        elif name == "challenge_start":
            self.state = "battle"
        elif name == "challenge_skip":
            if self.skip_advances:
                self.state = "next"
        elif name == "challenge_next":
            self.state = "finish"
        elif name == "challenge_finish":
            self.battles_done += 1
            self.state = "selector" if self.battles_done < self.rounds_until_runout else "runout"
        elif name in ("decide", "close"):
            self.state = self.after_decide
        elif name == "challenge_homeflag_black":
            self.state = "home"


def _task(**kwargs) -> ChallengeTask:
    kwargs.setdefault("sleep", lambda _seconds: None)
    kwargs.setdefault("poll_interval", 0.0)
    return ChallengeTask(**kwargs)


@pytest.mark.parametrize("name", CHALLENGE_TEMPLATES)
def test_challenge_templates_self_match(name: str) -> None:
    matcher = TemplateMatcher(TEMPLATES)
    image = _load(name)
    match = matcher.find(name, image)
    assert match is not None
    assert match.score > 0.99
    assert match.box[:2] == (0, 0)


def test_task_contract() -> None:
    task = ChallengeTask()
    assert task.name == "challenge"
    assert callable(task.run)


def test_observe_and_decide_are_reusable_without_device() -> None:
    task = _task()
    screen = task.observe(ImageAgent(_selector()))
    assert screen.in_selector is True
    assert screen.start is not None
    action, target = task.decide(screen)
    assert action is ChallengeAction.START
    assert target is screen.start


def test_decide_dismisses_runout_before_anything_else() -> None:
    decide = Match("decide", 250, 900, 220, 59, 0.99)
    skip = Match("challenge_skip", 516, 1033, 128, 40, 0.99)
    screen = ChallengeScreen(runout=Match("challenge_runout", 247, 560, 225, 92, 0.99), decide=decide, skip=skip)
    action, target = _task().decide(screen)
    assert action is ChallengeAction.DISMISS_RUNOUT
    assert target is decide


def test_decide_clicks_skip_during_battle() -> None:
    skip = Match("challenge_skip", 516, 1033, 128, 40, 0.99)
    screen = ChallengeScreen(skip=skip, ready=Match("challenge_ready", 254, 1132, 203, 57, 0.99))
    action, target = _task().decide(screen)
    assert action is ChallengeAction.SKIP
    assert target is skip


def test_decide_goes_home_during_ready_period() -> None:
    screen = ChallengeScreen(ready_period=Match("challenge_ready_period", 20, 100, 247, 67, 0.99))
    action, target = _task().decide(screen)
    assert action is ChallengeAction.GO_HOME
    assert target is None


def test_runs_until_runout_then_returns_home() -> None:
    agent = FakeAgent(rounds_until_runout=2)

    result = _task().run(agent)

    assert result.ok is True
    assert result.message == "今日挑战次数已用完，完成 2 次挑战，已回到主页"
    assert agent.battles_done == 2
    assert agent.state == "home"
    assert agent.device_clicks == [ChallengeTask.arena_entry_point]
    assert agent.clicks == [
        "challenge",
        "challenge_battle_total",
        "challenge_start",
        "challenge_skip",
        "challenge_next",
        "challenge_finish",
        "challenge_battle_total",
        "challenge_start",
        "challenge_skip",
        "challenge_next",
        "challenge_finish",
        "decide",
    ]


def test_runout_popup_on_home_is_dismissed_into_home() -> None:
    agent = FakeAgent(initial="runout_home")

    result = _task().run(agent)

    assert result.ok is True
    assert result.message == "今日挑战次数已用完，已回到主页"
    assert agent.clicks == ["decide"]
    assert agent.device_clicks == []
    assert agent.state == "home"


def test_runout_returns_home_from_arena_via_homeflag() -> None:
    # 对应 MAA 的失败点：点完确定后仍在竞技场页，ensure_home 认不出灰色主页 tab。
    agent = FakeAgent(initial="runout", after_decide="arena")

    result = _task().run(agent)

    assert result.ok is True
    assert agent.clicks == ["decide", "challenge_homeflag_black"]
    assert agent.state == "home"


def test_runout_returns_home_via_fixed_tab_when_flag_missing() -> None:
    agent = FakeAgent(initial="runout", after_decide="arena_plain")

    result = _task().run(agent)

    assert result.ok is True
    assert agent.clicks == ["decide"]
    assert agent.device_clicks == [ChallengeTask.home_tab_point]
    assert agent.state == "home"


def test_runout_popup_with_close_button_is_dismissed() -> None:
    agent = FakeAgent(initial="runout_close", after_decide="arena")

    result = _task().run(agent)

    assert result.ok is True
    assert agent.clicks == ["close", "challenge_homeflag_black"]


def test_direct_selector_does_not_click_arena_entry_point() -> None:
    agent = FakeAgent(arena_page=False)

    result = _task().run(agent)

    assert result.ok is True
    assert agent.device_clicks == []


def test_stops_at_max_rounds_and_returns_home() -> None:
    agent = FakeAgent(rounds_until_runout=99)

    result = _task(max_rounds=2).run(agent)

    assert result.ok is True
    assert result.message == "完成 2 次挑战（未检测到次数用完弹窗）"
    assert agent.battles_done == 2
    assert agent.state == "home"


def test_battle_timeout_reports_step() -> None:
    agent = FakeAgent(skip_advances=False)

    result = _task(battle_timeout=0.05).run(agent)

    assert result.ok is False
    assert "挑战中断" in result.message


def test_not_home_and_no_way_back_fails_before_entry() -> None:
    agent = FakeAgent(initial="blank", home_tab_works=False)

    result = _task(entry_timeout=0.05).run(agent)

    assert result.ok is False
    assert "不在主页" in result.message
    assert "challenge" not in agent.clicks


@pytest.mark.skipif(not HOME_SCREENSHOT.exists(), reason=f"真实截图不存在: {HOME_SCREENSHOT}")
def test_entry_matches_real_chinese_home() -> None:
    image = cv2.imread(str(HOME_SCREENSHOT))
    assert image is not None

    screen = _task().observe(ImageAgent(image))

    assert screen.home is not None
    assert screen.entry is not None
    assert screen.entry.center == (488, 1132)
    assert screen.entry.score >= ChallengeTask.thresholds["challenge"]


@pytest.mark.skipif(not ARENA_SCREENSHOT.exists(), reason=f"真实截图不存在: {ARENA_SCREENSHOT}")
def test_real_arena_page_is_recognized_by_absence_and_homeflag() -> None:
    image = cv2.imread(str(ARENA_SCREENSHOT))
    assert image is not None
    agent = ImageAgent(image)

    screen = _task().observe(agent)

    # 竞技场入口页没有主页 banner，也没有未选中的「竞技场」入口图标；
    # 底部「主页」是未选中态，要靠 homeflag 才能回主页。
    assert screen.home is None
    assert screen.entry is None
    assert screen.in_selector is False
    flag = agent.find(
        "challenge_homeflag_black", roi=ChallengeTask.home_flag_roi, threshold=0.85
    )
    assert flag is not None
    assert flag.center == ChallengeTask.home_tab_point
