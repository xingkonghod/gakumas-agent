"""把游戏窗口还原成标准尺寸（客户区 1080x1920 物理 → 渲染 720x1280）。

用于窗口被拉伸/缩放后截图形状不对（例如 720x999）导致 capture 校验失败。
用法（管理员）：python scripts/fix_game_window.py
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

from gkagent.device.win32 import USER32, find_game_hwnd  # noqa: E402

SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window")
        return 2
    client = RECT()
    window = RECT()
    USER32.GetClientRect(hwnd, ctypes.byref(client))
    USER32.GetWindowRect(hwnd, ctypes.byref(window))
    cw, ch = client.right - client.left, client.bottom - client.top
    ww, wh = window.right - window.left, window.bottom - window.top
    print(f"before client={cw}x{ch} window={ww}x{wh}")
    border_w, border_h = ww - cw, wh - ch
    if USER32.IsIconic(hwnd):
        USER32.ShowWindow(hwnd, 9)
        time.sleep(1.0)
    USER32.MoveWindow(
        hwnd,
        window.left,
        window.top,
        1080 + border_w,
        1920 + border_h,
        True,
    )
    time.sleep(1.5)
    USER32.GetClientRect(hwnd, ctypes.byref(client))
    print(f"after client={client.right-client.left}x{client.bottom-client.top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
