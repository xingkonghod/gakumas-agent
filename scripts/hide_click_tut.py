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
game = 526880
overlay = 527006

user32 = ctypes.WinDLL("user32", use_last_error=True)

ctrl = Win32Controller(game, SC.FramePool, IN.SendMessageWithCursorPos, IN.SendMessageWithCursorPos)
ctrl.post_connection().wait()

prev = ctrl.post_screencap().wait().get()
for i in range(5):
    user32.ShowWindow(overlay, 0)  # SW_HIDE
    time.sleep(0.3)
    user32.ShowWindow(game, 9)
    user32.SetForegroundWindow(game)
    time.sleep(0.3)
    ctrl.post_click(360, 1105).wait()
    time.sleep(2.5)
    img = ctrl.post_screencap().wait().get()
    diff = float(np.mean(cv2.absdiff(prev, img)))
    cv2.imwrite(os.path.join(OUT, f"hide_{i}.png"), img)
    print(f"iter {i} diff={diff:.2f}")
    prev = img
