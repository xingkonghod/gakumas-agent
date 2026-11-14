"""从主页走「初星课题 → 挑战任务 → 挑战」开始一局指定课题的培育。

流程（实拍确认）：
主页 → 课题横幅(280,845) → 挑战任务(360,1099) → 弹窗「挑战」(493,1144)
→ 培育开始确认「继续」(493,1145) → 进入培育
"""

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
    if not hwnd:
        print("no game window", file=sys.stderr)
        return 2
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    engine = OcrEngine()
    nav = Navigator(agent, engine)
    nav.ensure_home()

    def text() -> str:
        return " ".join(line.text for line in nav.lines())

    # 1) 主页点课题横幅
    agent.device.click(280, 845)
    time.sleep(2.5)
    current = text()
    print("after banner:", current[:120])
    if "挑战任务" in current:
        agent.device.click(360, 1099)
        time.sleep(2.0)
        current = text()
        print("after 挑战任务:", current[:120])
    if "挑战" in current and "取消" in current:
        agent.device.click(493, 1144)
        time.sleep(2.5)
        current = text()
        print("after 挑战:", current[:120])
    if "继续" in current:
        agent.device.click(493, 1145)
        time.sleep(3.0)
        current = text()
        print("after 继续:", current[:120])
    print("final:", text()[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
