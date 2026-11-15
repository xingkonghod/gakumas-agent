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
    "ExamPlayableValueAdd",
    "ExamLessonDependBlock",
    "ExamParameterBuff",
    "ExamParameterBuffMultiplePerTurn",
}
# 卡表里的效果名和卡面语义容易对反，以下以游戏 master 的卡面文本（卡名 + 效果）为准：
#   准备运动「打分+6 / 集中+2」     -> ExamLessonBuff [2]       = 集中
#   平衡感「集中+3」                -> ExamLessonBuff [3]       = 集中
#   打招呼的基础「强气变更」        -> ExamConcentration [1]    = 指針変更（強気 1 段階）
#   不会让出第一「好调 3 回合」     -> ExamParameterBuff turn 3 = 好调 3 回合
#   光之夜「绝好调 2 回合」         -> ExamParameterBuffMultiplePerTurn turn 2
#   祝福+「体力消耗 4 / 打分+40 / 好调 1 回合」
#                                 -> forceStamina 4 + ExamParameterBuff turn 1
# 所以 ExamLessonBuff 给 focus（集中层数）、ExamConcentration 给 strong_level
# （強気段階）、ExamParameterBuff* 给 condition（好调回合数）。不写死 1500‰ 的
# "审查基准加成"兜底：那些 effects 的 values 本来就是空的，兜底会把好调卡变成 ×1.5。
# 其它分析脚本（sim_idols / sim_search / …）还按旧 5 元组解包；在它们迁移前，
# build_pool() 默认只收完全落在旧集合里的卡，避免把抽牌/好印象卡当成"只有白值"。
# 温存/全力值/可出牌次数/元气依赖分/好调回合数/元气同样只能由 rich CardRow 承载，
# 所以只加进 MODELED_EFFECTS：旧 5 元组塞不下这些字段，硬加进来会被旧脚本当成纯白值卡。
# ExamConcentration 现在承载強気段階，旧 5 元组也表达不了，故从旧集合移除。
# 注意：LEGACY_MODELED_EFFECTS 仍含 ExamBlock（旧行为：旧 5 元组不承载元气），
# 只有 rich=True 的 CardRow 才会把 ExamBlock 的 values 映射到 CardSpec.vitality。
LEGACY_MODELED_EFFECTS = {"ExamLesson", "ExamBlock", "ExamLessonBuff"}

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
    extra_play: int = 0
    block_scale: int = 0
    parameter_buff: int = 0
    parameter_buff_turns: int = 1
    strong_level: int = 0
    # ExamBlock：出牌获得的元气（盾）。课程里优先抵牌费，也喂依赖元气的分数
    vitality: int = 0


