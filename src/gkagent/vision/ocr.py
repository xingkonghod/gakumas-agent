"""OCR 封装（RapidOCR）：读 720x1280 游戏截图里的中文/日文。

识别逻辑：
1. 可裁剪 ROI，默认放大 2 倍再做检测+识别（小字更准）
2. 丢弃低置信度行
3. 坐标按放大倍率还原到原图
4. 合并重叠的重复行
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    box: tuple[int, int, int, int]


class OcrEngine:
    def __init__(self, engine=None, scale: float = 2.0, min_score: float = 0.4) -> None:
        if engine is None:
            from rapidocr_onnxruntime import RapidOCR

            engine = RapidOCR()
        self._engine = engine
        self.scale = scale
        self.min_score = min_score

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
        if self.scale and self.scale != 1.0:
            target = cv2.resize(
                target,
                None,
                fx=float(self.scale),
                fy=float(self.scale),
                interpolation=cv2.INTER_CUBIC,
            )
        result, _ = self._engine(target)
        lines: list[OcrLine] = []
        for box, text, score in result or []:
            confidence = float(score)
            if confidence < self.min_score:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x0 = int(min(xs) / self.scale) + off_x
            y0 = int(min(ys) / self.scale) + off_y
            x1 = int(max(xs) / self.scale) + off_x
            y1 = int(max(ys) / self.scale) + off_y
            lines.append(OcrLine(str(text).strip(), confidence, (x0, y0, x1 - x0, y1 - y0)))
        return self._dedupe(lines)

    def find(
        self,
        needle: str,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> OcrLine | None:
        for line in self.read(image, roi):
            if needle and needle in line.text:
                return line
        return None

    def text(self, image: np.ndarray, roi: tuple[int, int, int, int] | None = None) -> str:
        return " ".join(line.text for line in self.read(image, roi))

    @staticmethod
    def _dedupe(lines: list[OcrLine]) -> list[OcrLine]:
        kept: list[OcrLine] = []
        for line in sorted(lines, key=lambda item: -item.score):
            duplicate = False
            for other in kept:
                if line.text != other.text:
                    continue
                ax, ay, _, _ = line.box
                bx, by, _, _ = other.box
                if abs(ax - bx) < 12 and abs(ay - by) < 12:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(line)
        return kept
