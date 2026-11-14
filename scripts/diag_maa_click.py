"""诊断：用 MAA 自带输入（Seize/LegacyEvent）点击，验证 MAA 的坐标换算是否准。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
MAA = Path(r"D:\Games\MaaGakumasu")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(MAA / "python" / "Lib" / "site-packages"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from gkagent.device.win32 import find_game_hwnd  # noqa: E402

os.chdir(MAA)

from maa.controller import Win32Controller  # noqa: E402
from maa.define import MaaWin32InputMethodEnum as IN  # noqa: E402
from maa.define import MaaWin32ScreencapMethodEnum as SC  # noqa: E402

X = int(sys.argv[1]) if len(sys.argv) > 1 else 360
Y = int(sys.argv[2]) if len(sys.argv) > 2 else 1098


def main() -> None:
    hwnd = find_game_hwnd()
    print(f"hwnd={hwnd} click=({X},{Y})")
    for method in ("Seize", "LegacyEvent", "PostMessage"):
        try:
            ctrl = Win32Controller(hwnd, SC.FramePool, getattr(IN, method), getattr(IN, method))
            ctrl.post_connection().wait()
            before = np.asarray(ctrl.post_screencap().wait().get())
            ctrl.post_click(X, Y).wait()
            time.sleep(1.2)
            after = np.asarray(ctrl.post_screencap().wait().get())
            diff = float(np.mean(cv2.absdiff(before, after)))
            print(f"{method}: diff={diff:.2f} before={before.shape} after={after.shape}")
            cv2.imwrite(str(ROOT / "data" / f"maa_{method}_after.png"), after)
            if diff > 5:
                print(f"CHANGED with {method}")
                break
        except Exception as exc:  # noqa: BLE001
            print(f"{method}: ERROR {exc!r}")


if __name__ == "__main__":
    main()
