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

from gkagent.data.run_record import (
    parse_eval_points,
    parse_exam_result,
    parse_grade,
    week_from_countdown,
)
from gkagent.runtime.tapguard import (
    PickerGuard,
    TapExpectation,
    expect_change,
    expect_dialog_gone,
)
from gkagent.vision.ocr import OcrEngine, OcrLine
from gkagent.vision.ocr_cache import SemanticScreenCache

if TYPE_CHECKING:
    from gkagent.vision.lesson import LessonCard, LessonState

# ---- 固定落点（720x1280；实测） -------------------------------------------
PRODUCE_ENTRY = (359, 1006)  # 主页「プロデュース」
REGULAR_DIFFICULTY = (220, 915)  # 难度选择页「レギュラー」按钮中心（2026-11-21 实测：旧值
# (359,900) 落在「レギュラー」和「プロ」两个按钮之间的缝隙，点了没反应）
NEXT_BUTTON = (398, 1124)  # 编成三步/开始确认 底部主按钮
AUTO_SUPPORT = (600, 1041)  # 支援卡页「自动」
DIALOG_OK = (456, 1190)  # 二级确认弹窗「确定/完成/下一步」
NET_RETRY = (510, 1151)  # 通信错误弹窗「重试」（获取资产失败 E203）
DIALOG_OK_SMALL = (360, 1163)  # 设置类弹窗「确定」
VOICE_OFF = (195, 852)  # 语音播放确认「不播放语音」
TRAIN_VO = (194, 1012)
TRAIN_DA = (360, 1012)
TRAIN_VI = (525, 1012)
LESSON_ACTION = (268, 1010)  # 「授课」二选一行动
EVENT_ADVANCE = (650, 1080)  # 事件卡右下 ▼
DIALOGUE_FAST = (600, 1185)  # 剧情「快进」
# 初模式「授课」答题屏：三个属性答案行（720x1280 设计坐标，实测中心）
CLASS_QUIZ_ROWS = ((360, 730), (360, 840), (360, 952))  # Vo / Da / Vi
DIALOGUE_SKIP = (208, 1185)  # 剧情「SKIP」

CANCEL_WORD = "取消"
# OCR 常把「剩余回合数」读成「剩余回合」；CLEAR/PERFECT 截止圆环也常被拆分
LESSON_WORDS = ("剩余回合", "CLEAR", "PERFECT")
# 「+N 飘字」：只认**正收益**（P+45 / 打分+38 / Da.上升了58 由文字分支兜底）。
# F#43 的真根因之一：旧正则 `[+\-]\s*\d+` 把外出饮料选择屏的 P 费标签「-100 / -50」
# 当成飘字 → 每步点屏幕中央空转 10 次停机（见 docs/FAILURES.md #43）。
_GAIN_RE = re.compile(r"[+＋]\s*\d+")
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
# 只有这些屏才可能出现三颗属性圆（行动页/训练页/外出咨询页）。课程、剧情、加载、
# 结算页都没有——用文本提示先筛掉，省掉每步 3 次单行 OCR。
_ATTR_PAGE_WORDS = (
    "请选择行动",
    "授课",
    "休息",
    "训练",
    "外出",
    "咨询",
    "活动奖励",
    "Vo",
    "Da",
    "Vi",
)


def _might_show_attributes(text: str | None) -> bool:
    """文本里是否可能出现行动页的三维圆；空文本按"不确定"处理（继续读）。"""
    if not text:
        return True
    return any(word in text for word in _ATTR_PAGE_WORDS)

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
LESSON_SKIP_POINT = (657, 800)  # 课程右下「SKIP」（点的是圆形箭头图标，不是 SKIP 文字）
TURN_END_YES = (492, 1197)  # SKIP 后「回合结束」确认框的「是」（2026-11-16 按真机截图 step_235 实测；旧值 y=1155 点空）
# 培育记录详情弹窗底部的圆形 X（OCR 读不出这个图标，只能固定坐标；真机截图核对：
# data/auto/step_055.png，720x1280 下圆心约 (360,1197)）
PRODUCE_RECORD_CLOSE = (360, 1197)
# ---- 培育结束后的结算/收尾画面（F#15） -------------------------------------
# 真机顺序：评价页 → 回忆照片选择页 → 培育记录详情 → 主页。
# 回忆照片选择页（data/settlement_photo_select.png，720x1280，真机截图）：
#   「请选择要作为回忆的照片」+ 3 列照片网格（第一张在左上，默认带橙框）
#   + 底部「保存到本地」「保存到相册」（「保存到相册」在右下）。
MEMORY_FIRST_PHOTO = (116, 575)  # 照片网格第一张（左上，点一下确保选中）
MEMORY_SAVE_ALBUM = (614, 1088)  # 「保存到相册」
MEMORY_SAVE_LOCAL = (430, 1088)  # 「保存到本地」
# ---- 考试/试镜模式（F#17） ---------------------------------------------------
# 考试页顶部有 1st..6th 排名条（真机 data/exam_rank_frame.png：1st 在 x≈240-310、
# y≈5-40，4th 到 x≈655，5th/6th 被屏幕右缘裁掉）。课程页没有这排字。
EXAM_RANK_ROI = (228, 0, 492, 48)  # 排名条 1st..4th（720x1280）
# ---- 跑局数据管道（data/run_record.py）读取 ROI ------------------------------
# 行动页左上「期中截止 / 最终截止」+ 下面一行「N周」（真机 data/manual/182343）。
# N 是距离截止的剩周：期中阶段 4周 = 第 2 周；期末阶段 6周 = 第 7 周。
WEEK_LABEL_ROI = (26, 20, 320, 70)
WEEK_NUM_ROI = (20, 72, 300, 58)
# 最终结算屏（真机 data/manual/190647）：标题「最终培育评价」、评价字母在中央
# 菱形里、评价点是下方大数字。标题框用来挡住「培育记录」等收尾页的误读。
FINAL_TITLE_ROI = (180, 130, 360, 80)
FINAL_GRADE_ROI = (200, 350, 320, 300)
FINAL_EVAL_ROI = (200, 810, 320, 90)
# 考试页 SKIP 与课程同坐标（真机 step_015 核对：圆形 SKIP 在 (655,800)）。
EXAM_SKIP_POINT = (655, 800)
_EXAM_RANK_RE = re.compile(r"[1-6]\s*(?:st|nd|rd|th)\b", re.IGNORECASE)
# 兜底降级用的「屏幕中央下方」（行动页/结算页通用的推进点）
SETTLE_CENTER_TAP = (360, 1000)
# OCR 会把卡面左下角的「SELECT」标签（及误读）一起读进卡名
UI_LABEL_WORDS = ("SELECT", "SEECT", "S", "A", "M")
_UI_LABEL_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:SELECT|SEECT|S|A|M)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_DETAIL_EFFECT_RE = re.compile(
    r"(?:打分|得分|元气|体力|好调|集中|指針|やる気|元気|好調|集中|指針)\s*[+＋]"
)
_DETAIL_EN_WORDS = ("active", "mental", "support", "trouble")
# 考试（audition）的卡片详情浮层和课程的文案不同：效果行是「得分+23（集中效果会2倍生效）」，
# 附加行是「考试·舞台中仅限1次」。旧规则只认「打分+」→ 考试里浮层永远判不出来，
# 出牌卡在「选牌 → 等下一帧 → 再选牌」循环（真机 ep-t1-e 期中考试 回合5，10 步停机）。
_DETAIL_CN_MARKERS = (
    "不满足使用条件",
    "可以使用",
    "仅限1次",
    "舞台中仅限",
)

