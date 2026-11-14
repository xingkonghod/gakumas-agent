"""界面导航：用 OCR 文本 + 已知入口坐标，在游戏里走位和恢复。

这是「一套逻辑」里的导航层：所有任务都通过 Navigator 到目标界面，
不再每个功能自己点固定坐标。
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from gkagent.agent import Agent
from gkagent.vision.ocr import OcrEngine, OcrLine


class Navigator:
    IDOL_TAB = (198, 1158)
    HOME_TAB = (95, 1188)
    HOME_ICON = (95, 1188)
    SUPPORT_ENTRY = "支援卡"
    # OCR 会把「培养P偶像」拆成「培养」+「P偶像」两行，必须分开匹配
    IDOL_ENTRIES = ("培养", "P偶像")
    SUPPORT_SCREEN_MARKERS = ("查看详情", "支援卡加成", "支援卡变换")
    IDOL_SCREEN_MARKERS = ("特训", "才能开花")

    def __init__(self, agent: Agent, ocr: OcrEngine | None = None, settle: float = 1.2) -> None:
        self.agent = agent
        self.ocr = ocr or OcrEngine()
        self.settle = settle

    def lines(self, image=None) -> list[OcrLine]:
        return self.ocr.read(image if image is not None else self.agent.shot())

    def find_text(self, needle: str, image=None) -> OcrLine | None:
        for line in self.lines(image):
            if needle in line.text:
                return line
        return None

    def click_text(self, needle: str, image=None, verify: str | None = None) -> bool:
        line = self.find_text(needle, image)
        if line is None:
            return False
        if verify is not None:
            return self.click_verified(line, verify_text=verify)
        x, y, w, h = line.box
        self.agent.device.click(x + w // 2, y + h // 2)
        time.sleep(self.settle)
        return True

    def click_exact(self, word: str, image=None) -> bool:
        """只点文本完全相等的行（避免「特训」点到「特训阶段」这种标签）。"""
        for line in self.lines(image):
            if line.text.strip() != word:
                continue
            x, y, w, h = line.box
            self.agent.device.click(x + w // 2, y + h // 2)
            time.sleep(self.settle)
            return True
        return False

    def click_verified(
        self,
        line: OcrLine,
        verify_text: str | None = None,
        retries: int = 3,
        threshold: float = 2.0,
    ) -> bool:
        """点击后校验：目标文字出现或画面变化，否则偏移重点。"""
        before = self.agent.shot()
        x, y, w, h = line.box
        cx, cy = x + w // 2, y + h // 2
        offsets = ((0, 0), (0, -10), (0, 10), (-10, 0), (10, 0))
        for dx, dy in offsets[: max(1, retries)]:
            self.agent.device.click(cx + dx, cy + dy)
            time.sleep(0.7)
            after = self.agent.shot()
            if verify_text and self.find_text(verify_text, after) is not None:
                return True
            changed = float(np.mean(cv2.absdiff(before, after)))
            if verify_text is None and changed > threshold:
                return True
            before = after
        return False

    def home(self) -> bool:
        return self.agent.ensure_home()

    def ensure_home(self, attempts: int = 3) -> bool:
        """用底栏房子图标回主页（详情页的底栏和主页不同，模板常对不上）。

        已经在培育/课程/考试里的话不要回主页，否则会把进行中的一局打断。
        """
        for _ in range(attempts):
            text = " ".join(line.text for line in self.lines())
            if any(
                word in text
                for word in (
                    "剩余回合数",
                    "CLEAR截止",
                    "PERFECT截止",
                    "审查基准",
                    "选择偶像",
                    "选择支援卡",
                    "选择回忆",
                    "培育信息",
                    "编成详情",
                    "定期公演",
                    "培育开始",
                    "SKIP",
                )
            ):
                return True
            if "主页" in text and any(word in text for word in ("扭蛋", "商店", "プロデュース", "礼物")):
                return True
            self.agent.device.click(*self.HOME_ICON)
            time.sleep(1.2)
        text = " ".join(line.text for line in self.lines())
        return "主页" in text

    def idol_menu(self, attempts: int = 2) -> bool:
        for _ in range(attempts):
            # 只认偶像菜单里的独立「支援卡」按钮；主页横幅「去升级2张支援卡…」会误命中
            if self._exact("支援卡") is not None or any(
                self._exact(entry) is not None for entry in self.IDOL_ENTRIES
            ):
                return True
            self.agent.device.click(*self.IDOL_TAB)
            time.sleep(1.6)
        return self._exact("支援卡") is not None

    def _exact(self, word: str):
        for line in self.lines():
            if line.text.strip() == word:
                return line
        return None

    def support_screen(self, attempts: int = 2) -> bool:
        for _ in range(attempts):
            if not self.idol_menu():
                continue
            entry = self._exact("支援卡")
            if entry is None:
                continue
            x, y, w, h = entry.box
            self.agent.device.click(x + w // 2, y + h // 2)
            time.sleep(1.8)
            if any(self.find_text(marker) for marker in self.SUPPORT_SCREEN_MARKERS):
                return True
        return False

    def idol_screen(self, attempts: int = 2) -> bool:
        for _ in range(attempts):
            if (
                self.idol_menu()
                and self._click_idol_entry()
                and any(self.find_text(marker) for marker in self.IDOL_SCREEN_MARKERS)
            ):
                return True
        return False

    def _click_idol_entry(self) -> bool:
        for entry in self.IDOL_ENTRIES:
            line = self.find_text(entry)
            if line is None:
                continue
            x, y, w, h = line.box
            self.agent.device.click(x + w // 2, y + h // 2)
            time.sleep(self.settle)
            return True
        return False
