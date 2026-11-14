"""测各输入方式：点击是否生效（截屏差异）＋ 是否移动系统光标。"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
MAA = Path(r"D:\Games\MaaGakumasu")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(MAA / "python" / "Lib" / "site-packages"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from gkagent.device.win32 import USER32, find_game_hwnd  # noqa: E402

os.chdir(MAA)

from maa.controller import Win32Controller  # noqa: E402
from maa.define import MaaWin32InputMethodEnum as IN  # noqa: E402
from maa.define import MaaWin32ScreencapMethodEnum as SC  # noqa: E402


def cursor() -> tuple[int, int]:
    point = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def main() -> None:
    hwnd = find_game_hwnd()
    x, y = 360, 1100
    print(f"hwnd={hwnd} click=({x},{y}) fg={USER32.GetForegroundWindow()}")
    for name in ("PostMessage", "AnchoredTouch", "SendMessage", "PostThreadMessage"):
        try:
            method = getattr(IN, name)
            ctrl = Win32Controller(hwnd, SC.FramePool, method, method)
            ctrl.post_connection().wait()
            before = np.asarray(ctrl.post_screencap().wait().get())
            cur0 = cursor()
            ctrl.post_click(x, y).wait()
            time.sleep(0.15)
            cur_hot = cursor()
            time.sleep(0.85)
            after = np.asarray(ctrl.post_screencap().wait().get())
            diff = float(np.mean(cv2.absdiff(before, after)))
            print(
                f"{name:20s} diff={diff:6.2f} cursor={cur0}->{cur_hot} moved={cur0 != cur_hot}"
            )
        except Exception as exc:
            print(f"{name:20s} ERROR {exc!r}")


if __name__ == "__main__":
    main()
