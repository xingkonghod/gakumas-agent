"""手牌识别：卡框、费用、可用性。

输入 720x1279（或任意等比例缩放）的 BGR 截图，输出 Contract 的 ``Card`` 列表。
MAA 的 ``ProduceRecognitionCards`` 只给 suggestions/cards/useless 三类框，本模块补上：

- **卡框位置**：亮色卡身连通域 + 边缘轮廓兜底；也可以直接吃 MAA 的框。
- **费用**：卡牌左上角费用徽章里的数字，用内置/外部模板做字形匹配。
- **可用性**：MAA 标签 > 费用/AP 约束 > 卡面明暗。
- **推荐标记**：优先吃 MAA 的 `suggestions` 标签；单看截图暂不猜推荐，避免属性色/特效
  混淆。调用方也可以自己往 `Observation.raw["suggested"]` 注入。
- **kind**：沿用 MAA 的 `cards/suggestions/useless` 三分类，现有 RuleCardPolicy 可直接复用。

``Card`` 契约本身没有 box 字段。这里用 ``HandCard`` 子类携带 box、置信度和推荐标记，
既保持 ``Observation.hand: list[Card]`` 兼容，又让调用方拿得到坐标。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import Field

from gkagent.contract.models import Card, Observation, Phase
from gkagent.vision.matcher import TemplateMatcher

REF_WIDTH = 720
REF_HEIGHT = 1279

# 手牌带：MAA 的 CARD_Y_MIN/CARD_Y_MAX 是 840/1000，实际卡框上下会超出这个范围。
DEFAULT_HAND_ROI = (0, 800, 720, 360)
# 费用徽章在卡牌内的相对位置 x/y/w/h。
DEFAULT_COST_ROI = (0.08, 0.02, 0.30, 0.18)

DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates"

_GLYPH_SIZE = 28
_GLYPH_FONTS = (
    cv2.FONT_HERSHEY_SIMPLEX,
    cv2.FONT_HERSHEY_DUPLEX,
    cv2.FONT_HERSHEY_COMPLEX,
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _as_bgr(image: Any) -> np.ndarray:
    """接受 BGR/GRAY/BGRA 截图，统一成 3 通道 uint8。"""
    if image is None:
        raise ValueError("image is None")
    array = np.asarray(image)
    if array.size == 0:
        raise ValueError("image is empty")
    if array.ndim == 2:
        array = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
    elif array.ndim == 3 and array.shape[2] == 4:
        array = cv2.cvtColor(array, cv2.COLOR_BGRA2BGR)
    elif array.ndim == 3 and array.shape[2] == 3:
        pass
    else:
        raise ValueError(f"unsupported image shape: {array.shape}")
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(array)


def _clip_box(
    box: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int] | None:
    x, y, w, h = (int(v) for v in box)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return x0, y0, x1 - x0, y1 - y0


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = float(ix * iy)
    union = float(aw * ah + bw * bh) - inter
    return inter / union if union > 0 else 0.0


def _size_score(
    w: float,
    h: float,
    *,
    min_w: float,
    max_w: float,
    min_h: float,
    max_h: float,
) -> float:
    """尺寸越接近区间中心越可信，超出区间直接 0。"""
    if not (min_w <= w <= max_w and min_h <= h <= max_h):
        return 0.0
    mid_w = (min_w + max_w) / 2.0
    mid_h = (min_h + max_h) / 2.0
    span_w = max((max_w - min_w) / 2.0, 1e-6)
    span_h = max((max_h - min_h) / 2.0, 1e-6)
    return _clamp01(1.0 - 0.5 * (abs(w - mid_w) / span_w + abs(h - mid_h) / span_h))


def _same_card_column(a: Sequence[int], b: Sequence[int]) -> bool:
    """两个亮块是否属于同一张卡：横向对齐、宽度相近、纵向缺口小。"""
    ax, ay, aw, ah, _ = a
    bx, by, bw, bh, _ = b
    if min(aw, bw) / max(aw, bw) < 0.80:
        return False
    overlap = min(ax + aw, bx + bw) - max(ax, bx)
    if overlap < 0.85 * min(aw, bw):
        return False
    gap = max(by - (ay + ah), ay - (by + bh))
    return gap <= 0.25 * max(ah, bh)


class HandCard(Card):
    """Contract Card + 定位信息。不修改 contract 模型。"""

    box: tuple[int, int, int, int]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    suggested: bool = False
    cost_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


@dataclass(frozen=True)
class CostReading:
    value: int
    score: float
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class _Candidate:
    box: tuple[int, int, int, int]
    confidence: float
    label: str | None = None
    source: str = "visual"


def _normalize_glyph(mask: np.ndarray) -> np.ndarray:
    """把任意大小的白字掩码缩放到 28x28 居中画布。"""
    binary = (mask > 127).astype(np.uint8) * 255
    ys, xs = np.nonzero(binary)
    if len(xs) == 0:
        return np.zeros((_GLYPH_SIZE, _GLYPH_SIZE), np.uint8)
    crop = binary[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    h, w = crop.shape[:2]
    scale = 22.0 / max(h, w)
    nh = max(1, round(h * scale))
    nw = max(1, round(w * scale))
    resized = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_NEAREST)
    canvas = np.zeros((_GLYPH_SIZE, _GLYPH_SIZE), np.uint8)
    y0 = (_GLYPH_SIZE - nh) // 2
    x0 = (_GLYPH_SIZE - nw) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


def _glyph_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """二值字形 IoU + 相关系数，抗锯齿/粗细小差异。"""
    ba = a > 127
    bb = b > 127
    union = np.logical_or(ba, bb).sum()
    inter = np.logical_and(ba, bb).sum()
    iou = float(inter / union) if union else 0.0
    corr = float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)[0, 0])
    return 0.7 * iou + 0.3 * max(0.0, corr)


class CostReader:
    """费用数字识别。

    优先读取 ``templates/cards_digit_<d>.png``；没有外部模板时用 OpenCV Hershey
    字体现场生成 0-9 字形。真实卡面字体不同，真机阶段应换成截图裁下的模板。
    """

    def __init__(
        self,
        template_dir: str | os.PathLike[str] | None = None,
        *,
        threshold: float = 0.45,
        glyph_threshold: float = 0.42,
    ) -> None:
        self.template_dir = Path(template_dir) if template_dir else DEFAULT_TEMPLATE_DIR
        self.threshold = threshold
        self.glyph_threshold = glyph_threshold
        self._templates = self._builtin_templates()
        self._templates.update(self._load_external_templates())

    # ------------------------------------------------------------------ 模板
    def _builtin_templates(self) -> dict[int, list[np.ndarray]]:
        templates: dict[int, list[np.ndarray]] = {}
        for digit in range(10):
            variants: list[np.ndarray] = []
            for font in _GLYPH_FONTS:
                for scale in (0.9, 1.05):
                    canvas = np.zeros((48, 48), np.uint8)
                    text = str(digit)
                    (tw, th), _ = cv2.getTextSize(text, font, scale, 2)
                    origin = ((48 - tw) // 2, (48 + th) // 2)
                    cv2.putText(canvas, text, origin, font, scale, 255, 2, cv2.LINE_AA)
                    variants.append(_normalize_glyph(canvas))
            templates[digit] = variants
        return templates

    def _load_external_templates(self) -> dict[int, list[np.ndarray]]:
        loaded: dict[int, list[np.ndarray]] = {}
        for digit in range(10):
            path = self.template_dir / f"cards_digit_{digit}.png"
            if not path.exists():
                continue
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue
            loaded.setdefault(digit, []).append(_normalize_glyph(image))
        return loaded

    # ------------------------------------------------------------------ 识别
    def read(self, image: Any, box: tuple[int, int, int, int]) -> CostReading | None:
        img = _as_bgr(image)
        x, y, w, h = box
        rx, ry, rw, rh = DEFAULT_COST_ROI
        cx = x + round(w * rx)
        cy = y + round(h * ry)
        cw = max(8, round(w * rw))
        ch = max(8, round(h * rh))
        cost_box = _clip_box((cx, cy, cw, ch), img.shape[1], img.shape[0])
        if cost_box is None:
            return None

        crop = img[cost_box[1] : cost_box[1] + cost_box[3], cost_box[0] : cost_box[0] + cost_box[2]]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        scale = max(1.0, 44.0 / max(gray.shape[0], 1))
        if scale > 1.0:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        _, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        adaptive_inv = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 4
        )
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 4
        )

        best: tuple[int, float, tuple[int, int, int, int]] | None = None
        for mask in (otsu_inv, otsu, adaptive_inv, adaptive):
            reading = self._read_mask(mask)
            if reading is not None and (best is None or reading[1] > best[1]):
                best = reading
        if best is None or best[1] < self.threshold:
            return None

        value, score, local = best
        gx = cost_box[0] + round(local[0] / scale)
        gy = cost_box[1] + round(local[1] / scale)
        gw = max(1, round(local[2] / scale))
        gh = max(1, round(local[3] / scale))
        glyph_box = _clip_box((gx, gy, gw, gh), img.shape[1], img.shape[0]) or cost_box
        return CostReading(value=int(value), score=_clamp01(score), box=glyph_box)

    def read_value(self, image: Any, box: tuple[int, int, int, int]) -> int | None:
        reading = self.read(image, box)
        return reading.value if reading else None

    def _read_mask(self, mask: np.ndarray) -> tuple[int, float, tuple[int, int, int, int]] | None:
        height, width = mask.shape[:2]
        num, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        glyphs: list[tuple[int, int, int, int]] = []
        for i in range(1, num):
            x, y, w, h, area = (int(v) for v in stats[i])
            if h < max(8, int(0.28 * height)) or h > int(0.99 * height):
                continue
            if w < max(3, int(0.12 * h)) or w > int(1.05 * h):
                continue
            if w > int(0.72 * width):
                continue
            if area < int(0.10 * w * h):
                continue
            glyphs.append((x, y, w, h))
        if not glyphs:
            return None
        glyphs.sort(key=lambda g: g[0])

        groups: list[list[tuple[int, int, int, int]]] = []
        if len(glyphs) >= 2:
            last_two = glyphs[-2:]
            heights_close = abs(last_two[0][3] - last_two[1][3]) <= 0.40 * max(
                last_two[0][3], last_two[1][3]
            )
            bottoms_close = abs(
                (last_two[0][1] + last_two[0][3]) - (last_two[1][1] + last_two[1][3])
            ) <= 0.40 * max(last_two[0][3], last_two[1][3])
            if heights_close and bottoms_close:
                groups.append(last_two)
        groups.append([glyphs[-1]])

        # 两位数的优先级高于“只读最右一位”，否则 10 会被读成 0。
        for group in groups:
            digits: list[int] = []
            scores: list[float] = []
            for gx, gy, gw, gh in group:
                digit, score = self._classify_glyph(mask[gy : gy + gh, gx : gx + gw])
                if digit is None or score < self.glyph_threshold:
                    digits = []
                    break
                digits.append(digit)
                scores.append(score)
            if not digits or len(digits) > 2:
                continue
            value = int("".join(str(d) for d in digits))
            score = float(sum(scores) / len(scores)) - 0.01 * (len(digits) - 1)
            x0 = min(g[0] for g in group)
            y0 = min(g[1] for g in group)
            x1 = max(g[0] + g[2] for g in group)
            y1 = max(g[1] + g[3] for g in group)
            return value, score, (x0, y0, x1 - x0, y1 - y0)
        return None

    def _classify_glyph(self, glyph: np.ndarray) -> tuple[int | None, float]:
        normalized = _normalize_glyph(glyph)
        if not normalized.any():
            return None, 0.0
        best_digit: int | None = None
        best_score = 0.0
        for digit, variants in self._templates.items():
            for variant in variants:
                score = _glyph_similarity(normalized, variant)
                if score > best_score:
                    best_digit, best_score = digit, score
        return best_digit, best_score


@dataclass
class HandScan:
    """一帧手牌识别结果，以及和 Observation 的桥。"""

    cards: list[HandCard] = field(default_factory=list)
    roi: tuple[int, int, int, int] = DEFAULT_HAND_ROI
    ap: int | None = None

    def __len__(self) -> int:
        return len(self.cards)

    def __iter__(self) -> Iterator[HandCard]:
        return iter(self.cards)

    def __getitem__(self, index: int) -> HandCard:
        return self.cards[index]

    @property
    def boxes(self) -> list[tuple[int, int, int, int]]:
        return [card.box for card in self.cards]

    def to_observation(
        self,
        *,
        frame_id: int = 0,
        ts_ms: int = 0,
        screen: str = "produce_card",
        phase: Phase = Phase.PRODUCE,
        turn: int | None = None,
        hp: int | None = None,
        stamina: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Observation:
        raw: dict[str, Any] = {
            "boxes": [list(card.box) for card in self.cards],
            "scores": [card.confidence for card in self.cards],
            "costs": [card.cost for card in self.cards],
            "suggested": [card.suggested for card in self.cards],
            "roi": list(self.roi),
        }
        if self.ap is not None:
            raw["ap"] = self.ap
        if extra:
            raw.update(extra)
        confidence = max((card.confidence for card in self.cards), default=0.0)
        return Observation(
            frame_id=frame_id,
            ts_ms=ts_ms,
            screen=screen,
            phase=phase,
            turn=turn,
            hp=hp,
            stamina=stamina,
            hand=list(self.cards),
            confidence=_clamp01(confidence),
            raw=raw,
        )


class HandRecognizer:
    """从截图中找手牌框，再逐张读出费用和可用性。"""

    def __init__(
        self,
        *,
        template_dir: str | os.PathLike[str] | None = None,
        hand_roi: tuple[int, int, int, int] = DEFAULT_HAND_ROI,
        cost_reader: CostReader | None = None,
        min_confidence: float = 0.30,
    ) -> None:
        self.template_dir = Path(template_dir) if template_dir else DEFAULT_TEMPLATE_DIR
        self.hand_roi = hand_roi
        self.min_confidence = min_confidence
        self.cost_reader = cost_reader or CostReader(self.template_dir)

    # -------------------------------------------------------------- 公共接口
    def scan(
        self,
        image: Any,
        *,
        ap: int | None = None,
        hits: Iterable[Any] | None = None,
    ) -> HandScan:
        img = _as_bgr(image)
        roi = self._resolve_roi(img)
        if hits is not None:
            candidates = self._seed_candidates(hits, img)
        else:
            candidates = self._visual_candidates(img, roi)
        if not candidates:
            return HandScan(cards=[], roi=roi, ap=ap)

        brightness = [self._interior_brightness(img, cand.box) for cand in candidates]
        reference = float(np.median(brightness)) if brightness else 0.0
        cards: list[HandCard] = []
        for index, (cand, value) in enumerate(zip(candidates, brightness, strict=True)):
            reading = self.cost_reader.read(img, cand.box)
            cost = reading.value if reading else None
            suggested = cand.label == "suggestions"
            if cand.label == "useless":
                playable = False
            elif cand.label in ("suggestions", "cards"):
                playable = True
            else:
                playable = True
                if (
                    len(candidates) >= 2
                    and reference > 0
                    and value < 0.68 * reference
                    and value < 150.0
                ):
                    playable = False
            if ap is not None and cost is not None and cost > ap:
                playable = False
            if not playable:
                suggested = False
                kind = "useless"
            elif suggested:
                kind = "suggestions"
            else:
                kind = "cards"

            confidence = cand.confidence
            if reading is not None:
                confidence += 0.05
            if suggested:
                confidence += 0.03
            cards.append(
                HandCard(
                    card_id=f"card_{index:02d}",
                    name=None,
                    cost=cost,
                    kind=kind,
                    playable=playable,
                    box=cand.box,
                    confidence=_clamp01(confidence),
                    suggested=suggested,
                    cost_confidence=reading.score if reading else 0.0,
                )
            )
        return HandScan(cards=cards, roi=roi, ap=ap)

    def recognize(
        self,
        image: Any,
        *,
        ap: int | None = None,
        hits: Iterable[Any] | None = None,
    ) -> list[Card]:
        return list(self.scan(image, ap=ap, hits=hits).cards)

    # -------------------------------------------------------------- ROI / 候选
    def _resolve_roi(self, image: np.ndarray) -> tuple[int, int, int, int]:
        height, width = image.shape[:2]
        sx = width / REF_WIDTH
        sy = height / REF_HEIGHT
        x, y, w, h = self.hand_roi
        x0 = max(0, min(width - 1, round(x * sx)))
        y0 = max(0, min(height - 1, round(y * sy)))
        x1 = max(x0 + 1, min(width, round((x + w) * sx)))
        y1 = max(y0 + 1, min(height, round((y + h) * sy)))
        return x0, y0, x1 - x0, y1 - y0

    def _visual_candidates(
        self, image: np.ndarray, roi: tuple[int, int, int, int]
    ) -> list[_Candidate]:
        x0, y0, rw, rh = roi
        crop = image[y0 : y0 + rh, x0 : x0 + rw]
        sx = image.shape[1] / REF_WIDTH
        sy = image.shape[0] / REF_HEIGHT
        candidates = self._bright_candidates(crop, sx, sy)
        candidates.extend(self._edge_candidates(crop, sx, sy))
        shifted = [
            _Candidate(
                box=(x0 + c.box[0], y0 + c.box[1], c.box[2], c.box[3]),
                confidence=c.confidence,
                label=c.label,
                source=c.source,
            )
            for c in candidates
        ]
        return self._select(shifted, image.shape[1], image.shape[0])

    def _bright_candidates(
        self, crop: np.ndarray, sx: float, sy: float
    ) -> list[_Candidate]:
        height, width = crop.shape[:2]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:, :, 2] >= 150) & (hsv[:, :, 1] <= 120)).astype(np.uint8) * 255
        if not mask.any():
            return []
        num, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        components = [
            tuple(int(v) for v in stats[i])
            for i in range(1, num)
            if int(stats[i][4]) > 0
        ]
        components = self._merge_columns(components)
        min_w, max_w = 80.0 * sx, 235.0 * sx
        min_h, max_h = 145.0 * sy, 315.0 * sy
        out: list[_Candidate] = []
        for bx, by, bw, bh, area in components:
            if not (min_w <= bw <= max_w and min_h <= bh <= max_h):
                continue
            ratio = bw / bh
            if not 0.35 <= ratio <= 1.15:
                continue
            fill = area / float(bw * bh)
            if fill < 0.30:
                continue
            margin_x = round(bw * 0.04)
            margin_y = round(bh * 0.03)
            ex = max(0, bx - margin_x)
            ey = max(0, by - margin_y)
            ew = min(width - ex, bw + 2 * margin_x)
            eh = min(height - ey, bh + 2 * margin_y)
            if ew <= 0 or eh <= 0:
                continue
            size = _size_score(
                bw, bh, min_w=min_w, max_w=max_w, min_h=min_h, max_h=max_h
            )
            confidence = _clamp01(0.50 + 0.30 * fill + 0.15 * size)
            out.append(_Candidate((ex, ey, ew, eh), confidence, source="bright"))
        return out

    @staticmethod
    def _merge_columns(
        components: Sequence[tuple[int, int, int, int, int]],
    ) -> list[tuple[int, int, int, int, int]]:
        """把同一张卡被深色卡图切开的上下亮块合成一列。

        卡图大面积遮挡时，亮色卡身会碎成上下两块；直接按块过滤会漏牌。
        只合并横向基本对齐、纵向缺口很小的块，避免把相邻卡或下方 UI 并进来。
        """
        groups = [list(component) for component in components]
        while len(groups) > 1:
            merged = False
            for i in range(len(groups)):
                for j in range(i + 1, len(groups)):
                    if not _same_card_column(groups[i], groups[j]):
                        continue
                    ax, ay, aw, ah, aa = groups[i]
                    bx, by, bw, bh, ba = groups[j]
                    x = min(ax, bx)
                    y = min(ay, by)
                    w = max(ax + aw, bx + bw) - x
                    h = max(ay + ah, by + bh) - y
                    groups[i] = [x, y, w, h, aa + ba]
                    groups.pop(j)
                    merged = True
                    break
                if merged:
                    break
            if not merged:
                break
        return [(g[0], g[1], g[2], g[3], g[4]) for g in groups]

    def _edge_candidates(self, crop: np.ndarray, sx: float, sy: float) -> list[_Candidate]:
        height, width = crop.shape[:2]
        if height < 40 or width < 40:
            return []
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        edges = cv2.Canny(cv2.GaussianBlur(enhanced, (3, 3), 0), 35, 100)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        min_w, max_w = 95.0 * sx, 235.0 * sx
        min_h, max_h = 155.0 * sy, 315.0 * sy
        out: list[_Candidate] = []
        for contour in contours:
            bx, by, bw, bh = cv2.boundingRect(contour)
            if not (min_w <= bw <= max_w and min_h <= bh <= max_h):
                continue
            ratio = bw / bh
            if not 0.38 <= ratio <= 1.08:
                continue
            area = cv2.contourArea(contour)
            fill = area / float(bw * bh)
            if fill < 0.28:
                continue
            size = _size_score(
                bw, bh, min_w=min_w, max_w=max_w, min_h=min_h, max_h=max_h
            )
            confidence = _clamp01(0.30 + 0.30 * min(fill, 1.0) + 0.15 * size)
            out.append(_Candidate((bx, by, bw, bh), confidence, source="edge"))
        return out

    def _seed_candidates(self, hits: Iterable[Any], image: np.ndarray) -> list[_Candidate]:
        height, width = image.shape[:2]
        out: list[_Candidate] = []
        for hit in hits:
            raw_box = _hit_field(hit, "box")
            if raw_box is None or len(raw_box) != 4:
                continue
            box = _clip_box(tuple(int(v) for v in raw_box), width, height)  # type: ignore[arg-type]
            if box is None:
                continue
            label = _hit_field(hit, "label")
            score = _hit_field(hit, "score")
            confidence = _clamp01(0.75 + 0.2 * float(score or 0.0))
            out.append(
                _Candidate(
                    box=box,
                    confidence=confidence,
                    label=str(label) if label is not None else None,
                    source="maa",
                )
            )
        out.sort(key=lambda c: (c.box[0], c.box[1]))
        return out

    def _select(
        self, candidates: Sequence[_Candidate], width: int, height: int
    ) -> list[_Candidate]:
        clipped: list[_Candidate] = []
        for cand in candidates:
            box = _clip_box(cand.box, width, height)
            if box is None or cand.confidence < self.min_confidence:
                continue
            clipped.append(_Candidate(box, cand.confidence, cand.label, cand.source))
        if not clipped:
            return []
        ordered = sorted(
            clipped,
            key=lambda c: (c.confidence, c.box[2] * c.box[3]),
            reverse=True,
        )
        kept: list[_Candidate] = []
        for cand in ordered:
            if all(_iou(cand.box, other.box) < 0.45 for other in kept):
                kept.append(cand)
        if len(kept) >= 2:
            centers = [c.box[1] + c.box[3] / 2.0 for c in kept]
            heights = [c.box[3] for c in kept]
            median_y = float(np.median(centers))
            median_h = float(np.median(heights))
            kept = [
                c
                for c in kept
                if abs((c.box[1] + c.box[3] / 2.0) - median_y) <= 0.35 * median_h
            ]
        if len(kept) >= 3:
            # 手牌同排同高：用稳健的参考尺寸统一框，并剔除明显不在同一排的误检。
            ref_h = round(float(np.percentile([c.box[3] for c in kept], 30)))
            ref_w = round(float(np.percentile([c.box[2] for c in kept], 30)))
            median_top = float(np.median([c.box[1] for c in kept]))
            kept = [
                c
                for c in kept
                if abs(c.box[1] - median_top) <= 0.15 * max(ref_h, 1)
            ]
            normalized: list[_Candidate] = []
            for cand in kept:
                x, y, w, h = cand.box
                cx = x + w / 2.0
                cy = y + h / 2.0
                box = _clip_box(
                    (
                        round(cx - ref_w / 2.0),
                        round(cy - ref_h / 2.0),
                        ref_w,
                        ref_h,
                    ),
                    width,
                    height,
                )
                if box is not None:
                    normalized.append(
                        _Candidate(box, cand.confidence * 0.95, cand.label, cand.source)
                    )
            kept = normalized
            deduped: list[_Candidate] = []
            for cand in kept:
                if all(_iou(cand.box, other.box) < 0.45 for other in deduped):
                    deduped.append(cand)
            kept = deduped
        kept.sort(key=lambda c: (c.box[0], c.box[1]))
        return kept[:9]

    def _interior_brightness(self, image: np.ndarray, box: tuple[int, int, int, int]) -> float:
        x, y, w, h = box
        ix = x + round(w * 0.12)
        iy = y + round(h * 0.12)
        iw = max(1, round(w * 0.76))
        ih = max(1, round(h * 0.76))
        patch = image[iy : iy + ih, ix : ix + iw]
        if patch.size == 0:
            return 0.0
        return float(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[:, :, 2].mean())


def _hit_field(hit: Any, name: str) -> Any:
    if isinstance(hit, dict):
        return hit.get(name)
    return getattr(hit, name, None)


_RECOGNIZER_CACHE: dict[tuple[str, tuple[int, int, int, int] | None], HandRecognizer] = {}
_BATTLE_MATCHERS: dict[str, TemplateMatcher] = {}


def _get_recognizer(
    template_dir: str | os.PathLike[str] | None = None,
    roi: tuple[int, int, int, int] | None = None,
) -> HandRecognizer:
    key = (str(template_dir or DEFAULT_TEMPLATE_DIR), tuple(roi) if roi else None)
    recognizer = _RECOGNIZER_CACHE.get(key)
    if recognizer is None:
        recognizer = HandRecognizer(template_dir=template_dir, hand_roi=roi or DEFAULT_HAND_ROI)
        _RECOGNIZER_CACHE[key] = recognizer
    return recognizer


def scan_hand(
    image: Any,
    *,
    ap: int | None = None,
    hits: Iterable[Any] | None = None,
    template_dir: str | os.PathLike[str] | None = None,
    roi: tuple[int, int, int, int] | None = None,
    recognizer: HandRecognizer | None = None,
) -> HandScan:
    """识别一帧手牌，返回带坐标的 HandScan。"""
    engine = recognizer or _get_recognizer(template_dir, roi)
    return engine.scan(image, ap=ap, hits=hits)


def recognize_hand(
    image: Any,
    *,
    ap: int | None = None,
    hits: Iterable[Any] | None = None,
    template_dir: str | os.PathLike[str] | None = None,
    roi: tuple[int, int, int, int] | None = None,
) -> list[Card]:
    """任务要求的入口：720x1279 截图 → list[Card]（实际元素是 HandCard，带 box）。"""
    return list(scan_hand(image, ap=ap, hits=hits, template_dir=template_dir, roi=roi).cards)


def is_produce_battle(
    image: Any,
    *,
    template_dir: str | os.PathLike[str] | None = None,
    threshold: float = 0.80,
) -> bool:
    """用 MAA 的体力/跳过回合模板判断是否处于出牌场景。

    只作为调用方的门禁；模板缺失时返回 False，不抛异常。
    """
    img = _as_bgr(image)
    key = str(template_dir or DEFAULT_TEMPLATE_DIR)
    matcher = _BATTLE_MATCHERS.get(key)
    if matcher is None:
        matcher = TemplateMatcher(key)
        _BATTLE_MATCHERS[key] = matcher
    for name in ("cards_health", "cards_skip_round"):
        try:
            if matcher.find(name, img, threshold=threshold) is not None:
                return True
        except FileNotFoundError:
            continue
    return False
