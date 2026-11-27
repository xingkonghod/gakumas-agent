import io, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(open("data/_p15_scope.out.txt", "wb"), encoding="utf-8")
from gkagent.sim import p_items as P

records = json.loads(Path("data/knowledge/p_items.json").read_text(encoding="utf-8"))["items"]
by_id = {r["id"]: r for r in records}
specs = []
for rec in records:
    specs.extend(P.record_to_specs(rec))

# 1) ExamParameterBuff no_value 细分：turn 列有值（好调N回合） vs conversion_source vs 其它
pb = [s for s in specs if s.effect_type == "ExamParameterBuff" and not s.implemented]
turn_ok = [s for s in pb if s.trigger in P.SUPPORTED_TRIGGERS]
print("== ExamParameterBuff no-op ==", len(pb))
cnt = Counter()
for s in turn_ok:
    rec = by_id[s.item_id]
    eff = next((e for e in rec["effects"] if e.get("type") == "ExamParameterBuff"), {})
    v = eff.get("values") or {}
    role = eff.get("role", "")
    if role == "conversion_source":
        cnt["conversion_source(系数,正确no-op)"] += 1
    elif v.get("turn"):
        cnt[f"好调N回合(turn列) trig={s.trigger}"] += 1
    else:
        cnt[f"其它 values={v} text={eff.get('text','')[:30]}"] += 1
for k, n in cnt.most_common():
    print(f"  {n:3d}  {k}")

# 2) 好调依赖换算：记录文本含「好调的N%数值变为」但目标段没 depends_on
print("\n== 好调依赖换算缺口（目标段空 values 无 depends_on，记录文本有好调的N%） ==")
import re
rx = re.compile(r"好调的(\d+)%数值变为")
gap = Counter()
examples = []
for rec in records:
    zh = rec.get("text_zh") or ""
    if not rx.search(zh):
        continue
    for e in rec["effects"]:
        if e.get("type") in ("ExamLesson", "ExamReview", "ExamBlock", "ExamLessonBuff", "ExamCardPlayAggressive", "ExamParameterBuff"):
            if not (e.get("values") or {}) and not e.get("depends_on") and e.get("role") != "conversion_source":
                gap[e["type"]] += 1
                if len(examples) < 8:
                    examples.append((rec["id"], rec["name"], e["type"], zh[:70]))
for k, n in gap.most_common():
    print(f"  {n:3d}  {k}")
for ex in examples:
    print("   ", ex)

# 3) 层数减少类 supported trigger 段
print("\n== 层数减少类（supported trigger） ==")
for et in ("ExamAggressiveReduce", "ExamLessonBuffReduce", "ExamFullPowerPointReduce", "ExamStaminaDamage", "ExamParameterBuffReduce"):
    ss = [s for s in specs if s.effect_type == et]
    sup = [s for s in ss if s.trigger in P.SUPPORTED_TRIGGERS]
    print(f"  {et}: total={len(ss)} supported={len(sup)} triggers={dict(Counter(s.trigger for s in sup))}")
    for s in sup[:3]:
        rec = by_id[s.item_id]
        eff = next((e for e in rec["effects"] if e.get("type") == et), {})
        print(f"     {s.item_id} {s.name} trig={s.trigger} values={eff.get('values')} cond={s.condition!r}")

# 4) ExamParameterBuffAdditive
print("\n== ExamParameterBuffAdditive ==")
for s in specs:
    if s.effect_type == "ExamParameterBuffAdditive":
        rec = by_id[s.item_id]
        eff = next((e for e in rec["effects"] if e.get("type") == "ExamParameterBuffAdditive"), {})
        print(f"  {s.item_id} {s.name} trig={s.trigger} supported={s.trigger in P.SUPPORTED_TRIGGERS} values={eff.get('values')}")

# 5) 好调换算源段原始结构（pitem_01-1-022 初阵之证・佑芽）
print("\n== 好调换算源段原始结构 ==")
for pid in ("pitem_01-1-022-0", "pitem_01-0-005-0-014"):
    rec = by_id.get(pid)
    if rec:
        print(f"  {pid} {rec['name']}: zh={rec.get('text_zh','')[:80]}")
        for e in rec["effects"]:
            print(f"     {e.get('type')} values={e.get('values')} role={e.get('role','')} text={e.get('text','')[:40]} depends_on={e.get('depends_on','')}")
