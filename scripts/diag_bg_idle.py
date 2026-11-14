"""等用户空闲 >3s 后，用 PostMessage 点一次「菜单」图标，验证后台点击是否真的生效。

不移动鼠标、不抢前台；只在用户停止操作时点一次，避免打扰。
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


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_ms() -> int:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    USER32.GetLastInputInfo(ctypes.byref(info))
    return ctypes.windll.kernel32.GetTickCount() - int(info.dwTime) & 0xFFFFFFFF


def main() -> None:
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 615
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
    max_wait = float(sys.argv[3]) if len(sys.argv) > 3 else 120.0
    hwnd = find_game_hwnd()
    ctrl = Win32Controller(hwnd, SC.FramePool, IN.PostMessage, IN.PostMessage)
    ctrl.post_connection().wait()
    print(f"hwnd={hwnd} target=({x},{y}) waiting for user idle ...")
    deadline = time.time() + max_wait
    while time.time() < deadline and idle_ms() < 3000:
        time.sleep(0.3)
    wait_idle = idle_ms()
    print(f"idle={wait_idle}ms before click")
    before = np.asarray(ctrl.post_screencap().wait().get())
    ctrl.post_click(x, y).wait()
    time.sleep(1.2)
    after = np.asarray(ctrl.post_screencap().wait().get())
    diff = float(np.mean(cv2.absdiff(before, after)))
    cv2.imwrite(str(ROOT / "data" / "bg_idle_after.png"), after)
    print(f"diff={diff:.2f} idle_after={idle_ms()}ms")
    print("RESULT: background click " + ("WORKS" if diff > 5 else "NO EFFECT"))


if __name__ == "__main__":
    main()
