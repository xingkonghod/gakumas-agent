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
from dataclasses import dataclass, field, replace

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
SKIP_POINT = (657, 800)
# 日文考试「残りターン」圆环数字紧框（720x1280）：宽框 turns ROI 会混入环弧
# 读成 912（matto r3-00074）；宽框读不到时用它兜底（见 read()）。
AUDITION_TURNS_TIGHT = (34, 56, 52, 52)
# 分数宝石上一回合没读到、下一回合重读时额外放宽的像素（宝石偶尔被边框/选中态切到）
SCORE_RETRY_PADS = (8, 14)

# 两种界面布局（课程 / 试镜）。位置按 720x1280 实拍标定。
LAYOUTS: dict[str, dict[str, tuple[int, int, int, int] | None]] = {
    "lesson": {
        "turns": (58, 56, 92, 58),
        "score": (588, 34, 116, 54),
        "stamina": (556, 156, 92, 54),
        # 正中圆环：上行「CLEAR截止 / PERFECT截止」是**当前档位**，下行数字是
        # **还差多少分**到该档位（不是过关线本身，2026-11-22 实拍核对）。
        "gauge": (300, 105, 120, 70),
        "goal": (295, 96, 150, 24),
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
# 日文客户端（DMM 原版/汉化 overlay 未覆盖屏）属性名：归一到中文规范名。
# 下游 sim.exam_plan.PARAMETER_TYPES / sim.uiobs._ATTRIBUTE_CODES 只认中文键，
# 这里做别名映射而不是改下游（F#48 日文别名先例；matto 基准 exam_attr 缺口）。
_ATTRIBUTE_JA_ALIASES: dict[str, str] = {
    "ボーカル": "歌唱",
    "ダンス": "舞蹈",
    "ビジュアル": "视觉",
}

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
    # 分数宝石没读到时用卡表 ``score_of`` 兜底的值：真值只能算"估"，策略要轻微降权
    score_estimated: bool = False
    # 屏幕分数和卡表都没读出来：score 记 0，但策略应把它当"未知"而不是"真的 0 分"
    score_unread: bool = False
    # 这张牌上一回合宝石没读到、卡表知道它有分：下一回合进手牌时优先重读宝石
    recheck: bool = False
    # 游戏高亮（金框/推荐）：机制提示「先铺倍率」，策略里无条件优先（2026-11-15 用户打法）
    highlight: bool = False

    @property
    def total_score(self) -> float:
        if self.score is None:
            return 0.0
        return float(self.score) * float(self.hits or 1)


def _gold_frame(image, rect: tuple[int, int, int, int]) -> bool:
    """手牌是否带游戏高亮的金色边框（推荐牌会闪金边，用来先铺 buff）。

    只看卡框左右各 ~8px 的竖条里金色像素占比；卡面本身的金色花纹不在这两列，
    不会误判。没有图像/尺寸异常一律 False（策略退回普通规则）。
    """
    if image is None or getattr(image, "ndim", 0) != 3 or image.shape[2] < 3:
        return False
    left, top, width, height = (int(value) for value in rect)
    x0 = max(0, left - 4)
    x1 = min(image.shape[1], left + width + 4)
    y0 = max(0, top)
    y1 = min(image.shape[0], top + height)
    patch = image[y0:y1, x0:x1]
    if patch.size == 0 or patch.shape[0] < 24:
        return False
    blue = patch[:, :, 0].astype(int)
    green = patch[:, :, 1].astype(int)
    red = patch[:, :, 2].astype(int)
    gold = (red >= 180) & (green >= 120) & (green <= 235) & (blue <= 110) & ((red - blue) >= 90)
    columns = gold.sum(axis=0)
    edge_width = min(8, max(2, patch.shape[1] // 10))
    if edge_width <= 0:
        return False
    edge = np.concatenate([columns[:edge_width], columns[-edge_width:]])
    ratio = float(edge.mean()) / float(max(patch.shape[0], 1))
    return ratio >= 0.25


@dataclass(frozen=True)
class LessonState:
    kind: str = "lesson"
    turns_left: int | None = None
    # 本课程总回合数（OCR 只读"剩余回合数"；能读到课程配置时由调用方填，
    # 用于判断"这是第几回合/还剩几回合"）。None = 未知。
    total_turns: int | None = None
    # 本课**已得分数**（相对开课，0 起）。注意：课程界面右上角显示的是培育属性值，
    # 不是课程分；课程分 = 右上属性值 − 开课时属性值（``LessonReader`` 按课跟踪基线）。
    score: int | None = None
    # CLEAR（过关）线。真机由「CLEAR截止 N / PERFECT截止 N（还差 N 分）」反推：
    # 还差分 + 已得分 = 该档位线。合成状态/评测脚本可以直接传。
    gauge: int | None = None
    # PERFECT（满分）线；真机读不到时按档位表（``sim.hajime_data``）或 2×过关线推。
    perfect: int | None = None
    # 正中圆环当前档位：``"clear"``（还没过关）/ ``"perfect"``（已过关，冲满分）。
    goal: str | None = None
    # 右上角读到的原始属性值（培育属性值；日志/诊断用，决策只看上面的 score）。
    attr: int | None = None
    stamina: int | None = None
    attribute: str | None = None
    multiplier: float | None = None
    cards: tuple[LessonCard, ...] = ()
    skip_point: tuple[int, int] | None = SKIP_POINT
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def current_turn(self) -> int | None:
        """当前回合号（1 起）；总回合数未知时返回 None。"""
        if self.total_turns is None or self.turns_left is None:
            return None
        return max(self.total_turns - self.turns_left + 1, 1)

    def summary(self) -> str:
        return (
            f"{self.kind} 回合{self._fmt(self.turns_left)}/{self._fmt(self.total_turns)} "
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
        # 卡名 → 上一回合分数宝石没读到。下次读到同一张牌时优先重读那颗宝石。
        self._recheck: set[str] = set()
        # 本课基线：右上角是培育属性值（绝对），课程分要减去开课瞬间的属性值。
        # 新开一节课时由调用方 ``reset_lesson()`` 清零。
        self._lesson_attr_base: int | None = None
        self._lesson_goal: str | None = None

    def reset_lesson(self) -> None:
        """新开一节课：清掉上一课的分基线/档位记忆（课程帧消失时调用）。"""
        self._lesson_attr_base = None
        self._lesson_goal = None

    @property
    def pending_recheck(self) -> tuple[str, ...]:
        """待重读分数宝石的卡名（日志/测试用；真正重读在 ``read_card`` 里做）。"""
        return tuple(sorted(self._recheck))

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
        if turns is None and "audition" in order:
            # 日文考试帧剩余回合是深色圆环里的白字：宽框会把环弧读成「912」
            # （matto r3-00074 实测）→ 超 1..40 拒读。紧框只罩数字，兜底再试一次；
            # 中文帧宽框能读到就不走这里（逐位不变）。
            turns = self._number(image, AUDITION_TURNS_TIGHT, 1, 40)
        score = self._first_number(image, order, "score", 0, 200000)
        stamina = self._first_number(image, order, "stamina", 0, 199)
        gauge = self._first_number(image, order, "gauge", 0, 200000)
        attribute = self._first_attribute(image, order)
        # H.I.F 本战属性倍率可超 999%（matto 真值 r3-00074 = 2805%）；旧上限 999
        # 会把高倍率整段拒读。上限放到 9999（屏幕百分比 4 位），低倍率行为不变。
        multiplier = self._first_number(image, order, "multiplier", 10, 9999)
        notes = []
        if turns is None:
            notes.append("turns-unread")
        if stamina is None:
            notes.append("stamina-unread")
        goal = None
        if kind == "lesson":
            # 圆环档位（CLEAR截止 / PERFECT截止）：动画帧会读不到，记住本课最近一次值。
            goal = self._read_goal(image)
            if goal is not None:
                self._lesson_goal = goal
            goal = self._lesson_goal
            if goal is None:
                notes.append("goal-unread")
        state = LessonState(
            kind=kind,
            turns_left=turns,
            # 课程右上角读到的是培育属性值；下面 _with_lesson_progress() 换算成课程分。
            score=score,
            gauge=gauge,
            goal=goal,
            attr=score if kind == "lesson" else None,
            stamina=stamina,
            attribute=attribute,
            multiplier=float(multiplier) if multiplier is not None else None,
            cards=tuple(cards),
            skip_point=(int(SKIP_POINT[0] * sx), int(SKIP_POINT[1] * sy)),
            notes=tuple(notes),
        )
        if kind == "lesson":
            state = self._with_lesson_progress(state)
        return state

    def _with_lesson_progress(self, state: LessonState) -> LessonState:
        """课程 HUD 原始读数 → 课程相对读数（本课得分 + CLEAR/PERFECT 线）。

        界面事实（2026-11-22 实拍核对，和 hiro 的课程 HUD 口径一致）：

        - 右上角 = **培育属性值**（属性图标 + 评级 + 数字），不是课程分；
          课程分 = 属性值 − 开课瞬间的属性值（基线由 ``reset_lesson()`` 重置）；
        - 正中圆环 = 「CLEAR截止 / PERFECT截止 N」= **还差 N 分**到当前档位；
          过了 CLEAR 换成 PERFECT，打满 PERFECT 课程立即结束；
        - 所以：过关线 = 本课已得分 + 圆环还差分。

        读不到属性值/圆环时保持原值（策略有未知兜底），绝不编造。
        """
        attr = state.attr
        remaining = state.gauge
        if attr is None:
            return state
        if self._lesson_attr_base is None:
            self._lesson_attr_base = int(attr)
        points = max(int(attr) - int(self._lesson_attr_base), 0)
        clear: int | None = None
        perfect: int | None = None
        left = None
        if remaining is not None:
            try:
                left = max(int(remaining), 0)
            except (TypeError, ValueError):
                left = None
        if left is not None:
            if state.goal == "perfect":
                # 已过关：圆环显示「还差多少到满分」，满分线 = 已得分 + 还差。
                perfect = points + left
                clear = max(round(perfect / 2.0), 1)
            else:
                # 未过关（或档位暂时读不到）：课程总是从 CLEAR 开始冲，按 CLEAR 理解。
                clear = points + left
                perfect = _perfect_line(clear)
        return replace(state, score=points, gauge=clear, perfect=perfect)

    def _read_goal(self, image: np.ndarray) -> str | None:
        """读正中圆环的当前档位：「CLEAR截止 / PERFECT截止」→ clear / perfect。"""
        box = (LAYOUTS.get("lesson") or {}).get("goal")
        if box is None:
            return None
        line = self._safe_line(image, box, digits_only=False)
        text = (line.text or "").upper() if line is not None else ""
        if "PERFECT" in text:
            return "perfect"
        if "CLEAR" in text:
            return "clear"
        return None

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
        cost_line = self._safe_line(image, cost_box)
        if not name:
            name_out = self._safe_line(image, name_box, digits_only=False)
            name = name_out.text if name_out is not None else ""
        # 查表用清洗后的名字（SELECT/SEECT 是选中态标签，不是卡名）；
        # LessonCard.name 保持原文，produce_ui 靠它判断"当前有牌被选中"。
        lookup_name = _clean_lookup_name(name)
        score_line = self._score_line(
            image, score_box, retry=bool(lookup_name) and lookup_name in self._recheck
        )
        score, hits = _parse_score(score_line.text if score_line else "")
        score_estimated = False
        score_unread = False
        recheck = False
        if score is None or score <= 0:
            table_score = self._table_score(lookup_name)
            if table_score is not None and table_score > 0:
                # 宝石没读到、卡表知道这张牌打多少：先按卡表估，下一回合重读宝石
                score = int(table_score)
                score_estimated = True
                recheck = True
                if lookup_name:
                    self._recheck.add(lookup_name)
            else:
                # 卡表也查不到：不编造分数，保持 0；但标成"没读到"，
                # 策略按未知处理（打最便宜的保成长），不会当成 0 分卡跳过，
                # 也不会当成高分。
                score = 0
                score_unread = table_score is None
                if lookup_name:
                    self._recheck.discard(lookup_name)
        elif lookup_name:
            # 这一回合宝石读到了正数，说明上一回合的重读请求已完成
            self._recheck.discard(lookup_name)
        cost = _parse_int(cost_line.text if cost_line else "")
        if cost is not None and not 0 <= cost <= 99:
            cost = None
        # 卡名对上属性表就用真值（OCR 爱心小字 + 确认帧预览都不可靠）
        if lookup_name and self.table is not None:
            table_cost = self.table.cost(lookup_name)
            if table_cost is not None:
                cost = int(table_cost)
        if cost is None and lookup_name and self.costs is not None:
            cached = self.costs.get(lookup_name)
            if cached is not None:
                cost = int(cached)
        text = ""
        buff = False
        conditional = False
        if lookup_name and self.cards is not None:
            info = self.cards.lookup(lookup_name)
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
            score_estimated=score_estimated,
            score_unread=score_unread,
            recheck=recheck,
            highlight=_gold_frame(image, rect),
        )

    def _score_line(self, image, box, *, retry: bool = False):
        """分数宝石：先读原框；待重读的牌再放宽几个框，读到正数就收工。"""
        line = self._safe_line(image, box)
        if not retry or _parse_score(line.text if line else "")[0]:
            return line
        x, y, w, h = box
        for pad in SCORE_RETRY_PADS:
            retried = self._safe_line(image, (x - pad, y - pad, w + pad * 2, h + pad * 2))
            if _parse_score(retried.text if retried else "")[0]:
                return retried
        return line

    def _table_score(self, name: str) -> int | None:
        """按（清洗后的）卡名查卡表打分；查不到返回 None。"""
        if not name or self.table is None:
            return None
        return self.table.score_of(name)

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
            # 汉字或假名都算卡名候选：纯假名卡名（イメトレ / ゆるふわおしゃべり）
            # 旧过滤只认汉字 → 整张漏读（matto 基准日文卡名缺口，F#48 别名先例）。
            if not any(
                "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" for ch in text
            ):
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
        for ja, canonical in _ATTRIBUTE_JA_ALIASES.items():
            if ja in line.text:
                return canonical
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


def _clean_lookup_name(name: str) -> str:
    """查表用的卡名：剔除 OCR 混进卡名的 SELECT/SEECT 等 UI 标签。

    ``tasks.produce_ui`` 依赖 vision 层，这里延迟导入避免顶层循环依赖；
    ``LessonCard.name`` 保留原始文本（选中态检测要靠它）。
    """
    if not name:
        return ""
    from gkagent.tasks.produce_ui import clean_card_name

    return clean_card_name(name)


def _perfect_line(clear: int) -> int:
    """由过关线反推满分线：优先主数据档位表（追い込み 90→360、165→600），缺省 2×。

    普通课 / SP 课的满分线都是过关线的 2 倍；追い込み课是 3.6–4 倍，档位表里能查到，
    不查就会以为"打满"了而收手（课程仍在继续，白丢属性）。
    """
    try:
        from gkagent.sim.hajime_data import perfect_target

        return int(perfect_target(int(clear)))
    except Exception:  # noqa: BLE001 - 查表失败按 2×过关线（绝大多数普通/SP 课如此）
        return int(clear) * 2


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
