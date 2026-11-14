"""把 gakumasu-diff 的 ProduceCard.yaml（和游戏 master 同一套 ID）转成卡牌属性表。

产出 ``data/knowledge/card_table.json``：中文卡名 → 体力费用 / 稀有度 / 方案 / 效果类型。
有了它，出牌时**不再靠 OCR 猜费用**（卡面爱心小字难认、确认帧预览会错位）。

用法：python scripts/build_card_table.py [--yaml path]
数据来源：https://github.com/vertesan/gakumasu-diff （main/ProduceCard.yaml）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
YAML = ROOT / "data" / "cache" / "ProduceCard.yaml"
MASTER = ROOT / "data" / "master" / "produce_cards.json"
OUT = ROOT / "data" / "knowledge" / "card_table.json"

_SCALARS = {
    "upgradeCount",
    "name",
    "stamina",
    "forceStamina",
    "rarity",
    "planType",
    "category",
    "costType",
    "costValue",
    "searchTag",
}


def parse_yaml(path: Path) -> list[dict]:
    """按行解析（41MB，PyYAML 会吃几个 GB；结构是定死的，行解析足够）。"""
    entries: list[dict] = []
    current: dict | None = None
    desc: dict | None = None
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            if current is not None:
                entries.append(current)
            current = {"id": line[6:].strip(), "descriptions": []}
            desc = None
            continue
        if current is None:
            continue
        if line.startswith("  - produceDescriptionType:"):
            desc = {"produceDescriptionType": line.split(": ", 1)[1]}
            current["descriptions"].append(desc)
            continue
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, _, value = stripped.partition(": ")
        if line.startswith("    ") and desc is not None:
            if key in ("examEffectType", "effectValue1", "effectValue2", "turn", "text", "targetId"):
                desc[key] = value
        elif line.startswith("  ") and key in _SCALARS:
            current[key] = value
            desc = None
    if current is not None:
        entries.append(current)
    return entries


def compact_effects(entry: dict) -> list[dict]:
    effects = []
    for desc in entry.get("descriptions", []):
        effect_type = desc.get("examEffectType", "")
        if not effect_type or effect_type.endswith("_Unknown"):
            continue
        values = [
            int(desc.get(key) or 0)
            for key in ("effectValue1", "effectValue2")
            if str(desc.get(key) or "0") not in ("0", "")
        ]
        effects.append(
            {
                "type": effect_type.replace("ProduceExamEffectType_", ""),
                "values": values,
                "turn": int(desc.get("turn") or 0),
            }
        )
    return effects


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    yaml_path = Path(argv[argv.index("--yaml") + 1]) if "--yaml" in argv else YAML
    if not yaml_path.exists():
        print(f"缺少 {yaml_path}（先下载 ProduceCard.yaml）")
        return 1
    entries = parse_yaml(yaml_path)
    print(f"YAML 条目: {len(entries)}")

    master = json.loads(MASTER.read_text(encoding="utf-8"))
    by_key = {(row["id"], int(row.get("upgrade") or 0)): row for row in master}
    print(f"master 条目: {len(master)}")

    table: dict[str, dict] = {}
    matched = 0
    for entry in entries:
        key = (entry.get("id", ""), int(entry.get("upgradeCount") or 0))
        row = by_key.get(key)
        if row is None:
            continue
        matched += 1
        name = row.get("name") or entry.get("name")
        if not name:
            continue
        effects = compact_effects(entry)
        table[name] = {
            "id": key[0],
            "upgrade": key[1],
            "cost": int(entry.get("stamina") or 0),
            "rarity": (entry.get("rarity") or "").replace("ProduceCardRarity_", ""),
            "plan": (entry.get("planType") or "").replace("ProducePlanType_", ""),
            "category": (entry.get("category") or "").replace("ProduceCardCategory_", ""),
            "effects": effects,
        }
    print(f"匹配到中文卡名: {matched} / 写入 {len(table)} 条")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "source": "vertesan/gakumasu-diff ProduceCard.yaml",
                "count": len(table),
                "cards": table,
            },
            ensure_ascii=False,
            indent=0,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    sample = next(iter(table.items()))
    print("样例:", sample[0], sample[1]["cost"], sample[1]["category"], sample[1]["effects"][:2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
