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

for name in ["Seize", "AnchoredTouch", "LegacyEvent", "PostMessage"]:
    try:
        method = getattr(IN, name)
        ctrl = Win32Controller(GAME, SC.FramePool, method, method)
        ctrl.post_connection().wait()
        user32.ShowWindow(OVERLAY, 0)
        time.sleep(0.4)
        user32.ShowWindow(GAME, 9)
        user32.SetForegroundWindow(GAME)
        time.sleep(0.4)
        before = ctrl.post_screencap().wait().get()
        ctrl.post_click(360, 1115).wait()
        time.sleep(1.5)
        after = ctrl.post_screencap().wait().get()
        diff = float(np.mean(cv2.absdiff(before, after)))
        cv2.imwrite(os.path.join(OUT, f"confirm_{name}.png"), after)
        print(name, "diff", round(diff, 2))
        if diff > 2.0:
            print("CHANGED with", name)
            break
    except Exception as e:
        print(name, "ERROR", e)
