"""把本地 masterTrans 数据整理成训练用数据集。

来源：D:\\Games\\Gakumas\\gakumas\\gakumas-local\\local-files\\masterTrans
输出：D:\\Games\\gakumas-agent\\data\\master\\*.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SRC = Path(r"D:\Games\Gakumas\gakumas\gakumas-local\local-files\masterTrans")
OUT = Path(r"D:\Games\gakumas-agent\data\master")


def load(name: str) -> list[dict]:
    with (SRC / name).open(encoding="utf-8") as f:
        return json.load(f).get("data", [])


def texts(item: dict, key: str = "produceDescriptions") -> str:
    parts: list[str] = []
    for desc in item.get(key, []) or []:
        text = (desc.get("text") or "").strip()
        if text:
            parts.append(text)
    return " / ".join(parts)


def tags(item: dict, key: str = "produceDescriptions") -> list[str]:
    found: set[str] = set()
    for desc in item.get(key, []) or []:
        for field in ("produceCardCategory", "examEffectType", "produceDescriptionType"):
            value = desc.get(field)
            if value and not value.endswith("_Unknown"):
                found.add(value)
    return sorted(found)


def export(name: str, rows: list[dict], key: str = "produceDescriptions") -> None:
    out = []
    for row in rows:
        out.append(
            {
                "id": row.get("id", ""),
                "name": row.get("name", ""),
                "upgrade": row.get("upgradeCount", row.get("level")),
                "text": texts(row, key),
                "tags": tags(row, key),
            }
        )
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{name}: {len(out)} -> {path}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    export("produce_cards", load("ProduceCard.json"))
    export("support_cards", load("SupportCard.json"), "upgradeProduceCardProduceDescriptions")
    export("events", load("ProduceStepEventDetail.json"))
    export("event_suggestions", load("ProduceStepEventSuggestion.json"))
    export("items", load("ProduceItem.json"))
    export("drinks", load("ProduceDrink.json"))
    export("skills", load("ProduceSkill.json"))
    export("idol_cards", load("IdolCard.json"))
    export("card_search", load("ProduceCardSearch.json"))

    counts = {p.stem: len(json.loads(p.read_text(encoding="utf-8"))) for p in OUT.glob("*.json")}
    (OUT / "index.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    print("counts:", counts)


if __name__ == "__main__":
    main()
