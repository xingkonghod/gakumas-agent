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
    sim = _sim(lesson_gain_ratio=1.0, support_bonus=1.0)
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


def test_choose_action_excludes_outing_outside_outing_weeks() -> None:
    from gkagent.sim.action_choice import choose_action, random_pool
    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import ProduceConfig

    deck = [CardSpec(name=f"c{i}", cost=3, score=9) for i in range(8)]
    config = ProduceConfig(outing_weeks=(3, 5))
    result = choose_action(deck, random_pool(), attrs=[100, 100, 100], stamina=30, week=4, config=config, episodes=4)
    actions = [row["action"] for row in result["ranking"]]
    assert "outing" not in actions
    result2 = choose_action(deck, random_pool(), attrs=[100, 100, 100], stamina=30, week=3, config=config, episodes=4)
    assert "outing" in [row["action"] for row in result2["ranking"]]


def test_choose_action_prefers_lesson_with_strong_attributes() -> None:
    from gkagent.sim.action_choice import choose_action, random_pool
    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import ProduceConfig

    deck = [CardSpec(name=f"c{i}", cost=3, score=12) for i in range(8)]
    result = choose_action(
        deck, random_pool(3), attrs=[900, 880, 860], stamina=30, week=9,
        config=ProduceConfig(), actions=("train", "rest", "lesson"), episodes=6,
    )
    assert result["action"] in ("lesson", "train")
    assert result["ranking"][0]["eval"] >= result["ranking"][-1]["eval"]


def test_reward_pool_only_contains_modeled_effects() -> None:
    """模拟器没建模的效果（好印象/抽牌/全力/温存…）不能进奖励池，否则会被当 0 分卡。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    pool = sp.build_pool()
    assert pool, "奖励池不应为空"
    assert len(pool) < 200, f"池子异常偏大（{len(pool)}），可能混进了未建模的卡"
    for _name, _cost, score, _condition, _focus in pool:
        assert score > 0


def test_stance_effects_reach_rich_card_spec() -> None:
    """温存/全力值要能从卡表解析进 rich 卡行，再进 CardSpec；旧 5 元组路径不变。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    assert {"ExamPreservation", "ExamFullPowerPoint"} <= sp.MODELED_EFFECTS
    # 旧 5 元组承载不了指針字段，保持排除，避免旧脚本把指針卡当纯白值卡
    assert "ExamPreservation" not in sp.LEGACY_MODELED_EFFECTS
    assert "ExamFullPowerPoint" not in sp.LEGACY_MODELED_EFFECTS

    preservation = sp._effect_fields(
        {"effects": [{"type": "ExamPreservation", "values": [2]}]}
    )
    assert preservation[6] == 2
    full_power = sp._effect_fields(
        {"effects": [{"type": "ExamFullPowerPoint", "values": [4]}]}
    )
    assert full_power[7] == 4

    keep = sp._spec_from_row(sp.CardRow("温存", 2, 0, 0, 0, preservation=1))
    assert keep.preservation == 1
    assert keep.full_power_point == 0
    power = sp._spec_from_row(sp.CardRow("全力", 2, 9, 0, 0, full_power_point=5))
    assert power.full_power_point == 5
    assert power.preservation == 0


