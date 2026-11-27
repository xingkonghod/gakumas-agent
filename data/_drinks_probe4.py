"""M6 探针 4：全 drink catalog 效果类型分布（build_drinks 设计用）。不提交。"""
import io
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_card_values import parse_effects  # noqa: E402

DRINK_YAML = ROOT / "data/models/uinet_master/ProduceDrink.yaml"
DEFFECT_YAML = ROOT / "data/models/uinet_master/ProduceDrinkEffect.yaml"
EFFECT_YAML = ROOT / "data/cache/ProduceExamEffect.yaml"


def parse_drinks(path):
    entries = []
    cur = None
    section = ""
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            cur = {"id": line[6:].strip(), "effect_ids": [], "name": "", "rarity": "", "plan": ""}
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
            if k == "name":
                cur["name"] = v.strip()
            elif k == "rarity":
                cur["rarity"] = v.strip()
            elif k == "planType":
                cur["plan"] = v.strip()
            continue
        if section == "effects" and indent == 2 and s.startswith("- "):
            cur["effect_ids"].append(s[2:].strip())
    return entries


def parse_drink_effects(path):
    table = {}
    cur = None
    for raw in path.open(encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        if line.startswith("- id: "):
            cur = line[6:].strip()
            table[cur] = ""
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("produceExamEffectId:"):
            table[cur] = s.partition(":")[2].strip()
    return table


drinks = parse_drinks(DRINK_YAML)
dmap = parse_drink_effects(DEFFECT_YAML)
effects = parse_effects(EFFECT_YAML)
print("drinks:", len(drinks), "drink_effect_map:", len(dmap), "effects:", len(effects))

types = Counter()
seg_total = 0
unknown_ids = []
for d in drinks:
    for peid in d["effect_ids"]:
        eid = dmap.get(peid, "")
        row = effects.get(eid)
        if row is None:
            unknown_ids.append((d["id"], peid, eid))
            types["<missing>"] += 1
            seg_total += 1
            continue
        et = str(row.get("effectType") or "").replace("ProduceExamEffectType_", "")
        types[et] += 1
        seg_total += 1
print("total segments:", seg_total)
for t, n in types.most_common():
    print(f"  {t}: {n}")
print("missing effect bodies:", len(unknown_ids))
for u in unknown_ids[:20]:
    print("  ", u)
