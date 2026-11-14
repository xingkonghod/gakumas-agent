"""诊断 2：连续多次 PostMessage 点击，确认是否真的后台生效（并检查用户是否在动鼠标）。"""

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


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def last_input_ms() -> int:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    USER32.GetLastInputInfo(ctypes.byref(info))
    return int(info.dwTime)


def ticks() -> int:
    return ctypes.windll.kernel32.GetTickCount()


def cursor() -> tuple[int, int]:
    point = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def main() -> None:
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 360
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 1100
    hwnd = find_game_hwnd()
    method = getattr(IN, sys.argv[3] if len(sys.argv) > 3 else "PostMessage")
    ctrl = Win32Controller(hwnd, SC.FramePool, method, method)
    ctrl.post_connection().wait()
    print(f"hwnd={hwnd} fg={USER32.GetForegroundWindow()} method={method}")

    prev = np.asarray(ctrl.post_screencap().wait().get())
    for i in range(4):
        idle_ms = ticks() - last_input_ms()
        before_cursor = cursor()
        fg0 = USER32.GetForegroundWindow()
        ctrl.post_click(x, y).wait()
        time.sleep(1.2)
        frame = np.asarray(ctrl.post_screencap().wait().get())
        diff = float(np.mean(cv2.absdiff(prev, frame)))
        print(
            f"click#{i + 1} diff={diff:6.2f} user_idle_ms={idle_ms:6d} "
            f"cursor={before_cursor}->{cursor()} fg_changed={fg0 != USER32.GetForegroundWindow()}"
        )
        prev = frame
        time.sleep(0.5)


if __name__ == "__main__":
    main()
