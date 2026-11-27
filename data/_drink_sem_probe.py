"""drink-keep 语义探针（可逆单击）：点手持首行勾选框，观察徽标/勾选态变化。不提交。"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkagent.device.win32 import Win32Device, find_game_hwnd  # noqa: E402
from gkagent.vision.ocr import OcrEngine  # noqa: E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402


def grab(dev):
    img = dev.capture()
    return img


def badge(img):
    eng = OcrEngine()
    lines = eng.read(img)
    txt = " | ".join(l.text for l in lines)
    return txt


def main():
    hwnd = find_game_hwnd()
    dev = Win32Device(hwnd).connect()
    before = grab(dev)
    cv2.imwrite(str(ROOT / "data" / "_drink_before.png"), before)
    print("BEFORE:", badge(before)[:400])
    pt = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (632, 870)
    dev.click_force(*pt)  # 可逆：再点一次恢复
    time.sleep(1.0)
    after = grab(dev)
    cv2.imwrite(str(ROOT / "data" / "_drink_after.png"), after)
    print("AFTER :", badge(after)[:400])
    print("changed:", not np.array_equal(before, after))


if __name__ == "__main__":
    main()