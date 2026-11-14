"""在 DMM Game Player 的 app.asar 里找 dmmgameplayer:// 协议用法。"""

from __future__ import annotations

import io
import sys

PATH = r"D:\DMM\GamePlayer\resources\app.asar"
PATTERN = b"dmmgameplayer://"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    data = io.open(PATH, "rb").read()
    index = 0
    count = 0
    while True:
        index = data.find(PATTERN, index)
        if index < 0:
            break
        count += 1
        chunk = data[max(0, index - 250) : index + 300]
        print(f"--- {count} @ {index} ---")
        print(chunk.decode("utf-8", "replace"))
        index += 1
    print(f"total={count}")


if __name__ == "__main__":
    main()
