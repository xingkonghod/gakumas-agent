"""原生 MAA controller 点击探针：坐标原样传入（不做 720x1280→客户区缩放），验证
MaaGakumasu 的 SendMessageWithCursorPos 期望哪种坐标系。
用法: python data/_ctrl_probe.py <x> <y> <tag> [method]
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = r"D:\Games\gakumas-agent"
MAA = r"D:\Games\MaaGakumasu"
sys.path.insert(0, os.path.join(ROOT, "src"))

import cv2

sys.path.append(os.path.join(MAA, "python", "Lib", "site-packages"))

from gkagent.device.win32 import USER32, find_game_hwnd

os.chdir(MAA)

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

x, y = int(sys.argv[1]), int(sys.argv[2])
tag = sys.argv[3]
method_name = sys.argv[4] if len(sys.argv) > 4 else "SendMessageWithCursorPos"
method = getattr(IN, method_name)

hwnd = find_game_hwnd()
rect = wintypes.RECT()
USER32.GetClientRect(hwnd, ctypes.byref(rect))
point = wintypes.POINT()
USER32.ClientToScreen(hwnd, ctypes.byref(point))
print("hwnd", hwnd, "client", rect.right, rect.bottom, "origin", point.x, point.y)
ctrl = Win32Controller(hwnd, SC.FramePool, method, method)
ctrl.post_connection().wait()
before = ctrl.post_screencap().wait().get()
cv2.imwrite(rf"D:\Games\gakumas-agent\data\_ctrl_{tag}_before.png", before)
ctrl.post_click(x, y).wait()
time.sleep(1.5)
after = ctrl.post_screencap().wait().get()
cv2.imwrite(rf"D:\Games\gakumas-agent\data\_ctrl_{tag}_after.png", after)
diff = float(cv2.absdiff(before, after).mean())
print(f"method={method_name} click=({x},{y}) before={before.mean():.1f} after={after.mean():.1f} diff={diff:.2f} changed={diff > 2.0}")
