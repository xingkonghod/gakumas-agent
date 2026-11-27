# P1-8 探针2：聚焦 天生的才能 + 塔 gimmick 计数 + buff_consume（不提交）
import json, collections, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

data = json.load(open(r"D:\Games\gakumas-agent\data\knowledge\p_items.json", encoding="utf-8"))
items = data["items"]

print("===== 天生的才能 pitem_01-3-346 =====")
for rec in items:
    if rec["id"].startswith("pitem_01-3-346"):
        print(json.dumps(rec, ensure_ascii=False, indent=1))

print("\n===== 塔 gimmick 段统计 =====")
cnt = collections.Counter()
tower_ids = set()
for rec in items:
    for eff in rec.get("effects", []):
        t = eff.get("type", "")
        if t in ("ExamGimmickSlump", "ExamGimmickLessonDebuff", "ExamGimmickSleepy", "ExamStaminaRecoverRestriction"):
            cnt[t] += 1
            tower_ids.add(rec["id"])
print(cnt, "唯一道具段 id 数:", len(tower_ids))
print("tower record ids:", sorted(tower_ids))

print("\n===== buff_consume / produce_start_lesson 触发全部段 =====")
for rec in items:
    if rec.get("trigger") in ("buff_consume", "produce_start_lesson"):
        effs = [(e.get("type"), e.get("values"), e.get("text","")[:40], e.get("target","")) for e in rec.get("effects",[])]
        print(f"  {rec['id']} | {rec['name']} | trig={rec['trigger']} | {effs}")

print("\n===== ExamFullPower/ExamConcentration 打分值增加 段分类 =====")
score_segs = []
other_segs = []
for rec in items:
    for eff in rec.get("effects", []):
        t = eff.get("type", "")
        if t in ("ExamFullPower", "ExamConcentration"):
            txt = eff.get("text", "")
            if "打分值增加" in txt:
                score_segs.append((rec, eff))
            else:
                other_segs.append((rec, eff))
print(f"打分值增加段: {len(score_segs)}；其他段: {len(other_segs)}")
trig_cnt = collections.Counter(rec.get("trigger") for rec, _ in score_segs)
print("打分值增加段触发分布:", trig_cnt)
for rec, eff in score_segs:
    print(f"  {rec['id']} | {rec['name']} | trig={rec.get('trigger')} | cond={rec.get('condition','')!r} | {eff.get('text','')!r} | target={eff.get('target','')}")
print("\n其他段（非打分值增加）:")
for rec, eff in other_segs:
    print(f"  {rec['id']} | {rec['name']} | trig={rec.get('trigger')} | {eff.get('text','')!r}")