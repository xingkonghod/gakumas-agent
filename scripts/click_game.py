"""可靠点击 v3：隐藏 DMM Play Assist + Seize 全局输入 + 截图校验 + 偏移重试。

经验：
- GamesPlayAssist.exe（player-assist，Tauri 窗口）会挡住真实鼠标，点之前先隐藏。
- 对话框底部按钮的视觉中心大约在 y=1130~1150，不是 1115。
- SendMessage 在部分弹窗无效，Seize 全局输入最稳。
"""

import ctypes
import os
import sys
import time

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

import cv2
import numpy as np

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

OUT = r"D:\Games\gakumas-agent\data"
GAME = 526880
OVERLAY = 527006
user32 = ctypes.WinDLL("user32", use_last_error=True)


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: click_game.py x y")
    x, y = int(sys.argv[1]), int(sys.argv[2])

    ctrl = Win32Controller(GAME, SC.FramePool, IN.Seize, IN.Seize)
    ctrl.post_connection().wait()

    before = ctrl.post_screencap().wait().get()
    cv2.imwrite(os.path.join(OUT, "click_before.png"), before)

    # 视觉中心附近的候选点：先中心，再上下微调
    candidates = [(x, y), (x, y + 8), (x, y - 8), (x, y + 15)]
    for attempt, (cx, cy) in enumerate(candidates):
        user32.ShowWindow(OVERLAY, 0)
        time.sleep(0.25)
        user32.ShowWindow(GAME, 9)
        user32.SetForegroundWindow(GAME)
        time.sleep(0.25)

        ctrl.post_click(cx, cy).wait()
        time.sleep(1.3)
        after = ctrl.post_screencap().wait().get()
        diff = float(np.mean(cv2.absdiff(before, after)))
        print(f"attempt {attempt} point=({cx},{cy}) diff={diff:.2f}")
        if diff > 0.8:
            cv2.imwrite(os.path.join(OUT, "click_after.png"), after)
            print("click landed")
            return
        before = after

    # 回退：PostMessage
    ctrl2 = Win32Controller(GAME, SC.FramePool, IN.SendMessageWithCursorPos, IN.SendMessageWithCursorPos)
    ctrl2.post_connection().wait()
    ctrl2.post_click(x, y).wait()
    time.sleep(1.3)
    after = ctrl2.post_screencap().wait().get()
    cv2.imwrite(os.path.join(OUT, "click_after.png"), after)
    print("fallback PostMessage done")


if __name__ == "__main__":
    main()
