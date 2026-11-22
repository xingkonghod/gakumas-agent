"""F#43 回归：外出饮料选择屏「result-tap/gain 连点 10 次」→ 必须点选项行推进。

真机现象（ep-t3-4 steps 20–29）：外出事件剧情放完后进入饮料选择屏
（ヨーグルトパフェ -100P / つくねハンバーグ -50P / ドリンクバー 免费），
bot 每步都点屏幕中央 (360,1000)（对话区，点了没反应），同一动作
``result-tap/gain`` 连续 10 次触发自保护停局。

根因（见 docs/FAILURES.md #43）：
1. 旧中文 OCR 字典没有假名，三条日文选项行**一条都读不出** → ``option_rows=0``，
   事件屏识别不出来（F#41 同类问题）；
2. 飘字正则 ``[+\\-]\\s*\\d+`` 把右侧 P 费标签「-100 / -50」当成 +N 飘字 →
   走进 4.5) 的 ``result-tap/gain`` 分支，点屏幕中央空转。

本文件用真机帧跑生产链路（``ProduceDriver.read_fast`` → ``decide``，日文 OCR 模型）：
选项行必须被识别成 ``event-choice`` 并点第 3 行（免费项 ドリンクバー），不能点中央空转；
再加合成单测守住「P 费不是飘字」「P 费标签定位免费项」「静态结果页第 3 次起找按钮」三条防线。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from gkagent.tasks import produce_ui
from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrLine

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ocr_jp.example.yaml"
MODEL_DIR = ROOT / "data" / "models" / "ocr_jp"
FRAME = ROOT / "tests" / "fixtures" / "event_ep_t3_4_drink_choice.png"

pytestmark = [
    pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml"),
    pytest.mark.skipif(
        not all((MODEL_DIR / name).is_file() for name in ("det.onnx", "rec.onnx", "keys.txt")),
        reason="缺少日文 OCR 模型（先跑 scripts/download_ocr_models.py）",
    ),
    pytest.mark.skipif(not FRAME.is_file(), reason="缺少 F#43 饮料选择屏 fixture"),
]


@dataclass
class FakeDevice:
    clicks: list[tuple[int, int]] = field(default_factory=list)

    def click_force(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)


@pytest.fixture(scope="module")
def ocr():
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2  # noqa: F401 - 确认 cv2 可用

    from gkagent.vision.ocr import OcrEngine

    return OcrEngine(config_path=CONFIG)


@pytest.fixture(scope="module")
def drink_frame(ocr):
    """(真机图像, 生产快速读屏 lines)；10 帧同一屏，取 step_021 做 fixture。"""
    import cv2

    image = cv2.imread(str(FRAME))
    assert image is not None
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    lines = driver.read_fast(image)
    return image, lines


def test_ep_t3_4_drink_choice_is_event_choice_not_gain(ocr, drink_frame) -> None:
    """DoD：真机饮料选择屏要判成 event-choice 并点第 3 行（免费项），不是点中央空转。"""
    image, lines = drink_frame
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    agent = FakeAgent()
    tick = driver.decide(agent, lines, image)
    assert tick.screen == "event-choice", tick.describe()
    assert tick.action == "last-row"
    assert agent.device.clicks, "必须真的点一下选项"
    x, y = agent.device.clicks[-1]
    assert x == 360
    # 三行：ヨーグルトパフェ / つくねハンバーグ / ドリンクバー（免费、默认高亮）
    assert 860 <= y <= 980, f"应点最下面那行选项，实际 y={y}"
    assert (x, y) != (360, 1000), "旧实现点屏幕中央（对话区）推不动这一屏"


def test_ep_t3_4_drink_choice_second_click_confirms(ocr, drink_frame) -> None:
    """选中后再点同一点确认（和 ep-t1-h/i 事件屏同一套两步点击）。"""
    image, lines = drink_frame
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    agent = FakeAgent()
    first = driver.decide(agent, lines, image)
    second = driver.decide(agent, lines, image)
    assert first.screen == "event-choice" and first.action == "last-row"
    assert second.screen == "event-choice" and second.action == "confirm"
    assert agent.device.clicks[-2] == agent.device.clicks[-1]
    assert driver.event_pending_y is None


def test_ep_t3_4_ten_consecutive_frames_never_result_tap(ocr, drink_frame) -> None:
    """复现 F#43：同一屏连续 10 步绝不能再出现 result-tap/gain（旧日志 10 连点停机）。"""
    image, lines = drink_frame
    driver = ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)
    agent = FakeAgent()
    ticks = [driver.decide(agent, lines, image) for _ in range(10)]
    screens = {tick.screen for tick in ticks}
    assert screens == {"event-choice"}, screens
    assert all(tick.ok for tick in ticks)
    assert all((x, y) != (360, 1000) for x, y in agent.device.clicks)


