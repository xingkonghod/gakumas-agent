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

prev = ctrl.post_screencap().wait().get()
static = 0
for i in range(6):
    user32.ShowWindow(OVERLAY, 0)
    time.sleep(0.2)
    user32.ShowWindow(GAME, 9)
    user32.SetForegroundWindow(GAME)
    time.sleep(0.2)
    ctrl.post_click(360, 600).wait()
    time.sleep(1.6)
    img = ctrl.post_screencap().wait().get()
    diff = float(np.mean(cv2.absdiff(prev, img)))
    cv2.imwrite(os.path.join(OUT, f"story_{i}.png"), img)
    print(f"tap {i} diff={diff:.2f}")
    prev = img
    if diff < 0.5:
        static += 1
        if static >= 2:
            print("static, stop")
            break
    else:
        static = 0
