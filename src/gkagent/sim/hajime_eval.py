"""初（レギュラー/PRO/MASTER）的最终评价计算。

公式与常数来自社区已核对的版本（hiro-gakumas-hero `docs/hajime-nia-mechanics.md` §3.1，
他们用自己的 4 局实机逐分对过）。这里独立实现，用于校验我们的模拟器与真实采集。

评价 = floor(属性和 × 2.3) + 名次分 + 最終試験分数的分段折算
  * 第 1 名：每项属性先 +30，再按属性上限截断
  * 名次分：1 → 1700、2 → 900、3 → 500
  * 分段折算：0-5000 每分 0.30、5000-1万 0.15、1-2万 0.08、2-3万 0.04、3-4万 0.02、4万+ 0.01
"""

from __future__ import annotations

import math

PARAM_FACTOR = 2.3
FIRST_PARAM_BONUS = 30
RANK_BONUS = {1: 1700, 2: 900, 3: 500}
SCORE_SLOPES = ((5000, 0.30), (10000, 0.15), (20000, 0.08), (30000, 0.04), (40000, 0.02), (None, 0.01))
ATTRS = ("Vo", "Da", "Vi")


def score_part(final_score: int) -> float:
    """最終試験分数 → 评价里加的那部分（分段斜率累加，不取整）。"""
    part, lo = 0.0, 0
    for hi, slope in SCORE_SLOPES:
        top = final_score if hi is None else min(final_score, hi)
        if top > lo:
            part += (top - lo) * slope
        if hi is None or final_score <= hi:
            break
        lo = hi
    return part


def hajime_evaluation(params: dict[str, int], final_score: int, rank: int, cap: int = 1000) -> int:
    """params 传最終考试之前的属性（不含第 1 名的 +30）。"""
    bonus = FIRST_PARAM_BONUS if rank == 1 else 0
    total = sum(min(cap, max(0, int(params.get(a, 0))) + bonus) for a in ATTRS)
    return (
        math.floor(total * PARAM_FACTOR + 1e-9)
        + RANK_BONUS.get(rank, 0)
        + math.floor(score_part(final_score) + 1e-9)
    )


def reverse_final_score(params: dict[str, int], target: int, rank: int, cap: int = 1000) -> int:
    """反推：要得到 target 这个评价，最終試験分数应该是多少。"""
    lo, hi = 0, 40000
    while lo < hi:
        mid = (lo + hi) // 2
        if hajime_evaluation(params, mid, rank, cap) < target:
            lo = mid + 1
        else:
            hi = mid
    return lo
