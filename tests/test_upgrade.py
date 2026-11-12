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
        OcrLine("培养", 0.9, (520, 890, 60, 30)),
        OcrLine("P偶像", 0.9, (520, 920, 70, 30)),
        OcrLine("查看详情", 0.9, (300, 1070, 100, 30)),
        OcrLine("支援卡加成", 0.9, (220, 910, 100, 20)),
        OcrLine("Lv强化", 0.9, (180, 1070, 90, 30)),
        OcrLine("特训", 0.9, (170, 790, 60, 30)),
        OcrLine("进行特训", 0.9, (470, 1200, 120, 30)),
        OcrLine("特训阶段确认", 0.9, (60, 585, 200, 30)),
        OcrLine("取消", 0.9, (200, 1155, 60, 30)),
        OcrLine("强化", 0.9, (440, 1155, 70, 30)),
        OcrLine("ふわふわでワクワク", 0.9, (100, 200, 300, 40)),
        OcrLine("Lv 1", 0.9, (100, 250, 80, 30)),
    ]


def make_task(**kwargs) -> UpgradeTask:
    kind = kwargs.pop("kind", "support")
    return UpgradeTask(
        kind=kind,
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


def test_support_dry_run_walks_to_confirm_without_spending() -> None:
    agent = FakeAgent()
    result = make_task(limit=1).run(agent)
    assert result.ok, result.message
    assert "支援卡 Lv强化 1 次" in result.message
    assert (455, 1155) not in agent.device.clicks  # dry_run 不点最后的强化


def test_idol_dry_run_walks_to_confirm_without_spending() -> None:
    agent = FakeAgent()
    result = make_task(kind="idol", limit=1).run(agent)
    assert result.ok, result.message
    assert "偶像特训 1 次" in result.message
    assert (522, 1160) not in agent.device.clicks  # dry_run 不点确认弹窗的「进行特训」


def test_click_uses_text_boxes() -> None:
    agent = FakeAgent()
    result = make_task(limit=1).run(agent)
    assert result.ok
    assert any(x > 250 and y > 850 for x, y in agent.device.clicks)