def _effect_fields(
    row: dict,
) -> tuple[int, int, int, int, int, int, int, int, int, int, int, int, int, int]:
    """从卡表一行的 ``effects`` 提取可喂给 ``CardSpec`` 的字段。

    返回 ``(score, condition, focus, draw, impression, scale, preservation,
    full_power_point, extra_play, block_scale, parameter_buff,
    parameter_buff_turns, strong_level, vitality)``。同类效果取最大值。
    （``vitality`` 放在最后，保持旧索引不变。）

    字段语义以游戏 master 卡面文本为准，effect 名容易误读：

    - ``ExamLesson`` = 打分；``ExamLessonBuff`` = **集中**层数（→ ``focus``）；
    - ``ExamConcentration`` = **指針変更（強気）**段階 1/2（→ ``strong_level``）；
    - ``ExamBlock`` = **元气（盾）**获得量（→ ``vitality``）；
    - ``ExamParameterBuff*`` = **好调/绝好调 N 回合**（→ ``condition = turn``），
      不是审查基准加成；卡表里它们的 ``values`` 是空的，所以 ``parameter_buff``
      只认显式 ``values[0]``（千分比），没有默认 1500‰ 兜底；
    - ``ExamReview`` 是好印象层数，``ExamCardDraw`` 是抽牌数，
      ``ExamLessonDependExamReview`` 是依赖好印象的百分比倍率（1000 = 层数×10），
      ``ExamLessonDependBlock`` 是依赖元气的百分比倍率（同构），
      ``ExamPreservation`` 是温存段階（1/2），``ExamFullPowerPoint`` 是全力值增量，
      ``ExamPlayableValueAdd`` 是本回合可出牌次数增量（卡表里通常没有 values，
      用 ``count`` 表示 +1/+2）。
    """
    score = condition = focus = draw = impression = impression_scale = 0
    preservation = full_power_point = extra_play = 0
    block_scale = parameter_buff = 0
    parameter_buff_turns = 1
    strong_level = 0
    vitality = 0
    for effect in row.get("effects") or []:
        kind = effect.get("type")
        values = [v for v in effect.get("values") or [] if v]
        value = int(values[0]) if values else 0
        if kind == "ExamPlayableValueAdd":
            extra_play = max(extra_play, value or int(effect.get("count") or 1))
            continue
        if kind in ("ExamParameterBuff", "ExamParameterBuffMultiplePerTurn"):
            # 卡面是「好调 N 回合 / 绝好调 N 回合」（祝福+、不会让出第一…），
            # 不是 1500‰ 的审查基准加成。turn 才是持续回合数。
            turn = int(effect.get("turn") or 0)
            if turn > 0:
                condition = max(condition, turn)
            parameter_buff = max(parameter_buff, value)
            if kind == "ExamParameterBuffMultiplePerTurn" and parameter_buff > 0:
                # 显式数值时才保留"整回合持续"语义；卡表实际 values 为空 → 不生效。
                parameter_buff_turns = max(parameter_buff_turns, turn or 2)
            continue
        if not value:
            continue
        if kind == "ExamLesson":
            score = max(score, value)
        elif kind == "ExamLessonBuff":
            # 卡面是「集中+2/+3」（准备运动/平衡感），不是好调。
            focus = max(focus, value)
        elif kind == "ExamConcentration":
            # 卡面是「強気変更」（打招呼的基础），values[0] 是 1/2 段階；不是集中。
            strong_level = max(strong_level, value)
        elif kind == "ExamBlock":
            # 元气（盾）：课程里先扣元气再扣体力；没有伤害来源，所以不是"挡伤害"
            vitality = max(vitality, value)
        elif kind == "ExamCardDraw":
            draw = max(draw, value)
        elif kind == "ExamReview":
            impression = max(impression, value)
        elif kind == "ExamLessonDependExamReview":
            impression_scale = max(impression_scale, value)
        elif kind == "ExamLessonDependBlock":
            block_scale = max(block_scale, value)
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
        extra_play,
        block_scale,
        parameter_buff,
        parameter_buff_turns,
        strong_level,
        vitality,
    )


