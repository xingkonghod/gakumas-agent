"""1 分钟干净测试：只用 PostMessage（不碰系统鼠标）点 SKIP，验证后台点击是否生效。

流程：
1. 等用户空闲 >= 4s
2. 截 A → PostMessage 点 SKIP(208,1204) → 截 B（应出现「跳过确认」弹窗）
3. PostMessage 点 取消(175,1163) → 截 C（弹窗消失）
输出两次 diff、光标/前台是否被我们改动、点击时用户空闲毫秒数。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
MAA = Path(r"D:\Games\MaaGakumasu")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(MAA / "python" / "Lib" / "site-packages"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from gkagent.device.win32 import USER32, find_game_hwnd  # noqa: E402

os.chdir(MAA)

from maa.controller import Win32Controller  # noqa: E402
from maa.define import MaaWin32InputMethodEnum as IN  # noqa: E402
from maa.define import MaaWin32ScreencapMethodEnum as SC  # noqa: E402


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_ms() -> int:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    USER32.GetLastInputInfo(ctypes.byref(info))
    return (ctypes.windll.kernel32.GetTickCount() - int(info.dwTime)) & 0xFFFFFFFF


def cursor() -> tuple[int, int]:
    point = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(cv2.absdiff(a, b)))


def main() -> None:
    hwnd = find_game_hwnd()
    ctrl = Win32Controller(hwnd, SC.FramePool, IN.PostMessage, IN.PostMessage)
    ctrl.post_connection().wait()
    deadline = time.time() + 20
    while time.time() < deadline and idle_ms() < 4000:
        time.sleep(0.2)
    start_idle = idle_ms()
    cur0, fg0 = cursor(), USER32.GetForegroundWindow()

    def shot() -> np.ndarray:
        return np.asarray(ctrl.post_screencap().wait().get())

    a = shot()
    idle1 = idle_ms()
    ctrl.post_click(208, 1204).wait()
    time.sleep(1.2)
    b = shot()
    d1 = diff(a, b)

    idle2 = idle_ms()
    ctrl.post_click(175, 1163).wait()
    time.sleep(1.2)
    c = shot()
    d2 = diff(b, c)

    cur1, fg1 = cursor(), USER32.GetForegroundWindow()
    cv2.imwrite(str(ROOT / "data" / "clean_a.png"), a)
    cv2.imwrite(str(ROOT / "data" / "clean_b.png"), b)
    cv2.imwrite(str(ROOT / "data" / "clean_c.png"), c)
    print(f"idle_at_start={start_idle}ms idle_click1={idle1}ms idle_click2={idle2}ms")
    print(f"diff_open={d1:.2f} diff_close={d2:.2f}")
    print(f"cursor={cur0}->{cur1} (moved_by_us={cur0 != cur1}) fg_changed={fg0 != fg1}")
    ok = d1 > 5 and d2 > 5
    print("RESULT: " + ("BACKGROUND CLICK WORKS" if ok else "NOT CONCLUSIVE"))


if __name__ == "__main__":
    main()
