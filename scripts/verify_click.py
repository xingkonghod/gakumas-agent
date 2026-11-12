"""验证点击方式：点一次游戏菜单，检查画面变化、光标是否还原、前台是否被抢。"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from gkagent.device.win32 import USER32, Win32Device, find_game_hwnd  # noqa: E402


def cursor() -> tuple[int, int]:
    point = wintypes.POINT()
    USER32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def main() -> None:
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 653
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 1244
    hwnd = find_game_hwnd()
    device = Win32Device(hwnd).connect()
    before = device.capture()
    cur0, fg0 = cursor(), USER32.GetForegroundWindow()
    clicked = device.click(x, y, respect_user=False)
    time.sleep(1.2)
    after = device.capture()
    cur1, fg1 = cursor(), USER32.GetForegroundWindow()
    diff = float(np.mean(cv2.absdiff(before.astype(float), after.astype(float))))
    cv2.imwrite(str(ROOT / "data" / "verify_after.png"), after)
    print(f"clicked={clicked} diff={diff:.2f}")
    print(f"cursor={cur0}->{cur1} restored={cur0 == cur1} fg_changed={fg0 != fg1}")
    print("RESULT: " + ("OK" if clicked and diff > 3 else "NO CHANGE"))


if __name__ == "__main__":
    main()
