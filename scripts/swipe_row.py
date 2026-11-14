import os
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from gkagent.device.win32 import Win32Device, find_game_hwnd

OUT = r"D:\Games\gakumas-agent\data"
os.makedirs(OUT, exist_ok=True)

hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("game window not found")
device = Win32Device(hwnd).connect()

img = device.capture()
cv2.imwrite(os.path.join(OUT, "row_before.png"), img)

for i in range(2):
    device.swipe(650, 960, 100, 960, 500)
    time.sleep(1.2)
    img = device.capture()
    cv2.imwrite(os.path.join(OUT, f"row_after{i}.png"), img)

print("saved row_before/row_after0/row_after1")
