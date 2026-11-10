"""Win32 设备：截屏 + 点击。

底层复用 MaaFramework 的 Win32Controller（FramePool 截图、SendMessageWithCursorPos 点击），
因为它已经解决了 Unity 游戏截屏和点击的大部分坑。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np


class Win32Device:
    def __init__(
        self,
        hwnd: int,
        maa_home: str | os.PathLike[str] = r"D:\Games\MaaGakumasu",
        screencap: str = "FramePool",
        input_method: str = "SendMessageWithCursorPos",
    ) -> None:
        self.hwnd = int(hwnd)
        self.maa_home = Path(maa_home)
        self.screencap = screencap
        self.input_method = input_method
        self._ctrl = None

    def connect(self) -> Win32Device:
        os.chdir(self.maa_home)
        site = self.maa_home / "python" / "Lib" / "site-packages"
        if site.exists() and str(site) not in sys.path:
            sys.path.insert(0, str(site))

        from maa.controller import Win32Controller
        from maa.define import MaaWin32InputMethodEnum as InputMethod
        from maa.define import MaaWin32ScreencapMethodEnum as ScreencapMethod

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

    def capture(self) -> np.ndarray:
        return self.controller.post_screencap().wait().get()

    def click(self, x: int, y: int, delay: float = 0.3) -> None:
        self.controller.post_click(int(x), int(y)).wait()
        if delay:
            time.sleep(delay)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.controller.post_swipe(int(x1), int(y1), int(x2), int(y2), int(duration_ms)).wait()

    def key(self, keycode: int) -> None:
        self.controller.post_click_key(int(keycode)).wait()


def find_game_hwnd(title_substr: str = "gakumas", class_name: str = "UnityWndClass") -> int | None:
    """按窗口类/标题查找游戏窗口。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []

    def _cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
        cbuf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cbuf, 256)
        cls = cbuf.value
        if class_name == cls or title_substr.lower() in title.lower():
            found.append(int(hwnd))
        return True

    user32.EnumWindows(proc_type(_cb), 0)
    return found[0] if found else None
