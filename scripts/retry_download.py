import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

from gkagent.device.win32 import Win32Device, find_game_hwnd
from gkagent.vision.matcher import TemplateMatcher

matcher = TemplateMatcher(r"D:\Games\gakumas-agent\templates")
hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("game window not found")
device = Win32Device(hwnd).connect()

for i in range(40):
    image = device.capture()
    match = matcher.find("produce_retry", image, threshold=0.8)
    if match is None:
        print("no retry dialog; stop at", i)
        break
    device.click(*match.center)
    print("retry", i)
    time.sleep(8)