# ---- 合成单测（不依赖 OCR 模型）：守住 F#43 的两条根因 ---------------------
def test_negative_p_cost_labels_are_not_gain_floats() -> None:
    """根因 2：P 费标签「-100 / -50」不能被飘字正则命中（否则事件屏被当结果页）。"""
    assert not produce_ui._GAIN_RE.search("P -100 P -50")
    assert not produce_ui._GAIN_RE.search("-100")
    assert produce_ui._GAIN_RE.search("P+45")
    assert produce_ui._GAIN_RE.search("打分+38")


def test_event_screen_with_unreadable_options_uses_cost_labels() -> None:
    """根因 1 的退化场景：选项文字全读不出时，用「最后一个 P 费标签 + 138px」点免费项。"""
    driver = ProduceDriver(sleep=lambda _seconds: None)
    agent = FakeAgent()
    lines = [
        OcrLine("外出", 0.9, (90, 51, 45, 26)),
        OcrLine("-100", 0.9, (598, 648, 64, 28)),
        OcrLine("-50", 0.9, (612, 750, 49, 26)),
        OcrLine("快进", 0.9, (584, 1187, 81, 28)),
        OcrLine("そこまで真剣だと慰労を超えますが……", 0.9, (76, 978, 474, 31)),
    ]
    tick = driver.decide(agent, lines)
    assert tick.screen == "event-choice", tick.describe()
    assert tick.action == "last-row"
    # -50 标签中心 y=763 → 免费（无费用）选项 y≈901
    assert agent.device.clicks[-1] == (360, 901)


def test_static_result_page_third_tick_clicks_next_button() -> None:
    """静态结果页：前两下点中央，第 3 下改找「下一步」按钮（WORKPLAN A3 的修法）。"""
    driver = ProduceDriver(sleep=lambda _seconds: None)
    agent = FakeAgent()
    lines = [
        OcrLine("结果", 0.9, (40, 60, 200, 40)),
        OcrLine("上升了58!", 0.9, (40, 120, 200, 40)),
        OcrLine("下一步", 0.9, (300, 1150, 120, 40)),
    ]
    driver.decide(agent, lines)
    driver.decide(agent, lines)
    tick = driver.decide(agent, lines)
    assert tick.screen == "result-tap"
    assert tick.action == "next"
    assert agent.device.clicks[-1] == (360, 1170)  # 「下一步」按钮中心
    assert driver.gain_waits == 0


def test_static_result_page_without_button_keeps_looking_and_taps_center() -> None:
    """找不到按钮时继续点中央推进，但保持计数（下一帧继续找，不再回到 0 重数）。"""
    driver = ProduceDriver(sleep=lambda _seconds: None)
    agent = FakeAgent()
    lines = [OcrLine("上升了58!", 0.9, (40, 120, 200, 40))]
    driver.gain_waits = 2
    tick = driver.decide(agent, lines)
    assert tick.screen == "result-tap"
    assert tick.action == "next"
    assert agent.device.clicks[-1] == (360, 1000)
    assert driver.gain_waits == 3
