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


def test_real_attribute_vector_fails_final_exam() -> None:
    """真机那局 170/147/315（偏堆）→ power 201.6，进不了前 3，复现"不合格"。"""
    sim = _sim()
    sim.attrs = [170, 147, 315]
    exam = sim.exam(1)
    assert exam["passed"] is False
    assert exam["rank"] >= 4


def test_balanced_beats_skewed_at_same_total() -> None:
    """同样总和，均衡三维比偏堆更容易进前 3（这是"补短板"策略的依据）。"""
    balanced = _sim()
    balanced.attrs = [205, 205, 205]      # total 615
    skewed = _sim()
    skewed.attrs = [123, 154, 338]        # total 615，偏视觉
    assert balanced.exam(1)["passed"] is True
    assert skewed.exam(1)["passed"] is False


def test_calibration_record_dedup_and_delta(tmp_path) -> None:
    from gkagent.data import calibration

    path = tmp_path / "attrs.jsonl"
    assert calibration.record([10, 20, 30], path=path) is True
    assert calibration.record([10, 20, 30], path=path) is False   # 重复不写
    assert calibration.record([20, 25, 40], path=path) is True
    summary = calibration.summarize(path)
    assert summary["records"] == 2
    assert summary["weeks"] == 1
    assert summary["deltas"][0]["delta"] == [10, 5, 10]
    assert summary["deltas"][0]["total"] == 25


def test_calibration_estimate_ratio(tmp_path) -> None:
    from gkagent.data import calibration

    path = tmp_path / "attrs.jsonl"
    calibration.record([0, 0, 0], path=path)
    calibration.record([60, 60, 60], path=path)   # 一周增长 180
    ratio = calibration.estimate_ratio([450], path=path)  # 本周课程得 450
    assert ratio is not None and abs(ratio - 0.4) < 0.01
