"""培育级模拟器的行为测试（不联网、不碰游戏）。"""

from __future__ import annotations

from gkagent.sim.lesson import CardSpec
from gkagent.sim.produce import (
    ProduceConfig,
    ProduceSim,
    StrategyParams,
    grade_for,
    strategy_from_params,
)

DECK = [
    CardSpec(name="训练用牌", cost=3, score=9),
    CardSpec(name="大牌", cost=5, score=27),
    CardSpec(name="免费牌", cost=0, score=4),
]


def _sim(seed: int = 3, **kwargs) -> ProduceSim:
    config = ProduceConfig(**kwargs) if kwargs else ProduceConfig()
    return ProduceSim(DECK, config=config, rng_seed=seed)


def test_training_raises_attribute_and_spends_stamina() -> None:
    sim = _sim()
    before = list(sim.attrs)
    sim.train(sim.best_attribute())
    assert sim.attrs[sim.best_attribute()] > before[sim.best_attribute()]
    assert sim.stamina < sim.config.start_stamina


def test_full_run_records_one_trace_row_per_week() -> None:
    sim = _sim()
    result = sim.run(strategy_from_params(StrategyParams()))
    assert len(sim.trace) == sim.config.weeks
    assert all("week" in row and "action" in row for row in sim.trace)
    assert result.attrs == tuple(sim.attrs)
    assert result.grade == grade_for(sum(sim.attrs))


def test_exam_rank_uses_six_competitors() -> None:
    sim = _sim()
    sim.attrs = [10, 10, 10]  # 极弱
    weak = sim.exam(1)
    assert weak["rank"] >= 4
    assert weak["passed"] is False

    sim.attrs = [900, 900, 900]  # 极强
    strong = sim.exam(1)
    assert strong["rank"] == 1
    assert strong["passed"] is True


def test_lesson_growth_ratio() -> None:
    """课程加的属性 ≈ 得分 × lesson_gain_ratio。"""
    sim = _sim(lesson_gain_ratio=1.0)
    before = list(sim.attrs)
    sim.lesson()
    gained = sum(sim.attrs) - sum(before)
    detail = sim.last_lesson
    assert detail is not None
    # 可能没打出任何牌得 0 分，但只要有分，成长就不为负
    assert gained >= 0
    if detail["score"] > 0:
        assert abs(gained - detail["score"]) <= 3


def test_strategy_rests_below_threshold() -> None:
    sim = _sim()
    sim.stamina = 5
    strategy = strategy_from_params(StrategyParams(rest_threshold=10))
    assert strategy(sim) == "rest"


def test_strategy_lessons_on_cadence() -> None:
    sim = _sim()
    sim.week = 3
    sim.stamina = 30
    strategy = strategy_from_params(StrategyParams(lesson_every=3, rest_threshold=6))
    assert strategy(sim) == "lesson"
    sim.week = 4
    assert strategy(sim) in ("train", "train_low")


def test_reward_adds_card_to_deck() -> None:
    sim = _sim(reward_pick="best")
    sim.reward_pool = [CardSpec(name="奖励牌", cost=2, score=30)]
    size = len(sim.deck)
    sim.lesson()
    assert len(sim.deck) == size + 1
    assert sim.reward_picks == 1


def test_no_reward_when_disabled() -> None:
    sim = _sim(reward_pick="none")
    sim.reward_pool = [CardSpec(name="奖励牌", cost=2, score=30)]
    size = len(sim.deck)
    sim.lesson()
    assert len(sim.deck) == size


def test_grade_thresholds_are_monotonic() -> None:
    grades = [grade_for(total) for total in (200, 600, 800, 1000, 1200, 1500, 1800, 2100)]
    order = ["E", "D", "C", "C+", "B", "B+", "A", "S"]
    assert [order.index(grade) for grade in grades] == sorted(order.index(grade) for grade in grades)
