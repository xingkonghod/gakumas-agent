"""逐步打印支援卡强化流程，定位循环中断点。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from gkagent.agent import Agent
    from gkagent.device.win32 import Win32Device, find_game_hwnd
    from gkagent.nav import Navigator
    from gkagent.vision.matcher import TemplateMatcher
    from gkagent.vision.ocr import OcrEngine

    hwnd = find_game_hwnd()
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    nav = Navigator(agent, OcrEngine())

    def text() -> str:
        return " | ".join(line.text for line in nav.lines())[:250]

    nav.ensure_home()
    agent.device.click(198, 1158)
    time.sleep(1.5)
    agent.device.click(368, 930)
    time.sleep(2.0)
    print("grid:", text())
    agent.device.click(140, 522)
    time.sleep(2.0)
    print("detail:", text())
    nav.click_exact("Lv强化")
    time.sleep(1.5)
    print("confirm:", text())
    nav.click_exact("Lv强化")
    time.sleep(2.0)
    print("after confirm:", text())
    for index in range(3):
        agent.device.click(283, 1192)
        time.sleep(1.2)
        print(f"after back {index + 1}:", text())
    nav.ensure_home()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
