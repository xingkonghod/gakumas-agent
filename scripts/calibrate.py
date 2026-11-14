"""查看真机属性标定数据（三维/周成长/课程系数估计）。

用法：
    python scripts/calibrate.py
    python scripts/calibrate.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

from gkagent.data.calibration import LOG, estimate_ratio, summarize


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    summary = summarize()
    if "--json" in argv:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    if not summary["records"]:
        print(f"还没有记录（{LOG}）。开真机跑一局，训练确认界面会自动记录三维。")
        return 0
    print(f"记录 {summary['records']} 条，可算 {summary['weeks']} 周增长")
    print(f"每周属性增长: 均值 {summary['mean_growth']} | 最大 {summary['max_growth']} | 最小 {summary['min_growth']}")
    print(f"最新三维: {summary['last_attrs']}")
    for item in summary["deltas"][-8:]:
        print(f"  {item['ts']}  +{item['total']:>3}  {item['delta']}  → {item['attrs']}")
    if len(argv) > 1 and argv[0] == "--scores":
        scores = [int(value) for value in argv[1:]]
        print("估计课程系数:", estimate_ratio(scores))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
