"""几十万局培育模拟：比较不同训练/上课/休息打法。

用法：
    python scripts/sim_produce.py --episodes 50000          # 每种策略 5 万局
    python scripts/sim_produce.py --episodes 20000 --only train_best,mixed

输出：每种策略的三维均值、总和、评价分布、上课/过关次数、CPU 时间。
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

CARD_TABLE = ROOT / "data" / "knowledge" / "card_table.json"


def build_deck() -> list[tuple[str, int, int, int, int]]:
    """卡组：(name, cost, score, condition, focus)，数值来自 card_table。"""
    table = {}
    if CARD_TABLE.exists():
        table = json.loads(CARD_TABLE.read_text(encoding="utf-8")).get("cards", {})
    import re

    master = {}
    master_path = ROOT / "data" / "master" / "produce_cards.json"
    if master_path.exists():
        for row in json.loads(master_path.read_text(encoding="utf-8")):
            master[row.get("name", "")] = row.get("text", "")

    names = [
        "好调", "集中", "魅力的基础", "魅力的基础+", "表现的基础", "表情的基础",
        "准备运动", "粉丝服务", "聊天时间", "凭势而行", "重新开始", "姿势的基础",
        "今天也早安", "视角的基础", "可爱的举动", "猛烈地",
    ]
    deck = []
    for name in names:
        row = table.get(name)
        if not row:
            continue
        score = condition = focus = 0
        for effect in row.get("effects") or []:
            kind = effect.get("type")
            values = [v for v in effect.get("values") or [] if v]
            value = int(values[0]) if values else 0
            if kind == "ExamLesson":
                score = max(score, value)
            elif kind == "ExamLessonBuff":
                condition = max(condition, value)
            elif kind == "ExamConcentration":
                focus = max(focus, value)
        if score == 0 and name in master:
            match = re.search(r"打分[^0-9]{0,8}(\d{1,3})", master[name])
            if match:
                score = int(match.group(1))
        deck.append((name, int(row.get("cost", 4)), score, condition, focus))
    return deck


def run_chunk(task: tuple) -> dict:
    """子进程：跑一段局数，返回聚合结果。"""
    strategy_name, episodes, seed, deck_raw = task
    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import STRATEGIES, ProduceSim, random_strategy

    deck = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in deck_raw]
    if strategy_name == "random":
        strategy = random_strategy(seed)
    else:
        strategy = STRATEGIES[strategy_name]

    totals, grades, clears, exams, lessons = [], Counter(), 0, 0, 0
    for episode in range(episodes):
        sim = ProduceSim(deck, rng_seed=seed + episode)
        result = sim.run(strategy)
        totals.append(result.total)
        grades[result.grade] += 1
        clears += result.cleared
        exams += result.exams_passed
        lessons += result.lessons
    return {
        "strategy": strategy_name,
        "n": episodes,
        "mean_total": round(stats.mean(totals), 1),
        "p90_total": round(sorted(totals)[int(len(totals) * 0.9)], 1),
        "grades": dict(grades.most_common()),
        "clear_rate": round(clears / max(lessons, 1), 3),
        "lessons_per_run": round(lessons / episodes, 2),
        "exams_passed": round(exams / episodes, 2),
    }


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=20000, help="每种策略的局数")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--only", default="train_best,train_lowest,lesson_heavy,mixed,random")
    args = parser.parse_args(argv)

    deck = build_deck()
    print(f"卡组 {len(deck)} 张: {deck}")
    names = [name.strip() for name in args.only.split(",") if name.strip()]
    workers = args.workers or min(8, (len(names)))
    tasks = [(name, args.episodes, 1234 + index * 7919, deck) for index, name in enumerate(names)]

    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_chunk, tasks))
    elapsed = time.perf_counter() - started

    for row in results:
        print(
            f"{row['strategy']:14s} n={row['n']:>7} 总和均值={row['mean_total']:>7} "
            f"p90={row['p90_total']:>7} 过关率={row['clear_rate']:.2f} "
            f"上课/局={row['lessons_per_run']:.1f} 考试通过={row['exams_passed']:.1f} "
            f"评价={row['grades']}"
        )
    total_runs = sum(row["n"] for row in results)
    print(f"\n合计 {total_runs} 局，{elapsed:.1f}s，{total_runs/max(elapsed,1e-9):.0f} 局/秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
