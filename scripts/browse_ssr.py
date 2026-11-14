import os
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from gkagent.device.win32 import Win32Device, find_game_hwnd

OUT = r"D:\Games\gakumas-agent\data\ssr"
os.makedirs(OUT, exist_ok=True)

hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("game window not found")
device = Win32Device(hwnd).connect()

for i in range(18):
    img = device.capture()
    cv2.imwrite(os.path.join(OUT, f"ssr_{i:02d}.png"), img)
    device.swipe(650, 960, 120, 960, 400)
    time.sleep(0.9)

print("saved 18 frames")
