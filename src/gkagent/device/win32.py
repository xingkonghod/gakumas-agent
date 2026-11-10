"""Win32 设备：截屏 + 点击。

底层复用 MaaFramework 的 Win32Controller。
点击默认用 Seize（DPI 感知的全局输入），并在点击前隐藏 DMM Play Assist，
否则真实鼠标会被 player-assist 覆盖层吃掉。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np

USER32 = ctypes.WinDLL("user32", use_last_error=True)


class Win32Device:
    def __init__(
        self,
        hwnd: int,
        maa_home: str | os.PathLike[str] = r"D:\Games\MaaGakumasu",
        screencap: str = "FramePool",
        input_method: str = "Seize",
    ) -> None:
        self.hwnd = int(hwnd)
        self.maa_home = Path(maa_home)
        self.screencap = screencap
        self.input_method = input_method
        self._ctrl = None
        self._overlay: int | None = None

    def connect(self) -> Win32Device:
        os.chdir(self.maa_home)
        site = self.maa_home / "python" / "Lib" / "site-packages"
        if site.exists() and str(site) not in sys.path:
            sys.path.insert(0, str(site))

        from maa.controller import Win32Controller
        from maa.define import MaaWin32InputMethodEnum as InputMethod
        from maa.define import MaaWin32ScreencapMethodEnum as ScreencapMethod

        self._overlay = find_window("player-assist")
        cap = getattr(ScreencapMethod, self.screencap)
        inp = getattr(InputMethod, self.input_method)
        self._ctrl = Win32Controller(self.hwnd, cap, inp, inp)
        self._ctrl.post_connection().wait()
        return self

    @property
    def controller(self):
        if self._ctrl is None:
            raise RuntimeError("device not connected; call connect() first")
        return self._ctrl

    def _prepare_input(self) -> None:
        if self._overlay:
            USER32.ShowWindow(self._overlay, 0)  # SW_HIDE
            time.sleep(0.12)
        USER32.ShowWindow(self.hwnd, 9)
        USER32.SetForegroundWindow(self.hwnd)
        time.sleep(0.12)

    def capture(self) -> np.ndarray:
        return self.controller.post_screencap().wait().get()

    def click(self, x: int, y: int, delay: float = 0.3) -> None:
        self._prepare_input()
        self.controller.post_click(int(x), int(y)).wait()
        if delay:
            time.sleep(delay)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._prepare_input()
        self.controller.post_swipe(int(x1), int(y1), int(x2), int(y2), int(duration_ms)).wait()

    def key(self, keycode: int) -> None:
        self.controller.post_click_key(int(keycode)).wait()


def find_window(title: str) -> int | None:
    """按标题精确查找可见窗口。"""
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []

    def _cb(hwnd, _lparam):
        length = USER32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            USER32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value == title and USER32.IsWindowVisible(hwnd):
                found.append(int(hwnd))
                return False
        return True

    USER32.EnumWindows(proc_type(_cb), 0)
    return found[0] if found else None


def find_game_hwnd(title_substr: str = "gakumas", class_name: str = "UnityWndClass") -> int | None:
    """按窗口类/标题查找游戏窗口。"""
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []

    def _cb(hwnd, _lparam):
        length = USER32.GetWindowTextLengthW(hwnd)
        title = ""
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            USER32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
        cbuf = ctypes.create_unicode_buffer(256)
        USER32.GetClassNameW(hwnd, cbuf, 256)
        cls = cbuf.value
        if class_name == cls or title_substr.lower() in title.lower():
            found.append(int(hwnd))
        return True

    USER32.EnumWindows(proc_type(_cb), 0)
    return found[0] if found else None