# ---- 快速读屏（省掉整屏检测） ------------------------------------------------
# 常用屏（加载/剧情/事件选项/行动/训练/外出咨询/领奖）的文字都在固定位置。
# 这里每个框只跑 line() 的"只识别"快路径（缓存命中的话连识别都不跑），
# 比"整屏检测 + 逐行识别"便宜一个数量级。检测框只用于确认"这屏是不是它"；
# 任何一项关键文字读不出来就退回整屏 read()，不拿猜测去点击。
FAST_STATUS_BOX = (26, 20, 320, 70)  # 剩余回合数 / 期中截止
FAST_ACTION_TITLE_BOX = (180, 830, 360, 60)  # 请选择行动
FAST_RECOMMEND_BOX = (420, 195, 300, 35)  # 推荐歌唱训练
FAST_TRAIN_LABEL_BOXES: tuple[tuple[int, int, int, int], ...] = (
    (95, 1040, 150, 60),  # Vo.训练
    (290, 1040, 150, 60),  # Da.训练
    (490, 1040, 150, 60),  # Vi.训练
)
FAST_LESSON_BOX = (285, 1055, 150, 60)  # 授课
FAST_REST_BOX = (605, 865, 95, 35)  # 休息
FAST_OUTING_BOX = (125, 1095, 130, 50)  # 外出
FAST_CONSULT_BOX = (300, 1095, 120, 50)  # 咨询
FAST_ACTIVITY_BOX = (465, 1095, 150, 50)  # 活动奖励
FAST_STAMINA_BOX = (310, 55, 110, 45)  # 24/35
FAST_P_BOX = (315, 105, 110, 45)  # P 41（P 点）
FAST_LOADING_BOX = (20, 1185, 220, 55)  # 正在下载数据
FAST_LOADING_EN_BOX = (540, 1175, 170, 55)  # NOW LOADING... / 快进
FAST_EVENT_FAST_BOX = (545, 1165, 170, 65)  # 快进（文字实际位置略高，兜底再读一次）
# 剧情选项/底部对白区域：快速路径的窄行 OCR 会把日文长句截成 1-2 个字
# （真机 ep-t3-3：选项气泡 785/885、对白 977/1019 全被截断 → 剧情选项永远点不到）。
# 有「快进」的帧补读这一条区域，供 decide 判断「剧情选项」。
FAST_DIALOGUE_AREA = (0, 600, 720, 540)
FAST_EVENT_ROW_BOXES: tuple[tuple[int, int, int, int], ...] = (
    (70, 690, 590, 90),
    (70, 790, 590, 90),
    (70, 890, 590, 90),
)
FAST_REWARD_TITLE_BOX = (200, 600, 400, 60)  # 请选择要领取的技能卡。
FAST_REWARD_RECOMMEND_BOX = (300, 945, 140, 55)  # 推荐标签
FAST_REWARD_CLAIM_BOX = (300, 1070, 130, 55)  # 领取
FAST_BUTTON_BOXES: tuple[tuple[int, int, int, int], ...] = (
    (250, 1080, 220, 100),  # 中下：确定/下一步/领取/完成
    (50, 1080, 200, 100),  # 左下：取消/否
    (470, 1080, 200, 100),  # 右下：关闭/保存
)
_FAST_ACTION_WORDS = ("授课", "休息", "外出", "咨询", "活动奖励", "训练")
# 事件选项行的费用后缀：体力 -8 / P 费 -50 / P 费 -100（3 位数，F#43 的饮料事件）。
# 允许 3 位，否则「… -100」既剥不掉、选项行又被数字污染（digit 过滤直接丢弃该行）。
_EVENT_ROW_COST_RE = re.compile(r"\s*[-−一]\s*\d{1,3}\s*$")
_EVENT_ROW_LABEL_RE = re.compile(r"^[A-Za-z0-9]{1,3}\s+")
_FAST_STATIC_CACHE_WORDS = ("快进", "SKIP", "LOADING", "加载", "正在下载")

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
    if any(marker in value for marker in _DETAIL_CN_MARKERS):
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


# ---- 画面分类（培育结束后的结算/收尾，F#15） --------------------------------
def _screen_text(text: str | None) -> str:
    """OCR 文本归一化：全角转半角、压缩空白，避免关键词匹配被空格/全角拆开。"""
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"[\s\u3000]+", " ", value).strip()


def is_produce_page(text: str | None) -> bool:
    """培育页（定期公演 + 难度选择）的特征文本。

    注意：培育记录详情弹窗的标题里也有「定期公演」，所以它不能单独作为"真培育页"
    判据——调用方需要先用 :func:`is_record_screen` / :func:`is_settlement_screen`
    把这些收尾画面排除掉。
    """
    value = _screen_text(text)
    return "定期公演" in value or ("培育" in value and "研修" in value)


def is_record_screen(text: str | None) -> bool:
    """培育记录详情弹窗：顶部「培育记录」+ 编成支援卡/回忆 + 最终持有P道具。

    真机 ep-cplus13 的 step_055：这一屏标题含「定期公演『初』 Regular」，被当成培育页
    每步点难度按钮，画面不动，12 次后停机。

    2026-11-21 真机踩坑（ep-t1-c）：支援卡页点「自动」会弹「自动编成」确认框，文案是
    「将自动编成支援卡 / ※当前编成未保存 / 取消 / 确定」——含「编成支援卡」子串，
    被误判成记录页 → 每步点记录页底部的 X（(360,1197) 正好落在两个按钮之间）空转 12 次。
    这种「自动编成」确认框必须先排除。
    """
    value = _screen_text(text)
    if not value:
        return False
    if "培育记录" in value or "育成记录" in value:
        return True
    if "自动编成" in value or "当前编成未保存" in value:
        return False
    return "编成支援卡" in value or "最终持有P道具" in value


def is_memory_photo_screen(text: str | None) -> bool:
    """回忆照片选择页：「请选择要作为回忆的照片」+「保存到本地/保存到相册」。"""
    value = _screen_text(text)
    if not value:
        return False
    if "回忆的照片" in value or "作为回忆" in value or "回忆照片" in value:
        return True
    return "保存到相册" in value or "保存到本地" in value


def is_exam_rank_text(text: str | None) -> bool:
    """这段 OCR 文本是否是考试/试镜页顶部的排名条（``1st``/``2nd``…/``4th``）。

    F#17：考试页被当成课程，体力门/「剩下牌不值得」/同屏兜底轮番按 SKIP，白送回合
    （ep-sup1 期中 4th、228Pt，1st=597 直接不合格）。考试里 SKIP 没有任何收益，
    所以先用这条廉价判据识别考试，再把所有 SKIP 路径禁掉。
    """
    return _EXAM_RANK_RE.search(_screen_text(text)) is not None


def is_settlement_screen(text: str | None) -> bool:
    """培育结束后的结算/收尾画面（评价页 / 回忆照片选择 / 培育记录 / SNS 投稿）。

    「请选择」单独不能算（行动页也有「请选择行动」），必须带保存/投稿/结算语境；
    评价页则要求同时出现「评价/结算」和推进按钮（下一步/确定/完成/保存）。
    """
    value = _screen_text(text)
    if not value:
        return False
    if is_record_screen(value) or is_memory_photo_screen(value):
        return True
    if "SNS" in value.upper() and any(word in value for word in ("投稿", "保存", "分享", "确认")):
        return True
    if "结算" in value and any(word in value for word in ("保存", "下一步", "确定", "完成")):
        return True
    return "评价" in value and any(
        word in value for word in ("保存", "下一步", "确定", "完成", "SNS", "投稿")
    )


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
    last_stamina: int | None = None,
    default_cost: int = DEFAULT_HAND_COST,
    exam: bool = False,
) -> tuple[tuple[int, int], str] | None:
    """课程体力门：体力不足/读不到 → ``(SKIP 落点, 原因)``，必须结束本回合。

    真机事故（ep-cplus10）：体力 0 时 bot 进了课程，手牌最低 1 费一张牌都打不出，
    却在课程页每步空转 25 分钟。判定顺序固定为：

    1. 体力来源：``state.stamina`` → 调用方状态条 ``stamina`` → 上一帧 ``last_stamina``；
    2. **体力 0：无条件 SKIP**——不看手牌、不看费用读没读到（读不到也要结束回合）；
    3. 体力 > 0：最低手牌费用 > 体力 → SKIP；
    4. 三处都读不到体力：**不假设充足**。手牌费用也全读不到（或没有手牌）时 SKIP；
       只有所有手牌费用都明确为 0 才放行（0 费牌 0 体力也打得出）。

    ``state.cards`` 为空通常是 OCR 掉帧（详情浮层/转场）；此时体力也读不到就 SKIP
    是保守但安全的：白送一回合 < 空转到超时。

    ``exam=True``（考试/试镜）：**永远不 SKIP**。考试每回合都得打牌，SKIP 等于白送
    回合（F#17 真机期中 4th/228Pt 直接不合格）；打不出去交给换牌/关浮层处理。
    """
    if exam:
        return None
    current = state.stamina
    if current is None:
        current = stamina
    if current is None:
        current = last_stamina
    point = state.skip_point or LESSON_SKIP_POINT
    lowest = lowest_hand_cost(state.cards, default_cost=default_cost)
    if current is not None:
        current = max(int(current), 0)
        if current == 0:
            detail = "体力 0，一张牌都打不出，直接 SKIP"
            if lowest is not None:
                detail = f"体力 0 < 最低手牌费用 {lowest}，一张牌都打不出，直接 SKIP"
            return point, detail
    if current is None:
        if state.cards and all(card.cost == 0 for card in state.cards):
            return None
        return point, "体力读不到，不假设充足，直接 SKIP"
    if lowest is None:
        return None
    if current < lowest:
        return point, f"体力 {current} < 最低手牌费用 {lowest}，一张牌都打不出"
    return None


def lesson_turn_signature(state: LessonState) -> tuple:
    """课程「这一回合」的语义签名：一模一样的回合/分数/体力/手牌 = 画面没推进。

    不能用像素 digest：真机帧有角色呼吸、卡面闪光和视频噪点，实测 step_150~169
    逐帧全图/任一 ROI 的 hash 都不同，只有游戏状态（剩余回合/分数/体力/手牌）稳定。
    """
    return (
        state.turns_left,
        state.score,
        state.stamina,
        lesson_hand_signature(state),
    )


