"""初模式验证数值的测试：档位反查、收益公式、考试基础分。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gkagent.sim.hajime_data import (
    EXAM_BASE,
    attr_gain,
    lesson_by_clear,
    perfect_target,
)


def test_exam_base_regular():
    assert EXAM_BASE["REGULAR"]["mid_base"] == 600
    assert EXAM_BASE["REGULAR"]["mid_cap"] == 900
    assert EXAM_BASE["REGULAR"]["final_base"] == 2450


def test_perfect_target_from_clear():
    # REGULAR 通常课 6 回合 25 过关 → 满分 50
    assert perfect_target(25, "REGULAR") == 50
    # SP 课 70 过关 → 140
    assert perfect_target(70, "REGULAR") == 140
    # 追い込み实机档 165 过关 → 600
    assert perfect_target(165, "REGULAR") == 600


def test_attr_gain_matches_real_observation():
    # 〔实〕REGULAR 第 9 周 Vo SP 课：满分线 140、加成 1272 → +178
    # 140 + floor(140 × 0.272) = 140 + 38 = 178
    assert attr_gain(140, 1272, 140) == 178


def test_attr_gain_caps_at_full():
    # 打超过满分线按满分线算
    assert attr_gain(999, 2000, 140) == 280


def test_lesson_by_clear():
    tier = lesson_by_clear(90, 9, "REGULAR")
    assert tier is not None
    assert tier.full == 360
    assert lesson_by_clear(12345, None, "REGULAR") is None
