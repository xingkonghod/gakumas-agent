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
from typing import NamedTuple

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

CARD_TABLE = ROOT / "data" / "knowledge" / "card_table.json"
# 模拟器（sim/lesson.py）真正建模了的效果类型
MODELED_EFFECTS = {
    "ExamLesson",
    "ExamBlock",
    "ExamLessonBuff",
    "ExamConcentration",
    "ExamCardDraw",
    "ExamReview",
    "ExamLessonDependExamReview",
    "ExamPreservation",
    "ExamFullPowerPoint",
}
# 其它分析脚本（sim_idols / sim_search / …）还按旧 5 元组解包；在它们迁移前，
# build_pool() 默认只收完全落在旧集合里的卡，避免把抽牌/好印象卡当成"只有白值"。
# 温存/全力值同样只能由 rich CardRow 承载，所以只加进 MODELED_EFFECTS：
# 旧 5 元组塞不下这两个字段，硬加进来会被旧脚本当成纯白值卡。
LEGACY_MODELED_EFFECTS = {"ExamLesson", "ExamBlock", "ExamLessonBuff", "ExamConcentration"}

# 旧接口：(name, cost, score, condition, focus)
LegacyCardRow = tuple[str, int, int, int, int]


class CardRow(NamedTuple):
    """build_deck(rich=True) / build_pool(rich=True) 返回的完整卡行。"""

    name: str
    cost: int
    score: int
    condition: int
    focus: int
    draw: int = 0
    impression: int = 0
    impression_scale: int = 0
    preservation: int = 0
    full_power_point: int = 0


def _effect_fields(row: dict) -> tuple[int, int, int, int, int, int, int, int]:
    """从卡表一行的 ``effects`` 提取可喂给 ``CardSpec`` 的字段。

    返回 ``(score, condition, focus, draw, impression, scale,
    preservation, full_power_point)``。同类效果取最大值；``ExamReview``
    是好印象层数，``ExamCardDraw`` 是抽牌数，``ExamLessonDependExamReview``
    是依赖好印象的百分比倍率（1000 = 层数×10），``ExamPreservation`` 是温存
    段階（1/2），``ExamFullPowerPoint`` 是全力值增量。
    """
    score = condition = focus = draw = impression = impression_scale = 0
    preservation = full_power_point = 0
    for effect in row.get("effects") or []:
        kind = effect.get("type")
        values = [v for v in effect.get("values") or [] if v]
        value = int(values[0]) if values else 0
        if not value:
            continue
        if kind == "ExamLesson":
            score = max(score, value)
        elif kind == "ExamLessonBuff":
            condition = max(condition, value)
        elif kind == "ExamConcentration":
            focus = max(focus, value)
        elif kind == "ExamCardDraw":
            draw = max(draw, value)
        elif kind == "ExamReview":
            impression = max(impression, value)
        elif kind == "ExamLessonDependExamReview":
            impression_scale = max(impression_scale, value)
        elif kind == "ExamPreservation":
            preservation = max(preservation, value)
        elif kind == "ExamFullPowerPoint":
            full_power_point = max(full_power_point, value)
    return (
        score,
        condition,
        focus,
        draw,
        impression,
        impression_scale,
        preservation,
        full_power_point,
    )


def build_deck(*, rich: bool = False) -> list[CardRow] | list[LegacyCardRow]:
    """卡组：(name, cost, score, condition, focus[, draw, impression, scale, ...])。

    数值来自 card_table。``rich=True`` 返回 ``CardRow``（带抽牌/好印象/依赖
    倍率/温存/全力值），供本脚本自己用；默认返回旧 5 元组，保持其它分析脚本兼容。
    """
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
    deck: list[CardRow] | list[LegacyCardRow] = []
    for name in names:
        row = table.get(name)
        if not row:
            continue
        (
            score,
            condition,
            focus,
            draw,
            impression,
            impression_scale,
            preservation,
            full_power_point,
        ) = _effect_fields(row)
        if score == 0 and name in master:
            match = re.search(r"打分[^0-9]{0,8}(\d{1,3})", master[name])
            if match:
                score = int(match.group(1))
        cost = int(row.get("cost", 4))
        if rich:
            deck.append(
                CardRow(
                    name,
                    cost,
                    score,
                    condition,
                    focus,
                    draw,
                    impression,
                    impression_scale,
                    preservation,
                    full_power_point,
                )
            )
        else:
            deck.append((name, cost, score, condition, focus))
    return deck


