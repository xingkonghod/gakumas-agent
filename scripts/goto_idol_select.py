"""把游戏导航到培育「选择偶像」界面，并打印该屏的 OCR 文本（含坐标）。

用途：初星课题要求"方案：感性"，需要人工/脚本确认哪个偶像是感性再点。

用法（经 daemon 以管理员运行）：
    python scripts/goto_idol_select.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

from gkagent.device.win32 import Win32Device, find_game_hwnd  # noqa: E402
from gkagent.vision.ocr import OcrEngine  # noqa: E402

HOME_MARKERS = ("亲密度", "活动经费", "商店", "扭蛋", "主页")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window")
        return 2
    device = Win32Device(hwnd).connect()
    engine = OcrEngine()

    for step in range(1, 9):
        image = device.capture()
        lines = engine.read(image)
        text = " ".join(line.text for line in lines)
        print(f"--- step {step}: {text[:160]}")
        if "选择偶像" in text:
            print("== 到达选择偶像界面 ==")
            for line in lines:
                if line.text.strip():
                    print(f"   {tuple(line.box)} {line.text}")
            return 0
        if "定期公演" in text:
            device.click_force(360, 900)  # レギュラー
            time.sleep(1.6)
            continue
        if "开始确认" in text or "选择支援卡" in text:
            print("!! 已经越过选择偶像界面")
            return 3
        if "培育" in text and "研修" in text:
            device.click_force(360, 1000)
            time.sleep(1.6)
            continue
        if any(word in text for word in HOME_MARKERS):
            device.click_force(360, 1048)  # プロデュース
            time.sleep(2.0)
            continue
        # 其它界面（弹窗/剧情/主界面）：点中央推进
        device.click_force(360, 1000)
        time.sleep(1.2)
    print("没走到选择偶像界面")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
