"""打分规则对照 gakumas-tools（BSD-3）的回归测试。

参考实现：`packages/gakumas-engine/engine/Executor/resolvers.js` 的 `resolveScore()`。
"""

from __future__ import annotations

from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim


def _sim(**buffs) -> LessonSim:
    sim = LessonSim([CardSpec("测试卡", 3, 40)], LessonConfig(turns=5, stamina=30, target_clear=100), rng_seed=1)
    for name, value in buffs.items():
        setattr(sim.buffs, name, value)
    return sim


def _score(sim: LessonSim, card: CardSpec | None = None) -> int:
    return sim._card_award(card or CardSpec("测试卡", 3, 40), uses=0)


def test_condition_multiplier_is_1_5_without_perfect_condition() -> None:
    """没有绝好调时，好调就是 ×1.5（40 → 60）。"""
    assert _score(_sim(condition_turns=3)) == 60


def test_perfect_condition_scales_with_condition_turns() -> None:
    """绝好调下好调倍率随回合数增长：1 + (0.5 + 0.1×turns)。"""
    scores = [_score(_sim(condition_turns=t, perfect_condition_turns=1)) for t in (1, 3, 5)]
    assert scores == sorted(scores)
    assert scores[0] < scores[1] < scores[2]
    # 40 × (1 + 0.5 + 0.1×3) = 40 × 1.8 = 72
    assert scores[1] == 72


def test_metamorphosis_performance_adds_25_percent() -> None:
    """メタモルフォーゼ「披露」分数增益 +25%（40 → 50）。"""
    assert _score(_sim(metamorphosis="performance")) == 50


def test_metamorphosis_preparation_multiplies_by_0_75() -> None:
    """メタモルフォーゼ「支度」×0.75（40 → 30）。"""
    assert _score(_sim(metamorphosis="preparation")) == 30


def test_poor_condition_multiplies_by_0_67() -> None:
    """不调 ×0.67（40 × 0.67 = 26.8 → ceil 27，参考引擎 safeCeil 口径）。"""
    assert _score(_sim(poor_condition_turns=1)) == 27
