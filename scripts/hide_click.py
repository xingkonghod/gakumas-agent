import ctypes
import os
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

OUT = r"D:\Games\gakumas-agent\data"
game = 526880
overlay = 527006
user32 = ctypes.WinDLL("user32", use_last_error=True)

x, y = int(sys.argv[1]), int(sys.argv[2])
wait = float(sys.argv[3]) if len(sys.argv) > 3 else 2.5

ctrl = Win32Controller(game, SC.FramePool, IN.SendMessageWithCursorPos, IN.SendMessageWithCursorPos)
ctrl.post_connection().wait()

user32.ShowWindow(overlay, 0)
time.sleep(0.2)
user32.ShowWindow(game, 9)
user32.SetForegroundWindow(game)
time.sleep(0.2)
ctrl.post_click(x, y).wait()
time.sleep(wait)
img = ctrl.post_screencap().wait().get()
path = os.path.join(OUT, f"click_{x}_{y}.png")
cv2.imwrite(path, img)
print("saved", path)
