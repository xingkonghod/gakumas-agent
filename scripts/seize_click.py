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

x, y = int(sys.argv[1]), int(sys.argv[2])
wait = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0

ctrl = Win32Controller(GAME, SC.FramePool, IN.Seize, IN.Seize)
ctrl.post_connection().wait()
user32.ShowWindow(OVERLAY, 0)
time.sleep(0.3)
user32.ShowWindow(GAME, 9)
user32.SetForegroundWindow(GAME)
time.sleep(0.3)
before = ctrl.post_screencap().wait().get()
ctrl.post_click(x, y).wait()
time.sleep(wait)
after = ctrl.post_screencap().wait().get()
print("diff", round(float(np.mean(cv2.absdiff(before, after))), 2))
path = os.path.join(OUT, f"seize_{x}_{y}.png")
cv2.imwrite(path, after)
print("saved", path)
