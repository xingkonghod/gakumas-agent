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


def test_exam_rank_uses_exam_score() -> None:
    """考试名次按局内最终得分与 NPC 分数档比；属性高低不直接决定名次。"""
    weak = _sim()
    weak.deck = [CardSpec("弱牌", 4, 1)]
    weak.attrs = [900, 900, 900]
    weak_exam = weak.exam(1)
    assert weak_exam["rank"] >= 4
    assert weak_exam["passed"] is False

    strong = _sim()
    strong.deck = [CardSpec("强牌", 0, 1000)]
    strong.attrs = [10, 10, 10]
    strong_exam = strong.exam(1)
    assert strong_exam["rank"] == 1
    assert strong_exam["passed"] is True


def test_lesson_growth_ratio() -> None:
    """旧口径（constants）：课程加的属性 ≈ 得分 × lesson_gain_ratio。"""
    sim = _sim(
        lesson_gain_ratio=1.0,
        support_bonus=1.0,
        support_lesson_bonus=0.0,
        schedule_source="constants",
    )
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
    """默认值锚定 16 周官方排期 + 真机 C+/5992 口径。"""
    config = ProduceConfig()
    assert config.schedule_source == "official"
    assert config.weeks == 16
    assert config.exam_weeks == (7, 16)
    assert config.lesson_gain_ratio == 0.5
    assert config.support_bonus == 1.2
    assert config.audition_coefficient == 4.11


def test_official_schedule_lesson_uses_clear_plus_perfect(tmp_path) -> None:
    """official 模式：上课收益 = CLEAR + PERFECT，训练收益 = train_clear。"""
    path = tmp_path / "official.json"
    path.write_text(
        json.dumps(
            {
                "schedule": [
                    {"week": 1, "action": "lesson", "clear": 40, "perfect": 25, "train_clear": 40}
                ]
            }
        ),
        encoding="utf-8",
    )
    lesson_sim = _sim(schedule_path=str(path), support_lesson_bonus=0.0)
    lesson_sim.lesson()
    assert lesson_sim.last_lesson is not None
    assert lesson_sim.last_lesson["attr_gain"] == 65
    assert lesson_sim.last_lesson["gain_source"] == "official"

    train_sim = _sim(schedule_path=str(path))
    before = list(train_sim.attrs)
    train_sim.train(train_sim.best_attribute())
    gained = sum(train_sim.attrs) - sum(before)
    assert 20 <= gained <= 60  # 40 ± 6σ，固定 seed 可复现


def test_missing_official_schedule_falls_back_to_constants(tmp_path) -> None:
    """official.json 缺失：训练退回 75×support_bonus，上课退回 score×ratio。"""
    missing = tmp_path / "missing.json"
    sim = _sim(schedule_path=str(missing))
    before = list(sim.attrs)
    sim.train(sim.best_attribute())
    gained = sum(sim.attrs) - sum(before)
    assert 60 <= gained <= 120  # 75×1.2=90，留出高斯尾部

    lesson_sim = _sim(schedule_path=str(missing))
    lesson_sim.lesson()
    assert lesson_sim.last_lesson is not None
    assert lesson_sim.last_lesson["gain_source"] == "constants"


