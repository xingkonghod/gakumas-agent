import sys

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from gkagent.device.win32 import Win32Device, find_game_hwnd

hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("no game window")
device = Win32Device(hwnd).connect()
img = device.capture()
cv2.imwrite(r"D:\Games\gakumas-agent\data\new_account.png", img)
print("captured", img.shape, "mean", round(float(img.mean()), 1))