def test_playable_value_add_reaches_rich_card_spec() -> None:
    """ExamPlayableValueAdd 从卡表 count 解析成 extra_play，再透传进 CardSpec。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    assert "ExamPlayableValueAdd" in sp.MODELED_EFFECTS
    # 旧 5 元组承载不了 extra_play，保持排除，避免旧脚本丢效果后当成纯白值卡
    assert "ExamPlayableValueAdd" not in sp.LEGACY_MODELED_EFFECTS

    # 卡表里这条效果通常没有 values，用 count 表示 +1/+2
    count_one = sp._effect_fields(
        {"effects": [{"type": "ExamPlayableValueAdd", "values": [], "count": 1}]}
    )
    assert count_one[8] == 1
    count_two = sp._effect_fields(
        {"effects": [{"type": "ExamPlayableValueAdd", "values": [], "count": 2}]}
    )
    assert count_two[8] == 2
    explicit = sp._effect_fields(
        {"effects": [{"type": "ExamPlayableValueAdd", "values": [1]}]}
    )
    assert explicit[8] == 1

    spec = sp._spec_from_row(sp.CardRow("加次数", 0, 0, 0, 0, extra_play=2))
    assert spec.extra_play == 2

    # rich 奖励池里至少要出现一张带额外出牌的卡，且能穿过 _spec_from_row
    rich_pool = sp.build_pool(rich=True)
    assert any(row.extra_play > 0 for row in rich_pool)
    extra_row = next(row for row in rich_pool if row.extra_play > 0)
    assert sp._spec_from_row(extra_row).extra_play == extra_row.extra_play


def test_block_and_parameter_buff_reach_rich_card_spec() -> None:
    """ExamLessonDependBlock / ExamParameterBuff* 解析成新字段，并透传进 CardSpec。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    new_types = {
        "ExamLessonDependBlock",
        "ExamParameterBuff",
        "ExamParameterBuffMultiplePerTurn",
    }
    assert new_types <= sp.MODELED_EFFECTS
    # 旧 5 元组承载不了这些字段，保持排除，避免旧脚本丢效果后当成纯白值卡
    assert not (new_types & sp.LEGACY_MODELED_EFFECTS)

    block = sp._effect_fields(
        {"effects": [{"type": "ExamLessonDependBlock", "values": [3200, 1000]}]}
    )
    assert block[9] == 3200
    assert block[10] == 0 and block[11] == 1

    # 卡表里 ExamParameterBuff 的 values 为空，只有 turn 记持续回合 → 用 1500‰ 兜底
    single = sp._effect_fields(
        {"effects": [{"type": "ExamParameterBuff", "values": [], "turn": 3}]}
    )
    assert single[10] == sp.PARAMETER_BUFF_DEFAULT == 1500
    assert single[11] == 1  # 非 MultiplePerTurn 只作用于本牌

    multi = sp._effect_fields(
        {"effects": [{"type": "ExamParameterBuffMultiplePerTurn", "values": [], "turn": 3}]}
    )
    assert multi[10] == 1500
    assert multi[11] == 3  # 本回合内持续

    explicit = sp._effect_fields({"effects": [{"type": "ExamParameterBuff", "values": [1200]}]})
    assert explicit[10] == 1200  # 有 values 时按 values[0]（千分比）

    spec = sp._spec_from_row(
        sp.CardRow(
            "依赖+加成",
            0,
            0,
            0,
            0,
            block_scale=1000,
            parameter_buff=1500,
            parameter_buff_turns=2,
        )
    )
    assert (spec.block_scale, spec.parameter_buff, spec.parameter_buff_turns) == (1000, 1500, 2)

    # rich 奖励池里要能出现吃审查基准加成的卡，且能穿过 _spec_from_row
    rich_pool = sp.build_pool(rich=True)
    buffed = [row for row in rich_pool if row.parameter_buff > 0]
    assert buffed, "rich 池里应有带审查基准加成的卡"
    row = buffed[0]
    assert sp._spec_from_row(row).parameter_buff == row.parameter_buff > 0


def test_legacy_pool_still_excludes_new_types() -> None:
    """旧 5 元组池子口径不变：仍只收 4 类基础效果，不因新建模而混入新卡。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    legacy = sp.build_pool()
    assert legacy
    for _name, _cost, score, _condition, _focus in legacy:
        assert score > 0
    # 新类型都不在旧集合里，旧池子张数应明显少于 rich 池
    assert len(legacy) < len(sp.build_pool(rich=True))


def test_objective_profiles_differ() -> None:
    """同一组统计下，不同口径应该给出不同排序（课题求稳 vs 冲榜看尾部）。"""
    from gkagent.sim.objective import OBJECTIVES, score

    steady = {"cplus_rate": 0.95, "p50_eval": 5200, "p90_eval": 5600, "p95_eval": 5700, "mean_total": 1600, "exams": 2}
    lucky = {"cplus_rate": 0.60, "p50_eval": 4200, "p90_eval": 6600, "p95_eval": 7800, "mean_total": 1500, "exams": 2}
    assert score("cplus", steady) > score("cplus", lucky)      # 课题：稳定优先
    assert score("rank", lucky) > score("rank", steady)        # 冲榜：尾部优先
    assert score("attr", steady) > score("attr", lucky)
    assert set(OBJECTIVES) == {"cplus", "rank", "attr", "exam"}


def test_objective_unknown_raises() -> None:
    from gkagent.sim.objective import score

    try:
        score("nope", {})
    except KeyError:
        return
    raise AssertionError("未知口径应当抛 KeyError")
