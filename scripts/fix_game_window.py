"""把游戏窗口还原成标准尺寸（客户区 1080x1920 物理 → 渲染 720x1280 → capture 1280x720）。

F#57b：截图口径锁死该尺寸——缩窗（如 540x960/684x949）会得 invalid shape (999,720)
（F#10 同病）。1920x1080@200% 屏上整窗必然 off-screen 下半，属物理约束；bot 走
SendMessage/PrintWindow 不受影响。auto_produce 的 PRODUCE_CLIENT_SIZE=(540,960) 是
DPI-unaware 逻辑口径（=物理 1080x1920 @200%），两者自洽。story 段窗口停局另查根因。
用法：python scripts/fix_game_window.py
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
    # F#57b：截图口径锁死客户区 1080x1920 物理（渲染 720x1280 → capture 1280x720）；
    # 缩窗会得 invalid shape (999,720)（F#10 同病）。1080p 屏放不下整窗是物理约束，
    # bot 走 SendMessage/PrintWindow 不受 off-screen 影响；story 段停局另查根因。
    target_w, target_h = 1080, 1920
    USER32.MoveWindow(
        hwnd,
        window.left,
        window.top,
        target_w + border_w,
        target_h + border_h,
        True,
    )
    time.sleep(1.5)
    USER32.GetClientRect(hwnd, ctypes.byref(client))
    print(f"after client={client.right-client.left}x{client.bottom-client.top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
