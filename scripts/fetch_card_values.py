"""把卡牌效果的具体数值补进 ``data/knowledge/card_table.json``。

数据实际存放位置（trace 结论）::

    ProduceCard.yaml
      - id / upgradeCount / stamina / playProduceExamTriggerId（使用条件）
      - playEffects[].produceExamEffectId  -> e_effect-...
    ProduceExamEffect.yaml
      - effectType / effectValue1 / effectValue2 / effectCount / effectTurn
      - chainProduceExamEffectId(s)  -> 链上的后续效果
    ProduceExamStatusEnchant.yaml
      - produceExamEffectIds -> 状态附魔展开后的内层效果

注意：ProduceCard.yaml 的 ``produceDescriptions`` 里也有 effectValue1，
但那是卡面展示用的文本片段（还混着大量 0），并非效果本体。上一版解析器
按 2 空格缩进判断字段，结果把 4 空格缩进的描述值覆盖到了效果上，导致
``values`` 全空——本脚本只读 ProduceExamEffect.yaml 顶层字段。

写回的 effects 结构::

    {"type": "ExamLesson", "values": [9], "turn": 0}
    {"type": "ExamLesson", "values": [3], "turn": 0, "count": 2}   # 3 分 x2 次
    {"type": "ExamStatusEnchant", "values": [], "turn": 3,
     "enchant": "...", "inner": [{"type": "ExamLessonBuff", "values": [2], "turn": 0}]}

- ``values``：effectValue1/effectValue2 的非零值（按原顺序）。
- ``count``：effectCount>1（多段/多叠），或 values 为空但 effectCount>0
  （例如「技能卡使用数 +1」）。
- ``inner``：ExamStatusEnchant 展开后的内层效果，外层本身没有数值。
- 卡牌级 ``trigger``：playProduceExamTriggerId，例如聊天时间的
  ``e_trigger-exam_start_turn-parameter_buff``（好调状态才可使用）。

用法::

    .venv\\Scripts\\python.exe scripts/fetch_card_values.py
    .venv\\Scripts\\python.exe scripts/fetch_card_values.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_YAML = ROOT / "data" / "cache" / "ProduceCard.yaml"
EFFECT_YAML = ROOT / "data" / "cache" / "ProduceExamEffect.yaml"
EXAM_ENCHANT_YAML = ROOT / "data" / "cache" / "ProduceExamStatusEnchant.yaml"
TABLE = ROOT / "data" / "knowledge" / "card_table.json"

_EFFECT_FIELDS = {
    "effectType",
    "effectValue1",
    "effectValue2",
    "effectCount",
    "effectTurn",
    "chainProduceExamEffectId",
    "produceExamStatusEnchantId",
    "produceCardStatusEnchantId",
    "targetProduceCardId",
    "targetExamEffectType",
}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _split(line: str) -> tuple[str, str]:
    """``key: value`` -> (key, value)；冒号后的空格可有可无。"""
    stripped = line.strip()
    key, _, value = stripped.partition(":")
    return key.strip(), value.strip()


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1].replace('\\"', '"')
    return text


def _as_int(value: object) -> int:
    try:
        return int(str(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def parse_cards(path: Path) -> list[dict]:
    """行解析 ProduceCard.yaml（41MB，PyYAML 会吃几个 GB）。"""
    entries: list[dict] = []
    current: dict | None = None
    section = ""
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            current = {
                "id": line[6:].strip(),
                "upgrade": 0,
                "stamina": 0,
                "name": "",
                "playProduceExamTriggerId": "",
                "playEffects": [],
                "descriptions": [],
            }
            entries.append(current)
            section = ""
            continue
        if current is None:
            continue
        indent = _indent(line)
        stripped = line.strip()
        if indent == 2 and stripped in ("playEffects:", "produceDescriptions:"):
            section = stripped[:-1]
            continue
        if indent == 2 and not stripped.startswith("- "):
            section = ""
            key, value = _split(stripped)
            if key == "upgradeCount":
                current["upgrade"] = _as_int(value)
            elif key == "stamina":
                current["stamina"] = _as_int(value)
            elif key in ("name", "playProduceExamTriggerId"):
                current[key] = _unquote(value)
            continue
        if section == "playEffects":
            if indent == 2 and stripped.startswith("- "):
                current["playEffects"].append({"trigger": "", "once": False})
                key, value = _split(stripped[2:])
                if key:
                    current["playEffects"][-1][key] = _unquote(value)
            elif indent >= 4 and current["playEffects"]:
                key, value = _split(stripped)
                if key in (
                    "produceExamTriggerId",
                    "produceExamEffectId",
                    "hideIcon",
                    "isOncePlayEffect",
                ):
                    current["playEffects"][-1][key] = _unquote(value)
        elif section == "descriptions":
            if indent == 2 and stripped.startswith("- "):
                current["descriptions"].append({})
                key, value = _split(stripped[2:])
                if key:
                    current["descriptions"][-1][key] = _unquote(value)
            elif indent >= 4 and current["descriptions"]:
                key, value = _split(stripped)
                if key in (
                    "text",
                    "examEffectType",
                    "examDescriptionType",
                    "effectValue1",
                    "effectValue2",
                    "effectCount",
                    "turn",
                    "targetId",
                ):
                    current["descriptions"][-1][key] = _unquote(value)
    return entries


def parse_effects(path: Path) -> dict[str, dict]:
    """e_effect-xxx -> 效果字段（只取 2 空格缩进的顶层字段）。"""
    table: dict[str, dict] = {}
    current: dict | None = None
    section = ""
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            current = {"id": line[6:].strip(), "chains": []}
            table[current["id"]] = current
            section = ""
            continue
        if current is None:
            continue
        indent = _indent(line)
        stripped = line.strip()
        if indent == 2 and not stripped.startswith("- "):
            key, value = _split(stripped)
            if key == "chainProduceExamEffectIds" and not value:
                section = "chains"
            elif key == "produceDescriptions":
                section = "descriptions"
            else:
                section = ""
                if key in _EFFECT_FIELDS:
                    current[key] = _unquote(value)
            continue
        if section == "chains" and indent == 2 and stripped.startswith("- "):
            current["chains"].append(_unquote(stripped[2:]))
    return table


def parse_exam_enchants(path: Path) -> dict[str, dict]:
    """enchant-xxx -> {"effect_ids": [...]}（状态附魔展开后的效果链）。"""
    table: dict[str, dict] = {}
    current: dict | None = None
    section = ""
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            current = {"id": line[6:].strip(), "effect_ids": []}
            table[current["id"]] = current
            section = ""
            continue
        if current is None:
            continue
        indent = _indent(line)
        stripped = line.strip()
        if indent == 2 and not stripped.startswith("- "):
            key, value = _split(stripped)
            if key == "produceExamEffectIds" and not value:
                section = "effect_ids"
            elif key == "produceDescriptions":
                section = "descriptions"
            else:
                section = ""
            continue
        if section == "effect_ids" and indent == 2 and stripped.startswith("- "):
            effect_id = _unquote(stripped[2:])
            if effect_id and effect_id not in current["effect_ids"]:
                current["effect_ids"].append(effect_id)
        elif section == "descriptions" and indent >= 4:
            key, value = _split(stripped)
            if key == "originProduceExamEffectId":
                effect_id = _unquote(value)
                if effect_id and effect_id not in current["effect_ids"]:
                    current["effect_ids"].append(effect_id)
    return table


def resolve_chain(effect_id: str, effects: dict[str, dict]) -> list[dict]:
    """广度优先展开 effect 本体 + chainProduceExamEffectId(s)。"""
    nodes: list[dict] = []
    queue = [effect_id]
    seen: set[str] = set()
    while queue:
        current_id = queue.pop(0)
        if not current_id or current_id in seen:
            continue
        seen.add(current_id)
        row = effects.get(current_id)
        if row is None:
            continue
        nodes.append(row)
        chained = _as_list(row.get("chains"))
        single = str(row.get("chainProduceExamEffectId") or "")
        if single:
            chained.append(single)
        queue.extend(chained)
    return nodes


def _effect_type(row: dict) -> str:
    return str(row.get("effectType") or "").replace("ProduceExamEffectType_", "")


def _values(row: dict) -> list[int]:
    values = [_as_int(row.get("effectValue1")), _as_int(row.get("effectValue2"))]
    return [value for value in values if value]


def _basic_effect(row: dict) -> dict:
    payload: dict = {
        "type": _effect_type(row),
        "values": _values(row),
        "turn": _as_int(row.get("effectTurn")),
    }
    count = _as_int(row.get("effectCount"))
    # count=1 是普通单段效果的默认值；多段，或本身没有 value 的「次数」效果才写。
    if count > 1 or (count > 0 and not payload["values"]):
        payload["count"] = count
    return payload


def build_effects(entry: dict, effects: dict[str, dict], enchants: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    for play in entry.get("playEffects") or []:
        effect_id = str(play.get("produceExamEffectId") or "")
        for index, node in enumerate(resolve_chain(effect_id, effects)):
            effect_type = _effect_type(node)
            if not effect_type or effect_type.endswith("Unknown"):
                continue
            payload = _basic_effect(node)
            enchant_id = str(node.get("produceExamStatusEnchantId") or "")
            inner = []
            for inner_id in enchants.get(enchant_id, {}).get("effect_ids") or []:
                for child in resolve_chain(inner_id, effects):
                    child_type = _effect_type(child)
                    if not child_type or child_type.endswith("Unknown"):
                        continue
                    inner.append(_basic_effect(child))
            if inner:
                payload["enchant"] = enchant_id
                payload["inner"] = inner
            trigger = str(play.get("produceExamTriggerId") or "")
            if index == 0 and trigger:
                payload["trigger"] = trigger
            out.append(payload)
    return out


def merge_by_type(old: list[dict], new: list[dict]) -> list[dict]:
    """类型序列对不上时，按类型顺序合并，保留旧类型列表。"""
    remaining = list(new)
    merged: list[dict] = []
    for old_effect in old:
        matched = next(
            (item for item in remaining if item.get("type") == old_effect.get("type")),
            None,
        )
        if matched is None:
            merged.append(old_effect)
            continue
        remaining.remove(matched)
        merged.append(matched)
    return merged


def update_cards(
    cards: dict[str, dict],
    entries: list[dict],
    effects: dict[str, dict],
    enchants: dict[str, dict],
) -> dict:
    by_key = {(entry["id"], int(entry.get("upgrade") or 0)): entry for entry in entries}
    stats = {
        "matched": 0,
        "missing": 0,
        "type_mismatch": 0,
        "cost_mismatch": 0,
        "triggered": 0,
        "effects": 0,
        "effects_with_values": 0,
        "effects_with_inner": 0,
        "cards_direct": 0,
        "cards_any": 0,
        "cards_none": [],
        "mismatch_samples": [],
        "cost_samples": [],
    }
    for name, row in cards.items():
        entry = by_key.get((str(row.get("id") or ""), int(row.get("upgrade") or 0)))
        if entry is None:
            stats["missing"] += 1
            continue
        stats["matched"] += 1
        if entry.get("stamina") != row.get("cost"):
            stats["cost_mismatch"] += 1
            if len(stats["cost_samples"]) < 10:
                stats["cost_samples"].append((name, row.get("cost"), entry.get("stamina")))
        resolved = build_effects(entry, effects, enchants)
        old_effects = list(row.get("effects") or [])
        old_types = [effect.get("type") for effect in old_effects]
        new_types = [effect.get("type") for effect in resolved]
        if old_types != new_types:
            stats["type_mismatch"] += 1
            if len(stats["mismatch_samples"]) < 10:
                stats["mismatch_samples"].append((name, old_types, new_types))
            resolved = merge_by_type(old_effects, resolved)
        row["effects"] = resolved
        trigger = str(entry.get("playProduceExamTriggerId") or "")
        if trigger:
            row["trigger"] = trigger
            stats["triggered"] += 1
        else:
            row.pop("trigger", None)
        stats["effects"] += len(resolved)
        has_direct = False
        has_any = False
        for effect in resolved:
            if effect.get("values"):
                stats["effects_with_values"] += 1
                has_direct = True
            if effect.get("inner"):
                stats["effects_with_inner"] += 1
            if effect.get("values") or effect.get("inner"):
                has_any = True
        stats["cards_direct"] += int(has_direct)
        stats["cards_any"] += int(has_any)
        if not has_any:
            stats["cards_none"].append(name)
    return stats


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="补齐 card_table.json 的卡牌效果数值")
    parser.add_argument("--cards-yaml", type=Path, default=CARD_YAML)
    parser.add_argument("--effects-yaml", type=Path, default=EFFECT_YAML)
    parser.add_argument("--exam-enchant-yaml", type=Path, default=EXAM_ENCHANT_YAML)
    parser.add_argument("--table", type=Path, default=TABLE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    for path in (args.cards_yaml, args.effects_yaml, args.table):
        if not path.exists():
            print(f"缺少文件: {path}")
            return 1

    data = json.loads(args.table.read_text(encoding="utf-8"))
    cards = data.get("cards") or {}
    if not cards:
        print(f"{args.table} 里没有 cards")
        return 1
    entries = parse_cards(args.cards_yaml)
    effects = parse_effects(args.effects_yaml)
    enchants = (
        parse_exam_enchants(args.exam_enchant_yaml)
        if args.exam_enchant_yaml.exists()
        else {}
    )
    print(
        f"YAML: cards={len(entries)} effects={len(effects)} "
        f"exam_enchants={len(enchants)}"
    )

    stats = update_cards(cards, entries, effects, enchants)
    total = len(cards)
    direct_ratio = stats["cards_direct"] / total if total else 0.0
    any_ratio = stats["cards_any"] / total if total else 0.0
    print(f"匹配: {stats['matched']}/{total}，缺失: {stats['missing']}")
    print(
        f"效果: {stats['effects']} 条，直接数值 {stats['effects_with_values']} 条，"
        f"带内层附魔 {stats['effects_with_inner']} 条"
    )
    print(
        f"卡牌覆盖: 直接数值 {stats['cards_direct']}/{total} ({direct_ratio:.1%})，"
        f"含附魔内层 {stats['cards_any']}/{total} ({any_ratio:.1%})"
    )
    print(f"使用条件 trigger: {stats['triggered']} 张")
    if stats["type_mismatch"]:
        print(f"类型序列不一致: {stats['type_mismatch']} 张（已按类型合并，保留旧类型）")
        for sample in stats["mismatch_samples"]:
            print("  ", sample)
    if stats["cost_mismatch"]:
        print(f"费用与 YAML 不一致: {stats['cost_mismatch']} 张（保留原 cost）")
        for sample in stats["cost_samples"]:
            print("  ", sample)
    if stats["cards_none"]:
        print(f"没有任何直接数值/内层数值: {len(stats['cards_none'])} 张")
        print("  " + "、".join(stats["cards_none"][:20]))

    if args.dry_run:
        print("--dry-run：未写回")
        return 0
    data["cards"] = cards
    data["count"] = len(cards)
    args.table.write_text(
        json.dumps(data, ensure_ascii=False, indent=0, sort_keys=True),
        encoding="utf-8",
    )
    print(f"写入 {args.table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
