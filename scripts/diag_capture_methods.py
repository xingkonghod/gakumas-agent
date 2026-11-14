"""诊断：在当前窗口状态下逐个尝试 MAA 截屏方式，找出能用的那一种。"""

from __future__ import annotations

import ctypes
import os
import sys
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
from maa.define import MaaWin32InputMethodEnum as InputMethod  # noqa: E402
from maa.define import MaaWin32ScreencapMethodEnum as ScreencapMethod  # noqa: E402


def main() -> None:
    hwnd = find_game_hwnd()
    if not hwnd:
        raise SystemExit("no game window")
    print(f"hwnd={hwnd} iconic={USER32.IsIconic(hwnd)} fg={USER32.GetForegroundWindow()}")

    for name in ("FramePool", "DXGI_DesktopDup_Window", "PrintWindow", "GDI", "ScreenDC", "Background", "Foreground"):
        try:
            ctrl = Win32Controller(hwnd, getattr(ScreencapMethod, name), InputMethod.PostMessage, InputMethod.PostMessage)
            ctrl.post_connection().wait()
            img = ctrl.post_screencap().wait().get()
            arr = np.asarray(img)
            print(f"{name:22s} shape={arr.shape} mean={arr.mean():.1f} min={arr.min()} max={arr.max()}")
            cv2.imwrite(str(ROOT / "data" / f"cap_{name}.png"), arr)
        except Exception as exc:  # noqa: BLE001
            print(f"{name:22s} FAILED {exc!r}")


if __name__ == "__main__":
    main()
