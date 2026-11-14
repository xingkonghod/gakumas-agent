"""诊断把游戏窗口抬到可见/前台的方法，并在抬升后立刻验证一次点击是否生效。"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from gkagent.device.win32 import USER32, KERNEL32, Win32Device, find_game_hwnd  # noqa: E402

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010


def cap_desktop() -> np.ndarray:
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    width = USER32.GetSystemMetrics(0)
    height = USER32.GetSystemMetrics(1)
    hdc = USER32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mem, bmp)

    class BIH(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BI(ctypes.Structure):
        _fields_ = [("bmiHeader", BIH), ("bmiColors", wintypes.DWORD * 3)]

    info = BI()
    info.bmiHeader.biSize = ctypes.sizeof(BIH)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    gdi32.BitBlt(mem, 0, 0, width, height, hdc, 0, 0, 0x00CC0020)
    buf = (ctypes.c_ubyte * (width * height * 4))()
    gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(info), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    USER32.ReleaseDC(0, hdc)
    return np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 4)[:, :, :3].copy()


def click_at(device: Win32Device, x: int, y: int) -> None:
    rect = wintypes.RECT()
    USER32.GetClientRect(device.hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    USER32.ClientToScreen(device.hwnd, ctypes.byref(origin))
    sx = origin.x + round(x * rect.right / 720.0)
    sy = origin.y + round(y * rect.bottom / 1280.0)
    print(f"click game({x},{y}) -> screen({sx},{sy})")
    USER32.SetCursorPos(sx, sy)
    time.sleep(0.15)
    USER32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    USER32.mouse_event(0x0004, 0, 0, 0, 0)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "topmost"
    hwnd = find_game_hwnd()
    device = Win32Device(hwnd).connect()
    before = device.capture()
    print(f"fg-before={USER32.GetForegroundWindow()} mean-before={before.mean():.1f}")

    if mode == "topmost":
        ok = USER32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        print(f"SetWindowPos TOPMOST -> {bool(ok)} err={ctypes.get_last_error()}")
    elif mode == "attachtop":
        # 先 AttachThreadInput，再抬到 topmost + SetForegroundWindow
        fg = USER32.GetForegroundWindow()
        fg_tid = USER32.GetWindowThreadProcessId(fg, None)
        cur_tid = KERNEL32.GetCurrentThreadId()
        USER32.AttachThreadInput(cur_tid, fg_tid, True)
        USER32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        USER32.ShowWindow(hwnd, 9)
        print(f"SetForegroundWindow -> {bool(USER32.SetForegroundWindow(hwnd))}")
        USER32.AttachThreadInput(cur_tid, fg_tid, False)
    time.sleep(0.8)
    print(f"fg-after={USER32.GetForegroundWindow()}")
    cv2.imwrite(str(ROOT / "data" / f"raise_{mode}.png"), cap_desktop())

    click_at(device, 600, 1041)  # 「自动」按钮
    time.sleep(1.5)
    after = device.capture()
    print(f"mean-after={after.mean():.1f} diff={np.abs(after.astype(float) - before.astype(float)).mean():.2f}")
    cv2.imwrite(str(ROOT / "data" / f"raise_{mode}_after.png"), after)

    if mode == "topmost":
        USER32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        print("restored NOTOPMOST")


if __name__ == "__main__":
    main()
