"""OCR 封装（RapidOCR）：读 720x1280 游戏截图里的中文/日文。

识别逻辑：
1. 可裁剪 ROI，默认放大 2 倍再做检测+识别（小字更准）
2. 丢弃低置信度行
3. 坐标按放大倍率还原到原图
4. 合并重叠的重复行
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    box: tuple[int, int, int, int]


class OcrEngine:
    def __init__(
        self,
        engine=None,
        scale: float = 2.0,
        min_score: float = 0.4,
        line_engine=None,
    ) -> None:
        if engine is None:
            from rapidocr_onnxruntime import RapidOCR

            engine = RapidOCR()
        self._engine = engine
        self._line_engine = line_engine
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

    # ------------------------------------------------------------------ 单行快路径
    def line(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int],
        *,
        scale: float = 4.0,
        min_score: float | None = None,
        digits_only: bool = False,
    ) -> OcrLine | None:
        """已知位置的一小段文字/数字，只跑识别不跑检测（实测 10-30ms）。

        手牌上的分数预览、体力费用、体力/回合数都是固定位置的小数字，
        走这条路径比整屏 OCR（2-5s）便宜两个数量级。

        ``digits_only`` 为 True 时只返回纯数字（允许 x2 这类倍率由调用方处理）。
        """
        x, y, w, h = roi
        height, width = image.shape[:2]
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))
        crop = image[y : y + h, x : x + w]
        if crop.size == 0:
            return None
        if scale and scale != 1.0:
            crop = cv2.resize(
                crop, None, fx=float(scale), fy=float(scale), interpolation=cv2.INTER_CUBIC
            )
        try:
            result, _ = self._line_core()(crop)
        except Exception:  # noqa: BLE001 - 快路径失败就退回整块识别
            if self._line_engine is not self._engine:
                return None
            lines = self.read(image, (x, y, w, h))
            text = " ".join(line.text for line in lines).strip()
            if not text:
                return None
            return OcrLine(text, max((line.score for line in lines), default=0.0), (x, y, w, h))

        best_text = ""
        best_score = 0.0
        for entry in result or []:
            text = str(entry[0]).strip()
            score = float(entry[1])
            if score > best_score:
                best_text, best_score = text, score
        if min_score is None:
            min_score = self.min_score
        if not best_text or best_score < min_score:
            return None
        if digits_only and not re.fullmatch(r"\d+", best_text):
            match = re.search(r"\d+", best_text)
            if match is None:
                return None
            best_text = match.group(0)
        return OcrLine(best_text, best_score, (x, y, w, h))

    def _line_core(self):
        """懒加载"只识别"引擎（RapidOCR use_det=False），失败时退回整块引擎。"""
        if self._line_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR

                self._line_engine = RapidOCR(use_det=False, use_cls=False)
            except Exception:  # noqa: BLE001 - 老版本 rapidocr 没有该开关
                self._line_engine = self._engine
        return self._line_engine

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
