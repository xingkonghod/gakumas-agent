import ctypes
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2
import numpy as np

from gkagent.device.win32 import Win32Device, find_game_hwnd

OUT = r"D:\Games\gakumas-agent\data"
user32 = ctypes.WinDLL("user32")


def cursor():
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("game window not found")
device = Win32Device(hwnd, input_method="PostMessage").connect()

before_cursor = cursor()
before = device.capture()
device.click(600, 1100, delay=1.2)
after = device.capture()
after_cursor = cursor()
diff = float(np.mean(cv2.absdiff(before, after)))
cv2.imwrite(f"{OUT}\\postmessage_test.png", after)
print("cursor", before_cursor, "->", after_cursor, "diff", round(diff, 2))
