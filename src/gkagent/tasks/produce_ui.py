"""OCR 驱动的培育 UI 导航（中文本地化界面）。

定位：模板/OCR 只回答「这一屏是什么」，本模块回答「这一步点哪里」。
每调用一次 ``tick``/``decide`` 只做一个动作，外部循环重复调用，便于逐步截图复盘。

坐标系：720x1280（游戏渲染分辨率），固定落点均为真机实测的按钮中心。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

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
LESSON_WORDS = ("剩余回合数", "CLEAR截止")
_GAIN_RE = re.compile(r"[+\-]\s*\d+")


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

    def __post_init__(self) -> None:
        if self.sleep is None:
            import time

            self.sleep = time.sleep

    # ------------------------------------------------------------------ 工具
    def engine(self) -> OcrEngine:
        if self.ocr is None:
            self.ocr = OcrEngine()
        return self.ocr

    def read(self, image) -> list[OcrLine]:
        return self.engine().read(image)

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
        return self.decide(agent, self.read(image))

    def decide(self, agent, lines: list[OcrLine]) -> TickResult:
        try:
            return self._decide(agent, lines)
        except UserBusy:
            return TickResult("pause", "user-active", ok=True)

    def _decide(self, agent, lines: list[OcrLine]) -> TickResult:
        text = self.text_of(lines)

        # 0) 空白/纯色转场：等待，不当作「无可执行动作」
        if len(text.strip()) <= 3:
            self.sleep(0.8)
            return TickResult("blank", "wait")

        # 0.5) 加载/转场：只等待，不当作「无可执行动作」
        upper = text.upper()
        if "LOADING" in upper or "加载" in text or "下载" in text or "通信" in text:
            return TickResult("loading", "wait")

        # 1) 弹窗：取消 + 确定/完成/下一步
        if CANCEL_WORD in text:
            if "不播放语音" in text:
                line = self.find(lines, "不播放语音")
                self._click(agent, self.center(line) if line else VOICE_OFF)
                confirm = self.find(lines, "确定")
                if confirm is not None:
                    self._click_once(agent, self.center(confirm))
                    self.sleep(0.9)
                return TickResult("dialog", "voice-off")
            if "再挑战" in text:
                cancel = self.find(lines, "取消")
                self._click_line(agent, cancel) if cancel else self._click(agent, (175, 1163))
                return TickResult("dialog", "cancel-retry")
            confirm = self.find(lines, "下一步", "确定", "完成")
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

        # 4.5) 课程结算飘字（Da.上升了58!）或奖励弹字（P+45）：点屏幕中央继续
        if any(word in text for word in ("上升了", "提升了", "下降了", "获得了")):
            self._click(agent, (360, 1000))
            return TickResult("result-tap", "tap")
        if _GAIN_RE.search(text):
            self._click(agent, (360, 1000))
            return TickResult("result-tap", "gain")

        # 4.4) 行动结算页（顶部「活动奖励/授课」标题、没有「请选择行动」按钮）：点一下继续
        if ("活动奖励" in text or "授课" in text) and "请选择行动" not in text:
            self._click(agent, (360, 1000))
            return TickResult("result-tap", "settle")

        # 4.6) 领取奖励（技能卡或 P 饮料）：先选一张，再点「领取」
        if "请选择要领取" in text:
            recommend = self.find(lines, "推荐")
            if recommend is not None:
                self._click(agent, self.center(recommend))
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

        # 5) 培养主界面：选择行动（三个训练按钮同时出现才算训练）
        if "请选择行动" in text or all(word in text for word in ("Vo.训练", "Da.训练", "Vi.训练")):
            if "授课" in text:
                self._click(agent, LESSON_ACTION)
                return TickResult("action", "lesson")
            point, label = self.choose_training(text)
            self._click(agent, point)
            return TickResult("action", f"train-{label}")

        # 6) 已选中行动，点同一点确认（训练预览「能力值上升」/ 授课预览「根据选项」）
        if "能力值上升" in text or "根据选项" in text or "SELECT" in text:
            point = self.last_point or TRAIN_DA
            self._click(agent, point)
            return TickResult("action-confirm", "confirm")

        # 7) 剧情快进/跳过
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
        for word in ("下一步", "继续", "完成", "获取", "领取", "确定", "关闭"):
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
        if len(text.strip()) > 10 and any(mark in text for mark in ("。", "！", "？", "…")):
            self._click(agent, (360, 1000))
            return TickResult("story", "tap")

        return TickResult("unknown", "no-op", ok=False, detail=text[:60])

    # ------------------------------------------------------------------ 策略
    def choose_training(self, text: str) -> tuple[tuple[int, int], str]:
        """优先跟随游戏推荐气泡，其次默认 Da（新号 Da 最低）。"""
        for word, point, label in (
            ("歌唱", TRAIN_VO, "Vo"),
            ("舞蹈", TRAIN_DA, "Da"),
            ("视觉", TRAIN_VI, "Vi"),
        ):
            if f"推荐{word}" in text:
                return point, label
        return TRAIN_DA, "Da"
