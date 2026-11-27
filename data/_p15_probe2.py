"""P1-5 探针2：no_value / unknown / no_target 段的原始记录抽样（不提交）。"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(open("data/_p15_probe2.out.txt", "wb"), encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gkagent.sim import p_items as P  # noqa: E402

records = json.loads(Path("data/knowledge/p_items.json").read_text(encoding="utf-8"))
if isinstance(records, dict):
    records = records.get("items") or records.get("records")

print("record keys:", sorted(records[0].keys()))
print("sample record:", json.dumps(records[0], ensure_ascii=False)[:800])

# 建 item_id -> record 索引
by_id = {r.get("id") or r.get("item_id"): r for r in records}

def show(s: P.PItemSpec, n: int = 3):
    rec = by_id.get(s.item_id, {})
    effs = rec.get("effects") or []
    # 找对应 effect 段
    for e in effs:
        if e.get("type") == s.effect_type:
            print(json.dumps(e, ensure_ascii=False)[:600])
            break
    print(f"  spec: name={s.name} trigger={s.trigger} value={s.value} cond={s.condition!r} text={s.text[:80]!r} effect_text={s.effect_text[:80]!r}")

specs = []
for rec in records:
    specs.extend(P.record_to_specs(rec))

groups = {
    "no_value_ExamParameterBuff": lambda s: not s.implemented and s.effect_type == "ExamParameterBuff" and s.trigger in P.SUPPORTED_TRIGGERS,
    "no_value_ExamLesson": lambda s: not s.implemented and s.effect_type == "ExamLesson" and s.trigger in P.SUPPORTED_TRIGGERS,
    "no_value_ExamBlock": lambda s: not s.implemented and s.effect_type == "ExamBlock" and s.trigger in P.SUPPORTED_TRIGGERS,
    "unknown_supported_trigger": lambda s: not s.implemented and s.effect_type == "unknown" and s.trigger in P.SUPPORTED_TRIGGERS,
    "ExamFullPower": lambda s: not s.implemented and s.effect_type == "ExamFullPower",
    "ExamBlockRestriction": lambda s: not s.implemented and s.effect_type == "ExamBlockRestriction",
    "ExamBlockAddDown": lambda s: not s.implemented and s.effect_type == "ExamBlockAddDown",
    "ExamGimmickSlump": lambda s: not s.implemented and s.effect_type == "ExamGimmickSlump",
    "ExamAggressiveReduce": lambda s: not s.implemented and s.effect_type == "ExamAggressiveReduce",
    "ExamParameterBuffAdditive": lambda s: not s.implemented and s.effect_type == "ExamParameterBuffAdditive",
    "ExamFullPowerPointReduce": lambda s: not s.implemented and s.effect_type == "ExamFullPowerPointReduce",
    "ExamLessonBuffReduce": lambda s: not s.implemented and s.effect_type == "ExamLessonBuffReduce",
    "ExamGimmickSleepy": lambda s: not s.implemented and s.effect_type == "ExamGimmickSleepy",
    "ExamGimmickLessonDebuff": lambda s: not s.implemented and s.effect_type == "ExamGimmickLessonDebuff",
    "ExamStaminaRecoverRestriction": lambda s: not s.implemented and s.effect_type == "ExamStaminaRecoverRestriction",
    "ExamStaminaDamage": lambda s: not s.implemented and s.effect_type == "ExamStaminaDamage",
    "ExamFullPowerLessonMultipleAdditive": lambda s: not s.implemented and s.effect_type == "ExamFullPowerLessonMultipleAdditive",
    "ExamConcentrationLessonMultipleAdditive": lambda s: not s.implemented and s.effect_type == "ExamConcentrationLessonMultipleAdditive",
    "ExamMetamorphose": lambda s: not s.implemented and s.effect_type == "ExamMetamorphose",
    "ExamCardDuplicate": lambda s: not s.implemented and s.effect_type == "ExamCardDuplicate",
    "ExamCardUpgrade": lambda s: not s.implemented and s.effect_type == "ExamCardUpgrade",
    "ExamDebuffRecover": lambda s: not s.implemented and s.effect_type == "ExamDebuffRecover",
}
for name, pred in groups.items():
    ss = [s for s in specs if pred(s)]
    print(f"\n===== {name}: {len(ss)} 段 =====")
    seen = set()
    shown = 0
    for s in ss:
        key = (s.effect_text or s.text, s.trigger)
        if key in seen:
            continue
        seen.add(key)
        print(f"[{s.item_id}] {s.name} trigger={s.trigger}")
        show(s)
        shown += 1
        if shown >= 4:
            break
