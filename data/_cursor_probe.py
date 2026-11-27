"""光标轨迹探针：MAA post_click 期间轮询真实光标位置，判定坐标约定（客户区 px vs 720x1280 截图坐标）。
用法: python data/_cursor_probe.py <x> <y> [method]
"""
import ctypes
import os
import sys
import time
import threading
from ctypes import wintypes

ROOT = r"D:\Games\gakumas-agent"
MAA = r"D:\Games\MaaGakumasu"
sys.path.insert(0, os.path.join(ROOT, "src"))

import cv2

from gkagent.device.win32 import USER32, find_game_hwnd

sys.path.append(os.path.join(MAA, "python", "Lib", "site-packages"))
os.chdir(MAA)

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

x, y = int(sys.argv[1]), int(sys.argv[2])
method_name = sys.argv[3] if len(sys.argv) > 3 else "SendMessageWithCursorPos"

hwnd = find_game_hwnd()
rect = wintypes.RECT()
USER32.GetClientRect(hwnd, ctypes.byref(rect))
origin = wintypes.POINT()
USER32.ClientToScreen(hwnd, ctypes.byref(origin))
print(f"hwnd={hwnd} client={rect.right}x{rect.bottom} origin=({origin.x},{origin.y}) target=({x},{y})")


def cursor():
    p = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


seen = []
stop = False


def poll():
    while not stop:
        c = cursor()
        if not seen or seen[-1] != c:
            seen.append(c)
        time.sleep(0.008)


ctrl = Win32Controller(hwnd, SC.FramePool, getattr(IN, method_name), getattr(IN, method_name))
ctrl.post_connection().wait()
before = ctrl.post_screencap().wait().get()
print("cursor before", cursor(), "fg", USER32.GetForegroundWindow())
t = threading.Thread(target=poll, daemon=True)
t.start()
ctrl.post_click(x, y).wait()
time.sleep(1.2)
stop = True
after = ctrl.post_screencap().wait().get()
diff = float(cv2.absdiff(before, after).mean())
print("cursor path:", seen[:12], "... last:", seen[-1] if seen else None)
print(f"diff={diff:.2f} changed={diff > 2.0} after_mean={after.mean():.1f}")
cv2.imwrite(os.path.join(ROOT, "data", "_cursor_after.png"), after)
