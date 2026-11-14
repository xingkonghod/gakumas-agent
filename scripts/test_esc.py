import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2
import numpy as np

from gkagent.device.win32 import find_game_hwnd

OUT = r"D:\Games\gakumas-agent\data"
user32 = ctypes.WinDLL("user32", use_last_error=True)
hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("no game window")

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

ctrl = Win32Controller(hwnd, SC.FramePool, IN.PostMessage, IN.PostMessage)
ctrl.post_connection().wait()
before = ctrl.post_screencap().wait().get()
user32.PostMessageW(hwnd, 0x0100, 0x1B, 0)  # WM_KEYDOWN VK_ESCAPE
time.sleep(0.05)
user32.PostMessageW(hwnd, 0x0101, 0x1B, 0)  # WM_KEYUP
time.sleep(1.2)
after = ctrl.post_screencap().wait().get()
diff = float(np.mean(cv2.absdiff(before, after)))
cv2.imwrite(f"{OUT}\\esc_test.png", after)
print("esc diff", round(diff, 2))
