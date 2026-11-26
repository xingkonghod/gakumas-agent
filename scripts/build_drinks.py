"""解析 ProduceDrink / ProduceDrinkEffect 主数据，产出 data/knowledge/drinks.json。

M6（2026-11-26）饮料全 catalog 结构化。数据来源（全部仓库内，只读）：
  * ``data/models/uinet_master/ProduceDrink.yaml`` —— 饮料 id / 日文名 / 稀有度 /
    planType / ``produceDrinkEffectIds``（→ p_drink_effect-*）；
  * ``data/models/uinet_master/ProduceDrinkEffect.yaml`` —— p_drink_effect-* →
    ``produceExamEffectId``（e_effect-*）；
  * ``data/cache/ProduceExamEffect.yaml`` —— 效果本体（effectType / effectValue1 /
    effectTurn / effectCount / produceCardSearchId / movePositionType / 附魔 id）；
  * ``data/cache/ProduceExamStatusEnchant.yaml`` —— 附魔内层效果 + 触发时机
    （``originProduceExamTriggerId`` / ``originProduceExamEffectId``）；
  * ``data/master/drinks.json`` —— 中文卡名 / 本地化描述（清洗 ``<nobr>`` 标签）。

效果段分类复用 ``sim/drinks.py`` 的 :func:`classify_drink_effect`（语义确定的实现，
其余显式 ``implemented=False`` no-op，不猜）。每瓶报 implemented/total 段数与 RNG
消费口径（:func:`rng_caliber`）。W9 三 id（pdrink_00-3-001 / 00-2-010 / 00-2-009）
的效果段与实机 execution.jsonl auto-drink-confirm labels 逐字对应（见 tests）。

用法::

    .venv\\Scripts\\python.exe scripts/build_drinks.py            # 生成 json + 打印统计
    .venv\\Scripts\\python.exe scripts/build_drinks.py --check    # 只打印统计，不写文件
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRINK_YAML = ROOT / "data" / "models" / "uinet_master" / "ProduceDrink.yaml"
DRINK_EFFECT_YAML = ROOT / "data" / "models" / "uinet_master" / "ProduceDrinkEffect.yaml"
EFFECT_YAML = ROOT / "data" / "cache" / "ProduceExamEffect.yaml"
ENCHANT_YAML = ROOT / "data" / "cache" / "ProduceExamStatusEnchant.yaml"
MASTER_DRINKS = ROOT / "data" / "master" / "drinks.json"
OUT = ROOT / "data" / "knowledge" / "drinks.json"

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from gkagent.sim.drinks import classify_drink_effect, rng_caliber  # noqa: E402

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")

RARITY = {
    "ProduceDrinkRarity_N": "N",
    "ProduceDrinkRarity_R": "R",
    "ProduceDrinkRarity_Sr": "SR",
    "ProduceDrinkRarity_Ssr": "SSR",
}


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


def clean_text(text: str) -> str:
    """本地化描述清洗：去 ``<nobr>`` 标签、去段分隔 `` / ``、压缩空白。"""
    text = TAG.sub("", text)
    text = text.replace(" / ", "").replace("/ ", "").replace(" /", "")
    return WS.sub(" ", text).strip()


def parse_drinks(path: Path) -> list[dict]:
    """行解析 ProduceDrink.yaml（顶层字段 + produceDrinkEffectIds 列表）。"""
    entries: list[dict] = []
    cur: dict | None = None
    section = ""
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            cur = {"id": line[6:].strip(), "effect_ids": [], "name_ja": "",
                   "rarity": "", "plan": ""}
            entries.append(cur)
            section = ""
            continue
        if cur is None:
            continue
        indent = len(line) - len(line.lstrip(" "))
        s = line.strip()
        if indent == 2 and s == "produceDrinkEffectIds:":
            section = "effects"
            continue
        if indent == 2 and s == "produceDescriptions:":
            section = "desc"
            continue
        if indent == 2 and not s.startswith("- "):
            section = ""
            k, _, v = s.partition(":")
            k = k.strip()
            if k == "name":
                cur["name_ja"] = _unquote(v)
            elif k == "rarity":
                cur["rarity"] = RARITY.get(v.strip(), v.strip())
            elif k == "planType":
                cur["plan"] = v.strip().replace("ProducePlanType_", "")
            continue
        if section == "effects" and indent == 2 and s.startswith("- "):
            cur["effect_ids"].append(_unquote(s[2:]))
    return entries


def parse_drink_effect_map(path: Path) -> dict[str, str]:
    """p_drink_effect-* → produceExamEffectId（e_effect-*）。"""
    table: dict[str, str] = {}
    cur = ""
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            cur = line[6:].strip()
            table[cur] = ""
            continue
        if not cur:
            continue
        s = line.strip()
        if s.startswith("produceExamEffectId:"):
            table[cur] = _unquote(s.partition(":")[2])
    return table


_EFFECT_FIELDS = {
    "effectType", "effectValue1", "effectValue2", "effectCount", "effectTurn",
    "produceCardSearchId", "movePositionType", "pickRangeType",
    "produceExamStatusEnchantId", "chainProduceExamEffectId",
}


def parse_effect_bodies(path: Path) -> dict[str, dict]:
    """e_effect-* → 效果本体字段（只取 2 空格缩进顶层字段 + chain 列表）。"""
    table: dict[str, dict] = {}
    cur: dict | None = None
    section = ""
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            cur = {"id": line[6:].strip(), "chains": []}
            table[cur["id"]] = cur
            section = ""
            continue
        if cur is None:
            continue
        indent = len(line) - len(line.lstrip(" "))
        s = line.strip()
        if indent == 2 and not s.startswith("- "):
            k, _, v = s.partition(":")
            k = k.strip()
            if k == "chainProduceExamEffectIds" and not v.strip():
                section = "chains"
            elif k == "produceDescriptions":
                section = "desc"
            else:
                section = ""
                if k in _EFFECT_FIELDS:
                    cur[k] = _unquote(v)
            continue
        if section == "chains" and indent == 2 and s.startswith("- "):
            cur["chains"].append(_unquote(s[2:]))
    return table


def parse_enchant_inner(path: Path) -> dict[str, list[dict]]:
    """enchant-* → 内层效果段 [{trigger, effect_id}]。

    附魔描述里触发句（``originProduceExamTriggerId``，如 e_trigger-start_play）与
    效果句（``originProduceExamEffectId``，如 e_effect-exam_card_draw-0001）常分属
    不同描述段；触发是附魔级的（描述「何时」），效果描述「做什么」。这里取附魔里
    第一个非空触发，配到每个内层效果上。
    """
    table: dict[str, list[dict]] = {}
    cur: dict | None = None
    in_desc = False
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            cur = {"trigger": "", "effect_ids": []}
            table[line[6:].strip()] = cur
            in_desc = False
            continue
        if cur is None:
            continue
        indent = len(line) - len(line.lstrip(" "))
        s = line.strip()
        if indent == 2 and s == "produceDescriptions:":
            in_desc = True
            continue
        if indent == 2 and not s.startswith("- "):
            in_desc = False
            continue
        if not in_desc or indent < 4:
            continue
        k, _, v = s.partition(":")
        k = k.strip()
        if k == "originProduceExamTriggerId":
            val = _unquote(v)
            if val and not cur["trigger"]:
                cur["trigger"] = val
        elif k == "originProduceExamEffectId":
            val = _unquote(v)
            if val and val not in cur["effect_ids"]:
                cur["effect_ids"].append(val)
    return {
        eid: [{"trigger": rec["trigger"], "effect_id": cid} for cid in rec["effect_ids"]]
        for eid, rec in table.items()
    }


def resolve_chain(effect_id: str, effects: dict[str, dict]) -> list[dict]:
    """广度优先展开 effect 本体 + chain（同 fetch_card_values.resolve_chain）。"""
    nodes: list[dict] = []
    queue = [effect_id]
    seen: set[str] = set()
    while queue:
        cid = queue.pop(0)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        row = effects.get(cid)
        if row is None:
            continue
        nodes.append(row)
        chained = list(row.get("chains") or [])
        single = str(row.get("chainProduceExamEffectId") or "")
        if single:
            chained.append(single)
        queue.extend(chained)
    return nodes


def effect_values(row: dict) -> dict:
    return {
        "effectValue1": _as_int(row.get("effectValue1")),
        "effectValue2": _as_int(row.get("effectValue2")),
        "effectCount": _as_int(row.get("effectCount")),
        "effectTurn": _as_int(row.get("effectTurn")),
    }


def build_drink(entry: dict, dmap: dict, effects: dict, enchants: dict,
                master: dict) -> dict:
    effects_out: list[dict] = []
    specs: list = []
    for peid in entry["effect_ids"]:
        eid = dmap.get(peid, "")
        for node in resolve_chain(eid, effects):
            et = str(node.get("effectType") or "").replace("ProduceExamEffectType_", "")
            if not et or et.endswith("Unknown"):
                continue
            search = str(node.get("produceCardSearchId") or "")
            move_to = str(node.get("movePositionType") or "").replace(
                "ProduceCardMovePositionType_", ""
            ).lower()
            inner: list[dict] = []
            enchant_id = str(node.get("produceExamStatusEnchantId") or "")
            if enchant_id:
                for seg in enchants.get(enchant_id, []):
                    child_id = seg.get("effect_id", "")
                    for child in resolve_chain(child_id, effects):
                        ctype = str(child.get("effectType") or "").replace(
                            "ProduceExamEffectType_", ""
                        )
                        if not ctype or ctype.endswith("Unknown"):
                            continue
                        inner.append({
                            "type": ctype,
                            "values": effect_values(child),
                            "trigger": seg.get("trigger", ""),
                        })
            eff = classify_drink_effect(
                et, effect_values(node), search=search, move_to=move_to,
                inner=inner, label=et,
            )
            specs.append(eff)
            rec = {
                "kind": eff.kind,
                "value": eff.value,
                "turns": eff.turns,
                "effect_type": et,
                "implemented": eff.implemented,
                "rng": eff.rng,
            }
            if eff.trigger:
                rec["trigger"] = eff.trigger
            if eff.search:
                rec["search"] = eff.search
                rec["move_to"] = eff.move_to
            if enchant_id:
                rec["enchant"] = enchant_id
            effects_out.append(rec)
    implemented = sum(1 for e in effects_out if e["implemented"])
    rng = rng_caliber(specs)
    m = master.get(entry["id"], {})
    return {
        "id": entry["id"],
        "name": m.get("name", entry["name_ja"]),
        "name_ja": entry["name_ja"],
        "rarity": entry["rarity"],
        "plan": entry["plan"],
        "text_zh": clean_text(m.get("text", "")),
        "effects": effects_out,
        "implemented": implemented,
        "total": len(effects_out),
        "rng": rng,
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="构建饮料全 catalog drinks.json")
    parser.add_argument("--check", action="store_true", help="只打印统计，不写文件")
    args = parser.parse_args(argv)

    for path in (DRINK_YAML, DRINK_EFFECT_YAML, EFFECT_YAML, MASTER_DRINKS):
        if not path.exists():
            print(f"缺少文件: {path}")
            return 1

    entries = parse_drinks(DRINK_YAML)
    dmap = parse_drink_effect_map(DRINK_EFFECT_YAML)
    effects = parse_effect_bodies(EFFECT_YAML)
    enchants = parse_enchant_inner(ENCHANT_YAML) if ENCHANT_YAML.exists() else {}
    master_rows = json.loads(MASTER_DRINKS.read_text(encoding="utf-8"))
    master = {r["id"]: r for r in master_rows}
    print(f"YAML: drinks={len(entries)} drink_effect_map={len(dmap)} "
          f"effects={len(effects)} enchants={len(enchants)} master={len(master)}")

    drinks = [build_drink(e, dmap, effects, enchants, master) for e in entries]
    seg_total = sum(d["total"] for d in drinks)
    seg_impl = sum(d["implemented"] for d in drinks)
    kinds = Counter(e["kind"] for d in drinks for e in d["effects"])
    unknown_types = Counter(
        e["effect_type"] for d in drinks for e in d["effects"] if not e["implemented"]
    )
    print(f"饮料 {len(drinks)} 瓶；效果段 implemented/total = {seg_impl}/{seg_total}")
    print("kind 分布:")
    for k, n in kinds.most_common():
        print(f"  {k}: {n}")
    print(f"未建模效果类型（显式 no-op）{sum(unknown_types.values())} 段:")
    for t, n in unknown_types.most_common():
        print(f"  {t}: {n}")
    # W9 三 id 逐字核对（中文描述清洗后）
    for did in ("pdrink_00-3-001", "pdrink_00-2-010", "pdrink_00-2-009"):
        d = next((x for x in drinks if x["id"] == did), None)
        if d:
            print(f"W9 {did} {d['name']}: {d['implemented']}/{d['total']} | {d['text_zh']}")

    if args.check:
        print("--check：未写回")
        return 0
    payload = {
        "schema": "gkagent.drinks.v1",
        "source": {
            "drink": "data/models/uinet_master/ProduceDrink.yaml",
            "drink_effect": "data/models/uinet_master/ProduceDrinkEffect.yaml",
            "effect": "data/cache/ProduceExamEffect.yaml",
            "enchant": "data/cache/ProduceExamStatusEnchant.yaml",
            "zh": "data/master/drinks.json",
        },
        "count": len(drinks),
        "segments_total": seg_total,
        "segments_implemented": seg_impl,
        "drinks": drinks,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
