# P1-8 探针：剩段数据盘点（不提交）
import json, collections, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

data = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\p_items.json", encoding="utf-8"))
items = data["items"]
print("stats:", json.dumps(data["stats"], ensure_ascii=False)[:600])
print("items:", len(items))

# 每条 record 的 effects 段里找四类剩段
groups = {
    "fullpower_conc_score": ("ExamFullPower", "ExamConcentration"),
    "tower_gimmick": ("ExamGimmickSlump", "ExamGimmickLessonDebuff", "ExamGimmickSleepy", "ExamStaminaRecoverRestriction"),
    "param_buff_reduce": ("ExamParameterBuffReduce",),
}
hits = collections.defaultdict(list)
for rec in items:
    for eff in rec.get("effects", []):
        t = eff.get("type", "")
        for g, types in groups.items():
            if t in types:
                hits[g].append((rec, eff))

for g, lst in hits.items():
    print(f"\n===== {g}: {len(lst)} 段 =====")
    for rec, eff in lst[:60]:
        print(f"  {rec['id']} | {rec['name']} | trig={rec.get('trigger')} fam={rec.get('trigger_family')} tid={rec.get('trigger_id','')}")
        print(f"    eff={json.dumps(eff, ensure_ascii=False)}")
        print(f"    cond={rec.get('condition','')!r} cond_known={rec.get('condition_known')} trig_known={rec.get('trigger_known')} target={eff.get('target','')}")

# 日文好調の%分：天生的才能
print("\n===== 天生的才能 / 好調の% =====")
for rec in items:
    if "天生的才能" in rec.get("name", "") or "好調" in rec.get("text_ja", "") and "%" in rec.get("text_ja",""):
        print(json.dumps(rec, ensure_ascii=False)[:1200])
        print("---")