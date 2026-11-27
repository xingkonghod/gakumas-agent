"""P1-7 探针：timer 道具的 gkbench loadout 覆盖 + ExamBlockFix/ExamBlock 分布 + 卡侧 fixedGenki（不提交）。"""
import io
import json
import re
import sys
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_p_items as bpi

out = io.open("data/_p17_cover_out.txt", "w", encoding="utf-8")
cat = json.load(open(ROOT / "data/knowledge/p_items.json", encoding="utf-8"))
items = {it["id"]: it for it in cat["items"]}

TIMER_IDS = [
    "pitem_00-2-116-0", "pitem_01-0-001-0-024", "pitem_02-0-006-0-015",
    "pitem_02-1-023-0", "pitem_02-1-023-1", "pitem_02-3-130-0", "pitem_02-3-130-1",
    "pitem_02-3-154-0", "pitem_02-3-154-1", "pitem_02-3-167-0", "pitem_02-3-167-1",
    "pitem_02-3-299-0", "pitem_02-3-299-1", "pitem_03-0-007-0-007", "pitem_03-0-007-0-008",
    "pitem_03-3-111-0", "pitem_03-3-111-1", "pitem_03-3-114-0", "pitem_03-3-114-1",
    "pitem_03-3-162-0", "pitem_03-3-162-1", "pitem_03-3-289-0", "pitem_03-3-289-1",
    "pitem_03-3-339-0", "pitem_03-3-339-1", "pitem_3-258-research-event-002",
]
# 本批新目标候选 id
NEW_IDS = [
    "pitem_01-3-161-0", "pitem_01-3-161-1", "pitem_01-3-245-challenge", "pitem_01-3-246-challenge",
    "pitem_01-3-044-0", "pitem_01-3-044-1", "pitem_02-0-002-0-002",
    "pitem_02-2-066-challenge", "pitem_02-2-067-challenge",
    "pitem_03-0-007-0-012", "pitem_03-0-007-0-013",
]

# gkbench loadout 覆盖
dl = ROOT / "data/bench_local/gkbench_dl/hif"
ids = collections.Counter()
files = list(dl.glob("*.json")) if dl.exists() else []
out.write(f"gkbench dl files: {len(files)}\n")
for f in files:
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("produce_item_ids", "produceItemIds") and isinstance(v, list):
                    for x in v:
                        ids[str(x)] += 1
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(d)
out.write(f"unique loadout ids: {len(ids)}\n")
out.write("timer 道具在 loadout: " + json.dumps({i: ids.get(i, 0) for i in TIMER_IDS if ids.get(i)}, ensure_ascii=False) + "\n")
out.write("新目标道具在 loadout: " + json.dumps({i: ids.get(i, 0) for i in NEW_IDS if ids.get(i)}, ensure_ascii=False) + "\n")

# ExamBlock / ExamBlockFix 段分布
cnt = collections.Counter()
for it in cat["items"]:
    for e in it.get("effects", []):
        if e["type"] in ("ExamBlock", "ExamBlockFix"):
            cnt[e["type"]] += 1
out.write(f"\nExamBlock/ExamBlockFix 段数: {dict(cnt)}\n")
fix_items = [(it["id"], it["name"], it["trigger"]) for it in cat["items"]
             if any(e["type"] == "ExamBlockFix" for e in it.get("effects", []))]
out.write(f"ExamBlockFix 道具 {len(fix_items)} 件（前 20）:\n")
for row in fix_items[:20]:
    out.write(f"  {row}\n")

# 恶作剧木偶 condition 解析状态
for iid in ("pitem_01-3-044-0", "pitem_02-0-002-0-002", "pitem_02-2-066-challenge",
            "pitem_02-2-067-challenge", "pitem_03-0-007-0-012", "pitem_01-3-245-challenge",
            "pitem_01-3-161-0", "pitem_02-1-023-0", "pitem_02-3-130-0"):
    it = items.get(iid, {})
    out.write(f"\n{iid} {it.get('name')}: trigger={it.get('trigger')} cond={it.get('condition')!r} "
              f"cond_known={it.get('condition_known', True)} trig_known={it.get('trigger_known', True)} "
              f"params={json.dumps(it.get('trigger_params', {}), ensure_ascii=False)} max_uses={it.get('max_uses')}\n")
    for e in it.get("effects", []):
        out.write(f"    {e['type']} values={json.dumps(e.get('values', {}), ensure_ascii=False)} text={e.get('text')!r} target={e.get('target')!r}\n")

# 卡侧 fixedGenki（参考 skill_cards.csv）
csv = (ROOT / "data/dl/gt/gakumas-tools-master/packages/gakumas-data/csv/skill_cards.csv").read_text(encoding="utf-8")
n_fix = len(re.findall(r"fixedGenki", csv))
n_genki = len(re.findall(r"genki\+=", csv))
n_gcb = len(re.findall(r"setGoodConditionTurnsBuff", csv))
out.write(f"\nskill_cards.csv fixedGenki 行数: {n_fix}\n")
out.write(f"skill_cards.csv genki+= 行数: {n_genki}\n")
out.write(f"skill_cards.csv setGoodConditionTurnsBuff 行数: {n_gcb}\n")
for line in csv.splitlines():
    if "setGoodConditionTurnsBuff" in line:
        out.write("  CARD-GCB: " + line[:200] + "\n")
out.close()
print("written data/_p17_cover_out.txt")
