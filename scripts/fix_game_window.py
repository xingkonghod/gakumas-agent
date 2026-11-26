"""把游戏窗口还原成标准尺寸（客户区 540x960 物理，与 auto_produce PRODUCE_CLIENT_SIZE 同口径）。

F#57（真机 ep-live-seed8/10 story 段窗口恢复连续失败根因）：旧版设 1080x1920 物理，
在 1920x1080@200% DPI 屏上窗口高出屏幕一倍 → 大半 off-screen → story/成就段焦点切换时
被 Windows 收回/最小化 → ensure_window 连续 5 次恢复失败停局。540x960+框≈996 ≤1080 才_fit_。
屏幕更矮时按高度保护等比缩。用法：python scripts/fix_game_window.py
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
    # F#57：屏幕高度保护（物理像素），窗口不得高出屏幕。
    screen_h = USER32.GetSystemMetrics(1)  # SM_CYSCREEN
    target_w, target_h = 540, 960
    if target_h + border_h > screen_h:
        scale = (screen_h - border_h) / target_h
        target_w, target_h = int(target_w * scale), int(target_h * scale)
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
