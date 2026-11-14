"""一局培育的体检报告：耗时 + 出牌质量信号。

用法：
    python scripts/episode_report.py [episode]

读 ``data/metrics.jsonl``（每步耗时/屏幕/动作）、``data/auto/auto_log_<ep>.log``（人类可读）、
``data/exam_results.jsonl``（考试名次）、``data/knowledge/card_costs.json``（学到的费用）。
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
METRICS = ROOT / "data" / "metrics.jsonl"


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = load_rows(METRICS)
    if not rows:
        print("没有 metrics.jsonl")
        return 1
    episodes = [row.get("episode") for row in rows if row.get("episode")]
    episode = argv[0] if argv else (episodes[-1] if episodes else "")
    steps = [row for row in rows if row.get("episode") == episode and "total_ms" in row]
    wraps = [row for row in rows if row.get("episode") == episode and "done" in row]

    print(f"=== {episode} ===")
    if wraps:
        wrap = wraps[-1]
        duration = float(wrap.get("ended_at") or 0) - float(wrap.get("started_at") or 0)
        print(f"墙钟: {duration/60:.1f} 分钟   步数: {len(steps)}   done={wrap.get('done')}")
        print(f"平均: {duration/max(len(steps),1):.2f} s/步")
    if not steps:
        return 0

    by_screen: dict[str, list[float]] = defaultdict(list)
    for row in steps:
        by_screen[str(row.get("screen"))].append(float(row.get("total_ms") or 0))
    print("\n屏幕耗时（秒/步，次数）:")
    for screen, values in sorted(by_screen.items(), key=lambda kv: -sum(kv[1])):
        print(f"  {screen:14s} {sum(values)/len(values)/1000:5.2f}s  x{len(values)}")

    lesson_ms = by_screen.get("lesson", [])
    if lesson_ms and wraps:
        duration = float(wraps[-1].get("ended_at") or 0) - float(wraps[-1].get("started_at") or 0)
        share = sum(lesson_ms) / 1000 / duration if duration else 0
        print(f"\n课程占比: {share*100:.0f}% 的时间花在 {len(lesson_ms)} 个课程步上")

    paused = sum(1 for row in steps if row.get("clicked") is False)
    print(f"暂停让步（你在操作）: {paused} 步")

    log_path = ROOT / "data" / "auto" / f"auto_log_{episode}.log"
    if log_path.exists():
        actions = Counter()
        lessons = []
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "[lesson]" in line:
                lessons.append(line)
                if "SKIP" in line:
                    actions["skip"] += 1
                elif "confirm" in line:
                    actions["confirm"] += 1
                elif "name-pick" in line or "分数" in line:
                    actions["play"] += 1
                elif "cost" in line:
                    actions["cost-learn"] += 1
        print(f"课程动作: {dict(actions)}")
        for line in lessons[-10:]:
            print("   ", line.strip()[:120])

    exams = [row for row in load_rows(ROOT / "data" / "exam_results.jsonl") if row.get("episode") == episode]
    if exams:
        print("\n考试名次:", ", ".join("/".join(row.get("ranks") or []) for row in exams[-3:]))

    costs_path = ROOT / "data" / "knowledge" / "card_costs.json"
    if costs_path.exists():
        costs = json.loads(costs_path.read_text(encoding="utf-8")).get("costs", {})
        print(f"费用知识库: {len(costs)} 张卡")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
