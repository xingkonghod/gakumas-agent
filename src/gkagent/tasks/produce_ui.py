"""OCR 驱动的培育 UI 导航（中文本地化界面）。

定位：模板/OCR 只回答「这一屏是什么」，本模块回答「这一步点哪里」。
每调用一次 ``tick``/``decide`` 只做一个动作，外部循环重复调用，便于逐步截图复盘。

坐标系：720x1280（游戏渲染分辨率），固定落点均为真机实测的按钮中心。
"""

from __future__ import annotations

import itertools
import re
import time
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import cv2
import numpy as np

from gkagent.vision.ocr import OcrEngine, OcrLine

if TYPE_CHECKING:
    from gkagent.vision.lesson import LessonCard, LessonState

# ---- 固定落点（720x1280；实测） -------------------------------------------
PRODUCE_ENTRY = (359, 1006)  # 主页「プロデュース」
REGULAR_DIFFICULTY = (359, 900)  # 培育页「レギュラー」
NEXT_BUTTON = (398, 1124)  # 编成三步/开始确认 底部主按钮
AUTO_SUPPORT = (600, 1041)  # 支援卡页「自动」
DIALOG_OK = (456, 1190)  # 二级确认弹窗「确定/完成/下一步」
DIALOG_OK_SMALL = (360, 1163)  # 设置类弹窗「确定」
VOICE_OFF = (195, 852)  # 语音播放确认「不播放语音」
TRAIN_VO = (194, 1012)
TRAIN_DA = (360, 1012)
TRAIN_VI = (525, 1012)
LESSON_ACTION = (268, 1010)  # 「授课」二选一行动
EVENT_ADVANCE = (650, 1080)  # 事件卡右下 ▼
DIALOGUE_FAST = (600, 1185)  # 剧情「快进」
DIALOGUE_SKIP = (208, 1185)  # 剧情「SKIP」

CANCEL_WORD = "取消"
# OCR 常把「剩余回合数」读成「剩余回合」；CLEAR/PERFECT 截止圆环也常被拆分
LESSON_WORDS = ("剩余回合", "CLEAR", "PERFECT")
_GAIN_RE = re.compile(r"[+\-]\s*\d+")
_STAMINA_RE = re.compile(r"(\d{1,3})\s*/\s*(\d{1,3})")

# ---- 属性三维专用 ROI（行动页三颗大属性圆） --------------------------------
# 真机布局：大数字（如 312）在圆心下方 y≈660-700，小字「/1000」在 y≈720。
# 整屏 OCR 要么把数值区裁掉、要么读不出「/1000」，所以用三个固定小框单独读大数字。
# 横向放宽到 190/150/180px：同时覆盖真机 100-210/300-410/500-610 与旧实拍帧
# 192-269/333-411/478-557（实拍校验见 data/produce_actions.png、data/g5.png）。
ATTR_ROIS: tuple[tuple[int, int, int, int], ...] = (
    (90, 655, 190, 70),  # Vo
    (285, 655, 150, 70),  # Da
    (465, 655, 180, 70),  # Vi
)
ATTR_MAX = 2000  # 合理上限：属性显示为 X/1000，加成分后也不会超过 2000
# 固定框兜底用的整图 OCR 取数范围：属性大数字/「/1000」小字/百分比都落在这一带，
# 顶部分数、左上角回合数、底部按钮文字会被排除。
ATTR_FALLBACK_Y = (600, 800)
ATTR_FALLBACK_X_SPLIT = (272, 442)  # 左/中/右三列分界（兼容两种真机布局）
# 三个固定框全空时的廉价闸门：行动页中央有「请选择行动」，别的页面没有。
# 没有这道闸门就要对每个非行动帧跑 5s 的整图 OCR。
ATTR_ACTION_TITLE_BOX = (180, 830, 360, 60)
_ATTR_ACTION_TITLE_WORDS = ("请选择行动", "选择行动", "行动")
_ATTR_NUMBER_RE = re.compile(r"\d+")
_ATTR_DENOMINATOR = 1000  # 显示条「X/1000」的分母

# ---- 课程出牌：卡片详情浮层 / 防死循环 -------------------------------------
# 选牌后游戏会弹出卡牌详情浮层（卡名 / Active / 好调状态的时候，可以使用 / 打分+38）。
# 浮层存在时再点同一坐标只会开关浮层或反复「不满足使用条件」，牌打不出去。
# 这组小框走 OcrEngine.line 的单行快路径（~30ms/个），比整块 OCR（数秒）便宜两个数量级。
CARD_DETAIL_PROBES: tuple[tuple[int, int, int, int], ...] = (
    (140, 618, 440, 40),  # 状态行：Active / Mental / 不满足使用条件
    (140, 658, 440, 38),  # 条件行：好调状态的时候，可以使用
    (140, 696, 440, 42),  # 效果行：打分+38 / 元气+4
    (140, 734, 440, 42),  # 第二条效果行
)
CARD_DETAIL_NAME_BOX = (140, 585, 440, 45)  # 浮层顶部卡名
CARD_DETAIL_BLANK = (360, 260)  # 浮层外上方空白：点这里关闭浮层
LESSON_SKIP_POINT = (657, 800)  # 课程右下「SKIP」
# OCR 会把卡面左下角的「SELECT」标签（及误读）一起读进卡名
UI_LABEL_WORDS = ("SELECT", "SEECT", "S", "A", "M")
_UI_LABEL_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:SELECT|SEECT|S|A|M)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_DETAIL_EFFECT_RE = re.compile(
    r"(?:打分|元气|体力|好调|集中|指針|やる気|元気|好調|集中|指針)\s*[+＋]"
)
_DETAIL_EN_WORDS = ("active", "mental", "support", "trouble")

# ---- 体力门（真机事故：体力 0 进课程，手牌最低 1 费一张都打不出，连按 SKIP 白送回合） ----
DEFAULT_REST_THRESHOLD = 8  # 体力 < 8：连训练都不练，只休息
DEFAULT_LESSON_THRESHOLD = 12  # 体力 < 12：绝不选「授课/课程」，优先休息
DEFAULT_HAND_COST = 3  # 手牌费用完全读不到时的兜底（与 pick_lesson_card 一致）


