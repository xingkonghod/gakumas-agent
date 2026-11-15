"""培育级模拟器的行为测试（不联网、不碰游戏）。"""

from __future__ import annotations

import json
from functools import lru_cache

from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.produce import (
    ProduceConfig,
    ProduceSim,
    StrategyParams,
    eval_value,
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
    last_exam = next(row["exam"] for row in reversed(sim.trace) if row.get("exam"))
    assert result.exam_score == last_exam["score"]
    assert result.grade == grade_for(
        sum(sim.attrs), last_exam["rank"], result.exam_score
    )


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


def test_calibrated_config_defaults() -> None:
    """默认值锚定真机 C+/5577：课程成长 0.5、支援卡 1.2、考试属性倍率 411%。"""
    config = ProduceConfig()
    assert config.lesson_gain_ratio == 0.5
    assert config.support_bonus == 1.2
    assert config.audition_coefficient == 4.11


@lru_cache(maxsize=2)
def _calibrated_400_episode_means(ratio: float) -> tuple[float, tuple[float, float, float]]:
    """用真机卡组/奖励池跑 400 局，返回 (三维总和均值, 三维均值)。

    固定种子 5000..5399，结果可复现；缓存避免两个用例重复跑同一组。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    deck = [sp._spec_from_row(row) for row in sp.build_deck(rich=True)]
    pool = [sp._spec_from_row(row) for row in sp.build_pool(rich=True)]
    config = ProduceConfig(lesson_gain_ratio=ratio)
    strategy = strategy_from_params(StrategyParams())
    totals: list[int] = []
    attrs = [0, 0, 0]
    for episode in range(400):
        sim = ProduceSim(deck, config=config, rng_seed=5000 + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        totals.append(result.total)
        for index, value in enumerate(result.attrs):
            attrs[index] += value
    return sum(totals) / len(totals), tuple(value / len(totals) for value in attrs)


def test_default_ratio_lands_in_real_machine_three_attr_band() -> None:
    """默认 ratio=0.5：400 局三维总和均值落在真机标定区间 900-1300。"""
    mean_total, mean_attrs = _calibrated_400_episode_means(0.5)
    assert 900 <= mean_total <= 1300, f"三维总和均值 {mean_total:.1f} 偏离真机标定区间"
    assert all(200 <= value <= 700 for value in mean_attrs), mean_attrs


def test_ratio_one_doubles_three_attrs_vs_calibrated_default() -> None:
    """把 ratio 改回机制值 1.0：课程成长翻倍，三维总和均值约翻倍（校准反向验证）。"""
    calibrated, _ = _calibrated_400_episode_means(0.5)
    doubled, _ = _calibrated_400_episode_means(1.0)
    assert 1.8 <= doubled / calibrated <= 2.2, f"{calibrated:.1f} -> {doubled:.1f}"


def test_strategy_rests_below_threshold() -> None:
    sim = _sim()
    sim.stamina = 5
    strategy = strategy_from_params(StrategyParams(rest_threshold=10))
    assert strategy(sim) == "rest"


def test_strategy_rests_instead_of_lesson_when_stamina_below_gate() -> None:
    """体力 5 + lesson_min_stamina=12：即使轮到上课周也改休息（真机事故回归）。"""
    sim = _sim()
    sim.week = 1
    sim.stamina = 5
    strategy = strategy_from_params(
        StrategyParams(rest_threshold=0, lesson_every=1, lesson_min_stamina=12)
    )
    assert strategy(sim) == "rest"

    # 体力 20 达标 → 正常上课
    sim.stamina = 20
    assert strategy(sim) == "lesson"


def test_strategy_does_not_train_when_stamina_insufficient() -> None:
    """体力低于 min_stamina_to_train 时不出训练，改休息；直接调 train() 也不发生。"""
    sim = _sim()
    sim.week = 2
    sim.stamina = 5
    strategy = strategy_from_params(
        StrategyParams(rest_threshold=0, lesson_every=0, min_stamina_to_train=12)
    )
    assert strategy(sim) == "rest"

    before = list(sim.attrs)
    assert sim.train(sim.best_attribute()) is False
    assert sim.attrs == before
    assert sim.stamina >= 0


def test_stamina_never_goes_negative_on_failed_lesson() -> None:
    """体力不足时上课打不出牌：返回失败标记、不加属性、体力绝不扣成负数。"""
    sim = _sim()
    sim.stamina = 5
    before = list(sim.attrs)
    assert sim.lesson() is False
    assert sim.last_lesson is not None
    assert sim.last_lesson["grade"] == "FAILED"
    assert sim.attrs == before
    assert sim.stamina >= 0

    # 连续失败也不累计负体力
    assert sim.lesson() is False
    assert sim.stamina >= 0


def test_search_grid_covers_lesson_stamina_gate() -> None:
    """搜索空间必须包含体力门，否则重跑也找不到新的 lesson_min_stamina。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_search as ss

    assert "lesson_min_stamina" in ss.GRID
    values = ss.GRID["lesson_min_stamina"]
    assert 12 in values
    assert all(isinstance(value, int) for value in values)


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


def test_exam_score_uses_audition_coefficient() -> None:
    """考试得分 = 2×三维总和×411%；课程倍率 1.0 时退回旧的 2×总和 proxy。"""
    attrs = [450, 400, 392]  # total 1242，典型局
    calibrated = _sim(audition_coefficient=4.11)
    calibrated.attrs = attrs
    exam = calibrated.exam(1)
    assert exam["score"] == int(sum(attrs) * 2 * 4.11) == 10209
    # 课程里属性倍率 1.0：课程得分/旧 proxy 不受影响
    legacy = _sim(audition_coefficient=1.0)
    legacy.attrs = attrs
    assert legacy.exam(1)["score"] == sum(attrs) * 2 == 2484


def test_eval_points_rise_with_audition_coefficient() -> None:
    """属性倍率 0.9 / 1.0 / 4.11 三档：考试得分与官方评价点都单调上升。"""
    # total 1210 / power 409.2 → 期末第 3 名（对照真机 5577 那局的 C+ 门槛）
    attrs = [450, 400, 360]
    total = sum(attrs)
    rows = []
    for coefficient in (0.9, 1.0, 4.11):
        sim = _sim(audition_coefficient=coefficient)
        sim.attrs = attrs
        exam = sim.exam(1)
        rows.append((exam["score"], eval_value(total, exam["rank"], exam["score"])))
    scores = [row[0] for row in rows]
    points = [row[1] for row in rows]
    assert scores == sorted(scores) and len(set(scores)) == 3
    assert points == sorted(points) and len(set(points)) == 3
    # 真机那局：旧口径 C（<4500），411% 后 C+（>=4500）
    assert points[1] < 4500 <= points[2]


@lru_cache(maxsize=1)
def _typical_run_evals(episodes: int = 200) -> tuple[int, ...]:
    """典型一局（默认策略 + 真机卡组/奖励池）的官方评价点，固定 seed 可复现。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    deck = [sp._spec_from_row(row) for row in sp.build_deck(rich=True)]
    pool = [sp._spec_from_row(row) for row in sp.build_pool(rich=True)]
    config = ProduceConfig()
    strategy = strategy_from_params(StrategyParams())
    evals: list[int] = []
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=7000 + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"):
                rank = row["exam"]["rank"]
                break
        evals.append(eval_value(result.total, rank, result.exam_score))
    return tuple(evals)


def test_typical_run_eval_p50_matches_real_machine_cplus() -> None:
    """典型一局评价点 P50 落在 5000-5800，对照真机 C+/5577。"""
    ordered = sorted(_typical_run_evals())
    p50 = ordered[len(ordered) // 2]
    assert 5000 <= p50 <= 5800, f"评价点 P50={p50} 偏离真机 C+/5577 标定区间"


def test_policy_json_audition_coefficient_matches_config_default() -> None:
    """policy.json 的 produce.audition_coefficient 与代码默认值一致（不丢键/不漂移）。"""
    import json
    from pathlib import Path

    policy_path = Path(__file__).resolve().parents[1] / "data" / "knowledge" / "policy.json"
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    assert raw["produce"]["audition_coefficient"] == 4.11
    assert raw["produce"]["audition_coefficient"] == ProduceConfig().audition_coefficient


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
    # 从满体力开始：上课后仍够下周再上课，lesson 严格优于先休息。
    # （体力 30 时新体力门会让 lesson 先手与 rest 打平，不再是 lesson 独优。）
    result = choose_action(
        deck, random_pool(3), attrs=[900, 880, 860], stamina=35, week=9,
        config=ProduceConfig(), actions=("train", "rest", "lesson"), episodes=6,
    )
    assert result["action"] == "lesson"
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


def test_block_and_condition_reach_rich_card_spec() -> None:
    """ExamLessonDependBlock → block_scale；ExamParameterBuff* → 好调回合数（condition）。"""
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

    # 卡表里 ExamParameterBuff 的 values 为空、turn 才是持续回合；卡面是「好调 N 回合」，
    # 不是 1500‰ 的审查基准加成（旧实现兜底后会把这张牌自己的分 ×1.5，导致分数虚高）。
    single = sp._effect_fields(
        {"effects": [{"type": "ExamParameterBuff", "values": [], "turn": 3}]}
    )
    assert single[1] == 3       # condition = 好调 3 回合
    assert single[10] == 0      # 不再兜底 1500‰
    assert single[11] == 1

    multi = sp._effect_fields(
        {"effects": [{"type": "ExamParameterBuffMultiplePerTurn", "values": [], "turn": 2}]}
    )
    assert multi[1] == 2        # 绝好调也按好调回合数建模（保守近似）
    assert multi[10] == 0
    assert multi[11] == 1

    explicit = sp._effect_fields({"effects": [{"type": "ExamParameterBuff", "values": [1200]}]})
    assert explicit[10] == 1200  # 只有显式 values[0] 才当审查基准加成（千分比）
    assert explicit[1] == 0

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

    # rich 池里不应再有"卡表空 values 却吃 1500‰"的卡；好调卡改为 condition > 0
    rich_pool = sp.build_pool(rich=True)
    assert not [row for row in rich_pool if row.parameter_buff > 0]
    conditioned = [row for row in rich_pool if row.condition > 0]
    assert conditioned, "rich 池里应有带好调回合数的卡"
    row = conditioned[0]
    assert sp._spec_from_row(row).condition == row.condition > 0


def test_lesson_buff_is_focus_and_concentration_is_stance() -> None:
    """用真实卡表锁定目标语义：ExamLessonBuff=集中、ExamConcentration=指針変更（強気）。

    证据（data/master/produce_cards.json 卡面文本）：
    - 准备运动「打分+6 / 集中+2」→ ExamLessonBuff [2]
    - 平衡感「集中+3」→ ExamLessonBuff [3]
    - 打招呼的基础「强气变更」→ ExamConcentration [1]
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    table = json.loads(sp.CARD_TABLE.read_text(encoding="utf-8"))["cards"]

    warmup = sp._effect_fields(table["准备运动"])
    assert warmup[2] == 2, "准备运动的「集中+2」必须解析成 focus=2"
    assert warmup[1] == 0, "准备运动不应被解析成好调（condition）"

    balance = sp._effect_fields(table["平衡感"])
    assert balance[2] == 3, "平衡感的「集中+3」必须解析成 focus=3"
    assert balance[1] == 0

    greeting = sp._effect_fields(table["打招呼的基础"])
    assert greeting[12] == 1, "打招呼的基础「强气变更」必须解析成強気 1 段階"
    assert greeting[2] == 0, "指針変更不是集中，不能塞进 focus"

    deck = {row.name: row for row in sp.build_deck(rich=True)}
    assert "准备运动" in deck
    warmup_spec = sp._spec_from_row(deck["准备运动"])
    assert (warmup_spec.score, warmup_spec.focus, warmup_spec.condition) == (6, 2, 0)

    stance_row = sp._spec_from_row(sp.CardRow("強気", 0, 0, 0, 0, strong_level=1))
    assert stance_row.strong_level == 1


def test_parameter_buff_condition_only_helps_later_cards() -> None:
    """好调卡的 N 回合走 condition：本牌不吃自己刚加的 ×1.5，后续牌才吃。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    fields = sp._effect_fields(
        {"effects": [{"type": "ExamParameterBuff", "values": [], "turn": 3}]}
    )
    assert fields[1] == 3 and fields[10] == 0
    buff = sp._spec_from_row(sp.CardRow("好调卡", 0, 10, fields[1], 0))
    assert (buff.score, buff.condition, buff.parameter_buff) == (10, 3, 0)

    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        LessonConfig(turns=2, stamina=10, target_clear=1, hand_size=3),
        rng_seed=0,
    )
    sim.hand = [buff, CardSpec("打分", 0, 10), CardSpec("占位", 0, 0)]
    sim.deck = []
    sim.discard = []

    sim.step(0)  # 本牌 10 分，不吃自己刚给的好调（旧实现会 ×1.5 → 15）
    assert sim.score == 10
    assert sim.buffs.condition_turns == 3

    sim.step(0)  # 后续牌好调 ×1.5：10 + 15
    assert sim.score == 25


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


def test_exam_block_reaches_rich_card_spec_as_vitality() -> None:
    """ExamBlock 的元气值要解析成 CardSpec.vitality（课程里优先抵牌费）。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    fields = sp._effect_fields({"effects": [{"type": "ExamBlock", "values": [4]}]})
    assert fields[13] == 4

    spec = sp._spec_from_row(sp.CardRow("表现的基础", 0, 0, 0, 0, vitality=4))
    assert spec.vitality == 4

    rich_deck = {row.name: row for row in sp.build_deck(rich=True)}
    assert rich_deck["表现的基础"].vitality == 4
    assert "视角的基础" in rich_deck
    assert rich_deck["视角的基础"].vitality == 1


def test_lesson_trace_contains_per_turn_skip_flags() -> None:
    """培育 trace 里带课程的逐回合 trace：每行都有 skipped，汇总字段与之一致。"""
    sim = _sim()
    sim.step(lambda _state: "lesson")
    row = sim.trace[-1]
    assert row["action"] == "lesson"
    detail = row["lesson"]
    assert detail is not None
    turns = detail["turns"]
    assert turns
    assert all(isinstance(turn["skipped"], bool) for turn in turns)
    assert detail["skipped"] == any(turn["skipped"] for turn in turns)

