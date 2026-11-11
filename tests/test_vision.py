from __future__ import annotations

import numpy as np

from gkagent.nav import Navigator
from gkagent.vision.ocr import OcrEngine, OcrLine
from gkagent.vision.recognize import ScreenRecognizer, ScreenType


class FakeRapid:
    def __init__(self, boxes):
        self.boxes = boxes

    def __call__(self, image):
        return self.boxes, None


def test_ocr_upscale_maps_boxes_back() -> None:
    boxes = [
        ([[20, 20], [120, 20], [120, 60], [20, 60]], "测试", 0.9),
    ]
    engine = OcrEngine(engine=FakeRapid(boxes), scale=2.0, min_score=0.4)
    lines = engine.read(np.zeros((100, 100, 3), dtype=np.uint8))
    assert len(lines) == 1
    assert lines[0].text == "测试"
    x, y, w, h = lines[0].box
    assert (x, y, w, h) == (10, 10, 50, 20)


def test_ocr_filters_low_confidence() -> None:
    boxes = [([[0, 0], [10, 0], [10, 10], [0, 10]], "low", 0.1)]
    engine = OcrEngine(engine=FakeRapid(boxes), scale=1.0, min_score=0.5)
    assert engine.read(np.zeros((50, 50, 3), dtype=np.uint8)) == []


class FakeOcr:
    def __init__(self, texts: list[str]):
        self._lines = [OcrLine(text, 0.9, (10, 10 * i, 100, 20)) for i, text in enumerate(texts)]

    def read(self, image=None, roi=None):
        return self._lines

    def find(self, needle, image=None, roi=None):
        return next((line for line in self._lines if needle in line.text), None)


def test_recognizer_home() -> None:
    recognizer = ScreenRecognizer(ocr=FakeOcr(["亲密度", "活动经费", "任务", "商店"]))
    result = recognizer.recognize(np.zeros((1280, 720, 3), dtype=np.uint8))
    assert result.screen is ScreenType.HOME
    assert result.confidence >= 0.5


class FakeDevice:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class FakeAgent:
    def __init__(self) -> None:
        self.device = FakeDevice()
        self.shots = 0

    def shot(self):
        self.shots += 1
        value = 0 if self.shots == 1 else 255
        return np.full((20, 20, 3), value, dtype=np.uint8)


def test_click_verified_detects_change() -> None:
    agent = FakeAgent()
    nav = Navigator(agent, ocr=FakeOcr([]))
    line = OcrLine("按钮", 0.9, (100, 100, 80, 30))
    assert nav.click_verified(line) is True
    assert agent.device.clicks