@lru_cache(maxsize=2)
def _calibrated_400_episode_means(
    ratio: float, schedule_source: str = "official"
) -> tuple[float, tuple[float, float, float]]:
    """用真机卡组/奖励池跑 400 局，返回 (三维总和均值, 三维均值)。

    固定种子 5000..5399，结果可复现；缓存避免两个用例重复跑同一组。
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    deck = [sp._spec_from_row(row) for row in sp.build_deck(rich=True)]
    pool = [sp._spec_from_row(row) for row in sp.build_pool(rich=True)]
    config = ProduceConfig(lesson_gain_ratio=ratio, schedule_source=schedule_source)
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
    """默认 official 排期 + wiki 体力口径：400 局三维总和均值落在 950-1450。

    2026-11-22 B3 真机规则修正后重新标定：训练/考试模拟器默认**每回合只出 1 张**，
    且「回合结束还有剩余出牌次数（SKIP）回 2 体力」（参考引擎 TurnManager），
    体力周转比旧口径（每回合 3 张、不回体力）宽松 → 同样 16 周能打更多训练，
    400 局三维总和均值从旧口径 ~800（3 张不回体力）/ 650-1100 带升到 **≈1198**。
    这里记录修正后口径做漂移哨兵，不代表与真机最终属性吻合（起始属性/官方排期
    口径仍在 WIKI_DUAL_SOURCE 里有已知偏差）。
    """
    mean_total, mean_attrs = _calibrated_400_episode_means(0.5)
    assert 950 <= mean_total <= 1450, f"三维总和均值 {mean_total:.1f} 偏离 B3 标定区间"
    assert all(120 <= value <= 800 for value in mean_attrs), mean_attrs


def test_ratio_one_doubles_three_attrs_vs_calibrated_default() -> None:
    """旧口径（constants）把 ratio 改回 1.0：课程成长翻倍（校准反向验证）。"""
    calibrated, _ = _calibrated_400_episode_means(0.5, schedule_source="constants")
    doubled, _ = _calibrated_400_episode_means(1.0, schedule_source="constants")
    assert 1.8 <= doubled / calibrated <= 2.2, f"{calibrated:.1f} -> {doubled:.1f}"


def test_strategy_rests_below_threshold() -> None:
    sim = _sim()
    sim.stamina = 5
    strategy = strategy_from_params(StrategyParams(rest_threshold=10))
    assert strategy(sim) == "rest"


def test_strategy_rests_instead_of_lesson_when_stamina_below_gate() -> None:
    """体力 5 + training_min_stamina=12：即使轮到训练周也改休息（真机事故回归）。"""
    sim = _sim()
    sim.week = 1
    sim.stamina = 5
    strategy = strategy_from_params(
        StrategyParams(rest_threshold=0, lesson_every=1, lesson_min_stamina=12)
    )
    assert strategy(sim) == "rest"

    # 体力 20 达标 → 正常训练
    sim.stamina = 20
    assert strategy(sim) == "training"


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
    """体力不够付最低牌费时训练不成立；体力绝不扣成负数。"""
    sim = _sim()
    sim.deck = [CardSpec("贵", 6, 5)]
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
    """搜索空间必须包含训练体力门（脚本层暂用旧键名，兼容两种键）。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_search as ss

    gate_key = "training_min_stamina" if "training_min_stamina" in ss.GRID else "lesson_min_stamina"
    assert gate_key in ss.GRID
    values = ss.GRID[gate_key]
    assert 12 in values
    assert all(isinstance(value, int) for value in values)


def test_strategy_lessons_on_cadence() -> None:
    sim = _sim()
    sim.week = 3
    sim.stamina = 30
    strategy = strategy_from_params(StrategyParams(lesson_every=3, rest_threshold=6))
    assert strategy(sim) == "training"
    sim.week = 4
    assert strategy(sim) in ("class", "class_low")


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
    """属性再高也不直接决定考试名次：局内得分低就会不合格（wiki 口径）。"""
    sim = _sim()
    sim.attrs = [170, 147, 315]
    sim.deck = [CardSpec("弱牌", 4, 1)]
    exam = sim.exam(1)
    assert exam["passed"] is False
    assert exam["rank"] >= 4


def test_exam_score_uses_audition_coefficient() -> None:
    """考试改成"真跑 12 回合"后，411% 倍率的得分必须高于 100% 倍率。"""
    attrs = [450, 400, 392]
    calibrated = _sim(audition_coefficient=4.11)
    calibrated.attrs = attrs
    high = calibrated.exam(1)["score"]
    legacy = _sim(audition_coefficient=1.0)
    legacy.attrs = attrs
    low = legacy.exam(1)["score"]
    assert high > 0 and low > 0
    assert high > low

