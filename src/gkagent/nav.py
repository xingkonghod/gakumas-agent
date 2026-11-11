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
    IDOL_TAB = (220, 1160)
    HOME_TAB = (95, 1200)
    SUPPORT_ENTRY = "支援卡"
    IDOL_ENTRY = "培养P偶像"

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

    def idol_menu(self, attempts: int = 2) -> bool:
        for _ in range(attempts):
            if self.find_text(self.IDOL_ENTRY) or self.find_text(self.SUPPORT_ENTRY):
                return True
            self.agent.device.click(*self.IDOL_TAB)
            time.sleep(self.settle)
        return self.find_text(self.IDOL_ENTRY) is not None

    def support_screen(self, attempts: int = 2) -> bool:
        for _ in range(attempts):
            if (
                self.idol_menu()
                and self.click_text(self.SUPPORT_ENTRY)
                and (self.find_text("强化") or self.find_text("特训") or self.find_text("等级"))
            ):
                return True
        return False

    def idol_screen(self, attempts: int = 2) -> bool:
        for _ in range(attempts):
            if (
                self.idol_menu()
                and self.click_text(self.IDOL_ENTRY)
                and (self.find_text("特训") or self.find_text("才能开花"))
            ):
                return True
        return False
