"""OCR 语义缓存：按"文字内容"而不是像素 digest 复用识别结果。

真机角色会呼吸、卡面会闪光、视频有噪点，同一屏的像素 digest 每帧都不同，
旧版 ``data/auto_produce.py`` 里的 ``ocr_cache[digest]`` 因此几乎从不命中。
这里提供两层缓存：

1. :class:`SemanticScreenCache`：key 是**整屏 OCR 文本的语义指纹**
   （NFKC + 压缩空白后做 sha1）。文字一样 = 游戏状态一样，直接复用上次的
   行列表（框坐标也一起复用，按钮照样能点）。
2. :class:`LineFingerprintCache`：单行小框 OCR 缓存。key 是 ROI 内**文字掩码**
   （自适应阈值后的 24x24 位图）的感知指纹，不看颜色/背景动画；命中时连识别
   模型都不跑。文字变了掩码就变，不会把旧数字当新数字。

两个缓存都有容量上限（LRU），不会随一局时长无限增长。
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections import OrderedDict
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:  # 避免 ocr.py ↔ ocr_cache.py 循环导入
    from gkagent.vision.ocr import OcrLine

# 文字掩码指纹的位图尺寸：24x24 = 576 bit。足够区分数字/汉字，又能容忍
# 角色呼吸带来的背景亮度微变（实测同样的字在动画帧之间差异 0-13 bit，
# 不同数字/卡名差异 ≥37 bit）。
MASK_GRID = 24
MASK_MAX_DISTANCE = 18


def normalize_ocr_text(text: str | None) -> str:
    """归一化 OCR 文本：全角转半角、压缩空白、去掉首尾标点空白。

    语义指纹只跟"看到了哪些字"有关，角色动画/阴影不应该影响它。
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    value = " ".join(value.split())
    return value.strip(" \t\r\n·・-—_|/\\")


def semantic_fingerprint(text: str | None) -> str:
    """OCR 文本的语义指纹；空文本返回空串（空屏不缓存，避免误命中）。"""
    normalized = normalize_ocr_text(text)
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


class SemanticScreenCache:
    """整屏/整块 OCR 结果的语义缓存（按 OCR 文本 hash 命中）。

    用法::

        cache = SemanticScreenCache()
        cached = cache.get(text)          # 先看这屏文字是不是见过
        if cached is None:
            lines = engine.read(image)
            cache.put(text_of(lines), lines)

    注意：调用方要保证 ``text`` 能代表这一屏的关键状态（按钮 + 标题 + 数值），
    否则同按钮不同内容的弹窗会复用错行。``ProduceDriver.read_fast`` 只对
    加载/剧情/对话这类"文字重复即状态重复"的屏幕启用。
    """

    def __init__(self, max_entries: int = 64) -> None:
        self.max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[str, tuple[str, tuple[OcrLine, ...]]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, text: str | None) -> list[OcrLine] | None:
        fingerprint = semantic_fingerprint(text)
        if not fingerprint:
            self.misses += 1
            return None
        entry = self._entries.get(fingerprint)
        if entry is None:
            self.misses += 1
            return None
        self._entries.move_to_end(fingerprint)
        self.hits += 1
        return list(entry[1])

    def put(self, text: str | None, lines: list[OcrLine]) -> str:
        fingerprint = semantic_fingerprint(text)
        if not fingerprint:
            return ""
        self._entries[fingerprint] = (normalize_ocr_text(text), tuple(lines))
        self._entries.move_to_end(fingerprint)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        return fingerprint

    def clear(self) -> None:
        self._entries.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._entries)


class LineFingerprintCache:
    """单行 OCR 缓存：ROI 内"文字掩码"的感知指纹相同就复用结果。

    只缓存**成功识别**和**确定读不到**两种结果；命中后不调用识别模型。
    指纹使用自适应阈值把文字从背景里分离出来，再缩成 24x24 位图，因此：

    * 角色呼吸/闪光改变背景颜色 → 掩码基本不变 → 命中；
    * 154 变成 192、卡名换一张 → 文字形状变化 → 指纹距离变大 → 不命中。
    """

    def __init__(
        self,
        max_entries: int = 512,
        max_distance: int = MASK_MAX_DISTANCE,
    ) -> None:
        self.max_entries = max(1, int(max_entries))
        self.max_distance = int(max_distance)
        # key: (roi, scale, digits_only) -> [(bits, line|None), ...]
        self._entries: OrderedDict[tuple, list[tuple[int, OcrLine | None]]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    # ------------------------------------------------------------------ 指纹
    @staticmethod
    def fingerprint(image: np.ndarray, roi: tuple[int, int, int, int]) -> int | None:
        """ROI 内文字掩码的感知指纹（int，576 bit）；无效输入返回 None。"""
        if image is None or getattr(image, "ndim", 0) != 3:
            return None
        height, width = image.shape[:2]
        x, y, w, h = (int(v) for v in roi)
        x0 = max(0, min(x, width - 1))
        y0 = max(0, min(y, height - 1))
        x1 = max(x0 + 1, min(width, x + w))
        y1 = max(y0 + 1, min(height, y + h))
        crop = image[y0:y1, x0:x1]
        if crop.size == 0 or crop.shape[0] < 6 or crop.shape[1] < 6:
            return None
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        # 自适应阈值：白字黑底、黑字白底都能抓成 255 的文字掩码。
        block = max(9, min(31, (min(gray.shape[:2]) // 2) * 2 + 1))
        mask = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block,
            8,
        )
        small = cv2.resize(mask, (MASK_GRID, MASK_GRID), interpolation=cv2.INTER_AREA)
        bits = np.packbits(small > 127).tobytes()
        return int.from_bytes(bits, "big")

    @staticmethod
    def distance(left: int, right: int) -> int:
        return (int(left) ^ int(right)).bit_count()

    # ------------------------------------------------------------------ 查/存
    def get(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int],
        *,
        scale: float = 1.0,
        digits_only: bool = False,
    ) -> tuple[bool, OcrLine | None]:
        """返回 ``(是否命中, 缓存结果)``；未命中返回 ``(False, None)``。"""
        bits = self.fingerprint(image, roi)
        if bits is None:
            self.misses += 1
            return (False, None)
        key = (tuple(int(v) for v in roi), float(scale), bool(digits_only))
        variants = self._entries.get(key)
        if not variants:
            self.misses += 1
            return (False, None)
        best: tuple[int, OcrLine | None] | None = None
        for stored, line in variants:
            distance = self.distance(bits, stored)
            if distance <= self.max_distance and (best is None or distance < best[0]):
                best = (distance, line)
        if best is None:
            self.misses += 1
            return (False, None)
        self._entries.move_to_end(key)
        self.hits += 1
        return (True, best[1])

    def put(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int],
        line: OcrLine | None,
        *,
        scale: float = 1.0,
        digits_only: bool = False,
    ) -> None:
        bits = self.fingerprint(image, roi)
        if bits is None:
            return
        key = (tuple(int(v) for v in roi), float(scale), bool(digits_only))
        variants = self._entries.setdefault(key, [])
        # 同一 ROI 最多留 8 个"长得不一样"的变体（不同数字/卡名）。
        if all(self.distance(bits, stored) > self.max_distance for stored, _ in variants):
            variants.append((bits, line))
            del variants[:-8]
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        return len(self._entries)