def test_eval_points_rise_with_audition_coefficient() -> None:
    """倍率 0.9 / 1.0 / 4.11：考试得分与评价点都单调上升。"""
    attrs = [450, 400, 360]
    total = sum(attrs)
    points = []
    for coefficient in (0.9, 1.0, 4.11):
        sim = _sim(audition_coefficient=coefficient)
        sim.attrs = attrs
        exam = sim.exam(1)
        points.append(eval_value(total, exam["rank"], exam["score"]))
    assert points[0] < points[1] < points[2]

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
    """典型局评价点 P50 落在 4000-6500（真机 5992 所在量级）。"""
    ordered = sorted(_typical_run_evals())
    p50 = ordered[len(ordered) // 2]
    assert 4000 <= p50 <= 6500, f"评价点 P50={p50} 偏离区间"

def test_policy_json_audition_coefficient_matches_config_default() -> None:
    """policy.json 的 produce.audition_coefficient 与代码默认值一致（不丢键/不漂移）。"""
    import json
    from pathlib import Path

    policy_path = Path(__file__).resolve().parents[1] / "data" / "knowledge" / "policy.json"
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    assert raw["produce"]["audition_coefficient"] == 4.11
    assert raw["produce"]["audition_coefficient"] == ProduceConfig().audition_coefficient


def test_exam_rank_ignores_attribute_balance() -> None:
    """考试名次只看局内得分：同牌组/同 seed 下，属性 615 均衡或偏堆都不改变名次。"""
    balanced = _sim()
    balanced.deck = [CardSpec("弱牌", 4, 1)]
    balanced.attrs = [205, 205, 205]
    skewed = _sim()
    skewed.deck = [CardSpec("弱牌", 4, 1)]
    skewed.attrs = [123, 154, 338]
    assert balanced.exam(1)["rank"] == skewed.exam(1)["rank"]


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
    # 官方排期 week2 是授業（40+30=70），训练只有 48：早期上课严格优于训练。
    # （week9 也能赢，但 margin 会受 rest 前瞻影响；用 week2 固定这个优先级。）
    result = choose_action(
        deck, random_pool(3), attrs=[900, 880, 860], stamina=35, week=2,
        config=ProduceConfig(), actions=("train", "rest", "lesson"), episodes=6,
    )
    assert result["action"] == "lesson"
    by_action = {row["action"]: row["eval"] for row in result["ranking"]}
    assert by_action["lesson"] > by_action["train"]
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
        LessonConfig(turns=2, stamina=10, target_clear=1, hand_size=3, plays_per_turn=3),
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


def test_new_effect_types_are_modeled() -> None:
    """2026-11-16 新卡池 16 种效果全部进 MODELED_EFFECTS（13 → 29）；
    T5② 2026-11-22 再加熱意追加/増加 → 31；P1-1 2026-11-24 のんびり预约
    ExamOverPreservation → 33；P1-2 2026-11-24 自尊
    ExamLessonValueMultipleDependReviewOrAggressive → 34；P1-3 2026-11-24
    指針固定 StanceLock → 35（ExamCardMove 2026-11-16 已在），旧集合不变。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    new_types = {
        "ExamLessonFullPowerPoint",
        "ExamStatusEnchantEncore",
        "ExamForcePlayCardSearch",
        "ExamStaminaRecoverFix",
        "ExamStatusEnchant",
        "ExamCardMove",
        "ExamEffectTimer",
        "ExamAddGrowEffect",
        "ExamCardCreateId",
        "ExamEffectTimerEndTurn",
        "ExamEnthusiasticTurnAdd",
        "ExamParameterBuffAdditiveFix",
        "ExamFullPowerLessonMultipleAdditive",
        "ExamAntiDebuff",
        "ExamReviewMultiple",
        "ExamCardPlayAggressive",
    }
    assert new_types <= sp.MODELED_EFFECTS
    assert len(sp.MODELED_EFFECTS) == 35
    # P1-1 2026-11-24 のんびり预约（ExamOverPreservation）接入
    assert "ExamOverPreservation" in sp.MODELED_EFFECTS
    # P1-2 2026-11-24 自尊（ExamLessonValueMultipleDependReviewOrAggressive）接入
    assert "ExamLessonValueMultipleDependReviewOrAggressive" in sp.MODELED_EFFECTS
    # P1-3 2026-11-24 指針固定（StanceLock，切磋琢磨）接入
    assert "StanceLock" in sp.MODELED_EFFECTS
    # T5② 2026-11-22 熱意：追加/増加/本牌適用倍数 三种效果接入（熱意延長 2026-11-16 已在）
    enthusiasm_types = {
        "ExamEnthusiasticAdditive",
        "ExamEnthusiasticMultiple",
        "ExamMultipleEnthusiasticLesson",
    }
    assert enthusiasm_types <= sp.MODELED_EFFECTS
    assert not (new_types & sp.LEGACY_MODELED_EFFECTS)
    assert sp.LEGACY_MODELED_EFFECTS == {"ExamLesson", "ExamBlock", "ExamLessonBuff"}


def test_stamina_recover_full_power_and_encore_parse_to_rich_row() -> None:
    """体力回复/全力折算/再演的数值进 rich 行，再原样透传进 CardSpec。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    fields = sp._effect_fields(
        {
            "effects": [
                {"type": "ExamStaminaRecoverFix", "values": [4]},
                {"type": "ExamLessonFullPowerPoint", "values": [1000]},
                {"type": "ExamStatusEnchantEncore", "values": []},
            ]
        }
    )
    assert (fields[14], fields[15], fields[16]) == (4, 1000, 1)

    spec = sp._spec_from_row(sp._rich_row("新卡", 0, fields))
    assert (spec.stamina_recover, spec.full_power_scale, spec.encore) == (4, 1000, True)

    # 双值形态：[固定打分, 折算千分比]（传递勇气的启明星 卡面 +20 / 650%）
    dual = sp._effect_fields(
        {"effects": [{"type": "ExamLessonFullPowerPoint", "values": [20, 6500]}]}
    )
    assert dual[0] == 20 and dual[15] == 6500


def test_status_enchant_expands_inner_and_encore_flag() -> None:
    """ExamStatusEnchant 递归展开内层；Encore 只置标记，不再把其检索内层算成抽牌。"""
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    outer = sp._effect_fields(
        {
            "effects": [
                {
                    "type": "ExamStatusEnchant",
                    "values": [],
                    "inner": [{"type": "ExamLessonDependBlock", "values": [1300]}],
                },
                {
                    "type": "ExamStatusEnchantEncore",
                    "values": [],
                    "inner": [{"type": "ExamForcePlayCardSearch", "values": []}],
                },
                {"type": "ExamEffectTimer", "values": [1]},
                {"type": "ExamEffectTimerEndTurn", "values": []},
                {"type": "ExamAntiDebuff", "values": []},
            ]
        }
    )
    assert outer[9] == 1300  # 内层元气依赖分被继承
    assert outer[16] == 1    # Encore
    assert outer[3] == 0     # Encore 的检索内层不重复算抽牌

    # 真实卡：粉丝所期望的事 的 ExamStatusEnchant 内层是 ExamFullPowerPoint +2
    table = json.loads(sp.CARD_TABLE.read_text(encoding="utf-8"))["cards"]
    assert sp._effect_fields(table["粉丝所期望的事"])[7] == 2


def test_search_create_move_are_approximated_as_one_draw() -> None:
    """检索/生成/移动 → 至少 +1 抽牌；已有更大抽牌数时取较大者（保守）。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    for kind in ("ExamForcePlayCardSearch", "ExamCardCreateId", "ExamCardMove"):
        fields = sp._effect_fields({"effects": [{"type": kind, "values": []}]})
        assert fields[3] == 1, kind

    both = sp._effect_fields(
        {
            "effects": [
                {"type": "ExamCardDraw", "values": [2]},
                {"type": "ExamForcePlayCardSearch", "values": []},
            ]
        }
    )
    assert both[3] == 2  # 不是 2 + 1

    # 本牌已有"可出牌次数追加"时不再加抽牌：资源收益已由次数表达，且 0 费
    # 检索+加次数牌会让 LessonSim 无限过牌
    with_play = sp._effect_fields(
        {
            "effects": [
                {"type": "ExamCardMove", "values": []},
                {"type": "ExamPlayableValueAdd", "values": [], "count": 1},
            ]
        }
    )
    assert (with_play[3], with_play[8]) == (0, 1)


def test_review_additive_and_full_power_lesson_turns_parse() -> None:
    """好印象强化 / 好调增加量追加 / 全力强化：数值 + 持续回合（-1 = 永久）。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    review = sp._effect_fields(
        {"effects": [{"type": "ExamReviewMultiple", "values": [2000], "turn": 3}]}
    )
    assert (review[17], review[18]) == (2000, 3)
    permanent = sp._effect_fields(
        {"effects": [{"type": "ExamReviewMultiple", "values": [100], "turn": -1}]}
    )
    assert permanent[18] == -1

    additive = sp._effect_fields(
        {"effects": [{"type": "ExamParameterBuffAdditiveFix", "values": [2], "turn": 2}]}
    )
    assert (additive[19], additive[20]) == (2, 2)

    lesson = sp._effect_fields(
        {
            "effects": [
                {"type": "ExamFullPowerLessonMultipleAdditive", "values": [100], "turn": 1}
            ]
        }
    )
    assert (lesson[21], lesson[22]) == (100, 1)


def test_enthusiastic_grow_and_aggressive_parse() -> None:
    """熱意延長/追加/増加、成长（values 空 → 0）、出牌干劲 → motivation。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    enthusiastic = sp._effect_fields(
        {"effects": [{"type": "ExamEnthusiasticTurnAdd", "values": [1]}]}
    )
    assert enthusiastic[29] == 1  # T5② 熱意延長（不再并进好调回合数）
    assert enthusiastic[1] == 0

    additive = sp._effect_fields(
        {"effects": [{"type": "ExamEnthusiasticAdditive", "values": [5], "turn": -1}]}
    )
    assert (additive[25], additive[26]) == (5, -1)  # 熱意追加 +5 永久

    multiple = sp._effect_fields(
        {"effects": [{"type": "ExamEnthusiasticMultiple", "values": [1000], "turn": 3}]}
    )
    assert (multiple[27], multiple[28]) == (1000, 3)  # 熱意増加 +1000‰ 3 回合

    lesson = sp._effect_fields(
        {
            "effects": [
                {"type": "ExamMultipleEnthusiasticLesson", "values": [3, 1000]}
            ]
        }
    )
    # 本牌直接打分 +3、本牌熱意適用倍数 1000+1000‰ = ×2
    assert (lesson[0], lesson[30]) == (3, 2000)

    empty_grow = sp._effect_fields({"effects": [{"type": "ExamAddGrowEffect", "values": []}]})
    assert empty_grow[23] == 0
    explicit_grow = sp._effect_fields(
        {"effects": [{"type": "ExamAddGrowEffect", "values": [50]}]}
    )
    assert explicit_grow[23] == 50

    aggressive = sp._effect_fields(
        {"effects": [{"type": "ExamCardPlayAggressive", "values": [4]}]}
    )
    assert aggressive[24] == 4
    spec = sp._spec_from_row(sp._rich_row("干劲", 0, aggressive))
    assert spec.motivation == 4


def test_all_new_fields_pass_through_spec_from_row() -> None:
    """30 元组后 16 个新字段全部能穿过 _spec_from_row，不再被静默丢掉。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    row = sp.CardRow(
        "全字段",
        1,
        10,
        2,
        3,
        draw=4,
        impression=5,
        impression_scale=600,
        preservation=1,
        full_power_point=2,
        extra_play=3,
        block_scale=700,
        parameter_buff=1500,
        parameter_buff_turns=2,
        strong_level=1,
        vitality=6,
        stamina_recover=7,
        full_power_scale=800,
        encore=1,
        review_multiple=900,
        review_multiple_turns=3,
        condition_additive=2,
        condition_additive_turns=2,
        full_power_lesson_multiple=100,
        full_power_lesson_multiple_turns=1,
        grow_score=50,
        motivation=4,
        enthusiasm_bonus=5,
        enthusiasm_bonus_turns=-1,
        enthusiasm_multiple=1000,
        enthusiasm_multiple_turns=3,
        enthusiasm_extension=1,
        enthusiasm_multiplier=2000,
    )
    spec = sp._spec_from_row(row)
    assert (
        spec.stamina_recover,
        spec.full_power_scale,
        spec.encore,
        spec.review_multiple,
        spec.review_multiple_turns,
        spec.condition_additive,
        spec.condition_additive_turns,
        spec.full_power_lesson_multiple,
        spec.full_power_lesson_multiple_turns,
        spec.grow_score,
        spec.motivation,
        spec.enthusiasm_bonus,
        spec.enthusiasm_bonus_turns,
        spec.enthusiasm_multiple,
        spec.enthusiasm_multiple_turns,
        spec.enthusiasm_extension,
        spec.enthusiasm_multiplier,
    ) == (7, 800, True, 900, 3, 2, 2, 100, 1, 50, 4, 5, -1, 1000, 3, 1, 2000)
    # 旧字段不受影响
    assert (spec.score, spec.condition, spec.focus, spec.draw, spec.vitality) == (10, 2, 3, 4, 6)


def test_rich_pool_includes_new_effect_cards_and_stays_modeled() -> None:
    """奖励池从 212 扩到更多新卡，且仍只收"效果类型全被建模"的卡。"""
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    rich = sp.build_pool(rich=True)
    assert len(rich) > 212, f"rich 池没有扩大：{len(rich)}"

    table = json.loads(sp.CARD_TABLE.read_text(encoding="utf-8"))["cards"]
    for row in rich:
        types = {str(e.get("type") or "") for e in table[row.name].get("effects") or []}
        assert types <= sp.MODELED_EFFECTS, row.name

    # 状态附魔内层打分让「决不停歇」第一次进池；新效果字段也确实传进池
    assert any(row.name == "决不停歇" for row in rich)
    assert any(row.stamina_recover > 0 for row in rich)
    assert any(row.motivation > 0 for row in rich)
    assert any(row.full_power_scale > 0 for row in rich)


def test_real_new_cards_parse_to_expected_fields() -> None:
    """用真实新卡锁定 16 种效果的解析口径（数值来自卡表，不是手写 CardRow）。"""
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sim_produce as sp

    table = json.loads(sp.CARD_TABLE.read_text(encoding="utf-8"))["cards"]

    full_power = sp._effect_fields(table["全力冲刺"])
    assert (full_power[7], full_power[15]) == (3, 1000)  # 全力值 +3 / 折算 100%

    grow = sp._effect_fields(table["化身为恶魔"])
    assert (grow[19], grow[20]) == (2, 2)  # 好调增加量追加 +2（2 回合）

    encore = sp._effect_fields(table["真实的自己"])
    assert (encore[16], encore[17]) == (1, 500)  # 再演 / 好印象强化 +50%

    now = sp._effect_fields(table["作为结果的现在"])
    assert (now[14], now[29]) == (4, 1)  # 回复 4 体力 / 熱意延長 1 回合

    # T5② 熱意真实卡：新生的光芒（温存2 + 熱意追加 +5 永久）
    fresh = sp._effect_fields(table["新生的光芒"])
    assert (fresh[6], fresh[25], fresh[26]) == (2, 5, -1)
    # 火力全开（温存1 + 熱意増加 +1000‰ 3 回合）
    throttle = sp._effect_fields(table["火力全开"])
    assert (throttle[6], throttle[27], throttle[28]) == (1, 1000, 3)
    # 手を伸ばした先に（本牌打分 +1、熱意適用倍数 1000+1000‰ = ×2）
    reach = sp._effect_fields(table["伸手所向之处"])
    assert (reach[0], reach[30]) == (1, 2000)
    assert sp._spec_from_row(sp._rich_row("新生的光芒", 4, fresh)).enthusiasm_bonus == 5

    wind = sp._effect_fields(table["我就是、风！"])
    assert (wind[0], wind[15], wind[21]) == (2, 1200, 100)  # 固定分 / 折算 / 全力强化

    aggressive = sp._effect_fields(table["还差一点点"])
    assert aggressive[24] == 3  # 干劲 +3

    move = sp._effect_fields(table["一点一滴的进步"])
    # 本牌同时有 +3 可出牌次数：按约定不再额外加抽牌，避免 0 费循环
    assert (move[3], move[8]) == (0, 3)


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


def test_exam_policy_can_be_injected_for_offline_ab() -> None:
    """考试内出牌策略可注入（离线 A/B 用）；默认仍是 greedy_policy。"""
    sim = _sim()
    assert sim.exam_policy_fn is None
    calls: list[int] = []

    def policy(inner) -> int | None:
        calls.append(inner.turns_left)
        legal = [index for index in inner.legal_actions() if index is not None]
        return legal[0] if legal else None

    sim.exam_policy_fn = policy
    exam = sim.exam(0)
    assert calls, "注入的考试策略没有被调用"
    assert exam["score"] >= 0

    # 不注入时维持历史口径（greedy_policy），分数应可复现。
    default = _sim().exam(0)
    assert default["score"] >= 0


