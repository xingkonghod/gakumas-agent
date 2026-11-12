"""在物理屏幕坐标上点一下（管理员运行；点完还原光标）。用于启动 DMM 内的游戏。"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

USER32 = ctypes.WinDLL("user32", use_last_error=True)


def main() -> None:
    x = int(sys.argv[1])
    y = int(sys.argv[2])
    saved = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(saved))
    USER32.SetCursorPos(x, y)
    time.sleep(0.15)
    USER32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    USER32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.3)
    USER32.SetCursorPos(saved.x, saved.y)
    print(f"clicked screen ({x},{y})")


if __name__ == "__main__":
    main()
