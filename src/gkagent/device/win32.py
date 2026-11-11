"""Win32 设备：截屏 + 点击。

底层复用 MaaFramework 的 Win32Controller。
默认用 PostMessage：不移动光标、不抢焦点；只隐藏 DMM Play Assist 覆盖层。
需要真实鼠标时才显式传 input_method="Seize"。
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
        input_method: str = "PostMessage",
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
        if self._overlay:
            USER32.ShowWindow(self._overlay, 0)
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
        # 不再移动光标/抢焦点；PostMessage 直接投递窗口消息。
        return

    def capture(self) -> np.ndarray:
        return self.controller.post_screencap().wait().get()

    def click(self, x: int, y: int, delay: float = 0.3) -> None:
        """原生 PostMessage 点击：不移动系统光标，不抢前台焦点。"""
        rect = wintypes.RECT()
        USER32.GetClientRect(self.hwnd, ctypes.byref(rect))
        cw, ch = rect.right, rect.bottom
        cx = round(int(x) * cw / 720.0)
        cy = round(int(y) * ch / 1280.0)
        lp = (cy << 16) | (cx & 0xFFFF)
        USER32.PostMessageW(self.hwnd, 0x0201, 0x0001, lp)  # WM_LBUTTONDOWN
        time.sleep(0.03)
        USER32.PostMessageW(self.hwnd, 0x0202, 0, lp)  # WM_LBUTTONUP
        if delay:
            time.sleep(delay)

    def click_force(self, x: int, y: int, delay: float = 0.4) -> None:
        """物理点击（必要时的兜底）：短暂聚焦+移动光标，点完恢复光标位置。"""
        rect = wintypes.RECT()
        USER32.GetClientRect(self.hwnd, ctypes.byref(rect))
        cw, ch = rect.right, rect.bottom
        origin = wintypes.POINT(0, 0)
        USER32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        sx = origin.x + round(int(x) * cw / 720.0)
        sy = origin.y + round(int(y) * ch / 1280.0)

        saved = wintypes.POINT()
        USER32.GetCursorPos(ctypes.byref(saved))
        # 绕过前台锁：最小化再恢复，强制把游戏拉到最前
        USER32.ShowWindow(self.hwnd, 6)
        time.sleep(0.12)
        USER32.ShowWindow(self.hwnd, 9)
        time.sleep(0.12)
        USER32.SetForegroundWindow(self.hwnd)
        time.sleep(0.1)
        USER32.SetCursorPos(sx, sy)
        time.sleep(0.05)
        USER32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)
        USER32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.06)
        USER32.SetCursorPos(saved.x, saved.y)
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
        if not USER32.IsWindowVisible(hwnd):
            return True
        if class_name == cls or title_substr.lower() in title.lower():
            found.append(int(hwnd))
        return True

    USER32.EnumWindows(proc_type(_cb), 0)
    return found[0] if found else None
