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
EFFECTS = ROOT / "data" / "cache" / "ProduceExamEffect.yaml"
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
    "produceExamEffectId",
    "effectType",
    "effectCount",
    "effectTurn",
    "chainProduceExamEffectId",
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
        if line.strip() == "playEffects:":
            current["_section"] = "playEffects"
            desc = None
            continue
        if line.startswith("  - produceDescriptionType:"):
            desc = {"produceDescriptionType": line.split(": ", 1)[1]}
            current["descriptions"].append(desc)
            continue
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, _, value = stripped.partition(": ")
        if current.get("_section") == "playEffects" and line.startswith("    ") and key == "produceExamEffectId":
            if value:
                current.setdefault("playEffectIds", []).append(value)
            continue
        if line.startswith("    ") and desc is not None:
            if key in ("examEffectType", "effectValue1", "effectValue2", "turn", "text", "targetId"):
                desc[key] = value
        elif line.startswith("  ") and key in _SCALARS:
            current[key] = value
            desc = None
    if current is not None:
        entries.append(current)
    return entries


def parse_effects_yaml(path: Path) -> dict[str, dict]:
    """e_effect-xxx -> {type, v1, v2, turn, chain}（29MB，行解析）。"""
    table: dict[str, dict] = {}
    current: dict | None = None
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            current = {"id": line[6:].strip()}
            table[current["id"]] = current
            continue
        # 只读 2 空格缩进的顶层字段；4 空格缩进的 produceDescriptions
        # 里也有 effectValue1（卡面展示值，常为 0），会覆盖真实数值。
        if current is None or not line.startswith("  ") or line.startswith("    "):
            continue
        key, _, value = line.strip().partition(": ")
        if key in ("effectType", "effectValue1", "effectValue2", "effectTurn", "chainProduceExamEffectId"):
            current[key] = value
    return table


def resolve_effects(effect_ids: list[str], effects: dict[str, dict], depth: int = 2) -> list[dict]:
    out: list[dict] = []
    for effect_id in effect_ids:
        seen = set()
        while effect_id and effect_id not in seen and depth > 0:
            seen.add(effect_id)
            row = effects.get(effect_id)
            if row is None:
                break
            effect_type = str(row.get("effectType") or "").replace("ProduceExamEffectType_", "")
            if effect_type and not effect_type.endswith("Unknown"):
                out.append(
                    {
                        "type": effect_type,
                        "v1": int(row.get("effectValue1") or 0),
                        "v2": int(row.get("effectValue2") or 0),
                        "turn": int(row.get("effectTurn") or 0),
                    }
                )
            effect_id = str(row.get("chainProduceExamEffectId") or "")
    return out


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
    effect_table = parse_effects_yaml(EFFECTS) if EFFECTS.exists() else {}
    print(f"效果表: {len(effect_table)} 条")

    master = json.loads(MASTER.read_text(encoding="utf-8"))
    by_key = {(row["id"], int(row.get("upgrade") or 0)): row for row in master}
    print(f"master 条目: {len(master)}")

    table: dict[str, dict] = {}
    # 日文卡名（YAML name，含 + 后缀）→ 中文卡名。游戏汉化 overlay 滞后时新卡
    # （尤其新偶像卡）会显示日文，OCR 读日文名；查表走别名才能命中（F#48）。
    ja_aliases: dict[str, str] = {}
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
        ja = str(entry.get("name") or "").strip()
        if ja and ja != name:
            ja_aliases.setdefault(ja, name)
        effects = compact_effects(entry)
        resolved = resolve_effects(entry.get("playEffectIds") or [], effect_table)
        if resolved:
            effects = [{"type": item["type"], "values": [v for v in (item["v1"], item["v2"]) if v], "turn": item["turn"]} for item in resolved]
        # 有些卡（祝福+：stamina=0 / forceStamina=4）的体力费用只写在 forceStamina，
        # 只读 stamina 会把它们变成 0 费高分卡；两者都存在时取较大值。
        stamina = int(entry.get("stamina") or 0)
        force_stamina = int(entry.get("forceStamina") or 0)
        table[name] = {
            "id": key[0],
            "upgrade": key[1],
            "cost": max(stamina, force_stamina),
            "rarity": (entry.get("rarity") or "").replace("ProduceCardRarity_", ""),
            "plan": (entry.get("planType") or "").replace("ProducePlanType_", ""),
            "category": (entry.get("category") or "").replace("ProduceCardCategory_", ""),
            "effects": effects,
        }
    print(f"匹配到中文卡名: {matched} / 写入 {len(table)} 条 / 日文别名 {len(ja_aliases)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "source": "vertesan/gakumasu-diff ProduceCard.yaml",
                "count": len(table),
                "cards": table,
                "ja_aliases": ja_aliases,
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
