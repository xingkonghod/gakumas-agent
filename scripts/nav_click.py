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
pairs = []
for arg in sys.argv[1:]:
    x, y = arg.split(",")
    pairs.append((int(x), int(y)))

for i, (x, y) in enumerate(pairs):
    device.click(x, y)
    time.sleep(1.2)
    img = device.capture()
    path = os.path.join(OUT, f"nav_{i}.png")
    cv2.imwrite(path, img)
    print(f"clicked {x},{y} -> {path} {img.shape}")
