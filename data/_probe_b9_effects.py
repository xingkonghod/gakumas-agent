"""B9 预分析 2：目标 effect type 的标签/文本/数值/触发分布。输出 data/_b9_effects.txt。"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "_b9_effects.txt"

TARGETS = [
    "ExamLessonValueMultiple",
    "ExamLessonValueMultipleDown",
    "ExamReviewMultiple",
    "ExamReviewCountAdd",
    "ExamExtraTurn",
    "ExamBuffConsumptionAdd",
    "ExamStaminaConsumptionDownFix",
    "ExamStaminaConsumptionDown",
    "ExamPreservation",
    "ExamConcentration",
    "ExamEnthusiasticMultiple",
    "ExamEnthusiasticAdditive",
    "ExamLessonBuffMultiple",
    "ExamLessonBuffAdditive",
    "ExamReviewAdditive",
    "ExamAggressiveAdditive",
    "ExamFullPowerPointAdditive",
    "ExamParameterBuffMultiplePerTurn",
    "ExamBlockFix",
    "ExamReviewReduce",
    "ExamFullPower",
    "ExamStaminaConsumptionAddFix",
    "ExamStaminaConsumptionAdd",
    "ExamBlockAddDown",
]


def main() -> int:
    payload = json.loads(
        (ROOT / "data" / "knowledge" / "p_items.json").read_text(encoding="utf-8-sig")
    )
    lines: list[str] = []
    add = lines.append
    per_type: dict[str, list[tuple]] = collections.defaultdict(list)
    labels: dict[str, set] = collections.defaultdict(set)
    for item in payload["items"]:
        for eff in item.get("effects") or []:
            t = eff.get("type")
            if t in TARGETS:
                per_type[t].append(
                    (
                        item["id"],
                        item["name"],
                        item.get("trigger"),
                        item.get("trigger_family"),
                        item.get("condition", ""),
                        (item.get("trigger_params") or {}),
                        eff.get("label", ""),
                        eff.get("text", ""),
                        eff.get("values"),
                        "IMPL" if (eff.get("depends_on") or eff.get("zero_stack")) else "",
                    )
                )
                labels[t].add(eff.get("label", ""))
    for t in TARGETS:
        rows = per_type.get(t, [])
        add(f"==== {t}  specs={len(rows)}  labels={sorted(labels[t])}")
        for row in rows[:6]:
            add("  " + " | ".join(str(x) for x in row))
        trg = collections.Counter(row[2] for row in rows)
        fam = collections.Counter(row[3] for row in rows)
        add(f"  triggers={dict(trg)}")
        add(f"  families={dict(fam)}")
        add("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
