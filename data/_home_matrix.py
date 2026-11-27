"""主页点击约定实验：标题页敲一下回主页，然后分别用「设计坐标」和「客户区坐标」点プロデュース。
用法: python data/_home_matrix.py
"""
import os
import sys
import time

ROOT = r"D:\Games\gakumas-agent"
MAA = r"D:\Games\MaaGakumasu"
sys.path.insert(0, os.path.join(ROOT, "src"))
import cv2

sys.path.append(os.path.join(MAA, "python", "Lib", "site-packages"))
os.chdir(MAA)

from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum as IN
from maa.define import MaaWin32ScreencapMethodEnum as SC

from gkagent.device.win32 import find_game_hwnd

hwnd = find_game_hwnd()
print("hwnd", hwnd)
ctrl = Win32Controller(hwnd, SC.FramePool, IN.SendMessageWithCursorPos, IN.SendMessageWithCursorPos)
ctrl.post_connection().wait()


def shot(tag):
    img = ctrl.post_screencap().wait().get()
    cv2.imwrite(rf"{ROOT}\data\_home_{tag}.png", img)
    print(tag, "mean", round(float(img.mean()), 1), "shape", img.shape)
    return img


def click(x, y, tag):
    before = ctrl.post_screencap().wait().get()
    ctrl.post_click(x, y).wait()
    time.sleep(2.0)
    after = ctrl.post_screencap().wait().get()
    diff = float(cv2.absdiff(before, after).mean())
    cv2.imwrite(rf"{ROOT}\data\_home_{tag}_after.png", after)
    print(f"{tag}: click=({x},{y}) before={before.mean():.1f} after={after.mean():.1f} diff={diff:.2f} changed={diff > 2.0}")
    return diff > 2.0


cur = shot("s0")
# 标题页：任意点击进入主页（SendMessageWithCursorPos 用在标题页应该是有效的）
ctrl.post_click(360, 1055).wait()
time.sleep(12)
home = shot("s1")
print("假设 s1 是主页（mean 应接近 172）")

# 实验 1：设计坐标 720x1280
ok_design = click(359, 1006, "design")
if ok_design:
    print("RESULT: design 坐标生效 -> MAA post_click 期望 720x1280 坐标（不应预缩放）")
    raise SystemExit(0)

# 实验 2：客户区坐标（预缩放 0.75）
ok_client = click(269, 754, "client")
if ok_client:
    print("RESULT: client 坐标生效 -> MAA 期望客户区像素（当前预缩放正确）")
else:
    print("RESULT: 两种坐标都不生效 -> 主页确实不吃 SendMessageWithCursorPos")
