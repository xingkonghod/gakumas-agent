"""诊断点击落点：模拟 click_force 的坐标换算，把光标挪过去并截桌面，看是否落在按钮上。"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

from gkagent.device.win32 import USER32, find_game_hwnd  # noqa: E402


def capture_desktop(path: Path) -> None:
    import cv2
    import numpy as np

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mem, bmp)

    class BITMAPINFOHEADER(ctypes.Structure):
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

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0

    gdi32.BitBlt(mem, 0, 0, width, height, hdc, 0, 0, 0x00CC0020)
    buf = (ctypes.c_ubyte * (width * height * 4))()
    gdi32.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(info), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0, hdc)
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 4)[:, :, :3].copy()
    cv2.imwrite(str(path), arr)
    print(f"desktop {width}x{height} -> {path}")


def main() -> None:
    hwnd = find_game_hwnd()
    print(f"hwnd={hwnd}")
    rect = wintypes.RECT()
    USER32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    USER32.ClientToScreen(hwnd, ctypes.byref(origin))
    win = wintypes.RECT()
    USER32.GetWindowRect(hwnd, ctypes.byref(win))
    print(f"client={rect.right}x{rect.bottom} origin={origin.x},{origin.y} window=({win.left},{win.top})-({win.right},{win.bottom})")
    print(f"fg={USER32.GetForegroundWindow()} target={hwnd}")

    x, y = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (398, 1124)
    sx = origin.x + round(x * rect.right / 720.0)
    sy = origin.y + round(y * rect.bottom / 1280.0)
    print(f"game({x},{y}) -> screen({sx},{sy})")
    old = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(old))
    USER32.SetCursorPos(sx, sy)
    time.sleep(0.2)
    now = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(now))
    print(f"cursor {old.x},{old.y} -> {now.x},{now.y}")
    capture_desktop(ROOT / "data" / "click_target.png")


if __name__ == "__main__":
    main()
