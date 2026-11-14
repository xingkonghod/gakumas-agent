"""对照实验：PostMessage 后台点击是否真的生效（不需要用户停手）。

1) 不点击，隔 1.5s 截两帧 → 动画噪声 control_diff
2) PostMessage 点一下，隔 1.5s 截帧 → click_diff
click_diff 明显大于 control_diff 才算生效。
"""

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


def diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(cv2.absdiff(a, b)))


def main() -> None:
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 360
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 1100
    hwnd = find_game_hwnd()
    ctrl = Win32Controller(hwnd, SC.FramePool, IN.PostMessage, IN.PostMessage)
    ctrl.post_connection().wait()
    print(f"hwnd={hwnd} target=({x},{y}) fg={USER32.GetForegroundWindow()} cursor={cursor()}")

    a = np.asarray(ctrl.post_screencap().wait().get())
    time.sleep(1.5)
    b = np.asarray(ctrl.post_screencap().wait().get())
    control = diff(a, b)
    cur0 = cursor()

    ctrl.post_click(x, y).wait()
    time.sleep(1.5)
    c = np.asarray(ctrl.post_screencap().wait().get())
    clicked = diff(b, c)
    cur1 = cursor()

    cv2.imwrite(str(ROOT / "data" / "bgv_before.png"), b)
    cv2.imwrite(str(ROOT / "data" / "bgv_after.png"), c)
    print(f"control_diff={control:.2f} click_diff={clicked:.2f} cursor={cur0}->{cur1}")
    print("RESULT: " + ("WORKS" if clicked > max(4.0, 2.0 * control) else "NO EFFECT"))


if __name__ == "__main__":
    main()