@dataclass
class SameScreenGuard:
    """同一屏连续无变化的兜底：5 步强制 SKIP，10 步判定卡死退出本局。

    与截图/点击解耦，真机与单测共用。``observe`` 每步喂一次**语义** digest
    （课程用 :func:`lesson_turn_signature`，不要用每帧都变的像素 hash）：

    - 第 ``force_skip_after`` 次（默认 5）返回 ``"force-skip"``：调用方无条件点 SKIP；
    - 第 ``exit_after`` 次（默认 10）返回 ``"stuck"``：调用方记 ``[stuck]`` 并退出本局；
    - 画面一旦变化（digest 不同）计数重置，返回 ``None``。
    """

    force_skip_after: int = 5
    exit_after: int = 10
    digest: tuple | None = None
    repeats: int = 0
    forced_skips: int = 0
    stuck_exits: int = 0

    def observe(self, digest: tuple) -> str | None:
        if digest == self.digest:
            self.repeats += 1
        else:
            self.digest = digest
            self.repeats = 1
        if self.repeats >= max(int(self.exit_after), 2):
            self.stuck_exits += 1
            return "stuck"
        if self.repeats == max(int(self.force_skip_after), 1):
            self.forced_skips += 1
            return "force-skip"
        return None

    def reset(self) -> None:
        self.digest = None
        self.repeats = 0


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


def _display_action(action: str) -> str:
    """日志里的行动名：用游戏术语（训练/上课）显示，内部 action id 保持兼容。

    - ``train-Vo``（点「Vo.训练」）→ ``class-Vo``：按 2026-11-16 统一后的
      代码名显示（``train`` 一律显示成 ``class``）；
    - ``lesson``（点「授课」）→ ``training``；
    - 其余 action（rest/outing/skip 等）原样返回。
    """
    if action.startswith("sim-train-"):
        return "sim-class-" + action[len("sim-train-"):]
    if action.startswith("train-"):
        return "class-" + action[len("train-"):]
    if action == "sim-lesson":
        return "sim-training"
    if action == "lesson":
        return "training"
    return action


