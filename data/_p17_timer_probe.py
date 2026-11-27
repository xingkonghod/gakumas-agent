"""P1-7 探针：yaml 里所有 exam_effect_timer 包装（delay 机制落点）（不提交）。"""
import io
import json
import re
import sys
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_p_items as bpi

out = io.open("data/_p17_timer_out.txt", "w", encoding="utf-8")
yaml_items = bpi.parse_yaml_items(bpi.YAML)
local = {row["id"]: row for row in bpi.load_master("ProduceItem.json")}
catalog = {it["id"]: it for it in bpi.json.load(open("data/knowledge/p_items.json", encoding="utf-8"))["items"]}

TIMER = re.compile(r"e_effect-exam_effect_timer-(\d+)-(\d+)-(e_effect-.+)")
rows = []
for iid, y in yaml_items.items():
    for d in y.get("descriptions", []):
        oid = (d.get("originProduceExamEffectId") or "").strip('"')
        m = TIMER.match(oid)
        if m and d.get("produceDescriptionType") == "ProduceDescriptionType_ProduceExamEffectType":
            et = (d.get("examEffectType") or "").replace("ProduceExamEffectType_", "")
            rows.append((iid, y.get("name", ""), int(m.group(1)), et, oid))

out.write(f"timer 包装的效果段总数: {len(rows)}\n")
by_type = collections.Counter(r[3] for r in rows)
out.write("按效果类型: " + json.dumps(dict(by_type), ensure_ascii=False) + "\n\n")
for iid, name, n, et, oid in rows:
    cat = catalog.get(iid, {})
    out.write(f"{iid} | {name} | delay={n} | {et} | trig={cat.get('trigger')} | {oid}\n")
    out.write(f"    zh: {cat.get('text_zh', '')[:150]}\n")
out.close()
print("written data/_p17_timer_out.txt")
