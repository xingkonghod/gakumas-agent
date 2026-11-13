"""离线验证：手牌 OCR 卡名 → 卡库估值选牌。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import cv2
    from gkagent.data.cards_db import CardLibrary
    from gkagent.tasks.produce_ui import ProduceDriver
    from gkagent.vision.cards import scan_hand
    from gkagent.vision.hand_names import pick_hand_card
    from gkagent.vision.ocr import OcrEngine

    image_path = sys.argv[1] if len(sys.argv) > 1 else "data/auto/step_120.png"
    image = cv2.imread(image_path)
    driver = ProduceDriver(ocr=OcrEngine(), sleep=lambda _s: None)
    lines = driver.read(image)
    print("TEXT:", driver.text_of(lines)[:300])
    hand = scan_hand(image)
    print("HAND boxes:", [tuple(card.box) for card in hand.cards], "costs:", [c.cost for c in hand.cards])
    library = CardLibrary()
    pick = pick_hand_card(lines, [tuple(c.box) for c in hand.cards], library, costs=[c.cost for c in hand.cards])
    print("PICK:", pick)


if __name__ == "__main__":
    main()
