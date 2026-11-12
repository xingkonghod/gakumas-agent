"""查看 masterTrans 的数据行（只读采样）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DIR = Path(r"D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans")


def peek(name: str, count: int = 2) -> None:
    data = json.loads((DIR / name).read_text(encoding="utf-8"))
    rows = data.get("data") if isinstance(data, dict) else data
    print(f"=== {name}: rows={len(rows)}")
    for row in rows[:count]:
        text = json.dumps(row, ensure_ascii=False)
        print(text[:900])
        print("---")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for name in ("ProduceStepLesson.json", "ProduceDrink.json", "Produce.json"):
        peek(name)


if __name__ == "__main__":
    main()