@dataclass
class TickResult:
    screen: str
    action: str
    ok: bool = True
    detail: str = ""
    # C1 执行层可靠性：本次点击的落点 / 动作理由 / 下一帧预算（动作前登记，
    # 动作后由 TapGuard 互验）。旧调用方不传这三个字段时行为不变。
    point: tuple[int, int] | None = None
    reason: str = ""
    expect: TapExpectation | None = None

    def describe(self) -> str:
        text = f"[{self.screen}] {_display_action(self.action)}"
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
    # 体力门 SKIP 的「每回合只点一次」记忆：签名 = lesson_turn_signature(state)。
    last_skip_signature: tuple | None = field(default=None, init=False)
    skip_clicks: int = field(default=0, init=False)

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

    def skip_done(self, signature: tuple | None) -> bool:
        """这个回合签名（剩余回合/分数/体力/手牌）是不是已经点过 SKIP 了。

        体力 0 时每步都会命中体力门；画面没推进（SKIP 点击无效/还在确认框）时
        签名不变——此时不能再点，否则就是每 7 秒一次的连点。签名一变（回合推进）
        自动放行下一回合的 SKIP。
        """
        return signature is not None and signature == self.last_skip_signature

    def skip_sent(self, signature: tuple | None) -> None:
        """记下「本回合已点 SKIP」：清出牌状态，但保留签名记忆与累计次数。"""
        clicks = self.skip_clicks
        self.reset()
        self.last_skip_signature = signature
        self.skip_clicks = clicks + 1

    def observe(
        self, overlay_open: bool, *, progressed: bool = True, allow_skip: bool = True
    ) -> tuple[str, tuple[int, int] | None]:
        """``allow_skip=False``（考试/试镜）：同一坐标没推进也不 SKIP，改成换牌/关浮层。"""
        if self.pending_point is not None:
            if overlay_open:
                return ("confirm", self.pending_point)
            # 第一击已经直接生效（没有浮层）：不要再点第二下
            self._progress()
            return ("wait", None)

        if self.awaiting_confirm:
            # 确认后浮层还开着，或浮层关了但分数/手牌完全没变 = 同一坐标没推进
            if overlay_open or not progressed:
                failed = self._register_failure()
                if failed and allow_skip:
                    return ("skip", LESSON_SKIP_POINT)
                # 没有浮层就不用再点空白，直接换一张；浮层还在先关掉它
                return ("close", CARD_DETAIL_BLANK) if overlay_open else ("pick", None)
            # 确认生效：浮层已关、手牌/分数已变，等一帧让动画稳定后再选
            self._progress()
            return ("wait", None)

        if overlay_open:
            if self.stale_closes >= max(int(self.skip_after), 1):
                if allow_skip:
                    return ("skip", LESSON_SKIP_POINT)
                # 考试：不许 SKIP，重置关浮层计数并换一张牌（点另一张会替换浮层）
                self.stale_closes = 0
                return ("pick", None)
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
        self.last_skip_signature = None
        self.skip_clicks = 0

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
    # 连续「剧情快进」步数：日文剧情 OCR 只剩碎片时，按布局点选项气泡的兜底计数
    story_fast_streak: int = field(default=0, init=False)
    # 「定期公演」兜底分支的连续计数：结算/培育记录页也含「定期公演」，点难度按钮空转
    scenario_sig: str | None = field(default=None, init=False)
    scenario_streak: int = field(default=0, init=False)
    # 结算/收尾画面（回忆照片选择、培育记录、评价页）的连续计数，防止点不动空转
    settle_sig: str | None = field(default=None, init=False)
    settle_streak: int = field(default=0, init=False)
    # 降级阈值（真机 ep-cplus13：同一屏空点 12 次后停机，这里必须更早换策略/退出）
    scenario_record_close_after: int = 3  # 记录页特征文本：第 3 次先点底部 X
    scenario_degrade_after: int = 5  # 第 6 次起改点屏幕中央下方
    scenario_exit_after: int = 10  # 第 11 次起返回 stuck，退出本局（失败）
    settlement_degrade_after: int = 4  # 结算页同屏 4 次 → 点屏幕中央下方
    settlement_exit_after: int = 8  # 结算页同屏 8 次 → stuck 退出本局
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
    # 整屏 OCR 结果的语义缓存：只对"文字重复=状态重复"的静态屏启用
    # （加载/剧情/结算等待），避免像素 digest 被角色呼吸打穿。
    screen_cache: SemanticScreenCache | None = None
    _frame_lines: list[OcrLine] | None = field(default=None, init=False, repr=False)
    _frame_text: str = field(default="", init=False, repr=False)
    _frame_attrs: tuple[int, int, int] | None = field(default=None, init=False, repr=False)
    _attrs_image: object | None = field(default=None, init=False, repr=False)
    # C1：本次 decide() 调用内是否发生过点击 / 分支登记的下一帧预算。
    # last_point 跨调用保留（action-confirm 分支要用上一次的落点），不能重置。
    _tapped_this_call: bool = field(default=False, init=False, repr=False)
    _tap_expect: TapExpectation | None = field(default=None, init=False, repr=False)
    # C1：奖励选卡（卡位 → 领取）两段式 picker 的分级重试状态机
    reward_picker: PickerGuard = field(default_factory=PickerGuard, init=False)

    def __post_init__(self) -> None:
        if self.sleep is None:
            import time

            self.sleep = time.sleep
        if self.screen_cache is None:
            self.screen_cache = SemanticScreenCache()

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

    # ------------------------------------------------------------ 快速读屏
    def _probe_text(self, image, roi: tuple[int, int, int, int]) -> str:
        """固定小框单行识别；异常/读不到返回空串（快速路径据此决定是否退回整屏）。"""
        try:
            line = self.engine().line(image, roi, digits_only=False)
        except Exception:  # noqa: BLE001 - 探针失败就退回整屏 OCR
            return ""
        return line.text.strip() if line is not None and line.text else ""

    @staticmethod
    def _clean_event_row(text: str) -> str:
        """事件选项行：去掉 OCR 混进来的体力花费（``-8``）和卡面角标（``2A``）。"""
        value = unicodedata.normalize("NFKC", text or "").strip()
        value = _EVENT_ROW_COST_RE.sub("", value).strip()
        value = _EVENT_ROW_LABEL_RE.sub("", value).strip()
        value = value.strip(" ·・-—_|")
        if not 2 <= len(value) <= 20:
            return ""
        if any(ch.isdigit() for ch in value):
            return ""
        return value

    def _loading_probe(self, image) -> list[OcrLine] | None:
        text = self._probe_text(image, FAST_LOADING_BOX)
        english = self._probe_text(image, FAST_LOADING_EN_BOX)
        if "下载" in text or "加载" in text or "通信" in text:
            return [OcrLine("LOADING", 0.9, FAST_LOADING_BOX)]
        if "NOW" in english.upper() or "LOADING" in english.upper():
            return [OcrLine("LOADING", 0.9, FAST_LOADING_EN_BOX)]
        return None

    def _event_probe(self, image) -> tuple[list[OcrLine] | None, str]:
        """事件/剧情快速读：快进按钮 + 3 个选项行。返回 ``(lines, fast_text)``。

        只在"快进"出现在固定按钮框里才识别选项；选项行不足 2 条时返回
        ``(None, fast_text)``，交给调用方退回整屏 OCR——绝不直接点快进把
        需要选奖/选项的事件跳过去。
        """
        fast_text = self._probe_text(image, FAST_LOADING_EN_BOX)
        if "快进" not in fast_text:
            fast_text = self._probe_text(image, FAST_EVENT_FAST_BOX)
        if "快进" not in fast_text:
            return (None, fast_text)
        rows: list[OcrLine] = []
        for roi in FAST_EVENT_ROW_BOXES:
            text = self._clean_event_row(self._probe_text(image, roi))
            if text:
                rows.append(OcrLine(text, 0.9, roi))
        if len(rows) < 2:
            return (None, fast_text)
        return ([OcrLine("快进", 0.9, FAST_LOADING_EN_BOX), *rows], fast_text)

    def _action_probe(self, image) -> list[OcrLine] | None:
        """行动/训练/外出咨询页：固定小框拼出 decide 需要的行；读不全返回 None。

        页面识别（真机实测）：
        * 三颗属性圆读齐 → 是行动/训练/外出类页面（课程页没有这三个圆）；
        * 再读「请选择行动/授课/休息/外出/咨询/活动奖励/Vo·Da·Vi 训练」；
        * 至少命中一个可点行动才返回，否则返回 None 让调用方整屏 OCR。
        """
        report = self.read_attrs_debug(image)
        attrs = report["attrs"]
        if attrs is None:
            return None
        lines: list[OcrLine] = [
            OcrLine(f"{value}/1000", 0.9, roi)
            for value, roi in zip(attrs, ATTR_ROIS, strict=False)
        ]
        status = self._probe_text(image, FAST_STATUS_BOX)
        if status:
            lines.append(OcrLine(status, 0.9, FAST_STATUS_BOX))
        stamina = self._probe_text(image, FAST_STAMINA_BOX)
        if stamina:
            lines.append(OcrLine(stamina, 0.9, FAST_STAMINA_BOX))
        p_points = self._probe_text(image, FAST_P_BOX)
        if "P" in p_points.upper() or p_points.isdigit():
            lines.append(OcrLine(p_points, 0.9, FAST_P_BOX))
        action_title = self._probe_text(image, FAST_ACTION_TITLE_BOX)
        if "请选择行动" in action_title:
            lines.append(OcrLine("请选择行动", 0.9, FAST_ACTION_TITLE_BOX))

        recommend = self._probe_text(image, FAST_RECOMMEND_BOX)
        if "推荐" in recommend:
            lines.append(OcrLine(recommend, 0.9, FAST_RECOMMEND_BOX))
        controls: list[str] = []
        for roi in FAST_TRAIN_LABEL_BOXES:
            text = self._probe_text(image, roi)
            if text:
                lines.append(OcrLine(text, 0.9, roi))
                controls.append(text)
        for roi in (
            FAST_LESSON_BOX,
            FAST_REST_BOX,
            FAST_OUTING_BOX,
            FAST_CONSULT_BOX,
            FAST_ACTIVITY_BOX,
        ):
            text = self._probe_text(image, roi)
            if not text:
                continue
            if any(word in text for word in _FAST_ACTION_WORDS) or text in ("Vo", "Da", "Vi"):
                lines.append(OcrLine(text, 0.9, roi))
                controls.append(text)
        if not controls:
            return None
        # 体力低又没读到休息：可能休息按钮被动画遮住/位置漂了，必须回整屏确认，
        # 不能因为探针没看到就继续训练（真机体力门事故就是这么来的）。
        parsed_stamina = parse_stamina(stamina)
        if (
            parsed_stamina is not None
            and parsed_stamina < DEFAULT_REST_THRESHOLD
            and not any("休息" in text for text in controls)
        ):
            return None
        self._frame_attrs = attrs
        self._attrs_image = image
        return lines

    def _reward_probe(self, image) -> list[OcrLine] | None:
        """领奖页快速读：标题 + 推荐标签 + 领取。推荐标签读不到就退回整屏。"""
        title = self._probe_text(image, FAST_REWARD_TITLE_BOX)
        if "请选择要领取" not in title:
            return None
        claim = self._probe_text(image, FAST_REWARD_CLAIM_BOX)
        if "领取" not in claim:
            return None
        recommend = self._probe_text(image, FAST_REWARD_RECOMMEND_BOX)
        if "推荐" not in recommend:
            # 没读到推荐标签时，整屏 OCR 会按卡名/分档估值挑更强的卡；
            # 这里不能直接点第一张，正确性优先于速度。
            return None
        return [
            OcrLine(title, 0.9, FAST_REWARD_TITLE_BOX),
            OcrLine(recommend, 0.9, FAST_REWARD_RECOMMEND_BOX),
            OcrLine(claim, 0.9, FAST_REWARD_CLAIM_BOX),
        ]

    def read_fast(self, image) -> list[OcrLine]:
        """常用屏快速读屏：分区固定小框，能确定屏幕类型就不再整屏 OCR。

        判定顺序（真机实测布局）：
        1. 加载页：左下「正在下载数据」/右下「NOW LOADING...」；
        2. 事件/课程类型选择：右下「快进」+ 3 条选项行；
        3. 行动/训练/外出咨询页：三颗属性圆 + 授课/休息/训练/外出/咨询/活动奖励；
        4. 领奖页：标题「请选择要领取的技能卡。」+ 推荐 + 领取；
        5. 以上都不成立 → 整屏 OCR 兜底（结果/结算/对话等低频屏）。

        任何一条关键文字读不到都退回整屏 OCR；快速路径只减少 OCR 区域，
        不改变 ``decide`` 的输入语义（文本和可点框位置都保留）。
        """
        if image is None or getattr(image, "shape", None) is None:
            return self.read(image)
        self._frame_lines = None
        self._frame_text = ""
        self._frame_attrs = None
        self._attrs_image = None

        loading = self._loading_probe(image)
        if loading is not None:
            return self._remember_frame(loading)

        event_lines, fast_text = self._event_probe(image)
        if event_lines is not None:
            # 剧情选项气泡/底部对白：窄行 OCR 日文常被截断，补读中部+底部整条区域；
            # 事件屏同样多一次区域 OCR（~0.3s），由 decide 自己的分支区分。
            try:
                dialogue_lines = self.engine().read(image, FAST_DIALOGUE_AREA)
            except Exception:  # noqa: BLE001 - 区域 OCR 失败就退回原行为
                dialogue_lines = []
            if dialogue_lines:
                event_lines = [*event_lines, *dialogue_lines]
            return self._remember_frame(event_lines)

        status = self._probe_text(image, FAST_STATUS_BOX)
        if any(word in status for word in ("期中", "剩余回合", "授课", "请选择行动")):
            action_lines = self._action_probe(image)
            if action_lines is not None:
                return self._remember_frame(action_lines)

        reward_lines = self._reward_probe(image)
        if reward_lines is not None:
            return self._remember_frame(reward_lines)

        # 整屏兜底：加载/剧情这类"文字重复=状态重复"的屏按语义指纹缓存，
        # 下次同样的按钮/标题直接复用行列表，不再检测+识别。
        probe_key = " ".join(part for part in (status, fast_text) if part).strip()
        if probe_key and any(word in probe_key for word in _FAST_STATIC_CACHE_WORDS):
            cached = self.screen_cache.get(probe_key) if self.screen_cache is not None else None
            if cached is not None:
                return self._remember_frame(cached)
        lines = self.engine().read(image)
        return self._remember_frame(lines, cache_key=probe_key)

    def _remember_frame(
        self,
        lines: list[OcrLine],
        *,
        cache_key: str | None = None,
    ) -> list[OcrLine]:
        self._frame_lines = lines
        self._frame_text = self.text_of(lines)
        if (
            cache_key
            and self.screen_cache is not None
            and any(word in cache_key for word in _FAST_STATIC_CACHE_WORDS)
        ):
            self.screen_cache.put(cache_key, lines)
        return lines

    def read_attrs(
        self,
        image,
        *,
        allow_full: bool = False,
        text_hint: str | None = None,
    ) -> tuple[int, int, int] | None:
        """读行动页三颗属性圆的大数字 ``(Vo, Da, Vi)``；三个都读到才返回。

        先用三个固定小框走 :meth:`OcrEngine.line` 单行快路径（每个 ~30ms）。
        ``allow_full=False``（默认）时**绝不跑整图 OCR**：固定框偏了就读不到，
        交给调用方按未知处理。整图兜底只在 ``allow_full=True`` 且「请选择行动」
        廉价探针确认是行动页时才允许——整图 OCR 在真机要 5-15s，一步跑一次
        就能把整局拖慢一倍。

        ``text_hint``：调用方已经读到的屏幕文本。非行动页直接返回 None，
        连三个小框都不读；行动页/未知页才继续。
        """
        if text_hint is not None and not _might_show_attributes(text_hint):
            return None
        if self._attrs_image is image and self._frame_attrs is not None:
            return self._frame_attrs
        report = self.read_attrs_debug(image)
        if report["attrs"] is not None:
            return report["attrs"]
        if not allow_full:
            return None
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
        """读 data/knowledge/policy.json 的 produce 段；坏文件/缺文件回退默认值。

        轮行动参数新旧键都认（``training_every`` 优先于 ``lesson_every``，
        ``training_min_stamina`` 优先于 ``lesson_min_stamina`` 等）；返回的 dict
        同时保留旧键别名，旧脚本读 ``lesson_every`` 也能拿到新值。
        """
        cached = getattr(self, "_produce_cfg", None)
        if isinstance(cached, dict):
            return cached
        defaults = {
            "prefer_lesson": True,
            "rest_threshold": DEFAULT_REST_THRESHOLD,
            "lesson_threshold": DEFAULT_LESSON_THRESHOLD,
            "reward_pick": "best",
            "training_every": 1,
            "attr_choice": "weight",
            "min_stamina_for_class": 10,
            "outing_below": -1,
        }
        try:
            import json as _json
            from pathlib import Path as _Path

            from gkagent.sim.produce import PRODUCE_KEY_ALIASES, normalize_produce_params

            raw = _json.loads(_Path(r"D:\Games\gakumas-agent\data\knowledge\policy.json").read_text(encoding="utf-8"))
            section = raw.get("produce") or {}
            if isinstance(section, dict):
                # 保留 policy.json 里的所有键（之前只保留默认字典里的键，新参数被静默丢弃）；
                # 先只对 policy 内容做新旧键归一，避免默认新键覆盖文件里的旧键值。
                defaults.update(normalize_produce_params(section))
            for old_key, new_key in PRODUCE_KEY_ALIASES.items():
                if new_key in defaults and old_key not in defaults:
                    defaults[old_key] = defaults[new_key]
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

    @staticmethod
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
        self._tapped_this_call = True

    def _click(self, agent, point: tuple[int, int]) -> None:
        self._click_once(agent, point)
        self.sleep(0.9)

    def _click_line(self, agent, line: OcrLine) -> None:
        self._click(agent, self.center(line))

    @staticmethod
    def _bubble_fill_kind(image, line: OcrLine) -> str:
        """剧情选项气泡填充色分类（F#45，不依赖 OCR 语言）。

        在气泡行内横向取 5 个采样点、取最亮者（避开深色文字笔画）：
        - white：近纯白（min>=238 且色差<=10）——v3.6.1 选中后顶部的效果描述气泡；
        - gray：未选中选项（180<=min<=232 且色差<=16，实测 228/227/227；深色背景不算）；
        - vivid：鲜色选中项（min>=60 且色差>=30，橙 255/156/73、粉 230/60/130 等）；
        - other：背景/不确定。
        旧版（11-22）未选中选项也是白色，故 white alone 不构成剔除理由；
        选中态判定 = 存在 vivid 项（其余灰/白），点其右侧 >> 箭头确认（见 4.45 分支）。
        """
        if image is None:
            return "other"
        h, w = image.shape[:2]
        x0, _y0, bw, _bh = line.box
        _cx, cy = ProduceDriver.center(line)
        cy = max(0, min(h - 1, int(cy)))
        best = None
        for fx in (0.15, 0.3, 0.5, 0.7, 0.85):
            sx = max(0, min(w - 1, int(x0 + bw * fx)))
            px = image[cy, sx]
            # 生产截帧是 BGR（与 _checkbox_checked 同口径）
            b, g, r = int(px[0]), int(px[1]), int(px[2])
            if best is None or min(r, g, b) > min(best):
                best = (r, g, b)
        if best is None:
            return "other"
        r, g, b = best
        mn, mx = min(r, g, b), max(r, g, b)
        if mn >= 238 and mx - mn <= 10:
            return "white"
        if 180 <= mn <= 232 and mx - mn <= 16:
            return "gray"
        if mn >= 60 and mx - mn >= 30:
            return "vivid"
        return "other"

    # ------------------------------------------------- 结算/收尾画面（F#15）
    @staticmethod
    def _frame_signature(text: str) -> str:
        """同屏判定签名：数字全部归一化（P/体力/日期每帧都在变），取前 120 字。"""
        return re.sub(r"\d+", "#", text)[:120]

    def _settlement_action(self, agent, lines: list[OcrLine], text: str) -> TickResult | None:
        """培育结束后的结算/收尾画面 → 下一步动作；不是这类画面返回 ``None``。

        真机顺序：评价页 → 回忆照片选择（请选择要作为回忆的照片 / 保存到本地 /
        保存到相册）→ 培育记录详情（标题含「定期公演」，底部圆形 X）→ 主页。
        旧逻辑把「培育记录」当培育页每步点难度按钮（12 次停机），把照片页当未知弹窗
        点空白。这里给每类画面明确按钮，并带同屏降级：连续 4 次点不动改点屏幕中央，
        8 次仍不动就返回 ``stuck`` 退出本局，绝不空转到超时。
        """
        if not is_settlement_screen(text):
            self.settle_sig = None
            self.settle_streak = 0
            return None
        signature = self._frame_signature(text)
        if signature == self.settle_sig:
            self.settle_streak += 1
        else:
            self.settle_sig = signature
            self.settle_streak = 1
        streak = self.settle_streak
        if streak > self.settlement_exit_after:
            return TickResult(
                "stuck",
                "settlement-loop",
                ok=False,
                detail=f"结算页连续 {streak} 次点不动，退出本局",
            )
        if streak > self.settlement_degrade_after:
            self._click(agent, SETTLE_CENTER_TAP)
            return TickResult("settlement", "tap-center", detail=f"结算页同屏 {streak} 次")
        if is_record_screen(text):
            # 「培育记录」详情：底部圆形 X 关闭（OCR 读不出图标，只能固定坐标）
            close = self.find_button(lines, ("关闭",))
            if close is not None:
                self._click_line(agent, close)
            else:
                self._click(agent, PRODUCE_RECORD_CLOSE)
            return TickResult("record", "close")
        if is_memory_photo_screen(text):
            # 回忆照片选择：先选第一张（默认已带橙框），再点「保存到相册」。
            # 注意别点顶部提示条「将这张照片保存到相册」——那是说明文字，不是按钮。
            self._click(agent, MEMORY_FIRST_PHOTO)
            save = self.find_button(lines, ("保存到相册",)) or self.find_button(
                lines, ("保存到本地",)
            )
            if save is not None:
                self._click_line(agent, save)
            else:
                self._click(agent, MEMORY_SAVE_ALBUM)
            return TickResult("settlement", "save-memory")
        button = self.find_button(
            lines, ("保存到相册", "保存到本地", "下一步", "确定", "完成", "关闭")
        )
        if button is not None:
            self._click_line(agent, button)
            return TickResult("settlement", f"tap-{button.text}")
        self._click(agent, SETTLE_CENTER_TAP)
        return TickResult("settlement", "tap-center")

    @staticmethod
    def _looks_like_record_title(text: str) -> bool:
        """疑似培育记录/结算页的标题行（真培育页不会同时出现 Regular/日期/Pt 这些）。"""
        value = _screen_text(text)
        if "Regular" in value or "レギュラー" in value or "Pt" in value:
            return True
        return re.search(r"20\d\d[/年]", value) is not None

    def _scenario_step(self, agent, text: str) -> TickResult:
        """培育页点难度按钮；同一屏点不动就逐级降级，最后返回 ``stuck`` 退出本局。

        F#15 真机 ep-cplus13：结算后停在「培育记录」详情（标题含「定期公演」），这里
        每步点难度按钮但画面只在文本上微变，12 次后停机。三级降级：

        1. 同一屏前 5 次：点「レギュラー/Regular」（正常培育页一次就推进）；
        2. 第 6-10 次：改点屏幕中央下方 ``(360, 1000)``（可能是被遮挡/换页了）；
        3. 第 11 次起：返回 ``stuck``，主循环记 ``[stuck]`` 并退出本局（返回失败）。

        带记录页特征（Regular/日期/Pt）的同屏文本在第 3 次先点一次底部 X（真机
        培育记录弹窗布局），但不重置计数，仍然会走到第 11 次的 stuck 退出。
        """
        self.support_auto_done = False
        signature = self._frame_signature(text)
        if signature == self.scenario_sig:
            self.scenario_streak += 1
        else:
            self.scenario_sig = signature
            self.scenario_streak = 1
        streak = self.scenario_streak
        if streak > self.scenario_exit_after:
            return TickResult(
                "stuck",
                "scenario-loop",
                ok=False,
                detail=f"同一屏 scenario 连续 {streak} 次点不动（培育记录/结算页误判），退出本局",
            )
        if streak > self.scenario_degrade_after:
            self._click(agent, SETTLE_CENTER_TAP)
            return TickResult("scenario-fallback", "tap-center", detail=f"同屏 {streak} 次")
        if streak == self.scenario_record_close_after and self._looks_like_record_title(text):
            self._click(agent, PRODUCE_RECORD_CLOSE)
            return TickResult("record", "close-fallback")
        self._click(agent, REGULAR_DIFFICULTY)
        return TickResult("scenario", "regular")

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

    # ------------------------------------------------- 考试/试镜模式（F#17）
    def exam_mode(self, image=None, lines: list[OcrLine] | None = None) -> bool:
        """当前帧是不是考试/试镜页（顶部排名条 ``1st``..``6th``）。

        有截图时只读排名条那个小框（~30ms 单行快路径），读不到再退回整行文本判断；
        判据是廉价且唯一的：课程页/编成页都没有 ``1st/2nd/...``。
        """
        if image is not None and getattr(image, "shape", None) is not None:
            try:
                line = self.engine().line(image, EXAM_RANK_ROI, digits_only=False)
            except Exception:  # noqa: BLE001 - 探针失败就走文本兜底
                line = None
            if line is not None and is_exam_rank_text(line.text):
                return True
        return is_exam_rank_text(self.text_of(lines or []))

    # ------------------------------------------------- 跑局数据（run_record.py）
    def read_week(self, image, text: str | None = None) -> tuple[int | None, str | None]:
        """行动页读当前周：左上「期中截止 / 最终截止」+ 下一行「N周」。

        返回 ``(绝对周数, "mid"|"final")``；周数换算见
        :func:`gkagent.data.run_record.week_from_countdown`。读不到返回 ``None``，
        调用方按顺序推周数并把缺失记进周记录，不要拿 0 顶替。
        """
        if image is None or getattr(image, "shape", None) is None:
            return None, None
        label = self._probe_text(image, WEEK_LABEL_ROI)
        joined = f"{label} {text or ''}"
        if "最终截止" in joined or "最終" in joined:
            phase = "final"
        elif "期中截止" in joined or "期中" in joined:
            phase = "mid"
        else:
            phase = None
        try:
            line = self.engine().line(image, WEEK_NUM_ROI, digits_only=False)
        except Exception:  # noqa: BLE001 - 单行识别失败按读不到处理
            line = None
        number_text = (line.text or "") if line is not None else ""
        return week_from_countdown(number_text, phase), phase

    def read_exam_result(self, image) -> dict | None:
        """考试结算屏：整屏 OCR 一次，解析 1st..6th + ``Pt`` 行。

        返回 ``{"rank", "score", "others", "note"?}``（``others`` 从高到低，
        含自己）；只有认出分数行才返回。调用方应先用廉价文本判据
        （排名序数 + ``Pt``）确认是结算屏，避免每步跑整屏 OCR。
        """
        if image is None or getattr(image, "shape", None) is None:
            return None
        try:
            lines = self.engine().read(image)
        except Exception:  # noqa: BLE001 - OCR 失败就当没读到，不影响跑局
            return None
        return parse_exam_result(lines)

    def read_final_result(self, image) -> dict | None:
        """最终结算屏：固定小框读评价字母和评价点（真机 190647 = C+/5577）。

        只跑两个 ``engine.line``（各 ~30ms），不跑整屏 OCR：评价字母在中央
        大菱形里、评价点是下方 4-6 位大数字。两项都读不到返回 ``None``。
        """
        if image is None or getattr(image, "shape", None) is None:
            return None
        # 先用标题闸门确认是「最终培育评价」屏：收尾的「培育记录」页也有粉丝数等
        # 5 位数字，落在评价点框里会被误读成 eval_points。
        title = self._probe_text(image, FINAL_TITLE_ROI)
        if not (("最终" in title and "评价" in title) or "最終" in title):
            return None
        grade = None
        eval_points = None
        try:
            line = self.engine().line(image, FINAL_GRADE_ROI, digits_only=False)
            grade = parse_grade(line.text) if line is not None else None
        except Exception:  # noqa: BLE001 - 单行识别失败按读不到处理
            grade = None
        try:
            line = self.engine().line(image, FINAL_EVAL_ROI, digits_only=True)
            eval_points = parse_eval_points(line.text) if line is not None else None
        except Exception:  # noqa: BLE001 - 单行识别失败按读不到处理
            eval_points = None
        if grade is None and eval_points is None:
            return None
        return {"grade": grade, "eval_points": eval_points}

    # ------------------------------------------------------------------ 主入口
    def tick(self, agent) -> TickResult:
        image = agent.shot()
        return self.decide(agent, self.read(image), image)

    def decide(self, agent, lines: list[OcrLine], image=None) -> TickResult:
        # C1 动作前预算下一帧（hiro 原则 3）：先记下点击前的语义签名；
        # 分支可登记更具体的期望（弹窗消失/对话出现…），没登记的默认「画面应变化」。
        before = self._frame_signature(self.text_of(lines))
        self._tapped_this_call = False
        self._tap_expect = None
        try:
            tick = self._decide(agent, lines, image)
        except UserBusy:
            return TickResult("pause", "user-active", ok=True)
        if self._tapped_this_call and tick.screen not in ("pause", "loading", "blank", "stuck"):
            tick.point = tuple(self.last_point) if self.last_point is not None else None
            tick.expect = self._tap_expect or expect_change(before)
        return tick

    def _decide(self, agent, lines: list[OcrLine], image=None) -> TickResult:
        text = self.text_of(lines)
        sig0 = self._frame_signature(text)
        if "快进" not in text and "SKIP" not in text:
            self.story_fast_streak = 0

        # 0) 空白/纯色转场：等待，不当作「无可执行动作」
        if len(text.strip()) <= 3:
            self.sleep(0.8)
            return TickResult("blank", "wait")

        # 0.4) 网络/资产下载错误弹窗（真机 ep-t1-d：获取资产失败 E203 + 重试/返回标题）。
        # 必须排在 0.5 的 loading 之前：这屏文案含「通信」，旧顺序会判成 loading 空等。
        if (
            "通信错误" in text
            or "获取资产失败" in text
            or ("获取资产" in text and "失败" in text)
            or ("重试" in text and "返回标题" in text)
        ):
            retry = self.find_button(lines, ("重试",))
            if retry is not None:
                self._click_line(agent, retry)
            else:
                self._click(agent, NET_RETRY)
            self._tap_expect = expect_dialog_gone(("通信错误", "获取资产失败", "返回标题"), sig0)
            return TickResult("net-error", "retry", reason="通信错误弹窗，点「重试」恢复")

        # 0.5) 加载/转场：只等待，不当作「无可执行动作」
        upper = text.upper()
        if "LOADING" in upper or "加载" in text or "下载" in text or "通信" in text:
            return TickResult("loading", "wait")

        # 0.6) 考试/试镜失败后的「再挑战」确认（不一定带「取消」按钮，先于取消弹窗处理）
        if "再挑战" in text and ("不合格" in text or "剩余" in text):
            retry = self.find_button(lines, ("再挑战",))
            free_available = "免费剩余" in text and re.search(r"免费剩余\s*0", text) is None
            left_available = re.search(r"剩余\s*[1-9]\d*\s*次", text) is not None
            # 再挑战确认弹窗（点过「再挑战」后的第二段）：「消耗再挑战道具，重新挑战
            # 考试吗？」+ 取消/确定。这屏**没有**「再挑战」按钮，只有 确定/取消；
            # 旧逻辑找不到 retry 就落到 end-produce 点 (355,1148) 空点 10 次：
            # ep-sup1 step 179-188 就是这么停机的。点确定 = 消耗票据重打，正是我们要的。
            retry_confirm = self.find_button(lines, ("确定",))
            cancel_btn = self.find_button(lines, ("取消",))
            if retry_confirm is not None and cancel_btn is not None:
                self._click_line(agent, retry_confirm)
                self._tap_expect = expect_dialog_gone((CANCEL_WORD,), sig0)
                return TickResult(
                    "dialog", "retry-confirm", reason="再挑战第二段确认框，点「确定」消耗票据重打"
                )
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

        # 0.7) 结算/收尾画面（F#15）：培育结束后的评价页 / 回忆照片选择 / 培育记录详情。
        # 必须先于 #2 的「定期公演」分支——培育记录弹窗标题也含「定期公演」，旧顺序会在
        # 那里每步点难度按钮空转 12 次停机（真机 ep-cplus13 第 58 步）。
        settle = self._settlement_action(agent, lines, text)
        if settle is not None:
            return settle
        # scenario 兜底计数只在培育页上累计；一旦离开培育页（主页/课程/剧情）就清零，
        # 避免几天后莫名其妙退出。
        if not is_produce_page(text):
            self.scenario_sig = None
            self.scenario_streak = 0

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
                    self._tap_expect = expect_dialog_gone((CANCEL_WORD,), sig0)
                    return TickResult(
                        "dialog", "retry-confirm", reason="再挑战第二段确认框，点「确定」"
                    )
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
                self._tap_expect = expect_dialog_gone((CANCEL_WORD,), sig0)
                return TickResult(
                    "dialog",
                    "confirm",
                    detail=confirm.text,
                    reason=f"弹窗确认「{confirm.text}」",
                )

        # 1.5) 「回合结束」确认框（SKIP 后必出）：必须先于所有通用「确定」匹配。
        # 之前放在通用按钮匹配之后，问句「确定要结束回合吗？」里的「确定」会先被
        # find("确定") 命中，点到问句文字上 → SKIP 永远确认不了（ep-cplus11 卡了 13 步）。
        if "结束回合" in text and (
            "尚可使用技能卡" in text or "确定要结束回合" in text or "下次起不再显示" in text
        ):
            # 固定坐标点「是」：不再用 find_button(("是",)) 模糊匹配——
            # 整屏任何含「是」的文本（卡名/说明/问句）都会被误当成按钮，
            # 导致点空后确认框不消失、课程卡死在弹窗上（ep-exp4 step 85 复现）。
            self._click(agent, TURN_END_YES)
            self._tap_expect = expect_dialog_gone(("结束回合",), sig0)
            return TickResult(
                "dialog", "end-turn-yes", reason="SKIP 后「回合结束」确认框，点「是」"
            )

        # 1.75) 培育记录详情弹窗在 0.7) 的 _settlement_action 里统一处理（返回
        # TickResult("record", "close")），这里不再重复匹配。

        # 2) 培育页：定期公演 + 难度（带同屏降级：5 次改点中央，11 次 stuck 退出）
        if is_produce_page(text):
            return self._scenario_step(agent, text)

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

        # 4.46) 技能卡强化屏（F#46，v3.6.1 真机 ep-t31-b）：旧逻辑无此分支 → 落 story/tap
        # 点中央空转 100+ 步。交互链（实证）：①「未选择技能卡」+ 卡片网格 → 点网格第一张卡
        # 选中；② 选中后出现「强化确认」（只是预览）+ 底部大「强化」按钮变亮 → 点底部「强化」
        # 执行；③ 强化后弹「技能卡强化后详情」→「关闭」（分支 8 已处理）→ 卡牌展示对白
        # 「X已强化。」（story/tap 推进）。这里处理 ①②，③ 走既有分支。
        if "技能卡强化后详情" in text:
            line = self.find(lines, "关闭")
            self._click_line(agent, line) if line else self._click(agent, (360, 1160))
            return TickResult("enhance", "close-detail")
        if "强化确认" in text:
            self._click(agent, (360, 1160))  # 底部大「强化」按钮（执行，非预览）
            return TickResult("enhance", "go")
        if "未选择技能卡" in text and "强化" in text:
            self._click(agent, (140, 755))  # 卡片网格第一张（选中）
            return TickResult("enhance", "pick-card")

        # 4.45) 剧情「选项气泡」：快进/SKIP 仍在，屏幕中部有 2–3 行选项，且**底部有对白长句**
        # ——这是培育开场的剧情二选一（真机 ep-t3-1：飲み物を持ってきました / 慣れてきましたか?），
        # 不是外出事件（事件屏选项带 P/体力费用标签，且没有底部对白）。旧逻辑先点快进 →
        # 选项永远点不到，剧情原地循环 100+ 步。
        if "快进" in text or "SKIP" in text:
            # 底部对白框：真机 OCR 行 y 实测在 977/1019（不是 1010 以下），阈值取 950。
            bottom_dialogue = any(
                self.center(line)[1] >= 950
                and len(line.text.strip()) >= 8
                and any(mark in line.text for mark in ("。", "！", "？", "…"))
                for line in lines
            )
            cost_hint = any(
                _EVENT_ROW_COST_RE.search(line.text)
                for line in lines
                if 600 <= self.center(line)[1] <= 1150
            )
            choices = [
                line
                for line in lines
                if 650 <= self.center(line)[1] <= 1010
                and 4 <= len(line.text.strip()) <= 40
                and "快进" not in line.text
                and "SKIP" not in line.text
            ]
            if bottom_dialogue and not cost_hint and len(choices) >= 2:
                # v3.6.1 真机 ep-t31-a（F#45）：选中选项后顶部会多出一层**白色效果描述**
                # 气泡（如「选择并获得特定的P饮料」），它不是选项，点它画面不动 → 同屏 10 次停机。
                # 选项气泡填充为橙（选中，OCR 带 ">" 箭头）/灰蓝/白（旧版未选中）；描述气泡近纯白。
                # 规则：① 有 ">" 箭头的选项（已选中、可确认）优先点；② 否则顶部近纯白且下方有
                # 橙/深灰选项 → 剔除描述层；③ 其余点最上选项。按 h>=60 的气泡带行去重（同一气泡
                # 的整行框与内部文字行只算一个），避免点到描述层的内部文字行。
                bands = [c for c in choices if c.box[3] >= 60]
                pool = bands if len(bands) >= 2 else choices
                ordered = sorted(pool, key=lambda line: self.center(line)[1])
                target = ordered[0]
                confirm = False
                arrowed = [
                    c for c in ordered if c.text.rstrip().endswith(">") or ">>" in c.text
                ]
                if arrowed:
                    target = arrowed[0]
                    confirm = True
                elif image is not None and len(ordered) >= 2:
                    kinds = [self._bubble_fill_kind(image, c) for c in ordered]
                    vivid = [i for i, k in enumerate(kinds) if k == "vivid"]
                    if vivid:
                        # 鲜色（橙/粉）选中项 + 其余灰/白 → 选中态，点选中项箭头确认。
                        # 选中项箭头未必被 OCR 读出（F#46 授课/重点练习屏），靠填充色判定。
                        target = ordered[vivid[0]]
                        confirm = True
                    elif kinds[0] == "white" and any(
                        k in ("vivid", "gray") for k in kinds[1:]
                    ):
                        # 顶部白色效果描述层 + 下方选项 → 剔除描述层，点第一个选项确认。
                        target = ordered[1]
                        confirm = True
                if confirm:
                    # F#46 实证：>> 箭头在气泡右侧、与文字同高；点中心只是重选（原地循环）。
                    # 带框（h>=60）中心偏下，用气泡内文字行（h<60）的中心 y 对齐箭头高度。
                    x0, y0, bw, bh = target.box
                    inner = [
                        c for c in choices
                        if c.box[3] < 60 and y0 <= self.center(c)[1] <= y0 + bh
                    ]
                    cy = self.center(inner[0])[1] if inner else y0 + 25
                    self._click(agent, (min(665, x0 + bw - 35), cy))
                else:
                    self._click_line(agent, target)
                return TickResult("story", "choice")

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
        # 事件屏不一定能 OCR 到「快进」（按钮小/灰），「外出」标题 + 多个选项也视为事件屏；
        # 行动选择页同样有「外出」但有「请选择行动」，已被这个条件排除。
        # 2026-11-21 真机 ep-t1-g：外出/授课 二选一的行动页里没有「请选择行动」，
        # 只有描述框「根据选项会发生各种效果／主要为消耗P点数来回复体力」——
        # 这行 tooltip 被当成事件选项 → 每步点空，外出永远执行不了，10+ 周原地循环。
        # 2026-11-21 真机 ep-t1-h：事件屏的标题「外出」和「快进」OCR 都会漏读，
        # 只剩选项行 → 事件屏被当成 result-tap/gain（选项里的 P-100 命中飘字正则），
        # 点屏幕中央 10 步不动停机。所以标题读不到时，用选项行 + 负 P 费/对话标点兜底。
        action_page_hint = any(word in text for word in ("授课", "咨询", "训练", "休息"))
        p_cost = re.search(r"[-－−]\s*\d{2,3}", text) is not None
        dialogue = any(mark in text for mark in ("……", "…", "？", "?"))
        # 右侧「P -100 / P -50」费用标签（整行只有负数字）：选项文字读残/读空时靠它定位。
        cost_rows = [
            line
            for line in lines
            if re.fullmatch(r"\s*[-－−]\s*\d{2,3}\s*", (line.text or "").strip())
        ]
        event_choice = (
            "请选择行动" not in text
            and not action_page_hint
            and "根据选项会发生各种效果" not in text
            and ("快进" in text or "外出" in text or p_cost or dialogue)
        )
        # 上一帧已经点过选项 → 本帧是「确认选择」的第二次点击。
        # 注意：选中态那一帧的选项文字常被读成 1 个字（len 过滤后 option_rows=0），
        # 不能用 option_rows 判断，只看「还像事件选择屏」的弱特征（P 费/快进/外出/对话）。
        if self.event_pending_y is not None and event_choice:
            y = self.event_pending_y
            self.event_pending_y = None
            self._click(agent, (360, y))
            return TickResult(
                "event-choice", "confirm", reason="事件选项两段式第二击：确认选择"
            )
        # F#43（ep-t3-4）：日文饮料选择屏（ヨーグルトパフェ / つくねハンバーグ / ドリンクバー，
        # 右侧 P -100 / P -50）在选项文字完全读不到时（旧中文 OCR），option_rows=0 也会走到
        # 这里：只要还读得到 P 费标签，就用「最后一个费用标签 +138px」定位免费项，不再交给
        # 飘字分支点中央空转。
        if event_choice and (
            len(option_rows) >= 2 or (p_cost and (len(option_rows) >= 1 or cost_rows))
        ):
            if len(option_rows) >= 2:
                target = max(option_rows, key=lambda line: self.center(line)[1])
                y = self.center(target)[1]
                detail = ""
            else:
                # 选项按钮文字 OCR 只剩 1 个字（日文浅底按钮很容易读残）：
                # 用右侧「P -100 / P -50」费用标签定位，最后一个带费用标签的选项
                # 下方 ~138px 就是无费用的那个选项（默认高亮、通常是免费项）。
                if cost_rows:
                    y = self.center(max(cost_rows, key=lambda line: self.center(line)[1]))[1] + 138
                else:
                    y = 905
                detail = f"选项行 OCR 只有 {len(option_rows)} 条，用 P 费标签兜底"
            self.event_pending_y = y
            self._click(agent, (360, y))
            return TickResult("event-choice", "last-row", detail=detail)

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
            return TickResult(
                "action-confirm", "confirm", reason="行动已选中（预览屏），同坐标再点一次确认"
            )

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
        if ("条件成就" in text or "True End" in text) and "请选择要领取" not in text:
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
        # F#47：「P饮料详情」是带「关闭」的模态弹窗（点中央空白会 tap-lost），有「关闭」先点它。
        if (
            "P饮料" in text
            and ("获得" in text or "饮料" in text)
            and "领取" not in text
            and "快进" not in text
        ):
            close = self.find(lines, "关闭")
            if close is not None:
                self._click_line(agent, close)
                return TickResult("toast", "close-detail")
            # F#47：饮料「使用/丢弃」确认态底部是 取消/使用（无「关闭」）；点取消收起弹窗。
            cancel = self.find(lines, "取消")
            if cancel is not None:
                self._click_line(agent, cancel)
                return TickResult("toast", "cancel-drink")
            use = self.find(lines, "使用")
            if use is not None:
                self._click_line(agent, use)
                return TickResult("toast", "use-drink")
            self._click(agent, (360, 1000))
            return TickResult("toast", "advance")

        # 4.35) 活动奖励进度页（培育结束后出现）：底部是「下一步」，点空白会一直空转
        if ("活动Pt" in text or "活动奖励进度" in text) and "下一步" in text:
            nxt = self.find_button(lines, ("下一步",))
            self._click_line(agent, nxt) if nxt else self._click(agent, (360, 1135))
            return TickResult("reward-page", "next")

        # 4.38) 初模式「授课」答题屏（三个属性答案 + 審査基準 + 右下「快进」）
        # 旧逻辑：这批字里包含「快进」→ 命中 7) 剧情分支，每步点快进 → 弹「是否快进？」
        # → 确认后回到同一屏 → 无限循环（真机 ep-finish1 第 50-145 步烧了 95 步）。
        # 三个答案按属性排（Vo/Da/Vi），点一个就进结算；默认点第一行（实测最便宜，
        # 且评价公式三维等权，早买哪个都算分）。课程类型选择页（重点练习）另有分支。
        if (
            ("審査基準" in text or "审查基准" in text)
            and ("授课" in text or "授業" in text)
            and "重点练习" not in text
            # 答题屏背后是课程 HUD（審査基準/授课 一直可见），所以领奖/弹窗类界面
            # 也会命中；必须排除，否则把「请选择要领取的技能卡」也当成答题屏，
            # 每步点同一块空白（ep-finish2 第 4-13 步）。
            and "请选择要领取" not in text
            and "领取" not in text
            and "再抽选" not in text
        ):
            index = {"Vo": 0, "Da": 1, "Vi": 2}.get(self.lesson_attribute or "", 0)
            self._click(agent, CLASS_QUIZ_ROWS[index])
            return TickResult("class-quiz", f"choose-{self.lesson_attribute or 'Vo'}")

        # 4.4) 行动结算页（顶部「活动奖励/授课」标题、没有「请选择行动」按钮）：点一下继续
        # 注意：奖励领取弹窗顶部也有「活动奖励」，必须排除，否则会一直点空白
        if (
            ("活动奖励" in text or "授课" in text)
            and "请选择行动" not in text
            and "领取" not in text
            # 事件/课程类型选择页顶部也有「授课」标签，右下是「快进」：必须先走
            # 下面的选项行分支，不能在这里点屏幕中央把事件跳过去。
            and "快进" not in text
        ):
            self._click(agent, (360, 1000))
            return TickResult("result-tap", "settle")

        # 4.6) 领取奖励（技能卡或 P 饮料）：推荐卡优先，其次分档估值最强，再点「领取」
        # C1：两段式 picker（卡位 → 领取）分级重试——同一奖励屏没关掉时，
        # 只重试「领取」（重点已选中的卡可能取消选中）；重试用尽才重置重新选卡。
        # 选中态暂无可靠离线探针（未归档真机奖励选卡帧），按 selected=None 保守处理：
        # 第一次领取发出后即按「已选中」，阶段 E 真机验收时可补选中读回。
        if "请选择要领取" in text:
            picker = self.reward_picker
            if picker.active and picker.signature == sig0:
                verdict = picker.observe(selected=None, screen_gone=False)
                if verdict.outcome == "wait":
                    self.sleep(0.6)
                    return TickResult("card-reward", "wait", reason=verdict.reason)
                if verdict.outcome in ("retap-confirm", "tap-confirm") and verdict.point is not None:
                    self._click(agent, verdict.point)
                    picker.confirm_tapped()
                    self.sleep(0.9)
                    self._tap_expect = expect_change(sig0)
                    return TickResult("card-reward", "claim-retry", reason=verdict.reason)
                if verdict.outcome == "retap-slot" and verdict.point is not None:
                    self._click(agent, verdict.point)
                    picker.slot_tapped()
                    self.sleep(0.6)
                    if picker.confirm_point is not None:
                        self._click(agent, picker.confirm_point)
                        picker.confirm_tapped()
                    self.sleep(0.9)
                    self._tap_expect = expect_change(sig0)
                    return TickResult("card-reward", "pick-retry", reason=verdict.reason)
                # failed：重试预算用尽 → 重置后重新走完整选卡+领取（既有同屏兜底仍封顶）
                picker.reset()
            best = self._best_reward_card(lines, image)
            if best is not None:
                slot = best
            else:
                recommend = self.find(lines, "推荐")
                if recommend is not None:
                    cx, cy = self.center(recommend)
                    # 「推荐」标签在卡牌下缘，点它选不中卡；向上 60px 点到卡身
                    slot = (cx, max(60, cy - 60))
                else:
                    # 三选一的第一张：点**卡面美术中心**。真机 ep-t1-f 用 (240,960)
                    # （卡框下缘/费用徽章附近）时点不中，领取按钮一直是灰的 → 10 步死循环；
                    # 实测 (230,918)（卡面中心）一点就选中、领取点亮。
                    slot = (230, 918)
            # 选卡后「领取」按钮要等一小段才点亮，直接连点会点空 → 反复重进本分支
            claim = self.find(lines, "领取")
            claim_pt = self.center(claim) if claim else (360, 1095)
            picker.start(slot, claim_pt, signature=sig0)
            self._click(agent, slot)
            picker.slot_tapped()
            self.sleep(0.6)
            self._click(agent, claim_pt)
            picker.confirm_tapped()
            self.sleep(0.5)
            # 点一次没关掉就再点一次（按钮点亮动画的兜底），仍关不掉交给 picker 重试
            self._click(agent, claim_pt)
            self.sleep(0.9)
            self._tap_expect = expect_change(sig0)
            return TickResult(
                "card-reward", "pick+claim", reason="奖励选卡+领取（两段式：卡位→领取）"
            )
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

        # 4.5) 课程结算飘字（Da.上升了58!）或奖励弹字（P+45）：点屏幕中央继续；
        # 连续 3 次还在 = 这是静态结果页（飘字只是页面标题，点中央推不动），
        # 改找「下一步/继续/完成/领取/关闭」按钮；找不到才继续点中央（F#43）。
        if any(word in text for word in ("上升了", "提升了", "下降了", "获得了")) or _GAIN_RE.search(text):
            self.gain_waits += 1
            if self.gain_waits >= 3:
                nxt = self.find_button(
                    lines,
                    ("下一步", "继续", "确定", "完成", "关闭", "领取", "了解"),
                )
                if nxt is not None:
                    self.gain_waits = 0
                    self._click_line(agent, nxt)
                    return TickResult("result-tap", "next")
                # 静态页但还没有可点的按钮：保持计数（每帧都重找按钮），继续点中央推进。
                self._click(agent, (360, 1000))
                return TickResult("result-tap", "next")
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
            # 真机 ep-t3-3：育成开场剧情是日文「快进 + 二选项气泡」，而 OCR 字典是中文，
            # 选项/对白只剩碎片（'物持' / '？' / '、。'），按文本判断选不出来。
            # 兜底：连续多次都只能点快进 → 按布局点最上面的**选项气泡**
            #（中部 700–1010、宽 200–700 的白色气泡框）。
            self.story_fast_streak += 1
            if self.story_fast_streak >= 5:
                bubbles = [
                    line
                    for line in lines
                    if 700 <= self.center(line)[1] <= 1010
                    and 200 <= line.box[2] <= 700
                    and line.box[3] <= 90
                    and "快进" not in line.text
                ]
                if len(bubbles) >= 2:
                    self.story_fast_streak = 0
                    target = min(bubbles, key=lambda line: self.center(line)[1])
                    self._click_line(agent, target)
                    return TickResult("story", "choice-by-layout")
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
