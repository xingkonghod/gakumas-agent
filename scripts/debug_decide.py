"""用当前截图跑一次 ProduceDriver.decide，打印判定结果（离线，不点游戏）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


class FakeDevice:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> bool:
        self.clicks.append((x, y))
        return True

    def click_force(self, x: int, y: int) -> bool:
        self.clicks.append((x, y))
        return True


class FakeAgent:
    def __init__(self) -> None:
        self.device = FakeDevice()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import cv2
    from gkagent.tasks.produce_ui import ProduceDriver
    from gkagent.vision.ocr import OcrEngine

    image_path = sys.argv[1] if len(sys.argv) > 1 else "data/cur12.png"
    image = cv2.imread(image_path)
    driver = ProduceDriver(ocr=OcrEngine(), sleep=lambda _s: None)
    lines = driver.read(image)
    text = driver.text_of(lines)
    print("TEXT:", text[:400])
    agent = FakeAgent()
    result = driver.decide(agent, lines, image)
    print("RESULT:", result.screen, result.action, result.detail)
    print("CLICKS:", agent.device.clicks)


if __name__ == "__main__":
    main()
