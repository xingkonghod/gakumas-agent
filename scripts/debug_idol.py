"""逐步打印偶像特训流程的 OCR 文本，用来定位 guard 失败点。"""

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
    from gkagent.vision.ocr import OcrEngine
    from gkagent.vision.matcher import TemplateMatcher

    hwnd = find_game_hwnd()
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    nav = Navigator(agent, OcrEngine())

    def text() -> str:
        return " | ".join(line.text for line in nav.lines())

    print("home ok:", nav.ensure_home())
    print("menu:", nav.idol_menu())
    print("text after menu:", text()[:300])
    print("click 培养:", nav._click_idol_entry())
    time.sleep(1.5)
    print("after 培养:", text()[:300])
    agent.device.click(180, 792)
    time.sleep(2.0)
    print("after 特训:", text()[:300])
    agent.device.click(526, 1212)
    time.sleep(2.0)
    print("after 进行特训:", text()[:300])
    # 取消弹窗，不消耗
    nav.click_text("取消")
    time.sleep(1.0)
    nav.ensure_home()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
