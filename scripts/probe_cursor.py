"""把光标移到物理坐标 (x, y)，截图并在对应逻辑位置画红圈，用于校准点击落点。"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

import cv2

USER32 = ctypes.WinDLL("user32", use_last_error=True)


def capture_desktop() -> "cv2.Mat":
    user32 = USER32
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    width = 1920
    height = 1080
    hdc = user32.GetDC(0)
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
    user32.ReleaseDC(0, hdc)
    import numpy as np

    return np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 4)[:, :, :3].copy()


def main() -> None:
    x = int(sys.argv[1])
    y = int(sys.argv[2])
    out = sys.argv[3] if len(sys.argv) > 3 else r"D:\Games\gakumas-agent\data\probe.png"
    USER32.SetCursorPos(x, y)
    time.sleep(0.3)
    img = capture_desktop()
    lx, ly = x // 2, y // 2
    cv2.circle(img, (lx, ly), 24, (0, 0, 255), 3)
    cv2.line(img, (lx - 34, ly), (lx + 34, ly), (0, 0, 255), 2)
    cv2.line(img, (lx, ly - 34), (lx, ly + 34), (0, 0, 255), 2)
    cv2.imwrite(out, img)
    print(f"cursor at physical ({x},{y}) -> logical ({lx},{ly}); saved {out}")


if __name__ == "__main__":
    main()
