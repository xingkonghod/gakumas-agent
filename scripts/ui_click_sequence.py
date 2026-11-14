import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

from gkagent.device.win32 import Win32Device, find_game_hwnd

POINTS = [(620, 1200), (380, 930)]

hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("no game window")
device = Win32Device(hwnd).connect()
for x, y in POINTS:
    device.click_force(x, y)
    time.sleep(1.5)
print("clicked", POINTS)
