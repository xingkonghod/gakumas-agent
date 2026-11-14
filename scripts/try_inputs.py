import os
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2
import numpy as np

from gkagent.device.win32 import find_game_hwnd

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

OUT = r"D:\Games\gakumas-agent\data"
hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("game window not found")

methods = ["AnchoredTouch", "Seize", "LegacyEvent"]
for name in methods:
    try:
        method = getattr(IN, name)
        ctrl = Win32Controller(hwnd, SC.FramePool, method, method)
        ctrl.post_connection().wait()
        before = ctrl.post_screencap().wait().get()
        ctrl.post_click(360, 1105).wait()
        time.sleep(2.0)
        after = ctrl.post_screencap().wait().get()
        diff = float(np.mean(cv2.absdiff(before, after)))
        cv2.imwrite(os.path.join(OUT, f"input_{name}.png"), after)
        print(name, "diff", round(diff, 2))
        if diff > 1.0:
            print("CHANGED with", name)
            break
    except Exception as e:
        print(name, "ERROR", e)
