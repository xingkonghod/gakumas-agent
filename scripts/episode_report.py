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

# 阶段归类：回答「这局每个阶段用了多久」。screen 是 ProduceDriver 的 TickResult.screen。
STAGE_BY_SCREEN = {
    "setup-idol": "开局编成",
    "setup-support": "开局编成",
    "setup-memory": "开局编成",
    "setup-confirm": "开局编成",
    "scenario": "开局编成",
    "story": "剧情事件",
    "event-choice": "剧情事件",
    "lesson": "课程",
    "action": "行动选择",
    "action-confirm": "行动选择",
    "drink": "行动选择",
    "drink-keep": "行动选择",
    "card-reward": "奖励领取",
    "result-tap": "奖励领取",
    "toast": "奖励领取",
    "reward-page": "奖励领取",
    "memory": "奖励领取",
    "shop": "奖励领取",
    "exam": "考试",
    "final": "结算",
    "home": "结算",
    "record": "结算",
    "pause": "等待/卡顿",
    "blank": "等待/卡顿",
    "loading": "等待/卡顿",
    "unknown": "等待/卡顿",
    "unknown-tap": "等待/卡顿",
    "button": "等待/卡顿",
}


def stage_of(screen: str) -> str:
    return STAGE_BY_SCREEN.get(screen, "其他")


def print_stage_timings(steps: list[dict], slow_ms: float = 15000.0) -> None:
    """按阶段汇总耗时 + 每 10 步耗时 + 慢步清单。"""
    stages: dict[str, list[float]] = defaultdict(list)
    for row in steps:
        stages[stage_of(str(row.get("screen")))].append(float(row.get("total_ms") or 0))
    total_ms = sum(sum(values) for values in stages.values())
    print("\n阶段耗时（按步累加，秒 / 占比 / 步数）:")
    for stage, values in sorted(stages.items(), key=lambda kv: -sum(kv[1])):
        seconds = sum(values) / 1000
        share = seconds / (total_ms / 1000) * 100 if total_ms else 0
        print(f"  {stage:8s} {seconds:7.1f}s  {share:5.1f}%  {len(values):3d} 步  "
              f"{sum(values)/len(values)/1000:.1f}s/步")

    print("\n每 10 步墙钟（从该步 total_ms 累计）:")
    buckets: list[float] = []
    for index, row in enumerate(steps, start=1):
        buckets.append(float(row.get("total_ms") or 0))
        if index % 10 == 0 or index == len(steps):
            seconds = sum(buckets) / 1000
            print(f"  {index - len(buckets) + 1:3d}-{index:3d}: {seconds:6.1f}s "
                  f"({seconds / len(buckets):.1f}s/步)")
            buckets = []

    slow = [(int(row.get("step") or 0), str(row.get("screen")), float(row.get("total_ms") or 0))
            for row in steps if float(row.get("total_ms") or 0) >= slow_ms]
    print(f"\n慢步（≥{slow_ms/1000:.0f}s）: {len(slow)} 步")
    for step, screen, ms in slow:
        print(f"  step {step:3d} {screen:12s} {ms/1000:5.1f}s")



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

    print_stage_timings(steps)

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
