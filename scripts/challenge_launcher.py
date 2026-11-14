"""初星课题挑战启动器：主页 → 课题 → 挑战任务 → 挑战 → 剧本 REGULAR → 按课题要求选方案 → 下一步。

用法：
    python scripts/challenge_launcher.py            # 方案按课题弹窗里的【条件】自动读
    python scripts/challenge_launcher.py 理性       # 强制指定方案

之后用 auto_produce.py 继续打这局（它不会再回主页）。
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

PLAN_POINTS = {"感性": (340, 396), "理性": (339, 483), "非凡": (340, 570)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from gkagent.agent import Agent
    from gkagent.device.win32 import Win32Device, find_game_hwnd
    from gkagent.nav import Navigator
    from gkagent.vision.matcher import TemplateMatcher
    from gkagent.vision.ocr import OcrEngine

    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window", file=sys.stderr)
        return 2
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    engine = OcrEngine()
    nav = Navigator(agent, engine)

    def text() -> str:
        return " ".join(line.text for line in nav.lines())

    nav.ensure_home()
    agent.device.click(280, 845)  # 课题横幅
    time.sleep(2.5)
    current = text()
    print("banner:", current[:100])

    plan = sys.argv[1] if len(sys.argv) > 1 else ""
    match = re.search(r"方案[:：]?\s*(感性|理性|非凡)", current)
    if match:
        plan = match.group(1)
    plan = plan or "理性"
    print("plan:", plan)

    if "挑战任务" in current:
        agent.device.click(360, 1099)
        time.sleep(2.0)
        current = text()
    if "挑战" in current and "取消" in current:
        agent.device.click(493, 1144)
        time.sleep(2.5)
        current = text()
    if "定期公演" in current:
        agent.device.click(360, 915)  # REGULAR
        time.sleep(4.0)
    current = text()
    print("scenario:", current[:100])
    if "方案" in current:
        agent.device.click(338, 735)  # 方案页签
        time.sleep(1.5)
        point = PLAN_POINTS.get(plan, PLAN_POINTS["理性"])
        agent.device.click(*point)
        time.sleep(1.5)
        current = text()
        print("plan selected:", current[:100])
        agent.device.click(339, 1075)  # 下一步
        time.sleep(4.0)
    final = text()
    print("final:", final[:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
