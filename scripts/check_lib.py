"""检查卡库在当前环境能否按卡名查到牌。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from gkagent.data.cards_db import CardLibrary

    lib = CardLibrary()
    print("count", len(lib))
    for name in ("表现的基础", "视觉的基础", "魅力的基础", "今天也早些", "聊天时间"):
        print(name, "->", lib.find(name))


if __name__ == "__main__":
    main()
