import ctypes
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

OUT = r"D:\Games\gakumas-agent\data"
user32 = ctypes.WinDLL("user32", use_last_error=True)

game = 526880
overlay = 527006

# 截 overlay 看它是什么
try:
    c = Win32Controller(overlay, SC.FramePool, IN.SendMessageWithCursorPos, IN.SendMessageWithCursorPos)
    c.post_connection().wait()
    img = c.post_screencap().wait().get()
    cv2.imwrite(f"{OUT}\\overlay.png", img)
    print("overlay captured", img.shape)
except Exception as e:
    print("overlay capture error", e)

# 最小化 overlay，把游戏放前台
user32.ShowWindow(overlay, 6)
time.sleep(0.5)
user32.ShowWindow(game, 9)
time.sleep(0.3)
user32.SetForegroundWindow(game)
time.sleep(0.5)

# 用 PostMessage 点击游戏
ctrl = Win32Controller(game, SC.FramePool, IN.SendMessageWithCursorPos, IN.SendMessageWithCursorPos)
ctrl.post_connection().wait()
ctrl.post_click(360, 1105).wait()
time.sleep(2.0)

img = ctrl.post_screencap().wait().get()
cv2.imwrite(f"{OUT}\\after_overlay_min.png", img)
print("after overlay min saved", img.shape)