def build_deck(*, rich: bool = False) -> list[CardRow] | list[LegacyCardRow]:
    """卡组：(name, cost, score, condition, focus[, draw, impression, ...])。

    数值来自 card_table。``rich=True`` 返回 ``CardRow``（带抽牌/好印象/依赖
    倍率/温存/全力值/可出牌次数/元气），供本脚本自己用；默认返回旧 5 元组，
    保持其它分析脚本兼容。
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
            extra_play,
            block_scale,
            parameter_buff,
            parameter_buff_turns,
            strong_level,
            vitality,
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
                    extra_play,
                    block_scale,
                    parameter_buff,
                    parameter_buff_turns,
                    strong_level,
                    vitality,
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
    ``rich=True`` 时使用完整 ``MODELED_EFFECTS``（含温存/全力值/可出牌次数/
    元气依赖分/好调回合数/元气）并返回带 draw/impression/preservation/
    full_power_point/extra_play/block_scale/parameter_buff/strong_level/vitality
    的 CardRow。
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
            extra_play,
            block_scale,
            parameter_buff,
            parameter_buff_turns,
            strong_level,
            vitality,
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
                    extra_play,
                    block_scale,
                    parameter_buff,
                    parameter_buff_turns,
                    strong_level,
                    vitality,
                )
            )
        else:
            pool.append((name, cost, score, condition, focus))
    return pool


def _spec_from_row(row: CardRow | LegacyCardRow):
    """把 build_deck/build_pool 的行转成 LessonSim 的 CardSpec。

    兼容两种行：rich 的 ``CardRow`` 带抽牌/好印象/依赖倍率/指針/可出牌次数/
    元气依赖分/好调回合数/強気段階/元气字段；旧 5 元组只有 score/condition/focus
    （其它分析脚本的默认输出）。
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
            extra_play=row.extra_play,
            block_scale=row.block_scale,
            parameter_buff=row.parameter_buff,
            parameter_buff_turns=row.parameter_buff_turns,
            strong_level=row.strong_level,
            vitality=row.vitality,
        )
    name, cost, score, condition, focus = row
    return CardSpec(name=name, cost=cost, score=score, condition=condition, focus=focus)


def run_chunk(task: tuple) -> dict:
    """子进程：跑一段局数，返回聚合结果。"""
    strategy_name, episodes, seed, deck_raw, pool_raw, reward_pick, support, audition = task
    from gkagent.sim.produce import (
        STRATEGIES,
        ProduceConfig,
        ProduceSim,
        eval_value,
        random_strategy,
    )

    deck = [_spec_from_row(row) for row in deck_raw]
    pool = [_spec_from_row(row) for row in pool_raw]
    config = ProduceConfig(
        reward_pick=reward_pick,
        support_bonus=support,
        audition_coefficient=audition,
    )
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
        # 终试得分已乘考试属性倍率（result.exam_score），再喂官方评价公式
        evals.append(eval_value(result.total, rank, result.exam_score))
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
    parser.add_argument("--support", type=float, default=1.2,
                        help="训练/课程收益倍率（默认 1.2 = 真机支援卡均值 Lv20 校准值）")
    parser.add_argument("--audition-coefficient", type=float, default=4.11,
                        help="考试/舞台属性倍率（默认 4.11 = 真机屏幕「歌唱 411%%」；"
                             "课程仍 1.0，传 1.0 可复现改前口径）")
    args = parser.parse_args(argv)

    # rich=True：把抽牌/好印象/依赖倍率带进 CardSpec（默认 5 元组给其它脚本兼容）
    deck = build_deck(rich=True)
    pool = build_pool(rich=True) if args.rewards != "none" else []
    print(
        f"卡组 {len(deck)} 张, 奖励池 {len(pool)} 张, 选牌={args.rewards}, "
        f"支援加成={args.support}, 考试属性倍率={args.audition_coefficient}"
    )
    names = [name.strip() for name in args.only.split(",") if name.strip()]
    workers = args.workers or min(8, (len(names)))
    tasks = [
        (
            name,
            args.episodes,
            1234 + index * 7919,
            deck,
            pool,
            args.rewards,
            args.support,
            args.audition_coefficient,
        )
        for index, name in enumerate(names)
    ]

    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_chunk, tasks))
    elapsed = time.perf_counter() - started

    for row in results:
        print(
            f"{row['strategy']:14s} n={row['n']:>7} 总和均值={row['mean_total']:>7} "
            f"评价点均值={row['mean_eval']:>7} P50={row['p50_eval']:>7} "
            f"P90={row['p90_eval']:>7} C+率={row['cplus_rate']*100:3.0f}% "
            f"上课/局={row['lessons_per_run']:.1f} 考试通过={row['exams_passed']:.1f} "
            f"评价={row['grades']}"
        )
    total_runs = sum(row["n"] for row in results)
    print(f"\n合计 {total_runs} 局，{elapsed:.1f}s，{total_runs/max(elapsed,1e-9):.0f} 局/秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
