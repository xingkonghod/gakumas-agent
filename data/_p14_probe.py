# P1-4 证据探针（一次性，不提交）：ExamBuffConsumptionAdd / nullifyDebuff / countDebuffs
# 输出 data/_p14_probe_out.txt（UTF-8）
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = []


def p(*a):
    OUT.append(" ".join(str(x) for x in a))


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


card_table = load("data/knowledge/card_table.json")["cards"]
card_meta = load("data/knowledge/card_meta.json")
ja2zh = card_meta["ja_aliases"]
pitems = load("data/knowledge/p_items.json")

# ---------- 1. card_table 里的 ExamAntiDebuff / ExamDebuffRecover 卡 ----------
p("=== 1. card_table ExamAntiDebuff / ExamDebuffRecover 卡 ===")
anti_cards = {}
for name, row in card_table.items():
    types = {e.get("type") for e in row.get("effects", [])}
    if types & {"ExamAntiDebuff", "ExamDebuffRecover"}:
        anti_cards[name] = row
        p(name, "| id=", row.get("id"), "| rarity=", row.get("rarity"),
          "| cost=", row.get("cost"), "| effects=",
          [(e.get("type"), e.get("values"), e.get("turn")) for e in row["effects"]])

# ---------- 2. p_items ExamAntiDebuff / ExamBuffConsumptionAdd / buff_consume ----------
p("\n=== 2. p_items 相关段 ===")
# p_items.json 顶层结构
p("top keys:", list(pitems.keys()))
records = pitems.get("items") or pitems.get("records") or []
if not records:
    for k, v in pitems.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "id" in v[0]:
            p("list key:", k, "len:", len(v))
            records = v
            break
anti_items, buffcost_items, buffconsume_items = [], [], []
for r in records:
    etypes = {e.get("type") for e in r.get("effects", [])}
    if "ExamAntiDebuff" in etypes or r.get("effect_type") == "ExamAntiDebuff":
        anti_items.append(r)
    if "ExamBuffConsumptionAdd" in etypes:
        buffcost_items.append(r)
    if r.get("trigger") == "buff_consume":
        buffconsume_items.append(r)
p("-- ExamAntiDebuff 段", len(anti_items))
for r in anti_items:
    p(r["id"], "|", r.get("name"), "| trigger=", r.get("trigger"),
      "| trigger_id=", r.get("trigger_id"), "| value=", r.get("value"),
      "| effects=", [(e.get("type"), e.get("values")) for e in r.get("effects", [])],
      "| text=", r.get("text_zh") or r.get("text_ja"))
p("-- ExamBuffConsumptionAdd 段", len(buffcost_items))
for r in buffcost_items:
    p(r["id"], "|", r.get("name"), "| trigger=", r.get("trigger"),
      "| trigger_id=", r.get("trigger_id"), "| max_uses=", r.get("max_uses"),
      "| effects=", [(e.get("type"), e.get("values"), e.get("target")) for e in r.get("effects", [])])
p("-- buff_consume 触发段", len(buffconsume_items))
for r in buffconsume_items:
    p(r["id"], "|", r.get("name"), "| trigger_id=", r.get("trigger_id"),
      "| effect_type=", r.get("effect_type"),
      "| effects=", [(e.get("type"), e.get("values"), e.get("target")) for e in r.get("effects", [])],
      "| text=", r.get("text_zh") or r.get("text_ja"))

# ---------- 3. 参考 skill_cards.csv：buff-cost 卡 + nullifyDebuff 卡 ----------
p("\n=== 3. 参考 skill_cards.csv ===")
ref_cards = list(csv.DictReader(io.open(
    ROOT / "data/dl/gt/gakumas-tools-master/packages/gakumas-data/csv/skill_cards.csv",
    encoding="utf-8")))
BUFF_IDS = ("goodImpressionTurns", "motivation", "concentration",
            "goodConditionTurns", "perfectConditionTurns", "fullPowerCharge")
buff_cost_rows = [r for r in ref_cards if any(k in (r["cost"] or "") for k in BUFF_IDS)]
nullify_rows = [r for r in ref_cards if "nullifyDebuff" in (r["actions"] or "")]
p("buff-cost 卡行数:", len(buff_cost_rows), " nullifyDebuff 卡行数:", len(nullify_rows))


def zh_name(ja):
    return ja2zh.get(ja)


def in_table(zh):
    return card_table.get(zh) if zh else None


p("-- nullifyDebuff 卡（参考→主数据交叉）")
for r in nullify_rows:
    zh = zh_name(r["name"])
    row = in_table(zh)
    p(r["id"], r["name"], "→", zh, "| master:",
      (row.get("id"), row.get("cost"), [(e.get("type"), e.get("values")) for e in row.get("effects", [])]) if row else None,
      "| ref cost=", r["cost"], "| ref actions=", r["actions"][:120])

p("-- buff-cost 卡（参考→主数据交叉；cost 列含强化状态消耗）")
buff_cost_zh = {}
for r in buff_cost_rows:
    zh = zh_name(r["name"])
    row = in_table(zh)
    buff_cost_zh[r["name"]] = zh
    p(r["id"], r["name"], "→", zh, "| master cost=", row.get("cost") if row else "MISSING",
      "| master id=", row.get("id") if row else "-", "| ref cost=", r["cost"])

