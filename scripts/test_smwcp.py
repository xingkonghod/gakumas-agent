"""验证原生 MAA 的 SendMessageWithCursorPos：点 SKIP → 应弹「跳过确认」；看光标是否被还原。"""

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

METHOD = getattr(IN, sys.argv[3] if len(sys.argv) > 3 else "SendMessageWithCursorPos")


def cursor() -> tuple[int, int]:
    point = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def main() -> None:
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 208
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 1204
    hwnd = find_game_hwnd()
    ctrl = Win32Controller(hwnd, SC.FramePool, METHOD, METHOD)
    ctrl.post_connection().wait()
    cur0, fg0 = cursor(), USER32.GetForegroundWindow()
    before = np.asarray(ctrl.post_screencap().wait().get())
    ctrl.post_click(x, y).wait()
    time.sleep(1.2)
    after = np.asarray(ctrl.post_screencap().wait().get())
    cur1, fg1 = cursor(), USER32.GetForegroundWindow()
    diff = float(np.mean(cv2.absdiff(before, after)))
    print(f"method={METHOD} click=({x},{y})")
    print(f"diff={diff:.2f} cursor={cur0}->{cur1} restored={cur0 == cur1} fg_changed={fg0 != fg1}")
    cv2.imwrite(str(ROOT / "data" / "smwcp_after.png"), after)
    # 若弹窗出现，用同方法点取消还原
    if diff > 5:
        ctrl.post_click(175, 1163).wait()
        time.sleep(0.8)
        print("clicked cancel to restore")


if __name__ == "__main__":
    main()
