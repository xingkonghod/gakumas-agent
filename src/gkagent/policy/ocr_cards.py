"""OCR 读卡决策：点开卡牌详情 → OCR 卡名/效果 → 查本地卡库打分。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gkagent.data.cards_db import CardLibrary, score_text
from gkagent.vision.ocr import OcrEngine


@dataclass(frozen=True)
class CardReading:
    name: str
    text: str
    value: float
    efficiency: float


class OcrCardPolicy:
    def __init__(
        self,
        engine: OcrEngine,
        library: CardLibrary,
        detail_roi: tuple[int, int, int, int] | None = None,
    ) -> None:
        self.engine = engine
        self.library = library
        self.detail_roi = detail_roi

    def read(self, image: np.ndarray, cost: float | None = None) -> CardReading:
        lines = self.engine.read(image, self.detail_roi)
        for line in lines:
            info = self.library.find(line.text)
            if info is not None:
                return CardReading(info.name, info.text, info.value, info.efficiency(cost))
        joined = " ".join(line.text for line in lines)
        value = score_text(joined)
        efficiency = value / float(cost) if cost else value
        return CardReading("", joined, value, efficiency)

    @staticmethod
    def best(readings: list[tuple[int, CardReading]]) -> tuple[int, CardReading] | None:
        if not readings:
            return None
        return max(readings, key=lambda item: item[1].efficiency)
