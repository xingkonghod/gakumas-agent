"""P1-6 一次性脚本（不提交）：用真实转换链路生成标注回归夹具的合成演示样例。

provenance=synthetic-demo：演示闭环用，不是真机 ground truth；
真机标注后由 scripts/annotations_to_regression.py 追加真实案例。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.report.annotations import SCHEMA, cases_from_annotations, merge_cases

RECORD = {
    "episode": "ep-demo-review",
    "started_at": "2026-11-24 12:00:00",
    "weeks": [
        {"week": 1, "action": "train", "lesson_score": None, "attrs_after": [132, 165, 224], "stamina": 27},
        {"week": 2, "action": "lesson", "lesson_score": None, "attrs_after": [132, 170, 270],
         "stamina": 27, "note": "lesson_score 未读到（未用属性增量推算）"},
        {"week": 3, "action": "lesson", "lesson_score": 152, "attrs_after": [140, 180, 280], "stamina": 22},
    ],
    "exams": [{"kind": "mid", "rank": 3, "score": 217, "others": [603, 387, 217, 206, 205]}],
    "final": {"attrs": [140, 180, 280], "rank": 1, "exam_score": 17300, "eval_points": 5577, "grade": "C+"},
    "meta": {"audition_coefficient": 4.11},
}

TRACE_ROWS = [
    {"episode": "ep-demo-review", "step": 12, "screen": "action", "action": "tap-card",
     "point": [270, 600], "reason": "演示：选卡", "expect_kind": "change",
     "expect_words": ["行动"], "outcome": "retap", "tries": 1},
]

PAYLOAD = {
    "schema": SCHEMA,
    "episode": "ep-demo-review",
    "fingerprint": "synthetic-demo",
    "provenance": "synthetic-demo",
    "annotations": [
        {"id": "week-1", "target": "week", "key": 1, "verdict": "bad",
         "comment": "演示闭环（合成样例）：人工读课程结算屏补 week2 lesson_score=152",
         "expected": {"lesson_score": 152}},
        {"id": "step-12", "target": "step", "key": 12, "verdict": "bad",
         "comment": "演示闭环（合成样例）：画面已推进应判 moved 而非 retap",
         "expected": {"outcome": "moved"}},
    ],
}

cases = cases_from_annotations(PAYLOAD, RECORD, TRACE_ROWS)
fixture = merge_cases(None, cases)
out = ROOT / "tests" / "fixtures" / "review_regressions.json"
out.write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"written {out}: {len(fixture['cases'])} cases")
for case in fixture["cases"]:
    print(" ", case["id"], case["kind"], case["provenance"])
