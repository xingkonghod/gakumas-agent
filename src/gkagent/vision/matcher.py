"""模板匹配：不依赖 MAA pipeline，直接在自己的截图上看图说话。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class Match:
    name: str
    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h


class TemplateMatcher:
    """从目录加载模板，在 BGR 截图上做 TM_CCOEFF_NORMED。"""

    def __init__(self, template_dir: str | os.PathLike[str], default_threshold: float = 0.85) -> None:
        self.template_dir = Path(template_dir)
        self.default_threshold = default_threshold
        self._cache: dict[str, np.ndarray] = {}

    def _load(self, name: str) -> np.ndarray:
        key = name if name.endswith(".png") else f"{name}.png"
        if key not in self._cache:
            path = self.template_dir / key
            img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if img is None:
                raise FileNotFoundError(f"template not found: {path}")
            if img.ndim == 3 and img.shape[2] == 4:
                alpha = img[:, :, 3:4].astype(np.float32) / 255.0
                img = (img[:, :, :3].astype(np.float32) * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
            self._cache[key] = img
        return self._cache[key]

    def find(
        self,
        name: str,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
        threshold: float | None = None,
    ) -> Match | None:
        template = self._load(name)
        off_x, off_y = 0, 0
        target = image
        if roi is not None:
            x, y, w, h = roi
            target = image[y : y + h, x : x + w]
            off_x, off_y = x, y
        if template.shape[0] > target.shape[0] or template.shape[1] > target.shape[1]:
            return None
        result = cv2.matchTemplate(target, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        limit = self.default_threshold if threshold is None else threshold
        if max_val < limit:
            return None
        th, tw = template.shape[:2]
        return Match(name, max_loc[0] + off_x, max_loc[1] + off_y, tw, th, float(max_val))

    def find_any(
        self,
        names: list[str],
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
        threshold: float | None = None,
    ) -> Match | None:
        best: Match | None = None
        for name in names:
            m = self.find(name, image, roi=roi, threshold=threshold)
            if m is not None and (best is None or m.score > best.score):
                best = m
        return best

    def exists(self, name: str, image: np.ndarray, **kwargs) -> bool:
        return self.find(name, image, **kwargs) is not None
