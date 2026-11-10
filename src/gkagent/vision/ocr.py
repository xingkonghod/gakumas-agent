"""OCR 封装（RapidOCR）：读 720x1280 游戏截图里的中文/日文。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    box: tuple[int, int, int, int]


class OcrEngine:
    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def read(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> list[OcrLine]:
        target = image
        off_x = off_y = 0
        if roi is not None:
            x, y, w, h = roi
            target = image[y : y + h, x : x + w]
            off_x, off_y = x, y
        result, _ = self._engine(target)
        lines: list[OcrLine] = []
        for box, text, score in result or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x0, y0 = int(min(xs)) + off_x, int(min(ys)) + off_y
            x1, y1 = int(max(xs)) + off_x, int(max(ys)) + off_y
            lines.append(OcrLine(str(text), float(score), (x0, y0, x1 - x0, y1 - y0)))
        return lines

    def text(self, image: np.ndarray, roi: tuple[int, int, int, int] | None = None) -> str:
        return " ".join(line.text for line in self.read(image, roi))
