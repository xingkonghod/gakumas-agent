from __future__ import annotations

import numpy as np

from gkagent.data.cards_db import CardInfo
from gkagent.tasks.upgrade import Owned, UpgradeTask
from gkagent.vision.ocr import OcrLine


class FakeDevice:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class FakeAgent:
    def __init__(self) -> None:
        self.device = FakeDevice()

    def shot(self):
        return np.zeros((1280, 720, 3), dtype=np.uint8)

    def ensure_home(self) -> bool:
        return True


class FakeOcr:
    def __init__(self, lines: list[OcrLine]) -> None:
        self._lines = lines

    def read(self, image=None, roi=None) -> list[OcrLine]:
        return self._lines


class FakeCards:
    def find(self, text: str):
        if "ふわふわ" in text:
            return CardInfo("x", "ふわふわでワクワク", "test", 1.0)
        return None


class FakeItems:
    def find(self, text: str):
        return None


def sample_lines() -> list[OcrLine]:
    return [
        OcrLine("支援卡", 0.9, (300, 900, 80, 30)),
        OcrLine("培养P偶像", 0.9, (500, 800, 120, 30)),
        OcrLine("强化", 0.9, (600, 100, 80, 30)),
        OcrLine("ふわふわでワクワク", 0.9, (100, 200, 300, 40)),
        OcrLine("Lv 1", 0.9, (100, 250, 80, 30)),
    ]


def make_task(**kwargs) -> UpgradeTask:
    return UpgradeTask(
        kind="support",
        dry_run=True,
        ocr=FakeOcr(sample_lines()),
        cards=FakeCards(),
        items=FakeItems(),
        **kwargs,
    )


def test_read_owned_level() -> None:
    task = make_task()
    owned = task.read_owned(sample_lines())
    card = next(o for o in owned if o.name == "ふわふわでワクワク")
    assert isinstance(card, Owned)
    assert card.level == 1


def test_dry_run_returns_plan() -> None:
    agent = FakeAgent()
    result = make_task().run(agent)
    assert result.ok
    assert "ふわふわでワクワク" in result.message
    assert agent.device.clicks


def test_click_uses_text_boxes() -> None:
    agent = FakeAgent()
    result = make_task(limit=1).run(agent)
    assert result.ok
    assert any(x > 250 and y > 850 for x, y in agent.device.clicks)
