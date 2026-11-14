"""离线诊断：培育出牌/主界面识别（手牌、阶段）。"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

from gkagent.vision.cards import scan_hand  # noqa: E402


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "new_account.png"
    image = cv2.imread(str(path))
    print(f"image {path.name}: {image.shape[1]}x{image.shape[0]} mean={image.mean():.1f}")
    scan = scan_hand(image)
    print(f"cards={len(scan.cards)}")
    for card in scan.cards:
        print(f"  {card.card_id} box={card.box} cost={card.cost} kind={card.kind} conf={card.confidence:.2f}")

    from gkagent.agent import Agent
    from gkagent.device.win32 import Win32Device, find_game_hwnd
    from gkagent.vision.matcher import TemplateMatcher

    hwnd = find_game_hwnd()
    device = Win32Device(hwnd).connect()
    agent = Agent(device, TemplateMatcher(ROOT / "templates"))
    from gkagent.tasks.produce import ProduceTask

    task = ProduceTask()
    screen = task.observe(agent, image)
    print(f"stage={screen.stage}")
    for name in ("home", "produce_entry", "ssr_title", "recommend", "event", "event_recommend", "scenario",
                 "main_page", "health", "skip_round", "decide", "close", "next_step", "start", "continue_"):
        value = getattr(screen, name)
        if value is not None:
            print(f"  {name}: score={value.score:.3f} center={value.center}")


if __name__ == "__main__":
    main()
