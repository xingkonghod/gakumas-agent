"""P1-7 探针：候选效果类型在主数据 p_items.json 的分布与描述（不提交）。"""
import json
import collections
import io

d = json.load(open("data/knowledge/p_items.json", encoding="utf-8"))
items = d["items"]
out = io.open("data/_p17_probe_out.txt", "w", encoding="utf-8")

CANDIDATES = [
    "ExamParameterBuffAdditive",
    "ExamBlockRestriction",
    "ExamBlockAddDown",
    "ExamParameterBuffReduce",
    "ExamFullPower",
    "ExamConcentration",
    "ExamGimmickSlump",
    "ExamGimmickLessonDebuff",
    "ExamGimmickSleepy",
    "ExamStaminaRecoverRestriction",
]

by_type = collections.defaultdict(list)
for it in items:
    for eff in it.get("effects", []):
        et = eff.get("type")
        if et in CANDIDATES:
            by_type[et].append((it, eff))

for et in CANDIDATES:
    rows = by_type.get(et, [])
    out.write(f"\n=== {et}: {len(rows)} 段 ===\n")
    for it, eff in rows:
        out.write(
            f"{it['id']} | {it['name']} | trig={it.get('trigger')} "
            f"trig_id={it.get('trigger_id')} params={json.dumps(it.get('trigger_params', {}), ensure_ascii=False)} "
            f"cond={it.get('condition')!r} values={json.dumps(eff.get('values', {}), ensure_ascii=False)} "
            f"max_uses={eff.get('max_uses')} text={eff.get('text')!r}\n"
        )
        out.write(f"    zh: {it.get('text_zh')}\n    ja: {it.get('text_ja')}\n")
out.close()
print("written data/_p17_probe_out.txt")
