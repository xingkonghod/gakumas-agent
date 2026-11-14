import os
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

OUT = r"D:\Games\gakumas-agent\data"
game = 526880

ctrl = Win32Controller(game, SC.FramePool, IN.SendMessageWithCursorPos, IN.SendMessageWithCursorPos)
ctrl.post_connection().wait()

for i in range(6):
    img = ctrl.post_screencap().wait().get()
    cv2.imwrite(os.path.join(OUT, f"tut_{i}.png"), img)
    b, g, r = (int(v) for v in img[1105, 360])
    yellow = r > 180 and g > 150 and b < 140
    print(f"frame {i} pixel=({b},{g},{r}) yellow={yellow}")
    if not yellow:
        print("stop: bottom button not the yellow 下一步")
        break
    ctrl.post_click(360, 1105).wait()
    time.sleep(2.2)