def build_pool(
    max_score: int = 40,
    allow_ssr: bool = False,
    *,
    rich: bool = False,
) -> list[CardRow] | list[LegacyCardRow]:
    """奖励池：真机早期能拿到的技能卡。

    默认排除 SSR/Legend（本账号支援卡弱、早期拿不到高分彩卡），并限制分数 <= 40；
    否则模拟器会"每节课都拿 155 分彩卡"，课程平均 320 分，和真机 60-180 完全不符。

    ``rich=False`` 时只收旧集合里的效果类型并返回旧 5 元组（其它脚本兼容）；
    ``rich=True`` 时使用完整 ``MODELED_EFFECTS``（含温存/全力值）并返回带
    draw/impression/preservation/full_power_point 的 CardRow。
    """
    table = json.loads(CARD_TABLE.read_text(encoding="utf-8")).get("cards", {})
    modeled = MODELED_EFFECTS if rich else LEGACY_MODELED_EFFECTS
    pool: list[CardRow] | list[LegacyCardRow] = []
    for name, row in table.items():
        cost = int(row.get("cost") or 0)
        if cost > 8 or cost < 0:
            continue
        (
            score,
            condition,
            focus,
            draw,
            impression,
            impression_scale,
            preservation,
            full_power_point,
        ) = _effect_fields(row)
        rarity = str(row.get("rarity") or "")
        if not allow_ssr and rarity in ("Ssr", "Legend"):
            continue
        if score <= 0 or score > max_score:
            continue
        # 只收"模拟器能建模"的卡：效果类型必须全在 modeled 里，
        # 否则会被当成 0 分卡（状态附魔等还没建模）
        effect_types = {str(e.get("type") or "") for e in row.get("effects") or []}
        if not effect_types or not effect_types <= modeled:
            continue
        if rich:
            pool.append(
                CardRow(
                    name,
                    cost,
                    score,
                    condition,
                    focus,
                    draw,
                    impression,
                    impression_scale,
                    preservation,
                    full_power_point,
                )
            )
        else:
            pool.append((name, cost, score, condition, focus))
    return pool


def _spec_from_row(row: CardRow | LegacyCardRow):
    """把 build_deck/build_pool 的行转成 LessonSim 的 CardSpec。

    兼容两种行：rich 的 ``CardRow`` 带抽牌/好印象/依赖倍率/指針字段；
    旧 5 元组只有 score/condition/focus（其它分析脚本的默认输出）。
    """
    from gkagent.sim.lesson import CardSpec

    if isinstance(row, CardRow):
        return CardSpec(
            name=row.name,
            cost=row.cost,
            score=row.score,
            condition=row.condition,
            focus=row.focus,
            draw=row.draw,
            impression=row.impression,
            impression_scale=row.impression_scale,
            preservation=row.preservation,
            full_power_point=row.full_power_point,
        )
    name, cost, score, condition, focus = row
    return CardSpec(name=name, cost=cost, score=score, condition=condition, focus=focus)


def run_chunk(task: tuple) -> dict:
    """子进程：跑一段局数，返回聚合结果。"""
    strategy_name, episodes, seed, deck_raw, pool_raw, reward_pick, support = task
    from gkagent.sim.produce import (
        STRATEGIES,
        ProduceConfig,
        ProduceSim,
        eval_value,
        random_strategy,
    )

    deck = [_spec_from_row(row) for row in deck_raw]
    pool = [_spec_from_row(row) for row in pool_raw]
    config = ProduceConfig(reward_pick=reward_pick, support_bonus=support)
    if strategy_name == "random":
        strategy = random_strategy(seed)
    else:
        strategy = STRATEGIES[strategy_name]

    totals, evals, grades, clears, exams, lessons = [], [], Counter(), 0, 0, 0
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=seed + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        totals.append(result.total)
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"):
                rank = row["exam"]["rank"]
                break
        evals.append(eval_value(result.total, rank, result.total * 2))
        grades[result.grade] += 1
        clears += result.cleared
        exams += result.exams_passed
        lessons += result.lessons
    return {
        "strategy": strategy_name,
        "n": episodes,
        "mean_total": round(stats.mean(totals), 1),
        "p90_total": round(sorted(totals)[int(len(totals) * 0.9)], 1),
        # 真正的目标指标：官方评价点（均值/P90）+ C+ 达成率
        "mean_eval": round(stats.mean(evals), 1),
        "p50_eval": round(sorted(evals)[len(evals) // 2], 1),
        "p90_eval": round(sorted(evals)[int(len(evals) * 0.9)], 1),
        "p95_eval": round(sorted(evals)[int(len(evals) * 0.95)], 1),
        "cplus_rate": round(sum(1 for e in evals if e >= 4500) / len(evals), 3),
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
    parser.add_argument("--only", default="train_best,train_lowest,lesson_heavy,mixed,random,smart")
    parser.add_argument("--rewards", choices=["best", "random", "none"], default="best")
    parser.add_argument("--support", type=float, default=1.0)
    args = parser.parse_args(argv)

    # rich=True：把抽牌/好印象/依赖倍率带进 CardSpec（默认 5 元组给其它脚本兼容）
    deck = build_deck(rich=True)
    pool = build_pool(rich=True) if args.rewards != "none" else []
    print(f"卡组 {len(deck)} 张, 奖励池 {len(pool)} 张, 选牌={args.rewards}, 支援加成={args.support}")
    names = [name.strip() for name in args.only.split(",") if name.strip()]
    workers = args.workers or min(8, (len(names)))
    tasks = [
        (name, args.episodes, 1234 + index * 7919, deck, pool, args.rewards, args.support)
        for index, name in enumerate(names)
    ]

    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_chunk, tasks))
    elapsed = time.perf_counter() - started

    for row in results:
        print(
            f"{row['strategy']:14s} n={row['n']:>7} 总和均值={row['mean_total']:>7} "
            f"评价点均值={row['mean_eval']:>7} P90={row['p90_eval']:>7} C+率={row['cplus_rate']*100:3.0f}% "
            f"上课/局={row['lessons_per_run']:.1f} 考试通过={row['exams_passed']:.1f} "
            f"评价={row['grades']}"
        )
    total_runs = sum(row["n"] for row in results)
    print(f"\n合计 {total_runs} 局，{elapsed:.1f}s，{total_runs/max(elapsed,1e-9):.0f} 局/秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
