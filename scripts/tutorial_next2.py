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
game = 526880

ctrl = Win32Controller(game, SC.FramePool, IN.SendMessageWithCursorPos, IN.SendMessageWithCursorPos)
ctrl.post_connection().wait()

prev = ctrl.post_screencap().wait().get()
static = 0
for i in range(6):
    ctrl.post_click(360, 1105).wait()
    time.sleep(2.5)
    img = ctrl.post_screencap().wait().get()
    diff = float(np.mean(cv2.absdiff(prev, img)))
    cv2.imwrite(os.path.join(OUT, f"tut2_{i}.png"), img)
    print(f"click {i} diff={diff:.2f}")
    prev = img
    if diff < 0.5:
        static += 1
        if static >= 2:
            print("screen static, stop")
            break
    else:
        static = 0
