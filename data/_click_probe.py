"""点击路径探针：复刻 auto_produce 的设备+暂停门，比较两条点击路径。
用法: python data/_click_probe.py <mode> <x> <y> <tag>
  mode=plain  纯 device.click_force
  mode=guard  PauseGate + SelfInputClickGuard（和 auto_produce 一样）
"""
import sys

sys.path.insert(0, r"D:\Games\gakumas-agent\src")
sys.path.insert(0, r"D:\Games\gakumas-agent\scripts")

import cv2

from gkagent.device.win32 import Win32Device, find_game_hwnd

mode = sys.argv[1]
x, y = int(sys.argv[2]), int(sys.argv[3])
tag = sys.argv[4]

hwnd = find_game_hwnd()
print("hwnd", hwnd)
dev = Win32Device(hwnd).connect()
before = dev.capture()
cv2.imwrite(rf"D:\Games\gakumas-agent\data\_probe_{tag}_before.png", before)
print("before mean", round(float(before.mean()), 1))

if mode == "plain":
    r = dev.click_force(x, y)
elif mode == "raw":
    dev.click_raw(x, y)
    r = True
else:
    from auto_produce import PauseGate, SelfInputClickGuard

    gate = PauseGate()
    guard = SelfInputClickGuard(dev, gate).install()
    digest = str(hash(before[::17, ::17].tobytes()))
    force_continue = gate.observe(digest)
    guard.force = force_continue
    print("force_continue", force_continue, "user_operating", gate.user_operating())
    r = dev.click_force(x, y)
print("click result", r)
import time

time.sleep(1.5)
after = dev.capture()
cv2.imwrite(rf"D:\Games\gakumas-agent\data\_probe_{tag}_after.png", after)
print("after mean", round(float(after.mean()), 1))
diff = float(cv2.absdiff(before, after).mean())
print("diff", round(diff, 2), "changed", diff > 2.0)
