"""按 z 序枚举顶层窗口，标出 topmost / 游戏窗口位置。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

WS_EX_TOPMOST = 0x8


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def title(hwnd: int) -> tuple[str, str]:
    tbuf = ctypes.create_unicode_buffer(256)
    cbuf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, tbuf, 256)
    user32.GetClassNameW(hwnd, cbuf, 256)
    return tbuf.value, cbuf.value


def main() -> None:
    fg = user32.GetForegroundWindow()
    hwnd = user32.GetTopWindow(None)
    print(f"foreground={fg}  (title={title(fg)})")
    i = 0
    while hwnd:
        if user32.IsWindowVisible(hwnd):
            t, c = title(hwnd)
            ex = user32.GetWindowLongW(hwnd, -20)
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            cloaked = ctypes.c_int(0)
            dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
            print(
                f"{i:2d} hwnd={hwnd} topmost={bool(ex & WS_EX_TOPMOST)} cloaked={cloaked.value} "
                f"class={c!r} title={t!r} rect=({r.left},{r.top})-({r.right},{r.bottom})"
            )
            i += 1
        hwnd = user32.GetWindow(hwnd, 2)  # GW_HWNDNEXT
        if i > 40:
            break


if __name__ == "__main__":
    main()
