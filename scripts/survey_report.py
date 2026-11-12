"""读取 data/survey.json，打印支援卡清单与训练建议。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = json.loads((ROOT / "data" / "survey.json").read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    print(f"cards={len(cards)}")
    for index, item in enumerate(data.get("ranking", []), 1):
        card = item["card"]
        text = card.get("text", "")
        # 从文本里抽「生概率N%增加」「能力值加成+X%」等关键词
        highlights = [part for part in card.get("effects", []) if any(k in part for k in ("SP", "加成", "+"))]
        rarity = card.get("rarity")
        level = card.get("level")
        pos = card.get("pos")
        print(f"{index}. {rarity} Lv{level} pos={pos} score={item['score']:.1f}")
        print("   effects:", " / ".join(highlights[:6]))
        print("   snippet:", text[:120].replace("\n", " "))


if __name__ == "__main__":
    main()
