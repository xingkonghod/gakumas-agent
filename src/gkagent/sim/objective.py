"""评价口径（objective）：同一套模拟器，按不同目标选参数。

为什么需要：课题要的是"稳定拿到 C+"（看达成率），冲榜要的是"N 局里的最高分"
（看 P95），两者会选出**不同的策略**——前者求稳，后者该赌。所以目标不能焊死在代码里。

内置口径：
- ``cplus``（默认）：C+ 达成率优先，其次评价点 P50 —— 做课题用
- ``rank``：评价点 P95 优先 —— 冲榜用（best-of-N）
- ``attr``：三维总和均值 —— 只关心属性成长时用
- ``exam``：考试通过数 —— 只关心过本时用

用法：
    from gkagent.sim.objective import score, OBJECTIVES
    score("cplus", stats)      # 越大越好
"""

from __future__ import annotations

from collections.abc import Callable

# 统计口径：这些键由评测脚本汇总出来
STAT_KEYS = (
    "cplus_rate",   # 评价点 ≥ 4500 的比例
    "p50_eval",     # 评价点中位数
    "p90_eval",
    "p95_eval",
    "mean_eval",
    "mean_total",   # 三维总和均值
    "exams",        # 平均通过考试数（0-2）
)

OBJECTIVES: dict[str, Callable[[dict], float]] = {
    # 课题：先保证"稳定能到 C+"，同分再看中位数
    "cplus": lambda s: s.get("cplus_rate", 0) * 10000 + s.get("p50_eval", 0),
    # 冲榜：只看尾部（N 次机会里最好的一次）
    "rank": lambda s: s.get("p95_eval", s.get("p90_eval", 0)),
    # 只关心属性成长
    "attr": lambda s: s.get("mean_total", 0),
    # 只关心能不能过本
    "exam": lambda s: s.get("exams", 0) * 1000 + s.get("p50_eval", 0),
}

DEFAULT_OBJECTIVE = "cplus"


def score(objective: str, stats: dict) -> float:
    fn = OBJECTIVES.get(objective)
    if fn is None:
        raise KeyError(f"未知评价口径: {objective}（可选: {', '.join(OBJECTIVES)}）")
    return float(fn(stats))


def describe() -> dict[str, str]:
    return {
        "cplus": "C+ 达成率优先，其次评价点 P50（做初星课题用）",
        "rank": "评价点 P95 优先（冲榜，best-of-N）",
        "attr": "三维总和均值（只关心属性成长）",
        "exam": "考试通过数优先（只关心过本）",
    }
