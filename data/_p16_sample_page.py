"""P1-6 一次性脚本（不提交）：生成一局自动复盘页样例 docs/review_sample.html。

记录 = 真机 ep-rule1（bot 最好 C+/5992，data/runs/ep-rule1.json，真实数据）；
轨迹 = 合成演示 6 步（本局跑在 C1 之前，无真机 step_trace），页面显著标注
trace_source=synthetic-demo，不当真机数据引用。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.report.review_page import write_review_page

record = json.loads((ROOT / "data" / "runs" / "ep-rule1.json").read_text(encoding="utf-8"))

DEMO_TRACE = [
    {"episode": "ep-rule1", "step": 1, "screen": "home", "action": "start-produce",
     "point": [270, 880], "reason": "演示：主页起局", "engine_note": "",
     "expect_kind": "change", "expect_words": ["编成"], "outcome": "confirmed", "tries": 0},
    {"episode": "ep-rule1", "step": 2, "screen": "action", "action": "tap-rest",
     "point": [135, 620], "reason": "演示：体力门选休息", "engine_note": "eng=expectimax",
     "expect_kind": "change", "expect_words": ["休息"], "outcome": "confirmed", "tries": 0},
    {"episode": "ep-rule1", "step": 3, "screen": "action", "action": "tap-outing",
     "point": [405, 620], "reason": "演示：外出", "engine_note": "",
     "expect_kind": "change", "expect_words": ["外出"], "outcome": "retap", "tries": 1},
    {"episode": "ep-rule1", "step": 4, "screen": "dialog", "action": "confirm-yes",
     "point": [300, 700], "reason": "演示：回合结束确认", "engine_note": "",
     "expect_kind": "dialog-gone", "expect_words": [], "outcome": "moved", "tries": 0},
    {"episode": "ep-rule1", "step": 5, "screen": "lesson", "action": "tap-card",
     "point": [270, 600], "reason": "演示：课程选卡", "engine_note": "eng=expectimax score=29",
     "expect_kind": "change", "expect_words": ["结果"], "outcome": "lost", "tries": 2},
    {"episode": "ep-rule1", "step": 6, "screen": "result", "action": "tap-next",
     "point": [270, 900], "reason": "演示：结算下一步", "engine_note": "",
     "expect_kind": "change", "expect_words": [], "outcome": "confirmed", "tries": 0},
]

path = write_review_page(record, DEMO_TRACE, out_dir=ROOT / "docs", trace_source="synthetic-demo")
# write_review_page 按 episode 命名 → 改名为 review_sample.html
target = ROOT / "docs" / "review_sample.html"
path.replace(target)
print(f"written {target} ({target.stat().st_size} bytes)")
