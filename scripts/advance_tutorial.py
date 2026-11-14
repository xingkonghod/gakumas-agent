import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from gkagent.device.win32 import find_game_hwnd

user32 = ctypes.WinDLL("user32", use_last_error=True)

hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("game window not found")

user32.ShowWindow(hwnd, 9)
time.sleep(0.3)
user32.SetForegroundWindow(hwnd)
time.sleep(0.5)

rect = wintypes.RECT()
user32.GetClientRect(hwnd, ctypes.byref(rect))
cw, ch = rect.right, rect.bottom
origin = wintypes.POINT(0, 0)
user32.ClientToScreen(hwnd, ctypes.byref(origin))


def click(x720: int, y720: int) -> None:
    sx = origin.x + int(x720 * cw / 720)
    sy = origin.y + int(y720 * ch / 1280)
    user32.SetCursorPos(sx, sy)
    time.sleep(0.1)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


# 点角色/文字区域，再按 Enter
click(360, 600)
time.sleep(1.0)
user32.keybd_event(0x0D, 0, 0, 0)
time.sleep(0.05)
user32.keybd_event(0x0D, 0, 2, 0)
time.sleep(2.0)

from gkagent.device.win32 import Win32Device

device = Win32Device(hwnd).connect()
img = device.capture()
cv2.imwrite(r"D:\Games\gakumas-agent\data\after_advance.png", img)
print("saved after_advance.png", img.shape)