def clean_card_name(text: str | None) -> str:
    """剔除 OCR 混进卡名的 UI 标签（SELECT/SEECT/单独的 S/A/M），返回真正卡名。

    清洗后可能为空（整行只读到标签）：调用方应改用分数/费用选牌，不能沿用脏名字。
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    value = _UI_LABEL_RE.sub(" ", value)
    value = re.sub(r"[\s\u3000]+", " ", value).strip()
    return value.strip("·・-—_|/\\")


def is_card_detail_text(text: str) -> bool:
    """这段 OCR 文本是否来自卡片详情浮层。"""
    value = unicodedata.normalize("NFKC", text or "").strip()
    if not value:
        return False
    if "不满足使用条件" in value or "可以使用" in value:
        return True
    lowered = value.lower()
    if any(word in lowered for word in _DETAIL_EN_WORDS):
        return True
    return _DETAIL_EFFECT_RE.search(value) is not None


def has_card_detail_overlay(lines: Iterable[OcrLine] | str | None) -> bool:
    """扫描 OCR 行：出现「打分+/Active/可以使用」或手牌区上方大块文本 = 详情浮层。

    除了明确关键词，还兜底「浮层区（y 540-850）出现两条以上长文本」：详情效果文本
    不一定含关键词（例如「考试·舞台中仅限1次」），但正常课程帧这个区域是空的。
    """
    if not lines:
        return False
    if isinstance(lines, str):
        return is_card_detail_text(lines)
    texts: list[str] = []
    block: list[tuple[int, int]] = []
    for line in lines:
        text = (getattr(line, "text", "") or "").strip()
        if not text:
            continue
        texts.append(text)
        _x, y, width, _height = getattr(line, "box", (0, 0, 0, 0))
        if 540 <= int(y) <= 850 and int(width) >= 120 and len(text) >= 6:
            block.append((int(width), len(text)))
    if any(is_card_detail_text(text) for text in texts):
        return True
    return len(block) >= 2 or any(width >= 240 and size >= 10 for width, size in block)


def has_selected_ui(cards: Iterable[LessonCard]) -> bool:
    """手牌里是否有「选中态」标签（卡名被读成 SELECT/SEECT/S/A/M 等）。

    这是浮层检测的免费兜底：选中卡片的卡名框会读到左下角 SELECT 标签，
    即使详情浮层的文字那几行 OCR 恰好失败，也能判定「当前有牌被选中」。
    """
    for card in cards:
        raw = (card.name or "").strip()
        if raw and clean_card_name(raw) != raw:
            return True
    return False


def overlay_card_name(lines: Iterable[OcrLine] | None) -> str:
    """从详情浮层 OCR 行里取真正的卡名（优先浮层顶部最短的一行）。"""
    candidates: list[tuple[int, int, str]] = []
    for line in lines or []:
        raw = (line.text or "").strip()
        if not raw:
            continue
        name = clean_card_name(raw)
        if not name or is_card_detail_text(raw):
            continue
        _x, y, _width, _height = line.box
        if not 540 <= int(y) <= 700:
            continue
        if any(ch.isdigit() for ch in name):
            continue
        if any(mark in name for mark in ("，", ",", "。", "、", "+", "＋")):
            continue
        if not 2 <= len(name) <= 12:
            continue
        candidates.append((len(name), -int(y), name))
    if not candidates:
        return ""
    return min(candidates)[2]


def clean_lesson_state(
    state: LessonState,
    *,
    exclude_names: Iterable[str] = (),
    exclude_points: Iterable[tuple[int, int]] = (),
) -> LessonState:
    """清洗卡名，并剔除已确认打不出去/被点过的牌（按名字或坐标）。"""
    names = set(exclude_names)
    points = {tuple(point) for point in exclude_points}
    cards: list[LessonCard] = []
    for card in state.cards:
        if tuple(card.point) in points:
            continue
        name = clean_card_name(card.name)
        if name and name in names:
            continue
        cards.append(replace(card, name=name))
    return replace(state, cards=tuple(cards))


def lesson_hand_signature(state: LessonState) -> tuple:
    """手牌/分数签名：确认点击后用它判断这一下到底有没有推进。

    只比「剩余回合 + 总分 + 手牌（序号/分数预览）」：选中态会把卡抬高、卡名框读到
    SELECT、费用框读不到，这些都不算推进；真正出牌后分数或牌序至少变一项。
    """
    cards = tuple(
        sorted(
            (int(card.index), int(card.score) if card.score is not None else -1)
            for card in state.cards
        )
    )
    return (state.turns_left, state.score, cards)


def pick_lesson_card(
    cards: Sequence[LessonCard],
    *,
    stamina: int | None = None,
    exclude_names: Iterable[str] = (),
    exclude_points: Iterable[tuple[int, int]] = (),
) -> LessonCard | None:
    """按界面分数/体力费用选牌（卡名清洗后为空也照样可参与）。

    收益 = 分数预览（含次数）÷ 体力费用；没有分数时退化为按费用最便宜。
    """
    names = set(exclude_names)
    points = {tuple(point) for point in exclude_points}
    best: LessonCard | None = None
    best_key: tuple[float, float, int] | None = None
    for card in cards:
        if tuple(card.point) in points:
            continue
        name = clean_card_name(card.name)
        if name and name in names:
            continue
        cost = card.cost if card.cost is not None else 3
        if stamina is not None and cost > stamina:
            continue
        score = float(card.total_score)
        key = (
            score / max(int(cost), 1) if score > 0 else -1.0,
            score,
            -int(cost),
        )
        if best_key is None or key > best_key:
            best_key = key
            best = card
    if best is None:
        return None
    return replace(best, name=clean_card_name(best.name))


def parse_stamina(text: str) -> int | None:
    """从左上角状态条读体力（如 31/35）；属性 /1000 不算。"""
    for match in _STAMINA_RE.finditer(text):
        current, maximum = int(match.group(1)), int(match.group(2))
        if maximum <= 60 and current <= maximum:
            return current
    return None


def parse_attr_value(text: str | None) -> int | None:
    """从属性框的 OCR 文本里取一项属性值（Vo/Da/Vi 之一）。

    大数字下方常带「/1000」小字，可能被一起读成 ``312/1000``；斜杠前缀的分母
    直接剔除。OCR 偶尔把斜杠丢掉、只读成 ``312 1000``，这种 1000 同样按分母
    处理（优先取另一个数），因此「312 和 1000 同时出现」时返回 312。
    框里混进图标/百分号时取剩余数字中最大的一个；读不到或不在 0..2000 返回
    ``None``（调用方不得用 0 顶替）。
    """
    if not text:
        return None
    values: list[int] = []
    for match in _ATTR_NUMBER_RE.finditer(text):
        digits = match.group(0)
        if not 2 <= len(digits) <= 4:  # 属性是 2-4 位数字，单字符噪声不要
            continue
        start = match.start()
        if start > 0 and text[start - 1] in ("/", "／"):
            continue  # 「/1000」分母
        value = int(digits)
        if 0 <= value <= ATTR_MAX:
            values.append(value)
    if not values:
        return None
    numerator = [value for value in values if value != _ATTR_DENOMINATOR]
    if numerator:
        values = numerator
    return max(values)


def lowest_hand_cost(
    cards: Iterable[LessonCard], *, default_cost: int = DEFAULT_HAND_COST
) -> int | None:
    """手牌里最低的体力费用；没有手牌返回 None，费用全读不到时按 ``default_cost``。"""
    cards = list(cards)
    if not cards:
        return None
    costs = [int(card.cost) for card in cards if card.cost is not None and int(card.cost) >= 0]
    return min(costs) if costs else int(default_cost)


def lesson_stamina_gate(
    state: LessonState,
    *,
    stamina: int | None = None,
    default_cost: int = DEFAULT_HAND_COST,
) -> tuple[tuple[int, int], str] | None:
    """课程体力门：体力 < 最低手牌费用（一张牌都打不出）→ ``(SKIP 落点, 原因)``。

    真机事故：体力 0 时 bot 进了课程，手牌最低 1 费一张都打不出，却一回合一点地
    连按 SKIP 白送回合。这里在出牌前直接判定，命中就立刻按 SKIP 结束本回合。
    ``stamina``：``LessonState`` 没读到时用调用方从状态条读到的体力兜底。
    """
    current = state.stamina if state.stamina is not None else stamina
    if current is None:
        return None
    lowest = lowest_hand_cost(state.cards, default_cost=default_cost)
    if lowest is None or current >= lowest:
        return None
    point = state.skip_point or LESSON_SKIP_POINT
    return point, f"体力 {int(current)} < 最低手牌费用 {lowest}，一张牌都打不出"


def choose_action_kind(
    *,
    stamina: int | None,
    has_rest: bool,
    has_lesson: bool,
    has_training: bool,
    rest_threshold: int = DEFAULT_REST_THRESHOLD,
    lesson_threshold: int = DEFAULT_LESSON_THRESHOLD,
) -> str:
    """选择行动时的体力门，返回 ``"rest"`` / ``"lesson"`` / ``"train"`` / ``"wait"``。

    - 体力 < ``rest_threshold``（默认 8）：不训练也不上课，只休息；没有休息按钮则等待；
    - 体力 < ``lesson_threshold``（默认 12）：绝不进课程，有休息先休息，否则训练；
    - 体力读不到（None）时保持旧逻辑：课程优先。
    """
    if stamina is not None:
        if stamina < rest_threshold:
            return "rest" if has_rest else "wait"
        if stamina < lesson_threshold:
            if has_rest:
                return "rest"
            if has_training:
                return "train"
            return "wait"
    if has_lesson:
        return "lesson"
    if has_training:
        return "train"
    if has_rest:
        return "rest"
    return "wait"


class UserBusy(Exception):
    """用户正在用键鼠：这一次动作先不做，等用户离开再继续。"""


@dataclass
class TickResult:
    screen: str
    action: str
    ok: bool = True
    detail: str = ""

    def describe(self) -> str:
        text = f"[{self.screen}] {self.action}"
        return f"{text} {self.detail}".strip()


@dataclass
class LessonPlayGuard:
    """课程出牌防死循环状态机（与截图/点击解耦，真机与单测共用）。

    每帧把「卡片详情浮层是否还开着」喂给 :meth:`observe`，返回下一步动作：

    - ``("pick", None)``：没有浮层，正常选一张牌点**一次**；
    - ``("confirm", point)``：浮层是刚选牌的详情，点同一点确认**一次**；
    - ``("close", CARD_DETAIL_BLANK)``：浮层挡路（残留浮层，或确认后仍开着），
      点浮层外空白关闭，**绝不重复点同一坐标**；
    - ``("skip", LESSON_SKIP_POINT)``：同一坐标连续 3 次没推进，点 SKIP 兜底；
    - ``("wait", None)``：第一次点击已经生效（没有浮层），等下一帧。

    确认失败（点完浮层还在，或浮层关了但分数/手牌没变）会把这张牌的坐标/名字记进
    ``failed_points``/``failed_names``，下次选牌换一张；换完仍不行时最终走到 SKIP。
    """

    skip_after: int = 3
    pending_point: tuple[int, int] | None = field(default=None, init=False)
    pending_name: str = field(default="", init=False)
    awaiting_confirm: bool = field(default=False, init=False)
    last_confirm_point: tuple[int, int] | None = field(default=None, init=False)
    last_confirm_name: str = field(default="", init=False)
    last_failed_point: tuple[int, int] | None = field(default=None, init=False)
    last_failed_name: str = field(default="", init=False)
    failed_names: set[str] = field(default_factory=set, init=False)
    failed_points: set[tuple[int, int]] = field(default_factory=set, init=False)
    same_point_failures: int = field(default=0, init=False)
    stale_closes: int = field(default=0, init=False)
    failure_pending: bool = field(default=False, init=False)

    def picked(self, point: tuple[int, int], name: str = "") -> None:
        """已点了一张牌（第一击），等下一帧看浮层是否出现。"""
        self.pending_point = (int(point[0]), int(point[1]))
        self.pending_name = clean_card_name(name)
        self.awaiting_confirm = False

    def confirm_clicked(self) -> None:
        """确认点击已发出：下一帧浮层还在 = 这张牌打不出去。"""
        if self.pending_point is None:
            return
        self.awaiting_confirm = True
        self.last_confirm_point = self.pending_point
        self.last_confirm_name = self.pending_name
        self.pending_point = None
        self.pending_name = ""

    def close_sent(self) -> None:
        """空白点击成功：累计连续关浮层次数，连续 3 次关不掉就 SKIP。"""
        self.stale_closes += 1

    def observe(
        self, overlay_open: bool, *, progressed: bool = True
    ) -> tuple[str, tuple[int, int] | None]:
        if self.pending_point is not None:
            if overlay_open:
                return ("confirm", self.pending_point)
            # 第一击已经直接生效（没有浮层）：不要再点第二下
            self._progress()
            return ("wait", None)

        if self.awaiting_confirm:
            # 确认后浮层还开着，或浮层关了但分数/手牌完全没变 = 同一坐标没推进
            if overlay_open or not progressed:
                if self._register_failure():
                    return ("skip", LESSON_SKIP_POINT)
                # 没有浮层就不用再点空白，直接换一张；浮层还在先关掉它
                return ("close", CARD_DETAIL_BLANK) if overlay_open else ("pick", None)
            # 确认生效：浮层已关、手牌/分数已变，等一帧让动画稳定后再选
            self._progress()
            return ("wait", None)

        if overlay_open:
            if self.stale_closes >= max(int(self.skip_after), 1):
                return ("skip", LESSON_SKIP_POINT)
            return ("close", CARD_DETAIL_BLANK)
        self.stale_closes = 0
        return ("pick", None)

    def _register_failure(self) -> bool:
        """记一次「同一坐标没推进」，返回是否已经连续 3 次该 SKIP。"""
        point = self.last_confirm_point
        name = self.last_confirm_name
        self.awaiting_confirm = False
        self.last_confirm_point = None
        self.last_confirm_name = ""
        if point is not None:
            if point == self.last_failed_point:
                self.same_point_failures += 1
            else:
                self.last_failed_point = point
                self.same_point_failures = 1
            self.failed_points.add(point)
        self.last_failed_name = name
        self.failure_pending = True
        if name:
            self.failed_names.add(name)
        return self.same_point_failures >= max(int(self.skip_after), 1)

    def take_failure(self) -> tuple[tuple[int, int] | None, str] | None:
        """取走一次「确认后没推进」的通知（调用方负责记日志/拉黑卡名）。"""
        if not self.failure_pending:
            return None
        self.failure_pending = False
        return (self.last_failed_point, self.last_failed_name)

    def reset(self) -> None:
        """离开课程/换回合：清空所有防死循环计数。"""
        self.pending_point = None
        self.pending_name = ""
        self.awaiting_confirm = False
        self.last_confirm_point = None
        self.last_confirm_name = ""
        self.last_failed_point = None
        self.last_failed_name = ""
        self.failed_names.clear()
        self.failed_points.clear()
        self.same_point_failures = 0
        self.stale_closes = 0
        self.failure_pending = False

    def reset_turn(self) -> None:
        """本回合已用 SKIP 结束：计数清零，下一回合重新开始。"""
        self.reset()

    def _progress(self) -> None:
        self.pending_point = None
        self.pending_name = ""
        self.awaiting_confirm = False
        self.last_confirm_point = None
        self.last_confirm_name = ""
        self.last_failed_point = None
        self.last_failed_name = ""
        self.same_point_failures = 0
        self.stale_closes = 0
        self.failure_pending = False


@dataclass
class ProduceDriver:
    ocr: OcrEngine | None = None
    sleep: Callable[[float], None] | None = None
    last_point: tuple[int, int] | None = field(default=None, init=False)
    support_auto_done: bool = field(default=False, init=False)
    exam_card_selected: bool = field(default=False, init=False)
    event_pending_y: int | None = field(default=None, init=False)
    lesson_attribute: str | None = field(default=None, init=False)
    toast_waits: int = field(default=0, init=False)
    stamina_hint: int | None = field(default=None, init=False)
    retry_count: int = field(default=0, init=False)
    gain_waits: int = field(default=0, init=False)
    drink_scroll: int = field(default=0, init=False)
    bottom_roi: tuple[int, int, int, int] = (0, 470, 720, 809)
    corner_roi: tuple[int, int, int, int] = (0, 0, 470, 160)
    top_roi: tuple[int, int, int, int] = (0, 0, 720, 190)
    top_roi_keys: tuple[str, ...] = (
        "下一步",
        "自动",
        "重置",
        "开始培育",
        "请选择行动",
        "选择",
    )

    def __post_init__(self) -> None:
        if self.sleep is None:
            import time

            self.sleep = time.sleep

    # ------------------------------------------------------------------ 工具
    def engine(self) -> OcrEngine:
        if self.ocr is None:
            self.ocr = OcrEngine()
        return self.ocr

    def read(self, image, corner_lines: list[OcrLine] | None = None) -> list[OcrLine]:
        """ROI OCR：底部（按钮/弹窗/行动）+ 左上角状态条（剩余回合数等），按需再补编成标题。

        RapidOCR 检测耗时随面积增长；左上角小条只有 ~6% 面积，常读也便宜。
        左上角很重要：课程屏的「剩余回合数」在这里，漏读会把课程误判成剧情去点 SKIP。
        ``corner_lines``：调用方已经读过左上角时传进来，避免重复 OCR。
        """
        lines = self.engine().read(image, self.bottom_roi)
        if corner_lines is None:
            corner_lines = self.engine().read(image, self.corner_roi)
        lines = lines + corner_lines
        text = self.text_of(lines)
        if any(key in text for key in self.top_roi_keys) or len(text.strip()) < 6:
            lines = lines + self.engine().read(image, self.top_roi)
        return lines

    def read_attrs(self, image) -> tuple[int, int, int] | None:
        """读行动页三颗属性圆的大数字 ``(Vo, Da, Vi)``；三个都读到才返回。

        先用三个固定小框走 :meth:`OcrEngine.line` 单行快路径（每个 ~30ms）；
        固定框偏了（≥2 个读不到、但至少 1 个读到）时退回整图 OCR，按 x 分三列取
        字高最大的数字——属性大数字比下方「/1000」小字和百分比高，能稳定选中。
        三个框全空时先用「请选择行动」廉价探针确认是行动页，再跑整图 OCR；非行动
        页不跑（整图 OCR ~5s，每步都跑会把一步拖慢一倍多，还容易把课程页数字当三维）。
        读不到一律返回 ``None``，不拿 0 顶替。
        """
        report = self.read_attrs_debug(image)
        if report["attrs"] is not None:
            return report["attrs"]
        values = [box["value"] for box in report["boxes"]]
        missing = sum(value is None for value in values)
        if missing >= 2 and any(value is not None for value in values):
            return self._read_attrs_full(image)
        if missing >= 3 and self._looks_like_action_page(image):
            return self._read_attrs_full(image)
        return None

    def _looks_like_action_page(self, image) -> bool:
        """整图兜底前的廉价闸门：行动页中央有「请选择行动」，课程/剧情/结算页没有。"""
        if image is None or getattr(image, "shape", None) is None:
            return False
        try:
            line = self.engine().line(image, ATTR_ACTION_TITLE_BOX, digits_only=False)
        except Exception:  # noqa: BLE001 - 探针失败就不要跑 5s 的整图 OCR
            return False
        text = (line.text or "") if line is not None else ""
        return any(word in text for word in _ATTR_ACTION_TITLE_WORDS)

    def read_attrs_debug(self, image) -> dict:
        """诊断：逐框返回裁剪位置、OCR 文本和解析值（框偏了还是 OCR 崩了一行定位）。

        返回 ``{"attrs": (vo, da, vi) | None, "boxes": [{"attr", "roi", "text", "value"}, ...]}``。
        只反映三个固定框的直读结果，不含整图兜底；``text`` 是每个小框的识别文本。
        """
        boxes: list[dict] = []
        if image is None or getattr(image, "shape", None) is None:
            return {"attrs": None, "boxes": boxes}
        values: list[int | None] = []
        for name, roi in zip(("vo", "da", "vi"), ATTR_ROIS):
            text = ""
            error = ""
            try:
                line = self.engine().line(image, roi, digits_only=False)
            except Exception as exc:  # noqa: BLE001 - 诊断接口不抛异常
                error = f"{type(exc).__name__}: {exc}"
            else:
                text = (line.text or "") if line is not None else ""
            value = parse_attr_value(text)
            values.append(value)
            row = {"attr": name, "roi": tuple(roi), "text": text, "value": value}
            if error:
                row["error"] = error
            boxes.append(row)
        attrs = None
        if all(value is not None for value in values):
            attrs = (values[0], values[1], values[2])
        return {"attrs": attrs, "boxes": boxes}

    def _read_attrs_full(self, image) -> tuple[int, int, int] | None:
        """固定框兜底：整图 OCR，按 x 分左/中/右三列，每列取字高最大的数字。

        真机 UI 在不同宽度/DPI 下位置会漂。全图 OCR 还会读到顶部分数、/1000 分母、
        下方百分比，所以限定属性行 y 带、再按列取「框最高」的那个：大数字最高，
        「/1000」小字次之，百分比最矮。三列都取到才算成功。
        """
        if image is None or getattr(image, "shape", None) is None:
            return None
        try:
            lines = self.engine().read(image)
        except Exception:  # noqa: BLE001 - 兜底 OCR 失败就当没读到
            return None
        left, right = ATTR_FALLBACK_X_SPLIT
        columns: list[list[tuple[int, int]]] = [[], [], []]
        for line in lines:
            x, y, width, height = line.box
            if not ATTR_FALLBACK_Y[0] <= y + height // 2 <= ATTR_FALLBACK_Y[1]:
                continue
            value = parse_attr_value(line.text)
            if value is None:
                continue
            center_x = x + width // 2
            index = 0 if center_x < left else 1 if center_x < right else 2
            columns[index].append((int(height), int(value)))
        picked: list[int] = []
        for column in columns:
            if not column:
                return None
            picked.append(max(column)[1])  # 字高优先：属性大数字 > /1000 小字 > 百分比
        return (picked[0], picked[1], picked[2])

    @staticmethod
    def text_of(lines: list[OcrLine]) -> str:
        return " ".join(line.text for line in lines)

    @staticmethod
    def find(lines: list[OcrLine], *needles: str) -> OcrLine | None:
        """先找整行完全相等的按钮文字，再退回包含匹配（取最短行，优先按钮而非标题）。"""
        for needle in needles:
            for line in lines:
                if line.text.strip() == needle:
                    return line
        for needle in needles:
            candidates = [line for line in lines if needle in line.text]
            if candidates:
                return min(candidates, key=lambda line: len(line.text))
        return None

    @staticmethod
    def find_button(lines: list[OcrLine], words: tuple[str, ...]) -> OcrLine | None:
        """只匹配完全相等的按钮文字（避免点到含关键词的问句/说明）。"""
        for word in words:
            for line in lines:
                if line.text.strip() == word:
                    return line
        return None

    def _simulator_action(
        self,
        agent,
        image,
        lines,
        text,
        stamina: int | None = None,
        *,
        rest_threshold: int = DEFAULT_REST_THRESHOLD,
        lesson_threshold: int = DEFAULT_LESSON_THRESHOLD,
    ):
        """调模拟器选行动：候选=当前界面能点的，比较期望评价点（体力门之后再放宽候选）。"""
        values = self._attr_values(lines or [])
        if values is None:
            return None  # 三维读不到就不冒险，交回原逻辑
        try:
            from gkagent.sim.action_choice import choose_action
            from gkagent.sim.lesson import CardSpec

            deck = [CardSpec(name=f"starter{i}", cost=3, score=9) for i in range(8)]
            deck_raw = getattr(self, "_sim_deck", None)
            if deck_raw:
                deck = deck_raw
            candidates = ["train", "train_low", "rest"]
            # 体力门：<12 不给课程候选；<8 连训练候选都不给，只准休息
            if "授课" in text and (stamina is None or stamina >= lesson_threshold):
                candidates.append("lesson")
            if "外出" in text:
                candidates.append("outing")
            if stamina is not None and stamina < rest_threshold:
                candidates = ["rest"]
            result = choose_action(
                deck,
                getattr(self, "_sim_pool", None),
                attrs=list(values),
                stamina=stamina if stamina is not None else 30,
                week=getattr(self, "_sim_week", 1),
                actions=tuple(candidates),
                episodes=10,
            )
            action = result["action"]
            self._sim_week = getattr(self, "_sim_week", 1) + 1
            if action == "rest":
                rest = self.find_button(lines, ("休息",)) or self.find(lines, "休息")
                self._click_line(agent, rest) if rest else self._click(agent, (360, 900))
                return TickResult("action", "sim-rest")
            if action == "lesson":
                lesson = self.find_button(lines, ("授课",)) or self.find(lines, "授课")
                self._click_line(agent, lesson) if lesson else self._click(agent, (360, 900))
                return TickResult("action", "sim-lesson")
            if action == "outing":
                outing = self.find_button(lines, ("外出",)) or self.find(lines, "外出")
                self._click_line(agent, outing) if outing else self._click(agent, (360, 900))
                return TickResult("action", "sim-outing")
            point, label = self.choose_training(text, lines)
            self.lesson_attribute = label
            self._click(agent, point)
            return TickResult("action", f"sim-train-{label}")
        except Exception:  # noqa: BLE001 - 模拟器出错就退回原逻辑
            return None

    def _produce_params(self) -> dict:
        """读 data/knowledge/policy.json 的 produce 段；坏文件/缺文件回退默认值。"""
        cached = getattr(self, "_produce_cfg", None)
        if isinstance(cached, dict):
            return cached
        defaults = {
            "prefer_lesson": True,
            "rest_threshold": DEFAULT_REST_THRESHOLD,
            "lesson_threshold": DEFAULT_LESSON_THRESHOLD,
            "reward_pick": "best",
            "lesson_every": 1,
            "attr_choice": "weight",
            "min_stamina_to_train": 10,
            "outing_below": -1,
        }
        try:
            import json as _json
            from pathlib import Path as _Path

            raw = _json.loads(_Path(r"D:\Games\gakumas-agent\data\knowledge\policy.json").read_text(encoding="utf-8"))
            section = raw.get("produce") or {}
            if isinstance(section, dict):
                # 保留 policy.json 里的所有键（之前只保留默认字典里的键，新参数被静默丢弃）
                defaults.update(section)
        except Exception:  # noqa: BLE001 - 参数文件坏了就用默认值
            self._produce_cfg = defaults
            return defaults
        self._produce_cfg = defaults
        return defaults

    _REWARD_TABLE = None
    RECOMMEND_WORDS = ("推荐", "おすすめ", "お勧め")

    @classmethod
    def _reward_table(cls):
        try:
            from gkagent.data.card_table import CardTable
        except Exception:  # noqa: BLE001 - 没有卡表就只认推荐标记
            return None
        if cls._REWARD_TABLE is None:
            cls._REWARD_TABLE = CardTable()
        return cls._REWARD_TABLE

    @staticmethod
    def _reward_point(line: OcrLine) -> tuple[int, int]:
        """奖励卡落点：OCR 框（卡名/推荐标签）在卡牌下缘，向上 60px 点到卡身。"""
        x, y, w, h = line.box
        return (x + w // 2, max(60, y + h // 2 - 60))

    @classmethod
    def _best_reward_card(cls, lines, image=None) -> tuple[int, int] | None:
        """奖励选卡：推荐标记（OCR「推荐」/ 金色卡框发光）> 分档估值 > 第一张。

        真机问题：奖励界面有 buff 卡/SSR 卡（游戏闪黄光并标「推荐」）时，旧逻辑
        只按打分/体力选，结果选了白值更高的普通卡。现在推荐标记优先级最高。
        """
        table = cls._reward_table()
        valued: list[tuple[float, tuple[int, int], int]] = []
        if table is not None:
            for line in lines:
                name = (line.text or "").strip()
                if not (2 <= len(name) <= 14):
                    continue
                value = table.value(name)
                if value is None or value <= 0:
                    continue
                point = cls._reward_point(line)
                valued.append((value, point, line.box[0] + line.box[2] // 2))
        # 1) 游戏「推荐」标签（绿底）：优先级最高，哪怕白值不如别的卡
        recommended = [
            (cls._reward_point(line), line.box[0] + line.box[2] // 2)
            for line in lines
            if any(word in (line.text or "") for word in cls.RECOMMEND_WORDS)
        ]
        if recommended:
            best: tuple[float, tuple[int, int]] | None = None
            for point, center_x in recommended:
                # 同一张卡的卡名行按 x 就近匹配，在推荐卡里再挑估值最高的那张
                value = max(
                    (value for value, _point, card_x in valued if abs(card_x - center_x) <= 140),
                    default=0.0,
                )
                if best is None or value > best[0]:
                    best = (value, point)
            if best is not None:
                return best[1]
        # 2) OCR 没读到「推荐」时，用金色卡框/发光兜底（SSR 卡框）
        glow = cls._gold_reward_point(image)
        if glow is not None:
            return glow
        # 3) 识别不到推荐标记：按分档估值挑最强
        if not valued:
            return None
        return max(valued, key=lambda item: item[0])[1]

    @staticmethod
    def _gold_reward_point(image) -> tuple[int, int] | None:
        """奖励卡「闪黄光」：卡身带里找成对的金色竖边，返回卡身中心。

        只认 100-190px 宽的一对竖边（一张卡的左右卡框），单条金色描边
        （卡面特效）不算，避免把普通卡误判成推荐。OCR 读不到「推荐」时才用。
        """
        if image is None or getattr(image, "ndim", 0) < 3 or image.shape[2] < 3:
            return None
        height, width = image.shape[:2]
        if width < 200 or height < 400:
            return None
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hue, sat, brightness = cv2.split(hsv)
        top, bottom = int(height * 0.65), int(height * 0.76)
        left, right = int(width * 0.06), int(width * 0.96)
        gold = (hue >= 15) & (hue <= 40) & (sat >= 120) & (brightness >= 170)
        band = gold[top:bottom, left:right]
        if band.size == 0:
            return None
        columns = band.sum(axis=0)
        threshold = max(8, band.shape[0] // 3)
        peaks = [index for index, count in enumerate(columns) if count >= threshold]
        if not peaks:
            return None
        groups: list[list[int]] = [[peaks[0]]]
        for index in peaks[1:]:
            if index - groups[-1][-1] <= 12:
                groups[-1].append(index)
            else:
                groups.append([index])
        centers = [left + round(sum(group) / len(group)) for group in groups]
        for first, second in itertools.pairwise(centers):
            if 100 <= second - first <= 190:
                return ((first + second) // 2, (top + bottom) // 2)
        return None

    def _checkbox_bands(image) -> list[tuple[int, int]]:
        """在勾选框列（x 610-655）扫描，返回每行勾选框的 (top, bottom)。"""
        if image is None:
            return []
        patch = image[:, 610:655]
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        mask = (gray < 245).astype(int).sum(axis=1)
        bands: list[list[int]] = []
        for y in np.where(mask > 5)[0]:
            if bands and y - bands[-1][-1] <= 8:
                bands[-1].append(int(y))
            else:
                bands.append([int(y)])
        return [(band[0], band[-1]) for band in bands]

    @staticmethod
    def _checkbox_checked(image, y: int) -> bool:
        """看右侧勾选框是否已选中（橙色勾）。拿不到图像就当作已选，避免乱点。"""
        if image is None:
            return True
        patch = image[max(0, y - 14) : y + 14, 600:670]
        if patch.size == 0:
            return True
        blue = patch[:, :, 0].astype(int)
        green = patch[:, :, 1].astype(int)
        red = patch[:, :, 2].astype(int)
        orange = ((red > 180) & (green > 70) & (green < 210) & (blue < 130)).mean()
        return bool(orange > 0.12)

    @staticmethod
    def center(line: OcrLine) -> tuple[int, int]:
        x, y, w, h = line.box
        return x + w // 2, y + h // 2

    def _click_once(self, agent, point: tuple[int, int]) -> None:
        device = agent.device
        force = getattr(device, "click_force", None)
        result = (force if force is not None else device.click)(*point)
        if result is False:
            raise UserBusy
        self.last_point = point

    def _click(self, agent, point: tuple[int, int]) -> None:
        self._click_once(agent, point)
        self.sleep(0.9)

    def _click_line(self, agent, line: OcrLine) -> None:
        self._click(agent, self.center(line))

    # ------------------------------------------------- 课程出牌浮层
    def card_detail_open(self, image, lines: Iterable[OcrLine] | None = None) -> bool:
        """当前帧是否有卡片详情浮层。

        有小图时用固定小框走单行快路径（~30-60ms）；没有图才退回整行文本判断。
        """
        if image is not None and getattr(image, "shape", None) is not None:
            for box in CARD_DETAIL_PROBES:
                try:
                    line = self.engine().line(image, box, digits_only=False)
                except Exception:  # noqa: BLE001, S112 - 单行识别失败就当这一行没读到
                    continue
                if line is not None and is_card_detail_text(line.text):
                    return True
            return False
        return has_card_detail_overlay(lines)

    def card_detail_name(self, image) -> str:
        """浮层顶部卡名（清洗掉 SELECT 等标签）；读不到返回空串。"""
        if image is None:
            return ""
        try:
            line = self.engine().line(image, CARD_DETAIL_NAME_BOX, digits_only=False)
        except Exception:  # noqa: BLE001 - 卡名读不到不阻断出牌
            return ""
        return clean_card_name(line.text) if line is not None else ""

    # ------------------------------------------------------------------ 主入口
    def tick(self, agent) -> TickResult:
        image = agent.shot()
        return self.decide(agent, self.read(image), image)

    def decide(self, agent, lines: list[OcrLine], image=None) -> TickResult:
        try:
            return self._decide(agent, lines, image)
        except UserBusy:
            return TickResult("pause", "user-active", ok=True)

    def _decide(self, agent, lines: list[OcrLine], image=None) -> TickResult:
        text = self.text_of(lines)

        # 0) 空白/纯色转场：等待，不当作「无可执行动作」
        if len(text.strip()) <= 3:
            self.sleep(0.8)
            return TickResult("blank", "wait")

        # 0.5) 加载/转场：只等待，不当作「无可执行动作」
        upper = text.upper()
        if "LOADING" in upper or "加载" in text or "下载" in text or "通信" in text:
            return TickResult("loading", "wait")

        # 0.6) 考试/试镜失败后的「再挑战」确认（不一定带「取消」按钮，先于取消弹窗处理）
        if "再挑战" in text and ("不合格" in text or "剩余" in text):
            retry = self.find_button(lines, ("再挑战",))
            free_available = "免费剩余" in text and re.search(r"免费剩余\s*0", text) is None
            left_available = re.search(r"剩余\s*[1-9]\d*\s*次", text) is not None
            # 只有「不合格」才重开；合格的结果屏虽然也有「再挑战」按钮，但点「下一步」继续
            failed = "不合格" in text or "FAILED" in text
            if failed and retry is not None and (free_available or left_available) and self.retry_count < 2:
                self.retry_count += 1
                self._click_line(agent, retry)
                return TickResult("dialog", "retry")
            end = self.find_button(lines, ("结束培育", "下一步"))
            if end is not None:
                self._click_line(agent, end)
            else:
                self._click(agent, (355, 1148))
            return TickResult("dialog", "end-produce")

        # 1) 弹窗：取消 + 确定/完成/下一步
        if CANCEL_WORD in text:
            # 扭蛋/抽卡确认：和培育无关，一律取消（跑培育时误入过）
            if "扭蛋" in text and "确认" in text:
                cancel = self.find(lines, "取消")
                self._click_line(agent, cancel) if cancel else self._click(agent, (210, 1155))
                return TickResult("dialog", "cancel-gacha")
            if "不播放语音" in text:
                line = self.find(lines, "不播放语音")
                self._click(agent, self.center(line) if line else VOICE_OFF)
                confirm = self.find(lines, "确定")
                if confirm is not None:
                    self._click_once(agent, self.center(confirm))
                    self.sleep(0.9)
                return TickResult("dialog", "voice-off")
            if "再挑战" in text:
                # 期末/考试不合格后的重挑战：有免费次数就重打（用户要求：落后就重开），
                # 没有次数才结束培育。注意不能用「取消」（那是结束培育）。
                # 每局最多重开 2 次，避免在确认框里来回点
                # 第二段确认框（消耗再挑战道具 / 结束培育确认）只有 确定/取消：点确定
                confirm = self.find_button(lines, ("确定",))
                cancel = self.find_button(lines, ("取消",))
                if confirm is not None and cancel is not None:
                    self._click_line(agent, confirm)
                    return TickResult("dialog", "retry-confirm")
                # 授课/课程「再次挑战」确认（消耗道具重上这节课）：取消，继续培育
                if "再次挑战" in text:
                    cancel_btn = self.find_button(lines, ("取消",))
                    self._click_line(agent, cancel_btn) if cancel_btn else self._click(agent, (210, 1155))
                    return TickResult("dialog", "cancel-lesson-retry")
                retry = self.find_button(lines, ("再挑战",))
                free_available = "免费剩余" in text and re.search(r"免费剩余\s*0", text) is None
                left_available = re.search(r"剩余\s*[1-9]\d*\s*次", text) is not None
                if retry is not None and (free_available or left_available) and self.retry_count < 2:
                    self.retry_count += 1
                    self._click_line(agent, retry)
                    return TickResult("dialog", "retry")
                # 该结果屏的按钮是 再挑战/下一步（不是 结束培育）：没次数就点下一步继续
                end = self.find_button(lines, ("结束培育", "下一步"))
                if end is not None:
                    self._click_line(agent, end)
                else:
                    self._click(agent, (355, 1148))
                return TickResult("dialog", "end-produce")
            if "再生成" in text and "确认" in text:
                # 回忆再生成确认：不花票据，取消
                cancel = self.find_button(lines, ("取消",))
                self._click_line(agent, cancel) if cancel else self._click(agent, (210, 1155))
                return TickResult("dialog", "cancel-memory-regen")
            if "休息确认" in text:
                rest = self.find(lines, "休息")
                self._click_line(agent, rest) if rest else self._click(agent, (456, 1163))
                return TickResult("dialog", "rest-confirm")
            # 按钮文本必须精确匹配：「确定继续吗?」这种问句里也含「确定」，
            # 用包含匹配会点到问题文字上（实测卡死 12 次）
            confirm = self.find_button(lines, ("下一步", "确定", "完成", "选择", "OK"))
            if confirm is not None:
                self._click_line(agent, confirm)
                return TickResult("dialog", "confirm", detail=confirm.text)

        # 2) 培育页：定期公演 + 难度
        if "定期公演" in text or ("培育" in text and "研修" in text):
            self.support_auto_done = False
            self._click(agent, REGULAR_DIFFICULTY)
            return TickResult("scenario", "regular")

        # 3) 开始前编成四步
        if "选择偶像" in text:
            self._click(agent, NEXT_BUTTON)
            return TickResult("setup-idol", "next")
        if "选择支援卡" in text:
            auto = self.find(lines, "自动")
            # 自动编成只需点一次；之后再点会反复弹「自动编成」确认，永远到不了下一步
            if auto is not None and not self.support_auto_done and "自动编成" not in text:
                self.support_auto_done = True
                self._click_line(agent, auto)
                return TickResult("setup-support", "auto")
            self._click(agent, NEXT_BUTTON)
            return TickResult("setup-support", "next")
        if "选择回忆" in text:
            self.support_auto_done = False
            self._click(agent, NEXT_BUTTON)
            return TickResult("setup-memory", "next")
        if "开始确认" in text:
            start = self.find(lines, "开始培育")
            self._click_line(agent, start) if start else self._click(agent, NEXT_BUTTON)
            return TickResult("setup-confirm", "start")

        # 4) 教学出牌：交给卡牌策略
        if any(word in text for word in LESSON_WORDS):
            return TickResult("lesson", "card-policy")

        # 4.3) 特定弹窗优先于通用「+N 飘字」处理，否则会被 _GAIN_RE 抢走
        if "持有上限" in text or ("保留" in text and "饮料" in text):
            # 勾选不够时「保留」是灰的：先补勾未选中的饮料行
            need = 0
            need_match = re.search(r"还可选择\s*(\d+)", text)
            if need_match:
                need = int(need_match.group(1))
            if need > 0 and image is not None:
                # 「获得的饮料」段勾选是灰的（不可选)；按勾选框列扫描出行位置，
                # 只补勾「手持的饮料」下面未勾选的行（行位置和文字行 y 有 20-50px 偏差，不能直接用文字行）
                hand_header = self.find(lines, "手持的饮料")
                header_y = hand_header.box[1] if hand_header is not None else 400
                clicked = False
                for top, bottom in self._checkbox_bands(image):
                    center = (top + bottom) // 2
                    if center < header_y + 20 or center > 1100:
                        continue
                    if not self._checkbox_checked(image, center):
                        self._click(agent, (632, center))
                        clicked = True
                        break
                if clicked:
                    return TickResult("drink-keep", "check-row")
                # 找不到未勾选行：第三瓶可能在列表下方（需要滚动）
                if self.drink_scroll < 2:
                    self.drink_scroll += 1
                    agent.device.swipe(360, 1020, 360, 760)
                    time.sleep(0.8)
                    return TickResult("drink-keep", "scroll")
            keep = self.find(lines, "保留")
            self._click_line(agent, keep) if keep else self._click(agent, (360, 1166))
            return TickResult("drink-keep", "keep")

        # 4.35) P点数兑换商店（咨询）：不买，直接「结束」
        if ("进行兑换" in text or "兑换的道具" in text or "用P点数" in text) and "结束" in text:
            end = self.find(lines, "结束")
            self._click_line(agent, end) if end else self._click(agent, (640, 1165))
            return TickResult("shop", "exit")

        # 4.4) 外出/事件选择：点最下面那个选项（默认高亮、通常是免费项），再点一次确认
        # 实测两种布局：戏剧/体育/露营（短标签），以及「平时都做些什么工作呢？」这种长句选项；
        # P 费用里的「-」经常 OCR 丢，所以不按费用配对了。
        option_rows = [
            line
            for line in lines
            if 600 <= self.center(line)[1] <= 950
            and 2 <= len(line.text.strip()) <= 20
            and not any(ch.isdigit() for ch in line.text)
            and "P" not in line.text
            and "快进" not in line.text
        ]
        if "快进" in text and "请选择行动" not in text and len(option_rows) >= 2:
            if self.event_pending_y is not None:
                y = self.event_pending_y
                self.event_pending_y = None
                self._click(agent, (360, y))
                return TickResult("event-choice", "confirm")
            target = max(option_rows, key=lambda line: self.center(line)[1])
            y = self.center(target)[1]
            self.event_pending_y = y
            self._click(agent, (360, y))
            return TickResult("event-choice", "last-row")

        # 5) 培养主界面：选择行动（三训练 / 授课+活动奖励 / 外出+咨询 / 休息）
        # 必须排在通用「+N 飘字」之前：行动页常驻 +12.9% 之类的属性数字
        training_hits = sum(1 for word in ("Vo", "Da", "Vi") if word in text)
        stamina = parse_stamina(text)
        params = self._produce_params()
        rest_threshold = int(params.get("rest_threshold", DEFAULT_REST_THRESHOLD))
        lesson_threshold = int(params.get("lesson_threshold", DEFAULT_LESSON_THRESHOLD))
        # 体力不够就别硬练：优先休息（当前帧没读到体力就用上一帧的）
        effective_stamina = stamina if stamina is not None else self.stamina_hint
        has_rest = "休息" in text
        has_lesson = "授课" in text
        has_training = training_hits >= 1 or "训练" in text
        on_action_screen = (
            "请选择行动" in text
            or (training_hits >= 2 and "训练" in text)
            or ("授课" in text and "活动奖励" in text)
            or (has_rest and (has_lesson or has_training))
        )
        # 外出/咨询不耗体力（外出还回体力），体力再低也能选，放在体力门之前
        if "外出" in text and "咨询" in text:
            self._click(agent, (450, 1027))
            return TickResult("action", "consult")
        if "外出" in text and "授课" in text:
            # 外出（耗 P 回体力）+ 授课 的二选一：选外出回体力
            self._click(agent, (268, 1010))
            return TickResult("action", "go-out")
        if on_action_screen:
            # 体力门（真机事故）：体力 0 进了课程，手牌最低 1 费一张都打不出，
            # bot 却一回合一点连按 SKIP 白送回合。这里先按体力剔掉课程/训练。
            action_kind = choose_action_kind(
                stamina=effective_stamina,
                has_rest=has_rest,
                has_lesson=has_lesson,
                has_training=has_training,
                rest_threshold=rest_threshold,
                lesson_threshold=lesson_threshold,
            )
            if effective_stamina is not None and action_kind == "rest":
                rest = self.find_button(lines, ("休息",)) or self.find(lines, "休息")
                self._click_line(agent, rest) if rest else self._click(agent, (640, 860))
                return TickResult("action", "rest")
            if effective_stamina is not None and action_kind == "wait":
                # 没有任何安全的行动（体力 <8 又没休息）：等恢复，绝不点授课/训练
                self.sleep(0.8)
                return TickResult(
                    "action",
                    "stamina-wait",
                    ok=False,
                    detail=f"体力 {effective_stamina} 不足（<{rest_threshold}），只休息",
                )
            # 模拟器选行动（默认关）：对候选行动做 rollout 比评价点，再映射到界面按钮
            if params.get("sim_choice") and image is not None:
                sim_pick = self._simulator_action(
                    agent,
                    image,
                    lines,
                    text,
                    effective_stamina,
                    rest_threshold=rest_threshold,
                    lesson_threshold=lesson_threshold,
                )
                if sim_pick is not None:
                    return sim_pick

            # 模拟器结论：课程（得分×0.6 转属性）明显强于训练，能上课就上课
            if (
                action_kind == "lesson"
                and "授课" in text
                and (training_hits == 0 or params.get("prefer_lesson", True))
            ):
                lesson_line = self.find(lines, "授课")
                if lesson_line is not None:
                    self._click_line(agent, lesson_line)
                else:
                    self._click(agent, LESSON_ACTION)
                return TickResult("action", "lesson")
            point, label = self.choose_training(text, lines)
            # 训练属性即接下来课程的属性：记下来给手牌加权用（之前没记 → 出牌不看属性 → CLEAR 失败）
            self.lesson_attribute = label
            train_line = self.find(lines, f"{label}") if label in ("Vo", "Da", "Vi") else None
            if train_line is not None:
                self._click_line(agent, train_line)
            else:
                self._click(agent, point)
            return TickResult("action", f"train-{label}")

        # 6) 已选中行动，点同一点确认（训练预览「能力值上升」/ 授课预览「根据选项」）
        if "能力值上升" in text or "根据选项" in text or "SELECT" in text:
            # 顺手记录三维（真机标定用：每周一条，反解"课程得分→属性成长"系数）
            try:
                values = self._attr_values(lines or [])
                if values is not None:
                    from gkagent.data.calibration import record

                    record(values, tag="train-confirm")
            except Exception:  # noqa: BLE001 - 标定失败不影响培育
                self._calib_failed = True
            point = self.last_point or TRAIN_DA
            self._click(agent, point)
            return TickResult("action-confirm", "confirm")

        # 4.54) 培育结束后的「回忆概览」页：点「下一步」（页面上的百分比/数字会让飘字分支误判）
        if "回忆概览" in text or ("回忆变换" in text and "重新生成" in text):
            nxt = self.find_button(lines, ("下一步",))
            self._click_line(agent, nxt) if nxt else self._click(agent, (339, 1075))
            return TickResult("memory", "next")

        # 4.55) 获得 P 点数的提示条会盖住行动按钮，等它消失
        # 注意只认连在一起的「获得P点数」，避免把行动页说明「消耗P点数，可以获得…」误判
        # 连续等 3 次还在 = 是「结果弹窗」里的获得P点数，点关闭/中央推进
        if "获得P点数" in text or "P点数获得" in text:
            self.toast_waits += 1
            if self.toast_waits >= 3:
                self.toast_waits = 0
                close = self.find(lines, "关闭")
                self._click_line(agent, close) if close else self._click(agent, (360, 1215))
                return TickResult("toast", "dismiss")
            self.sleep(0.6)
            return TickResult("toast", "wait")
        self.toast_waits = 0
        # 4.56) True End / 条件成就 达成弹窗：底部 ✕ 关闭
        if "条件成就" in text or "True End" in text:
            close = self.find(lines, "关闭")
            self._click_line(agent, close) if close else self._click(agent, (360, 1215))
            return TickResult("achievement", "close")

        # 4.57) 考试「移动」阶段：先点上方技能卡（y≈500），再点移动（两步交替）
        if "移动" in text:
            if not self.exam_card_selected:
                self.exam_card_selected = True
                self._click(agent, (185, 500))
                return TickResult("exam", "select-card")
            self.exam_card_selected = False
            move = self.find(lines, "移动")
            self._click_line(agent, move) if move else self._click(agent, (360, 1166))
            return TickResult("exam", "move")

        # 4.56) P饮料获得/技能发动说明弹窗：点中央推进（带「领取」的是奖励选择弹窗，走 4.6）
        # 注意：外出事件的效果说明里也有「获得随机P饮料」，带「快进」的是事件屏，交给 4.4
        if (
            "P饮料" in text
            and ("获得" in text or "饮料" in text)
            and "领取" not in text
            and "快进" not in text
        ):
            self._click(agent, (360, 1000))
            return TickResult("toast", "advance")

        # 4.35) 活动奖励进度页（培育结束后出现）：底部是「下一步」，点空白会一直空转
        if ("活动Pt" in text or "活动奖励进度" in text) and "下一步" in text:
            nxt = self.find_button(lines, ("下一步",))
            self._click_line(agent, nxt) if nxt else self._click(agent, (360, 1135))
            return TickResult("reward-page", "next")

        # 4.4) 行动结算页（顶部「活动奖励/授课」标题、没有「请选择行动」按钮）：点一下继续
        # 注意：奖励领取弹窗顶部也有「活动奖励」，必须排除，否则会一直点空白
        if (
            ("活动奖励" in text or "授课" in text)
            and "请选择行动" not in text
            and "领取" not in text
        ):
            self._click(agent, (360, 1000))
            return TickResult("result-tap", "settle")

        # 4.6) 领取奖励（技能卡或 P 饮料）：推荐卡优先，其次分档估值最强，再点「领取」
        if "请选择要领取" in text:
            best = self._best_reward_card(lines, image)
            if best is not None:
                self._click(agent, best)
            else:
                recommend = self.find(lines, "推荐")
                if recommend is not None:
                    cx, cy = self.center(recommend)
                    # 「推荐」标签在卡牌下缘，点它选不中卡；向上 60px 点到卡身
                    self._click(agent, (cx, max(60, cy - 60)))
                else:
                    self._click(agent, (250, 915))  # 三选一的第一张
            claim = self.find(lines, "领取")
            self._click_once(agent, self.center(claim) if claim else (360, 1097))
            self.sleep(0.9)
            return TickResult("card-reward", "pick+claim")
        # 4.05) "领取完成/已领取以下奖励" 结算弹窗：点关闭，别反复点领取（会死循环）
        if any(word in text for word in ("领取完成", "已领取以下奖励", "已领取以下报酬")):
            close = self.find_button(lines, ("关闭", "确定")) or self.find(lines, "关闭")
            self._click_line(agent, close) if close else self._click(agent, (360, 1160))
            return TickResult("reward-done", "close")
        if "领取" in text:
            claim = self.find_button(lines, ("领取", "全部领取")) or self.find(lines, "领取")
            self._click_line(agent, claim) if claim else self._click(agent, (360, 1131))
            return TickResult("card-reward", "claim")

        # 4.2) 课程类型选择（重点练习歌唱/舞蹈/视觉效果，底部还带「快进」按钮）
        if "重点练习" in text:
            match = re.search(r"推荐\s*(歌唱|舞蹈|视觉)", text)
            choice = match.group(1) if match else "舞蹈"
            self.lesson_attribute = {"歌唱": "Vo", "舞蹈": "Da", "视觉": "Vi"}[choice]
            point = {"歌唱": (360, 702), "舞蹈": (360, 798), "视觉": (360, 894)}[choice]
            self._click(agent, point)
            return TickResult("lesson-choice", f"pick-{choice}")

        # 4.45) 结果弹窗（工作完成/活动完成等）：底部有「完成」就点它，别被飘字分支抢走
        complete = None
        for word in ("完成",):
            line = self.find(lines, word)
            if line is not None and self.center(line)[1] > 1080:
                complete = line
                break
        if complete is not None:
            self._click_line(agent, complete)
            return TickResult("button", "完成")

        # 4.5) 课程结算飘字（Da.上升了58!）或奖励弹字（P+45）：点屏幕中央继续
        # 连续 3 次还在 = 是静态结果页，改点「下一步/确定/关闭」
        if any(word in text for word in ("上升了", "提升了", "下降了", "获得了")) or _GAIN_RE.search(text):
            self.gain_waits += 1
            if self.gain_waits >= 3:
                self.gain_waits = 0
                nxt = self.find_button(lines, ("下一步", "确定", "完成", "关闭", "领取"))
                if nxt is not None:
                    self._click_line(agent, nxt)
                    return TickResult("result-tap", "next")
            else:
                self._click(agent, (360, 1000))
                return TickResult("result-tap", "gain")
            self._click(agent, (360, 1000))
            return TickResult("result-tap", "gain")

        # 7) 剧情快进/跳过 + 最终演出跳过
        # 7.0) 剧情播放器（1章6话 那种：播放条 + 「到下一个选项」+ 选项气泡）
        if "到下一个选项" in text or ("显示所有字幕" in text and "章" in text):
            options = [
                line
                for line in lines
                if 650 <= self.center(line)[1] <= 1150
                and ("？" in line.text or "?" in line.text)
                and len(line.text.strip()) <= 20
            ]
            if options:
                target = min(options, key=lambda line: self.center(line)[1])
                self._click_line(agent, target)
                return TickResult("story", "choice")
            self._click(agent, (665, 50))  # 右上「下一个选项/跳过」
            return TickResult("story", "next")
        if "跳过演出" in text or "演出跳过" in text:
            line = self.find(lines, "跳过演出") or self.find(lines, "演出跳过")
            self._click_line(agent, line) if line else self._click(agent, DIALOGUE_SKIP)
            return TickResult("story", "skip-live")
        if "SKIP" in text or "快进" in text:
            fast = self.find(lines, "快进")
            if fast is not None:
                self._click_line(agent, fast)
                return TickResult("story", "fast")
            skip = self.find(lines, "SKIP")
            if skip is not None:
                self._click_line(agent, skip)
                return TickResult("story", "skip")
            self._click(agent, DIALOGUE_SKIP)
            return TickResult("story", "skip-fallback")

        # 8) 事件卡/结果页：找按钮文字
        for word in ("下一步", "继续", "完成", "获取", "领取", "确定", "跳过", "关闭"):
            line = self.find(lines, word)
            if line is not None:
                self._click_line(agent, line)
                return TickResult("button", word)

        # 9) 主页 → 培育入口
        if "主页" in text or "プロデュース" in text:
            self._click(agent, PRODUCE_ENTRY)
            return TickResult("home", "enter-produce")

        # 10) 事件卡只有 ▼
        if "打分" in text or "▼" in text:
            self._click(agent, EVENT_ADVANCE)
            return TickResult("event", "advance")

        # 11) 带标点的长文本基本是剧情/对话：点对话框继续
        # 11.0) 先处理「剧情选择项」：底部 2-3 个带问号的选项气泡，点最上面那个
        # 「回合结束」确认弹窗：点「是」（SKIP 后必出，点不到就永远出不了课程）
        if "回合结束" in text and "确定" in text:
            self._click(agent, (500, 1200))
            return TickResult("dialog", "end-turn-yes")

        # 误触打开的「育成目标」面板：立刻点底部 X 关闭，别在里面空转
        if "育成目标" in text and ("亲密度" in text or "编成" in text):
            self._click(agent, (360, 1218))
            return TickResult("panel", "close")

        choices = [
            line
            for line in lines
            if 650 <= self.center(line)[1] <= 1150
            and ("？" in line.text or "?" in line.text)
            and 2 <= len(line.text.strip()) <= 25
        ]
        if len(choices) >= 2:
            target = min(choices, key=lambda line: self.center(line)[1])
            self._click_line(agent, target)
            return TickResult("story", "choice")
        if len(text.strip()) > 10 and any(mark in text for mark in ("。", "！", "？", "…")):
            self._click(agent, (360, 1000))
            return TickResult("story", "tap")

        # 12) 空转兜底：认不出的弹窗/提示（P饮料获得、技能发动说明等）点中央推进
        if len(text.strip()) > 6:
            self._click(agent, (360, 1000))
            return TickResult("unknown-tap", "tap", detail=text[:40])

        return TickResult("unknown", "no-op", ok=False, detail=text[:60])

    # ------------------------------------------------------------------ 策略
    @staticmethod
    def _attr_values(line: list[OcrLine]) -> tuple[int, int, int] | None:
        """训练界面三个 X/1000 的属性值 → (Vo, Da, Vi)；读不到返回 None。"""
        import re as _re

        found: list[tuple[int, int]] = []
        for item in line:
            match = _re.search(r"(\d{1,4})\s*/\s*1000", item.text or "")
            if match:
                found.append((item.box[0], int(match.group(1))))
        if len(found) < 3:
            return None
        found.sort(key=lambda pair: pair[0])
        return (found[0][1], found[1][1], found[2][1])

    def choose_training(self, text: str, lines: list[OcrLine] | None = None) -> tuple[tuple[int, int], str]:
        """优先跟随游戏「推荐」气泡；开了补短板(attr_choice=lowest)时练三维最低的那项。"""
        # 补短板：模拟器结论——同样总和，均衡三维能进前 3，偏堆会不合格
        if lines and self._produce_params().get("attr_choice") == "lowest":
            values = self._attr_values(lines)
            if values is not None:
                labels = ("Vo", "Da", "Vi")
                index = min(range(3), key=lambda i: values[i])
                points = {"Vo": TRAIN_VO, "Da": TRAIN_DA, "Vi": TRAIN_VI}
                return points[labels[index]], labels[index]
        points = {"Vo": TRAIN_VO, "Da": TRAIN_DA, "Vi": TRAIN_VI}
        if lines:
            for line in lines:
                if "推荐" not in line.text:
                    continue
                for word, label in (("歌唱", "Vo"), ("舞蹈", "Da"), ("视觉", "Vi")):
                    if word in line.text:
                        return points[label], label
                cx, _ = self.center(line)
                if cx < 265:
                    return TRAIN_VO, "Vo"
                if cx < 440:
                    return TRAIN_DA, "Da"
                return TRAIN_VI, "Vi"
        for word, point, label in (
            ("歌唱", TRAIN_VO, "Vo"),
            ("舞蹈", TRAIN_DA, "Da"),
            ("视觉", TRAIN_VI, "Vi"),
        ):
            if f"推荐{word}" in text:
                return point, label
        return TRAIN_DA, "Da"
