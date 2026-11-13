"""手牌卡名选牌：离线单元测试。"""

from __future__ import annotations

from types import SimpleNamespace

from gkagent.vision.hand_names import pick_hand_card
from gkagent.vision.ocr import OcrLine


class FakeLibrary:
    def __init__(self, values: dict[str, float]) -> None:
        self.values = values

    def find(self, name: str):
        if name not in self.values:
            return None
        value = self.values[name]
        return SimpleNamespace(value=value, efficiency=lambda cost: value / (cost or 1))


def test_picks_highest_value_card() -> None:
    lines = [
        OcrLine("魅力的基础", 0.9, (80, 1010, 120, 30)),
        OcrLine("想象的基础", 0.9, (280, 1010, 120, 30)),
    ]
    boxes = [(60, 860, 160, 200), (260, 860, 160, 200)]
    library = FakeLibrary({"魅力的基础": 9.0, "想象的基础": 3.0})
    pick = pick_hand_card(lines, boxes, library)
    assert pick is not None
    assert pick.name == "魅力的基础"
    assert pick.point == (140, 960)


def test_skips_unaffordable_card() -> None:
    lines = [
        OcrLine("猛烈地", 0.9, (80, 1010, 120, 30)),
        OcrLine("想象的基础", 0.9, (280, 1010, 120, 30)),
    ]
    boxes = [(60, 860, 160, 200), (260, 860, 160, 200)]
    library = FakeLibrary({"猛烈地": 20.0, "想象的基础": 3.0})
    pick = pick_hand_card(lines, boxes, library, stamina=5, costs=[30, 2])
    assert pick is not None
    assert pick.name == "想象的基础"


def test_returns_none_without_known_names() -> None:
    lines = [OcrLine("随便写写", 0.9, (80, 1010, 120, 30))]
    boxes = [(60, 860, 160, 200)]
    library = FakeLibrary({})
    assert pick_hand_card(lines, boxes, library) is None
