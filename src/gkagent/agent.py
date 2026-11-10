"""Agent：把设备、模板、任务串起来。"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from gkagent.device.win32 import Win32Device
from gkagent.vision.matcher import Match, TemplateMatcher


class Agent:
    def __init__(self, device: Win32Device, matcher: TemplateMatcher) -> None:
        self.device = device
        self.matcher = matcher

    def shot(self) -> np.ndarray:
        return self.device.capture()

    def find(self, name: str, image: np.ndarray | None = None, **kwargs) -> Match | None:
        img = self.shot() if image is None else image
        return self.matcher.find(name, img, **kwargs)

    def click(self, match: Match) -> None:
        self.device.click(*match.center)

    def ensure_home(self, attempts: int = 4) -> bool:
        """确保在主页：先认 home.png，找不到就点底部主页 tab。"""
        for _ in range(attempts):
            img = self.shot()
            if self.matcher.find("home", img, threshold=0.85) is not None:
                return True
            tab = self.matcher.find("home_tab", img, threshold=0.9)
            if tab is None:
                return False
            self.device.click(*tab.center)
            time.sleep(1.2)
        return False

    def close_popup(self, image: np.ndarray | None = None) -> bool:
        img = self.shot() if image is None else image
        for name in ("close", "decide"):
            m = self.matcher.find(name, img, threshold=0.85)
            if m is not None:
                self.device.click(*m.center)
                time.sleep(0.8)
                return True
        return False

    def claim_activity_fee(self) -> bool:
        if not self.ensure_home():
            return False
        img = self.shot()
        fee = self.matcher.find("activity_fee", img, threshold=0.85)
        if fee is None:
            return False
        self.device.click(*fee.center)
        time.sleep(1.5)
        return self.close_popup()

    def add_work(self) -> bool:
        """占位：后续按工作流程补。"""
        return False


def build_agent(templates_dir: str | Path = "templates", hwnd: int | None = None) -> Agent:
    from gkagent.device.win32 import find_game_hwnd

    handle = hwnd or find_game_hwnd()
    if not handle:
        raise RuntimeError("game window not found; pass --hwnd or start the game")
    device = Win32Device(handle).connect()
    matcher = TemplateMatcher(templates_dir)
    return Agent(device, matcher)
