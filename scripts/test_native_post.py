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
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001


def cursor():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("no game window")
rect = wintypes.RECT()
user32.GetClientRect(hwnd, ctypes.byref(rect))
cw, ch = rect.right, rect.bottom
print("hwnd", hwnd, "client", cw, ch)

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

ctrl = Win32Controller(hwnd, SC.FramePool, IN.PostMessage, IN.PostMessage)
ctrl.post_connection().wait()

x, y = 600, 1100
cx = int(round(x * cw / 720))
cy = int(round(y * ch / 1280))
lp = (cy << 16) | (cx & 0xFFFF)
before_cursor = cursor()
before = ctrl.post_screencap().wait().get()
user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
time.sleep(0.05)
user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
time.sleep(1.2)
after = ctrl.post_screencap().wait().get()
after_cursor = cursor()
diff = float(np.mean(cv2.absdiff(before, after)))
cv2.imwrite(f"{OUT}\\native_post.png", after)
print("native post cursor", before_cursor, "->", after_cursor, "diff", round(diff, 2))
