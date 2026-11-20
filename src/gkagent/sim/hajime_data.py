"""初（レギュラー / PRO / MASTER / レジェンド）的验证过数值。

来源：hiro-gakumas-hero `docs/hajime-nia-mechanics.md`（每条标了出处：主数据 / 社区 / 实测 / 逆向）。
这里只收录**被核对过**的数，推断项不进来。

用途：
* 考试：``exam_base`` 给出中間/最終的基础分与封顶，用来算 PERFECT 目标
* 课程：``lesson_tiers`` 给每档课的「回合 / 过关线 / 满分线」，识别不到过关线时兜底
* 收益：``attr_gain`` 复刻「基础值 + floor(基础值 × 加成)」
"""

from __future__ import annotations

from dataclasses import dataclass

# 属性上限（主数据 Produce.idolCardParameterGrowthLimit）
PARAM_CAP = {
    "REGULAR": 1000,
    "PRO": 1500,
    "MASTER": 1800,
    "LEGEND": 3000,
}

# 考试基础分（主数据 ProduceStepAuditionDifficulty，篠澤広的档位）
#   mid_base: 中間基础分 / mid_cap: 中間封顶（打到封顶直接结束）/ final_base: 最終基础分
EXAM_BASE = {
    "REGULAR": {"mid_base": 600, "mid_cap": 900, "final_base": 2450, "rank_pass": 3},
    "PRO": {"mid_base": 1150, "mid_cap": 1700, "final_base": 6950, "rank_pass": 3},
    "MASTER": {"mid_base": 1380, "mid_cap": None, "final_base": 8340, "rank_pass": 3},
}

# 周数 / AP（主数据 Produce）
PRODUCE_WEEKS = {
    "REGULAR": 13,
    "PRO": 16,
    "MASTER": 18,
    "LEGEND": 18,
}
PRODUCE_AP = {"REGULAR": 15, "PRO": 20, "MASTER": 20, "LEGEND": 20}


@dataclass(frozen=True)
class LessonTier:
    """一档课：回合数 / 过关线 / 满分线。"""

    turns: int
    clear: int
    full: int


# 篠澤広（plan2 / やる気流派）的课程档位。
# 注意：序号不是「第几次上」，用哪一档由日程逐周决定（等级 = baseStepLevel + AddStepLevel）。
# REGULAR 的追い込み用**实机**数值（9/90/360、11/165/600），主数据给的是 9/75/300、9/100/400。
LESSON_TIERS = {
    "REGULAR": {
        "normal": (
            LessonTier(6, 25, 50),
            LessonTier(6, 25, 50),
            LessonTier(7, 40, 80),
            LessonTier(7, 40, 80),
        ),
        "sp": (
            LessonTier(6, 40, 80),
            LessonTier(7, 70, 140),
            LessonTier(7, 70, 140),
        ),
        "oikomi": (
            LessonTier(9, 90, 360),
            LessonTier(11, 165, 600),
        ),
    },
    "PRO": {
        "normal": (
            LessonTier(6, 30, 60),
            LessonTier(6, 30, 60),
            LessonTier(7, 55, 110),
            LessonTier(7, 60, 120),
            LessonTier(7, 75, 150),
        ),
        "sp": (
            LessonTier(6, 45, 90),
            LessonTier(7, 85, 170),
            LessonTier(7, 100, 200),
            LessonTier(7, 110, 220),
        ),
        "oikomi": (
            LessonTier(9, 90, 360),
            LessonTier(11, 165, 600),
        ),
    },
    "MASTER": {
        "normal": (),
        "sp": (),
        "oikomi": (
            LessonTier(9, 90, 360),
            LessonTier(11, 165, 600),
        ),
    },
}


def exam_base(mode: str) -> dict:
    return EXAM_BASE[mode]


def perfect_target(clear: int, mode: str = "REGULAR", kind: str = "lesson") -> int:
    """由画面上的过关线反推满分线（找不到对应档位时退回 2× 过关线）。"""
    tiers = LESSON_TIERS.get(mode, {})
    for group in tiers.values():
        for tier in group:
            if tier.clear == clear:
                return tier.full
    if kind == "exam":
        base = EXAM_BASE.get(mode, {})
        cap = base.get("mid_cap")
        if cap:
            return int(cap)
    return clear * 2


def attr_gain(base: int, bonus_permil: int, full: int) -> int:
    """属性收益 = 基础值（封顶满分线） + floor(基础值 × 加成)。

    ``bonus_permil`` 是画面读数的千分比写法（1472 表示 +47.2%）。
    """
    base = max(0, min(int(base), int(full)))
    # 画面读数是「千分比写法」：1472 表示 +47.2%，即加成部分 = (permil-1000)/1000
    bonus = int(base * (int(bonus_permil) - 1000) // 1000)
    return base + max(0, bonus)


def lesson_by_clear(clear: int, turns: int | None = None, mode: str = "REGULAR") -> LessonTier | None:
    """按过关线（可再加回合数）反查档位。"""
    for group in LESSON_TIERS.get(mode, {}).values():
        for tier in group:
            if tier.clear != clear:
                continue
            if turns is None or tier.turns == turns:
                return tier
    return None
