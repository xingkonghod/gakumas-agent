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

for i in range(180):
    image = device.capture()
    retry = matcher.find("produce_retry", image, threshold=0.8)
    if retry is not None:
        device.click(*retry.center)
        print("retry", i, flush=True)
        time.sleep(10)
        continue
    loading = matcher.find("produce_loading", image, threshold=0.9)
    if loading is not None:
        time.sleep(5)
        continue
    print("no loading/error, stop at", i, flush=True)
    break