# ---------- 4. sim_produce 牌组/池 + eval_expectimax 牌组 ----------
p("\n=== 4. 评测牌组/奖励池落点 ===")
import sim_produce as sp

deck = sp.build_deck(rich=True)
pool = sp.build_pool(rich=True)
p("build_deck:", len(deck), "build_pool:", len(pool))
zh_buffcost = {v for v in buff_cost_zh.values() if v}
zh_anti = set(anti_cards)
deck_names = {r.name for r in deck}
pool_names = {r.name for r in pool}
p("deck ∩ buff-cost 卡:", sorted(deck_names & zh_buffcost))
p("pool ∩ buff-cost 卡:", sorted(pool_names & zh_buffcost))
p("deck ∩ ExamAntiDebuff 卡:", sorted(deck_names & zh_anti))
p("pool ∩ ExamAntiDebuff 卡:", sorted(pool_names & zh_anti))

import eval_expectimax as ee

for scen in ("small", "large"):
    d = ee.build_deck(scen)
    names = {c.name for c in d}
    p(f"eval {scen} ({len(d)} 张) ∩ buff-cost:", sorted(names & zh_buffcost),
      "| ∩ anti:", sorted(names & zh_anti))
    p(f"eval {scen} 牌组:", [c.name for c in d])

# ---------- 5. gkbench hif loadout ----------
p("\n=== 5. gkbench hif loadout ===")
prob_path = ROOT / "data/bench_local/problems_hif.json"
if prob_path.exists():
    probs = json.loads(prob_path.read_text(encoding="utf-8"))
    if isinstance(probs, dict):
        p("problems keys:", list(probs.keys())[:5])
        probs = probs.get("problems") or probs.get("items") or []
    p("题数:", len(probs))
    hit_buffcost, hit_anti, hit_tower = [], [], []
    deck_buffcost_hits = []
    sample_deck = None
    for pr in probs:
        raw = pr.get("raw") or pr
        arch = raw.get("archive") or {}
        lo = arch.get("loadout") or {}
        ids = lo.get("produce_item_ids") or []
        pid = pr.get("id") or raw.get("id")
        for i in ids:
            s = str(i)
            if s.endswith("-345") or s.endswith("-349") or "-345-" in s or "-349-" in s:
                hit_buffcost.append((pid, s))
            if s.endswith("-317") or "-317-" in s:
                hit_anti.append((pid, s))
            if "tower" in s:
                hit_tower.append((pid, s))
        dc = lo.get("deck_cards") or []
        if sample_deck is None and dc:
            sample_deck = dc[:3]
        for entry in dc:
            cid = entry.get("id") if isinstance(entry, dict) else entry
            # 卡 id → 中文名：card_meta cards 按名字索引，这里反查
            for zh, row in card_table.items():
                if row.get("id") == cid and zh in zh_buffcost:
                    deck_buffcost_hits.append((pid, cid, zh))
                    break
    p("loadout 含 ExamBuffConsumptionAdd 道具(345/349):", len(hit_buffcost), hit_buffcost[:30])
    p("loadout 含 317(おさぼりタオル):", len(hit_anti), hit_anti[:10])
    p("loadout 含 tower:", len(hit_tower), hit_tower[:10])
    p("loadout 牌组含 buff-cost 卡:", len(deck_buffcost_hits), deck_buffcost_hits[:20])
    p("deck_cards 样例:", sample_deck)
else:
    p("problems_hif.json 不存在")

# ---------- 6. countDebuffs / 低下状態の数 全参考 CSV + 主数据 ----------
p("\n=== 6. countDebuffs 用法检索 ===")
csv_dir = ROOT / "data/dl/gt/gakumas-tools-master/packages/gakumas-data/csv"
for f in sorted(csv_dir.glob("*.csv")):
    txt = f.read_text(encoding="utf-8")
    for kw in ("countDebuffs", "removeDebuffs"):
        n = txt.count(kw)
        if n:
            p(f.name, kw, n)
            for line in txt.splitlines():
                if kw in line:
                    p("   ", line[:200])
# 主数据 trigger/条件里有没有 debuff 计数
trig_hits = set()
for r in records:
    tid = r.get("trigger_id") or ""
    if "debuff" in tid.lower():
        trig_hits.add(tid)
p("p_items trigger_id 含 debuff:", sorted(trig_hits))
ct_hits = [name for name, row in card_table.items()
           if any("debuff" in str(e.get("type", "")).lower() for e in row.get("effects", []))]
p("card_table 效果含 debuff 的卡名:", sorted(set(ct_hits))[:40])

# ---------- 7. wiki buffs.json ----------
p("\n=== 7. wiki buffs.json 相关条 ===")
buffs = load("data/knowledge/buffs.json")
if isinstance(buffs, dict):
    p("buffs keys:", list(buffs.keys())[:10])
    entries = buffs.get("buffs") or buffs.get("entries") or []
else:
    entries = buffs
for b in entries if isinstance(entries, list) else []:
    name = str(b.get("name") or b.get("ja") or "")
    if any(k in name for k in ("低下", "無効", "コスト増加", "强化状态", "低下状态")):
        p(json.dumps(b, ensure_ascii=False)[:400])

(ROOT / "data/_p14_probe_out.txt").write_text("\n".join(OUT), encoding="utf-8")
print("written", len(OUT), "lines")
