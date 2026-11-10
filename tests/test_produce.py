"""ProduceTask 的离线测试：模板自匹配、真实截图选择页、SSR 配置、主循环。

真实截图在 data/ 下，可能被其它抓图脚本覆盖；如果已经不再包含 SSR 选择页，
对应测试会 skip，不影响 ``uv run pytest tests/test_produce.py -q``。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from gkagent.contract.models import Card
from gkagent.policy.router import Recommendation, RuleCardPolicy
from gkagent.tasks.produce import HandState, ProduceStage, ProduceTask
from gkagent.vision.matcher import Match, TemplateMatcher

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DATA = ROOT / "data"

NEW_TEMPLATES = (
    "produce_entry",
    "produce_ssr_title",
    "produce_get",
    "produce_exchange",
    "produce_cancel",
    "produce_cancel_cn",
    "produce_decide",
    "produce_close",
    "produce_next",
    "produce_finished",
    "produce_continue",
    "produce_start",
    "produce_recommend",
    "produce_event",
    "produce_event_recommend",
    "produce_auto_support",
    "produce_checkbox",
    "produce_support_replace",
    "produce_mainpage_ranking",
    "produce_scenario_hajime",
    "produce_scenario_hif",
    "produce_scenario_nia",
    "produce_health",
    "produce_skip_round",
    "produce_round_close",
    "produce_cards_get",
)


# ------------------------------------------------------------------ 测试工具


def _task(**overrides) -> ProduceTask:
    """测试默认不等待、不 sleep；需要跨多屏时靠 FakeAgent 立即换屏。"""
    options = {
        "poll_interval": 0.0,
        "click_delay": 0.0,
        "entry_timeout": 0.0,
        "selector_timeout": 0.0,
        "prepare_timeout": 0.0,
        "main_timeout": 0.0,
        "max_steps": 20,
        "max_panel_steps": 8,
        "get_retry": 0.0,
        "sleep": lambda _seconds: None,
    }
    options.update(overrides)
    return ProduceTask(**options)


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


def _screen(*placements: tuple[str, int, int], size: tuple[int, int] = (720, 1280)) -> np.ndarray:
    """浅灰底，把模板贴到指定坐标，模拟一个界面。"""
    width, height = size
    image = np.full((height, width, 3), 245, dtype=np.uint8)
    for name, x, y in placements:
        template = _load_template(name)
        h, w = template.shape[:2]
        assert x + w <= width and y + h <= height, f"{name} at ({x},{y}) out of screen"
        image[y : y + h, x : x + w] = template
    return image


def _home() -> np.ndarray:
    # home.png 是主页上的「プロデュース」文字；produce_entry.png 与它同源。
    return _screen(("home", 235, 963))


def _ssr_select(*extra: tuple[str, int, int]) -> np.ndarray:
    return _screen(("produce_ssr_title", 60, 18), ("produce_get", 390, 1075), *extra)


def _scenario() -> np.ndarray:
    return _screen(
        ("produce_scenario_hajime", 240, 240),
        ("produce_mainpage_ranking", 500, 1050),
    )


def _support_auto() -> np.ndarray:
    return _screen(("produce_auto_support", 560, 970))


def _support_checkbox() -> np.ndarray:
    return _screen(("produce_checkbox", 480, 960))


def _support_next() -> np.ndarray:
    return _screen(("produce_next", 300, 1050))


def _card_play() -> np.ndarray:
    return _screen(("produce_recommend", 300, 600), ("produce_health", 550, 140))


def _event() -> np.ndarray:
    return _screen(("produce_event", 50, 850), ("produce_event_recommend", 300, 700))


def _finished() -> np.ndarray:
    return _screen(("produce_finished", 250, 700))


def _real(relative: str) -> np.ndarray:
    path = DATA / relative
    if not path.exists():
        pytest.skip(f"真实截图不存在: {path}")
    image = cv2.imread(str(path))
    assert image is not None
    return image


def _real_selection(relative: str) -> np.ndarray:
    """只接受当前仍然是 SSR 选择页的真实截图，避免被其它抓图脚本干扰。"""
    image = _real(relative)
    match = TemplateMatcher(TEMPLATES).find(
        "produce_ssr_title",
        image,
        roi=(0, 0, 720, 100),
        threshold=ProduceTask.thresholds["produce_ssr_title"],
    )
    if match is None:
        pytest.skip(f"{relative} 已不是 SSR 选择页（可能被其它脚本覆盖）")
    return image


class FakeDevice:
    """记录 device.click(x, y) 并换到下一屏。"""

    def __init__(self, agent: FakeAgent) -> None:
        self.agent = agent

    def click(self, x: int, y: int) -> None:
        self.agent.points.append((x, y))
        self.agent.advance()


class FakeAgent:
    """按脚本逐屏推进的 Agent：click/device.click 一次就换到下一屏。"""

    def __init__(self, screens: list[np.ndarray]) -> None:
        self.matcher = TemplateMatcher(TEMPLATES)
        self.screens = screens
        self.index = 0
        self.clicks: list[tuple[str, tuple[int, int]]] = []
        self.points: list[tuple[int, int]] = []
        self.device = FakeDevice(self)

    @property
    def current(self) -> np.ndarray:
        return self.screens[min(self.index, len(self.screens) - 1)]

    def shot(self) -> np.ndarray:
        return self.current

    def find(
        self,
        name: str,
        image: np.ndarray | None = None,
        roi: tuple[int, int, int, int] | None = None,
        threshold: float | None = None,
    ) -> Match | None:
        target = self.current if image is None else image
        return self.matcher.find(name, target, roi=roi, threshold=threshold)

    def advance(self) -> None:
        if self.index < len(self.screens) - 1:
            self.index += 1

    def click(self, match: Match) -> None:
        self.clicks.append((match.name, match.center))
        self.advance()

    def ensure_home(self, attempts: int = 4) -> bool:
        for _ in range(attempts):
            if self.matcher.find("home", self.current, threshold=0.85) is not None:
                return True
            tab = self.matcher.find("home_tab", self.current, threshold=0.9)
            if tab is None:
                return False
            self.click(tab)
        return False

    def close_popup(self, image: np.ndarray | None = None) -> bool:
        target = self.current if image is None else image
        for name in ("close", "decide"):
            match = self.matcher.find(name, target, threshold=0.85)
            if match is not None:
                self.click(match)
                return True
        return False


# ------------------------------------------------------------------ 模板


@pytest.mark.parametrize("name", NEW_TEMPLATES)
def test_produce_templates_exist_and_self_match(name: str) -> None:
    path = TEMPLATES / f"{name}.png"
    assert path.exists(), path
    image = _load_template(name)
    match = TemplateMatcher(TEMPLATES).find(name, image)
    assert match is not None
    assert match.score > 0.99
    assert match.box[:2] == (0, 0)


def test_task_contract() -> None:
    task = ProduceTask()
    assert task.name == "produce"
    for attr in ("run", "observe", "classify", "decide_card", "read_hand"):
        assert hasattr(task, attr)


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError):
        ProduceTask(selection_action="bogus")
    with pytest.raises(ValueError):
        ProduceTask(scenario="bogus")


def test_hand_reader_enables_rule_policy() -> None:
    task = _task(hand_reader=lambda _image: HandState())
    assert isinstance(task.card_policy, RuleCardPolicy)


# ------------------------------------------------------------------ 真实截图


def test_real_home_screenshot_has_produce_entry() -> None:
    image = _real("live_before.png")
    matcher = TemplateMatcher(TEMPLATES)
    match = matcher.find("produce_entry", image, threshold=0.85)
    if match is None:
        pytest.skip("live_before.png 已不是当前中文主页（可能被其它脚本覆盖）")
    # 主页截图会被 live_check 覆盖；只校验「主页入口在左中下区域」。
    assert match.center[0] > 200
    assert match.center[1] > 800

    screen = _task().observe(FakeAgent([image]), image)
    assert screen.stage == ProduceStage.HOME
    assert screen.produce_entry is not None


@pytest.mark.parametrize(
    "relative",
    ["sel_after.png", "ssr/ssr_00.png", "ssr/ssr_10.png"],
)
def test_real_selection_screenshot_is_recognized(relative: str) -> None:
    image = _real_selection(relative)
    screen = _task().observe(FakeAgent([image]), image)

    assert screen.stage == ProduceStage.SSR_SELECT
    assert screen.ssr_title is not None
    assert screen.ssr_title.score >= ProduceTask.thresholds["produce_ssr_title"]
    assert screen.get is not None
    assert screen.get.score >= ProduceTask.thresholds["produce_get"]
    # 获取按钮在下半屏右侧；不能误点到左上角标题。
    assert screen.get.center[0] > 300
    assert screen.get.center[1] > 1000


# ------------------------------------------------------------------ 选择页


def test_observe_selection_page_and_get_button() -> None:
    image = _ssr_select()
    agent = FakeAgent([image])
    screen = _task().observe(agent, image)

    assert screen.stage == ProduceStage.SSR_SELECT
    assert screen.ssr_title is not None
    assert screen.get is not None
    assert screen.get.center == (435, 1102)


def test_selection_action_get_clicks_get_then_enters_scenario() -> None:
    agent = FakeAgent([_ssr_select(), _scenario()])
    result = _task()._select_ssr(agent)

    assert result.ok is True
    assert [name for name, _ in agent.clicks] == ["produce_get"]


def test_get_confirm_clicks_decide_before_scenario() -> None:
    agent = FakeAgent(
        [
            _ssr_select(),
            _screen(("decide", 250, 1080)),
            _scenario(),
        ]
    )
    result = _task()._select_ssr(agent)

    assert result.ok is True
    assert [name for name, _ in agent.clicks] == ["produce_get", "decide"]


def test_selection_action_exchange_is_configurable() -> None:
    image = _screen(("produce_ssr_title", 60, 18), ("produce_exchange", 260, 1100))
    agent = FakeAgent([image, _home()])

    result = _task(selection_action="exchange").run(agent)

    assert result.ok is True
    assert "变换" in result.message
    assert [name for name, _ in agent.clicks] == ["produce_exchange"]


def test_selection_action_cancel_is_configurable() -> None:
    image = _screen(("produce_ssr_title", 60, 18), ("produce_cancel", 260, 1100))
    agent = FakeAgent([image, _home()])

    result = _task(selection_action="cancel").run(agent)

    assert result.ok is True
    assert "取消" in result.message
    assert [name for name, _ in agent.clicks] == ["produce_cancel"]


def test_selection_action_cancel_supports_chinese_template() -> None:
    image = _screen(("produce_ssr_title", 60, 18), ("produce_cancel_cn", 260, 1100))
    agent = FakeAgent([image, _home()])

    result = _task(selection_action="cancel").run(agent)

    assert result.ok is True
    assert [name for name, _ in agent.clicks] == ["produce_cancel_cn"]


def test_stuck_on_ssr_selection_reports_stage() -> None:
    agent = FakeAgent([_ssr_select()])

    result = _task(max_get_clicks=2).run(agent)

    assert result.ok is False
    assert "SSR偶像选择" in result.message
    assert [name for name, _ in agent.clicks] == ["produce_get", "produce_get"]


def test_stuck_after_get_reports_stage() -> None:
    agent = FakeAgent([_home(), _ssr_select(), _screen()])

    result = _task().run(agent)

    assert result.ok is False
    assert "SSR偶像选择" in result.message


# ------------------------------------------------------------------ 主循环


def test_full_produce_flow_from_home_to_home() -> None:
    agent = FakeAgent(
        [
            _home(),
            _real_selection("sel_after.png"),
            _scenario(),
            _support_auto(),
            _support_checkbox(),
            _support_next(),
            _card_play(),
            _event(),
            _finished(),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert "已回到主页" in result.message
    names = [name for name, _ in agent.clicks]
    assert names == [
        "produce_entry",
        "produce_get",
        "produce_scenario_hajime",
        "produce_auto_support",
        "produce_checkbox",
        "produce_next",
        "produce_event_recommend",
        "produce_finished",
    ]
    # 出牌走 device.click(推荐按钮中心)，不走 agent.click。
    assert agent.points == [(357, 618)]


def test_run_resumes_inside_produce() -> None:
    agent = FakeAgent([_scenario(), _card_play(), _home()])

    result = _task().run(agent)

    assert result.ok is True
    assert [name for name, _ in agent.clicks] == ["produce_scenario_hajime"]
    assert agent.points == [(357, 618)]


def test_support_replace_is_cancelled() -> None:
    agent = FakeAgent(
        [
            _screen(("produce_support_replace", 40, 500), ("produce_cancel", 250, 1100)),
            _card_play(),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert [name for name, _ in agent.clicks][:1] == ["produce_cancel"]


def test_card_decision_falls_back_to_recommend_template() -> None:
    image = _card_play()
    play = _task().decide_card(FakeAgent([image]), image)

    assert play is not None
    assert play.source == "template:recommend"
    assert play.point == (357, 618)


def test_card_decision_falls_back_to_first_hand_card() -> None:
    image = _hand_screen(2)
    play = _task().decide_card(FakeAgent([image]), image)

    assert play is not None
    assert play.source == "first_hand_card"
    assert play.point == (95, 1095)


def test_card_decision_delegates_to_policy() -> None:
    boxes = ((40, 980, 100, 200), (160, 980, 100, 200))
    hand = HandState(
        cards=(Card(card_id="a"), Card(card_id="b")),
        boxes=boxes,
    )

    class FakeRecommender:
        def __init__(self) -> None:
            self.obs = None

        def recommend(self, obs):
            self.obs = obs
            return Recommendation(index=1, confidence=1.0, reason="fake")

    recommender = FakeRecommender()
    task = _task(card_policy=recommender, hand_reader=lambda _image: hand)
    image = _card_play()
    play = task.decide_card(FakeAgent([image]), image)

    assert play is not None
    assert play.index == 1
    assert play.point == (210, 1080)
    assert play.source.startswith("policy")
    assert recommender.obs is not None
    assert [card.card_id for card in recommender.obs.hand] == ["a", "b"]


def test_event_without_recommend_clicks_first_option() -> None:
    agent = FakeAgent([_screen(("produce_event", 50, 850)), _home()])

    result = _task()._play_main(agent)

    assert result.ok is True
    assert agent.points == [(222, 886)]


def test_settlement_clicks_next_and_close() -> None:
    agent = FakeAgent(
        [
            _screen(("produce_next", 250, 1050)),
            _screen(("close", 250, 1050)),
            _home(),
        ]
    )

    result = _task()._play_main(agent)

    assert result.ok is True
    assert [name for name, _ in agent.clicks] == ["produce_next", "close"]


def test_prepare_stuck_reports_stage() -> None:
    result = _task()._prepare(FakeAgent([_screen()]))

    assert result.ok is False
    assert "场景选择" in result.message


def test_main_loop_stuck_fails_bounded() -> None:
    result = _task()._play_main(FakeAgent([_screen()]))

    assert result.ok is False
    assert "培育主界面" in result.message


def test_not_home_fails_before_entry() -> None:
    result = _task().run(FakeAgent([_screen()]))

    assert result.ok is False
    assert "主页" in result.message


def test_home_popup_is_closed_before_produce_entry() -> None:
    agent = FakeAgent(
        [
            _screen(("home", 235, 963), ("close", 250, 1120)),
            _home(),
            _real_selection("sel_after.png"),
            _scenario(),
            _card_play(),
            _home(),
        ]
    )

    result = _task().run(agent)

    assert result.ok is True
    assert [name for name, _ in agent.clicks][:3] == ["close", "produce_entry", "produce_get"]


# ------------------------------------------------------------------ 手牌/OCR


def _hand_screen(count: int = 4) -> np.ndarray:
    image = np.full((1280, 720, 3), 235, dtype=np.uint8)
    for index in range(count):
        x = 35 + index * 150
        cv2.rectangle(image, (x, 980), (x + 120, 1210), (30, 30, 30), 3)
        cv2.rectangle(image, (x + 10, 1000), (x + 110, 1150), (180, 120, 200), -1)
        cv2.putText(
            image,
            str(index + 1),
            (x + 15, 1010),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )
    return image


def test_read_hand_detects_boxes_and_cost() -> None:
    image = _hand_screen(4)
    hand = _task().read_hand(image)

    assert len(hand.boxes) == 4
    assert len(hand.cards) == 4
    assert all(card.cost is None for card in hand.cards)

    priced = _task(text_reader=lambda _image, _roi=None: ["2"]).read_hand(image)
    assert len(priced.cards) == 4
    assert all(card.cost == 2 for card in priced.cards)


def test_ocr_fallback_recognizes_selection_page() -> None:
    def reader(_image, roi=None):
        if roi is not None and roi[1] < 100:
            return ["SSRプロデュースアイドルを選んでください"]
        return ["获取"]

    image = _screen()
    screen = _task(text_reader=reader).observe(FakeAgent([image]), image)

    assert screen.stage == ProduceStage.SSR_SELECT
    assert screen.ssr_title is not None
    assert screen.get is not None
    assert screen.get.center == (360, 1100)


def test_ocr_fallback_recognizes_support_page() -> None:
    def reader(_image, roi=None):
        if roi is not None and roi[1] > 900:
            return ["おまかせ"]
        return []

    image = _screen()
    screen = _task(text_reader=reader).observe(FakeAgent([image]), image)

    assert screen.stage == ProduceStage.SUPPORT
    assert screen.auto_support is not None


def test_ocr_fallback_recognizes_chinese_next_button() -> None:
    """中文 UI 的「下一步」大按钮和 MAA next.png 不同，靠 OCR 兜底。"""

    def reader(_image, roi=None):
        if roi is not None and roi[1] >= 1000:
            return ["下一步"]
        return []

    image = _screen()
    screen = _task(text_reader=reader).observe(FakeAgent([image]), image)

    assert screen.stage == ProduceStage.RESULT
    assert screen.next_step is not None
    assert screen.next_step.center == (360, 1140)

