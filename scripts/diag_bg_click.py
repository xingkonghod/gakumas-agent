"""诊断：哪些 MAA 输入方式能在**不移动系统鼠标/不抢前台**的情况下点到游戏。

对每一屏点同一个点，比较点击前后截图差异、光标位置、前台窗口。
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

X = int(sys.argv[1]) if len(sys.argv) > 1 else 360
Y = int(sys.argv[2]) if len(sys.argv) > 2 else 1100


def cursor() -> tuple[int, int]:
    point = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def main() -> None:
    hwnd = find_game_hwnd()
    print(f"hwnd={hwnd} target=({X},{Y}) fg={USER32.GetForegroundWindow()} cursor={cursor()}")
    for name in (
        "PostMessage",
        "SendMessage",
        "AnchoredTouch",
        "PostMessageWithCursorPos",
        "SendMessageWithCursorPos",
        "PostThreadMessage",
    ):
        try:
            method = getattr(IN, name)
            ctrl = Win32Controller(hwnd, SC.FramePool, method, method)
            ctrl.post_connection().wait()
            before = np.asarray(ctrl.post_screencap().wait().get())
            cur0 = cursor()
            fg0 = USER32.GetForegroundWindow()
            ctrl.post_click(X, Y).wait()
            time.sleep(1.2)
            after = np.asarray(ctrl.post_screencap().wait().get())
            cur1 = cursor()
            fg1 = USER32.GetForegroundWindow()
            diff = float(np.mean(cv2.absdiff(before, after)))
            print(
                f"{name:24s} diff={diff:6.2f} cursor={cur0}->{cur1} fg_changed={fg0 != fg1}"
            )
            if diff > 5:
                cv2.imwrite(str(ROOT / "data" / f"bg_{name}.png"), after)
                print(f"  CHANGED with {name}")
                break
        except Exception as exc:  # noqa: BLE001
            print(f"{name:24s} ERROR {exc!r}")


if __name__ == "__main__":
    main()
