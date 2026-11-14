"""OCR 驱动的培育 UI 导航（中文本地化界面）。

定位：模板/OCR 只回答「这一屏是什么」，本模块回答「这一步点哪里」。
每调用一次 ``tick``/``decide`` 只做一个动作，外部循环重复调用，便于逐步截图复盘。

坐标系：720x1280（游戏渲染分辨率），固定落点均为真机实测的按钮中心。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import numpy as np

from gkagent.vision.ocr import OcrEngine, OcrLine

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


def parse_stamina(text: str) -> int | None:
    """从左上角状态条读体力（如 31/35）；属性 /1000 不算。"""
    for match in _STAMINA_RE.finditer(text):
        current, maximum = int(match.group(1)), int(match.group(2))
        if maximum <= 60 and current <= maximum:
            return current
    return None


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

    def _click(self, agent, point: tuple[int, int]) -> None:
        self._click_once(agent, point)
        self.sleep(0.9)

    def _click_line(self, agent, line: OcrLine) -> None:
        self._click(agent, self.center(line))

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
            if retry is not None and (free_available or left_available):
                self._click_line(agent, retry)
                return TickResult("dialog", "retry")
            end = self.find_button(lines, ("结束培育",))
            self._click_line(agent, end) if end else self._click(agent, (185, 1144))
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
                retry = self.find_button(lines, ("再挑战",))
                free_available = "免费剩余" in text and re.search(r"免费剩余\s*0", text) is None
                left_available = re.search(r"剩余\s*[1-9]\d*\s*次", text) is not None
                if retry is not None and (free_available or left_available) and self.retry_count < 2:
                    self.retry_count += 1
                    self._click_line(agent, retry)
                    return TickResult("dialog", "retry")
                end = self.find_button(lines, ("结束培育",))
                self._click_line(agent, end) if end else self._click(agent, (185, 1144))
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
                # 「获得的饮料」段勾选是灰的（不可选）；按勾选框列扫描出行位置，
                # 只补勾「手持的饮料」下面未勾选的行（行位置和文字行 y 有 20-50px 偏差，不能直接用文字行）
                hand_header = self.find(lines, "手持的饮料")
                header_y = hand_header.box[1] if hand_header is not None else 400
                for top, bottom in self._checkbox_bands(image):
                    center = (top + bottom) // 2
                    if center < header_y + 20 or center > 1100:
                        continue
                    if not self._checkbox_checked(image, center):
                        self._click(agent, (632, center))
                        return TickResult("drink-keep", "check-row")
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
        # 体力不够就别硬练：优先休息（当前帧没读到体力就用上一帧的）
        effective_stamina = stamina if stamina is not None else self.stamina_hint
        if "休息" in text and effective_stamina is not None and effective_stamina < 15:
            rest = self.find(lines, "休息")
            self._click_line(agent, rest) if rest else self._click(agent, (640, 860))
            return TickResult("action", "rest")
        if "外出" in text and "咨询" in text:
            self._click(agent, (450, 1027))
            return TickResult("action", "consult")
        if "外出" in text and "授课" in text:
            # 外出（耗 P 回体力）+ 授课 的二选一：选外出回体力
            self._click(agent, (268, 1010))
            return TickResult("action", "go-out")
        if (
            "请选择行动" in text
            or (training_hits >= 2 and "训练" in text)
            or ("授课" in text and "活动奖励" in text)
        ):
            if "授课" in text and training_hits == 0:
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

        # 4.4) 行动结算页（顶部「活动奖励/授课」标题、没有「请选择行动」按钮）：点一下继续
        # 注意：奖励领取弹窗顶部也有「活动奖励」，必须排除，否则会一直点空白
        if (
            ("活动奖励" in text or "授课" in text)
            and "请选择行动" not in text
            and "领取" not in text
        ):
            self._click(agent, (360, 1000))
            return TickResult("result-tap", "settle")

        # 4.6) 领取奖励（技能卡或 P 饮料）：先选一张，再点「领取」
        if "请选择要领取" in text:
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
        if "领取" in text:
            claim = self.find(lines, "领取")
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
        if any(word in text for word in ("上升了", "提升了", "下降了", "获得了")):
            self._click(agent, (360, 1000))
            return TickResult("result-tap", "tap")
        if _GAIN_RE.search(text):
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
    def choose_training(self, text: str, lines: list[OcrLine] | None = None) -> tuple[tuple[int, int], str]:
        """优先跟随游戏「推荐」气泡：气泡带属性词就用词，只有「推荐」二字就用气泡所在列。"""
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
