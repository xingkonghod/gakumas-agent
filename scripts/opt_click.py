import ctypes
import os
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2
import numpy as np

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

OUT = r"D:\Games\gakumas-agent\data"
GAME = 526880
OVERLAY = 527006
user32 = ctypes.WinDLL("user32", use_last_error=True)

ctrl = Win32Controller(GAME, SC.FramePool, IN.Seize, IN.Seize)
ctrl.post_connection().wait()


def press(x: int, y: int, wait: float, tag: str) -> None:
    user32.ShowWindow(OVERLAY, 0)
    time.sleep(0.3)
    user32.ShowWindow(GAME, 9)
    user32.SetForegroundWindow(GAME)
    time.sleep(0.3)
    before = ctrl.post_screencap().wait().get()
    ctrl.post_click(x, y).wait()
    time.sleep(wait)
    after = ctrl.post_screencap().wait().get()
    diff = float(np.mean(cv2.absdiff(before, after)))
    cv2.imwrite(os.path.join(OUT, f"opt_{tag}.png"), after)
    print(tag, "diff", round(diff, 2))


press(150, 795, 1.5, "radio")
press(380, 1115, 2.0, "ok")
