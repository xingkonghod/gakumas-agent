"""读取支援卡网格上的等级（Lv N），输出每个格子的位置和等级。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

GRID = [
    (140, 522),
    (390, 522),
    (615, 522),
    (140, 700),
    (390, 700),
    (615, 700),
    (140, 880),
    (390, 880),
    (615, 880),
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from gkagent.agent import Agent
    from gkagent.device.win32 import Win32Device, find_game_hwnd
    from gkagent.nav import Navigator
    from gkagent.vision.matcher import TemplateMatcher
    from gkagent.vision.ocr import OcrEngine

    hwnd = find_game_hwnd()
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    engine = OcrEngine()
    nav = Navigator(agent, engine)
    nav.ensure_home()
    if not nav.support_screen():
        print("no support screen")
        return
    image = agent.shot()
    lines = engine.read(image)
    levels = []
    for line in lines:
        match = re.search(r"Lv\.?\s*(\d{1,3})", line.text)
        if match:
            levels.append((int(match.group(1)), line.box))
    levels.sort(key=lambda item: (item[1][1], item[1][0]))
    print("levels:", [(value, box) for value, box in levels][:20])


if __name__ == "__main__":
    main()
