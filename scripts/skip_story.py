import ctypes
import os
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

OUT = r"D:\Games\gakumas-agent\data"
GAME = 526880
OVERLAY = 527006
user32 = ctypes.WinDLL("user32", use_last_error=True)

ctrl = Win32Controller(GAME, SC.FramePool, IN.Seize, IN.Seize)
ctrl.post_connection().wait()


def press(x: int, y: int, wait: float) -> None:
    user32.ShowWindow(OVERLAY, 0)
    time.sleep(0.25)
    user32.ShowWindow(GAME, 9)
    user32.SetForegroundWindow(GAME)
    time.sleep(0.25)
    ctrl.post_click(x, y).wait()
    time.sleep(wait)


press(200, 1195, 1.5)  # SKIP
press(500, 1140, 3.0)  # 确定
img = ctrl.post_screencap().wait().get()
cv2.imwrite(os.path.join(OUT, "skip_result.png"), img)
print("saved skip_result.png")
