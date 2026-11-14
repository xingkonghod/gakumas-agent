"""课程/试镜读屏：读游戏自己给出的数字，不再靠卡名猜价值。

界面事实（720x1280 基准，2026-11 实拍核对）：

- 手牌左上角菱形 = **这张牌当下能打多少分**（已含好调/集中/属性倍率，``26 x2`` 表示 2 次）
- 手牌右下角爱心 = **体力消耗**
- 左上「剩余回合数 N」/ 右上分数 / 右侧爱心 X（选中牌时下方显示 ``-N`` 预览）
- 右下「SKIP」= 结束本回合

读法：手牌带一次整块 OCR 找卡名（卡名一行一张，位置稳定），
其余小数字全部走 ``OcrEngine.line`` 的"只识别"快路径（10-30ms/个）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from gkagent.data.buffs import BuffLibrary
from gkagent.data.card_effects import estimate_value, is_buff_text
from gkagent.data.card_table import CardTable
from gkagent.data.cards_db import CardLibrary
from gkagent.vision.cards import scan_hand
from gkagent.vision.ocr import OcrEngine

HAND_BAND = (0, 860, 720, 340)
NAME_BAND = (0, 1060, 720, 100)
CARD_WIDTH = 190
CARD_HEIGHT = 232
# 手牌那一排的固定上沿（720x1280）：课程/试镜都是 y≈892，选中态会抬高 ~25px
CARD_TOP = 892
SKIP_POINT = (660, 868)

# 两种界面布局（课程 / 试镜）。位置按 720x1280 实拍标定。
LAYOUTS: dict[str, dict[str, tuple[int, int, int, int] | None]] = {
    "lesson": {
        "turns": (58, 56, 92, 58),
        "score": (588, 34, 116, 54),
        "stamina": (556, 156, 92, 54),
        "gauge": (300, 105, 120, 70),
    },
    "audition": {
        "turns": (34, 56, 92, 60),
        "score": None,
        "stamina": (566, 202, 82, 52),
        "gauge": None,
        "attribute": (98, 50, 82, 36),
        "multiplier": (110, 78, 92, 44),
    },
}

_ATTRIBUTES = ("歌唱", "舞蹈", "视觉")

# 选中卡后右上角的体力预览：``25`` 和 ``-6`` 两行，两种界面各一套位置
STAMINA_PREVIEWS: tuple[tuple[tuple[int, int, int, int], tuple[int, int, int, int]], ...] = (
    ((560, 160, 76, 42), (556, 198, 82, 38)),  # 课程
    ((556, 204, 80, 42), (552, 242, 84, 38)),  # 试镜
)


@dataclass(frozen=True)
class LessonCard:
    index: int
    box: tuple[int, int, int, int]
    point: tuple[int, int]
    name: str = ""
    score: int | None = None
    hits: int | None = None
    cost: int | None = None
    buff: bool = False
    conditional: bool = False
    text: str = ""

    @property
    def total_score(self) -> float:
        if self.score is None:
            return 0.0
        return float(self.score) * float(self.hits or 1)


@dataclass(frozen=True)
class LessonState:
    kind: str = "lesson"
    turns_left: int | None = None
    score: int | None = None
    gauge: int | None = None
    stamina: int | None = None
    attribute: str | None = None
    multiplier: float | None = None
    cards: tuple[LessonCard, ...] = ()
    skip_point: tuple[int, int] | None = SKIP_POINT
    notes: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        return (
            f"{self.kind} 回合{self._fmt(self.turns_left)} "
            f"体力{self._fmt(self.stamina)} 分数{self._fmt(self.score)} "
            f"{self.attribute or ''}{self.multiplier or ''} 手牌{len(self.cards)}"
        )

    @staticmethod
    def _fmt(value: float | None = None) -> str:
        return "-" if value is None else str(int(value))


class LessonReader:
    """从截图读出课程/试镜局面 + 手牌的分数与体力费用。"""

    def __init__(
        self,
        engine: OcrEngine,
        *,
        cards: CardLibrary | None = None,
        buffs: BuffLibrary | None = None,
        costs=None,
        table: CardTable | None = None,
    ) -> None:
        self.engine = engine
        self.cards = cards
        self.buffs = buffs or BuffLibrary.load()
        self.costs = costs
        self.table = table if table is not None else CardTable()

    # ------------------------------------------------------------------ 主入口
    def read(
        self,
        image: np.ndarray,
        *,
        kind: str = "lesson",
        lines=None,
    ) -> LessonState:
        height, width = image.shape[:2]
        sx = width / 720.0
        sy = height / 1280.0
        cards = self.read_cards(image, lines=lines)
        # 课程和试镜的数值位置不同（试镜顶部多一排名次），按 kind 优先、另一种兜底
        order = [kind] if kind in LAYOUTS else []
        order += [name for name in ("lesson", "audition") if name not in order]
        turns = self._first_number(image, order, "turns", 1, 40)
        score = self._first_number(image, order, "score", 0, 200000)
        stamina = self._first_number(image, order, "stamina", 0, 199)
        gauge = self._first_number(image, order, "gauge", 0, 200000)
        attribute = self._first_attribute(image, order)
        multiplier = self._first_number(image, order, "multiplier", 10, 999)
        notes = []
        if turns is None:
            notes.append("turns-unread")
        if stamina is None:
            notes.append("stamina-unread")
        return LessonState(
            kind=kind,
            turns_left=turns,
            score=score,
            gauge=gauge,
            stamina=stamina,
            attribute=attribute,
            multiplier=float(multiplier) if multiplier is not None else None,
            cards=tuple(cards),
            skip_point=(int(SKIP_POINT[0] * sx), int(SKIP_POINT[1] * sy)),
            notes=tuple(notes),
        )

    # ------------------------------------------------------------------ 手牌
    def read_cards(
        self, image: np.ndarray, *, lines=None, boxes=None
    ) -> list[LessonCard]:
        """手牌：优先用轮廓定框（~180ms）+ 逐张单行识别，定框失败才退回整块 OCR。

        整块 OCR 读卡名要 4-7s/步，是课程步的主要耗时；轮廓定框便宜两个数量级。
        """
        if boxes is None:
            boxes = self._detect_boxes(image)
        if len(boxes) >= 2 and self._slot_layout_ok(boxes):
            cards = []
            for index, box in enumerate(boxes[:5]):
                left = box[0] + box[2] // 2 - CARD_WIDTH // 2
                rect = (left, CARD_TOP, CARD_WIDTH, CARD_HEIGHT)
                card = self.read_card(image, index, rect)
                cards.append(card)
            if sum(1 for card in cards if card.name or card.score is not None) >= len(cards) - 1:
                return cards
        name_lines = self._name_lines(image, lines)
        cards = []
        for index, (name, box) in enumerate(name_lines):
            left = box[0] + box[2] // 2 - CARD_WIDTH // 2
            top = box[1] - CARD_HEIGHT + 24
            rect = (left, top, CARD_WIDTH, CARD_HEIGHT)
            cards.append(self.read_card(image, index, rect, name=name))
        return cards

    def _slot_layout_ok(self, boxes: list[tuple[int, int, int, int]]) -> bool:
        """框的中心是否落在标准手牌槽位上（2/3/4/5 张各有固定间距）。

        轮廓定框偶尔会把选中态的内框、或者卡面里的色块当成卡；落在标准槽位上
        才敢用快路径，否则退回整块 OCR（慢但准）。
        """
        counts = {2: (252, 469), 3: (142, 360, 577), 4: (143, 287, 432, 577)}
        expected = counts.get(len(boxes))
        if expected is None:
            return False
        centers = sorted(box[0] + box[2] // 2 for box in boxes)
        return all(abs(center - slot) <= 45 for center, slot in zip(centers, expected))

    def _detect_boxes(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        """轮廓定框，并把框归一到标准手牌尺寸（选中态会给出内框）。"""
        try:
            scan = scan_hand(image)
        except Exception:  # noqa: BLE001 - 定框失败就走 OCR 兜底
            return []
        boxes: list[tuple[int, int, int, int]] = []
        for card in scan.cards:
            x, y, w, h = (int(v) for v in card.box)
            if not 100 <= w <= 260 or not 120 <= h <= 300:
                continue
            center = x + w // 2
            boxes.append((center - CARD_WIDTH // 2, y, CARD_WIDTH, CARD_HEIGHT))
        boxes.sort(key=lambda box: box[0])
        return boxes

    def read_card(
        self,
        image: np.ndarray,
        index: int,
        rect: tuple[int, int, int, int],
        *,
        name: str = "",
    ) -> LessonCard:
        left, top, width, height = rect
        score_box = (left + 2, top - 26, 116, 62)
        cost_box = (left + 134, top + 154, 78, 52)
        name_box = (left + 8, top + 196, width - 16, 34)
        score_line = self._safe_line(image, score_box)
        cost_line = self._safe_line(image, cost_box)
        if not name:
            name_out = self._safe_line(image, name_box, digits_only=False)
            name = name_out.text if name_out is not None else ""
        score, hits = _parse_score(score_line.text if score_line else "")
        cost = _parse_int(cost_line.text if cost_line else "")
        if cost is not None and not 0 <= cost <= 99:
            cost = None
        # 卡名对上属性表就用真值（OCR 爱心小字 + 确认帧预览都不可靠）
        if name and self.table is not None:
            table_cost = self.table.cost(name)
            if table_cost is not None:
                cost = int(table_cost)
        if cost is None and name and self.costs is not None:
            cached = self.costs.get(name)
            if cached is not None:
                cost = int(cached)
        text = ""
        buff = False
        conditional = False
        if name and self.cards is not None:
            info = self.cards.lookup(name)
            if info is not None:
                text = info.text
                buff = is_buff_text(text)
                conditional = CardTable.looks_conditional(text)
        point = (left + width // 2, top + height // 2)
        return LessonCard(
            index=index,
            box=rect,
            point=point,
            name=name,
            score=score,
            hits=hits,
            cost=cost,
            buff=buff,
            conditional=conditional,
            text=text,
        )

    def _name_lines(self, image: np.ndarray, lines=None) -> list[tuple[str, tuple[int, int, int, int]]]:
        """卡名一行一张：按 x 聚类，返回 [(name, box)]。"""
        if lines is None:
            lines = self.engine.read(image, NAME_BAND)
        candidates = []
        for line in lines:
            text = (line.text or "").strip()
            if not (2 <= len(text) <= 14):
                continue
            if any(ch.isdigit() for ch in text):
                continue
            if not any("\u4e00" <= ch <= "\u9fff" for ch in text):
                continue
            x, y, w, _h = line.box
            if w < 28:
                continue
            candidates.append((y, x + w // 2, text, (x, y, w, _h)))
        candidates.sort(key=lambda item: item[1])
        clusters: list[list] = []
        for item in candidates:
            if clusters and abs(item[1] - clusters[-1][-1][1]) <= 70:
                clusters[-1].append(item)
            else:
                clusters.append([item])
        found: list[tuple[str, tuple[int, int, int, int]]] = []
        for cluster in clusters:
            best = max(cluster, key=lambda item: (len(item[2]), -item[1]))
            found.append((best[2], best[3]))
        found.sort(key=lambda item: item[1][0])
        return found

    # ------------------------------------------------------------------ 数字/文字
    def _safe_line(self, image, box, *, digits_only: bool = True):
        try:
            return self.engine.line(image, box, digits_only=digits_only)
        except Exception:  # noqa: BLE001 - 快路径不可用时视为没读到
            return None

    def _first_number(self, image, order, key: str, low: int, high: int) -> int | None:
        for name in order:
            layout = LAYOUTS.get(name) or {}
            value = self._number(image, layout.get(key), low, high)
            if value is not None:
                return value
        return None

    def _first_attribute(self, image, order) -> str | None:
        for name in order:
            layout = LAYOUTS.get(name) or {}
            value = self._attribute(image, layout.get("attribute"))
            if value is not None:
                return value
        return None

    def _number(self, image, box, low: int, high: int) -> int | None:
        if box is None:
            return None
        x, y, w, h = box
        # 小数字识别偶发失败：先原框，再上下左右各放 8px 重试一次
        for attempt in ((x, y, w, h), (x - 8, y - 8, w + 16, h + 16)):
            line = self._safe_line(image, attempt)
            value = _parse_int(line.text if line else "")
            if value is not None and low <= value <= high:
                return value
        return None

    def _attribute(self, image, box) -> str | None:
        if box is None:
            return None
        line = self._safe_line(image, box, digits_only=False)
        if line is None:
            return None
        for word in _ATTRIBUTES:
            if word in line.text:
                return word
        return None


def _parse_int(text: str) -> int | None:
    match = re.search(r"\d{1,5}", text or "")
    return int(match.group(0)) if match else None


def _parse_score(text: str) -> tuple[int | None, int | None]:
    """``84`` → (84, 1)；``26x2`` / ``26 x2`` / ``26×2`` → (26, 2)。"""
    if not text:
        return None, None
    cleaned = text.replace("×", "x").replace("X", "x").replace(" ", "")
    match = re.match(r"(\d{1,5})(?:x(\d{1,2}))?$", cleaned)
    if match:
        score = int(match.group(1))
        hits = int(match.group(2)) if match.group(2) else 1
        return score, hits
    number = _parse_int(cleaned)
    return (number, 1) if number is not None else (None, None)


def read_stamina_preview(
    engine: OcrEngine, image: np.ndarray
) -> tuple[int | None, int | None]:
    """读"选中一张卡后"右上角的体力预览，返回 ``(当前体力, 这张卡的体力消耗)``。

    出牌两段式的第一段之后调用：这两个数字很大，识别率远高于卡面爱心上的小字，
    用来学习 ``卡名 → 费用``。读不到就返回 None，不阻断出牌。
    """
    stamina_value: int | None = None
    delta_value: int | None = None
    for stamina_box, delta_box in STAMINA_PREVIEWS:
        try:
            stamina_line = engine.line(image, stamina_box, digits_only=True)
            delta_line = engine.line(image, delta_box, digits_only=True)
        except Exception:  # noqa: BLE001, S112 - 快路径不可用时视为没读到
            continue
        stamina = _parse_int(stamina_line.text if stamina_line else "")
        delta = _parse_int(delta_line.text if delta_line else "")
        if stamina is not None and 0 <= stamina <= 199:
            stamina_value = stamina
        if delta is not None and 0 <= delta <= 99:
            delta_value = delta
        if stamina_value is not None and delta_value is not None:
            return stamina_value, delta_value
    return stamina_value, delta_value


def card_value(card: LessonCard, *, turns_left: int | None = None) -> float:
    """手牌估值：优先用界面分数预览；没有就按卡名查卡库/机制估。"""
    if card.score is not None:
        return card.total_score
    if card.text:
        return estimate_value(card.text, turns_left=turns_left).score
    return 0.0
