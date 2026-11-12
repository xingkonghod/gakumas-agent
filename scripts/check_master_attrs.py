"""检查 MasterData 里有哪些库、支援卡能否被匹配。"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from gkagent.data.master import MasterData  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    master = MasterData()
    attrs = [a for a in dir(master) if not a.startswith("_") and not a.startswith("load")]
    print("attrs:", attrs)
    for name in ("support_cards", "produce_cards", "idol_cards", "items", "drinks"):
        entries = getattr(master, name, None)
        count = len(entries) if entries is not None else 0
        sample = ""
        if entries:
            first = entries[0]
            sample = getattr(first, "name", str(first))[:30]
        print(f"{name}: type={type(entries).__name__} count={count} sample={sample}")


if __name__ == "__main__":
    main()
