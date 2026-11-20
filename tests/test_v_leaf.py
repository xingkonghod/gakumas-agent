"""V_leaf / 叶子契约回归测试（2026-11-19 审查补测）。

覆盖本批新增代码里实测到的坑：

1. ``features()`` 只认 ``ExpectState`` 字段；训练脚本曾直接喂 ``LessonSim``，
   ``clear`` / ``focus`` / ``condition_turns`` / ``perfect`` 等全部静默变 0；
2. 指針名是 ``save`` / ``strong1`` / ``strong2`` / ``full``，不是
   ``Preservation`` / ``Concentration`` / ``FullPower``（旧映射恒为 0）；
3. 训练采样取「回合开始」快照，而搜索叶子在「回合末」估值：``leaf_features``
   负责把手牌并进弃牌堆，让 ``hand_*`` 特征与推理分布一致；
4. ``fit_ridge`` 的标准化/反标准化（权重还原到原始尺度、截距）；
5. ``LinearLeafValue`` 与 ``AnalyticLeafValue`` 的 ``sigma=0`` 硬阈值契约；
6. ``expectimax`` 接受任何实现 ``predict``/``utility`` 的 leaf；
7. ``LessonSim`` 与 ``expectimax`` 的三处新机制打分必须同源。
"""

from __future__ import annotations

import numpy as np
import pytest

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    ExpectState,
    apply_card,
    end_turn_state,
    expectimax_with_stats,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.v_leaf import (
    DIM,
    FEATURE_NAMES,
    LinearLeafValue,
    features,
    fit_ridge,
    leaf_features,
)


def _feats(state) -> dict[str, float]:
    return dict(zip(FEATURE_NAMES, features(state), strict=True))


# ---------------------------------------------------------------- features 字段
def test_features_read_real_expectstate_fields_not_defaults() -> None:
    """必须读到 ExpectState 的真实字段，而不是缺失字段默认 0。"""
    state = ExpectState(
        hand=(CardSpec("a", 1, 12), CardSpec("b", 2, 30)),
        deck=(CardSpec("c", 1, 5),),
        stamina=10,
        stamina_max=20,
        vitality=3,
        score=50,
        turns_left=4,
        total_turns=6,
        plays_used=1,
        play_limit=3,
        extra_plays=1,
        clear=200,
        perfect=400,
        condition_turns=2,
        focus=5,
        impression=3,
        motivation=4,
        stance=("save", 0, 2, 0),
    )
    feat = _feats(state)
    assert feat["clear"] == 200
    assert feat["gap_clear"] == 150
    assert feat["gap_perfect"] == 350
    assert feat["focus"] == 5
    assert feat["condition_turns"] == 2
    assert feat["impression"] == 3
    assert feat["motivation"] == 4
    assert feat["plays_left"] == 3  # 3 + 1 extra - 1 used
    assert feat["plays_used"] == 1
    assert feat["hand_count"] == 2
    assert feat["hand_mean_score"] == 21
    assert feat["hand_max_score"] == 30
    assert feat["hand_affordable"] == 2
    assert feat["pool_count"] == 3
    assert feat["stance_save"] == 1
    assert feat["stance_strong"] == 0
    assert feat["turns_x_focus"] == 20


@pytest.mark.parametrize(
    ("stance", "expected_field"),
    [
        ("save", "stance_save"),
        ("strong1", "stance_strong"),
        ("strong2", "stance_strong"),
        ("full", "stance_full"),
        ("normal", None),
    ],
)
def test_features_stance_flags_use_real_stance_names(
    stance: str, expected_field: str | None
) -> None:
    """指針字段是 save/strong1/strong2/full；旧实现永远命中不了。"""
    feat = _feats(ExpectState(turns_left=2, clear=100, stance=(stance, 2, 2, 0)))
    for field in ("stance_save", "stance_strong", "stance_full"):
        assert feat[field] == (1.0 if field == expected_field else 0.0)


def test_features_play_left_clamps_and_counts_extra_plays() -> None:
    feat = _feats(ExpectState(turns_left=1, clear=1, plays_used=5, play_limit=3, extra_plays=1))
    assert feat["plays_left"] == 0


def test_state_from_sim_carries_the_fields_training_used_to_zero() -> None:
    """训练采样必须经 state_from_sim：clear/focus/buff/perfect/指針都要在。"""
    sim = LessonSim(
        [CardSpec("测试卡", 1, 10)],
        LessonConfig(turns=6, stamina=20, target_clear=150, target_perfect=300),
        rng_seed=0,
    )
    sim.score = 300
    sim.buffs.focus = 4
    sim.buffs.condition_turns = 2
    sim.buffs.impression = 3
    sim.motivation = 5
    sim.stance.stance = "strong2"
    feat = _feats(state_from_sim(sim))
    assert feat["clear"] == 150
    assert feat["focus"] == 4
    assert feat["condition_turns"] == 2
    assert feat["impression"] == 3
    assert feat["motivation"] == 5
    assert feat["stance_strong"] == 1
    assert feat["turns_left"] == 6
    # score 300 已达 PERFECT 线 → 该特征不再是常量 0
    assert feat["perfect_x_turns"] == 6
    # 旧实现直接 features(LessonSim)：clear/focus/condition/impression/stance 全 0
    assert feat["clear"] != 0 and feat["focus"] != 0


# ---------------------------------------------------------------- 训练/叶子对齐
def test_leaf_features_moves_hand_to_discard_and_zeros_hand_features() -> None:
    state = ExpectState(
        hand=(CardSpec("h1", 1, 10), CardSpec("h2", 2, 20)),
        deck=(CardSpec("d1", 1, 5),),
        discard=(CardSpec("x", 1, 1),),
        turns_left=3,
        clear=100,
        play_limit=3,
    )
    start = _feats(state)
    leaf = dict(zip(FEATURE_NAMES, leaf_features(state), strict=True))
    assert leaf["hand_count"] == 0
    assert leaf["hand_mean_score"] == 0
    assert leaf["hand_max_score"] == 0
    assert leaf["hand_affordable"] == 0
    assert leaf["hand_score_cards"] == 0
    # 池子总组成不因手牌搬家而改变
    assert leaf["pool_count"] == start["pool_count"] == 4
    assert leaf["pool_mean_score"] == pytest.approx(start["pool_mean_score"])
    assert leaf["turns_left"] == start["turns_left"]
    assert leaf["score"] == start["score"]


def test_leaf_features_rejects_lesson_sim_to_avoid_silent_zero_skew() -> None:
    sim = LessonSim(
        [CardSpec("测试卡", 1, 10)],
        LessonConfig(turns=3, stamina=10, target_clear=10),
        rng_seed=0,
    )
    with pytest.raises(TypeError, match="state_from_sim"):
        leaf_features(sim)


# ---------------------------------------------------------------- fit_ridge
def test_fit_ridge_recovers_weights_intercept_and_r2() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, DIM))
    coef = rng.normal(size=DIM)
    y = x @ coef + 7.25
    weights, sigma, r2 = fit_ridge(list(zip(x, y, strict=True)), ridge=1e-9)
    assert weights.shape == (DIM + 1,)
    np.testing.assert_allclose(weights[:-1], coef, atol=1e-6)
    assert weights[-1] == pytest.approx(7.25, abs=1e-6)
    assert r2 == pytest.approx(1.0)
    assert sigma == pytest.approx(1.0)  # 夹到最小 1


def test_fit_ridge_handles_constant_feature_and_empty_samples() -> None:
    empty_weights, empty_sigma, empty_r2 = fit_ridge([])
    assert empty_weights.shape == (DIM + 1,)
    assert not empty_weights.any()
    assert (empty_sigma, empty_r2) == (60.0, 0.0)

    x = np.zeros((20, DIM))
    x[:, 0] = np.arange(20.0)
    x[:, 1] = 5.0  # 常量特征：标准化后整列为 0，权重应为 0
    y = 2.0 * x[:, 0] + 1.0
    weights, _, r2 = fit_ridge(list(zip(x, y, strict=True)), ridge=1e-6)
    assert np.isfinite(weights).all()
    assert weights[1] == 0.0
    assert weights[0] == pytest.approx(2.0, abs=1e-6)
    assert weights[-1] == pytest.approx(1.0, abs=1e-5)
    assert r2 == pytest.approx(1.0)


def test_fit_ridge_does_not_penalize_intercept() -> None:
    """标准 ridge 只惩罚特征；截距即使 ridge 很大也不能被压小。"""
    x = np.zeros((10, DIM))
    y = np.full(10, 7.0)
    weights, _, _ = fit_ridge(list(zip(x, y, strict=True)), ridge=10.0)
    assert weights[-1] == pytest.approx(7.0)


# ---------------------------------------------------------------- leaf 契约
def test_linear_leaf_matches_analytic_hard_threshold_contract() -> None:
    """sigma=0 时必须与 analytic 一样走硬档位（包括 score 正好等于阈值）。"""
    state = ExpectState(score=100, turns_left=2, clear=100, perfect=100)
    linear = LinearLeafValue(weights=np.zeros(DIM + 1), sigma=0.0)
    analytic = AnalyticLeafValue(sigma=0.0)
    assert linear.predict(state) == analytic.predict(state) == (0.0, 0.0)
    assert linear.utility(state) == analytic.utility(state) == 2.0


def test_linear_leaf_gaussian_utility_matches_analytic_when_mu_matches() -> None:
    """μ 相同时，两边的高斯档位效用必须一致（同一个 erf 公式）。"""
    state = ExpectState(score=40, turns_left=2, clear=100, perfect=200)
    linear = LinearLeafValue(weights=np.zeros(DIM + 1), sigma=30.0)
    analytic = AnalyticLeafValue(sigma=30.0)
    assert linear.predict(state)[0] == analytic.predict(state)[0] == 0.0
    assert linear.utility(state) == pytest.approx(analytic.utility(state))


def test_linear_leaf_load_keeps_explicit_zero_sigma(tmp_path) -> None:
    path = tmp_path / "v_leaf.json"
    model = LinearLeafValue(weights=np.zeros(DIM + 1), sigma=0.0, a_clear=0.0)
    model.save(path)
    loaded = LinearLeafValue.load(path)
    assert loaded.sigma == 0.0
    assert loaded.a_clear == 0.0
    assert loaded.a_perfect == 1.0


def test_expectimax_accepts_linear_leaf_value() -> None:
    """搜索只调用 utility；LinearLeafValue 必须能直接传进去。"""
    state = ExpectState(
        hand=(CardSpec("a", 1, 10),),
        stamina=10,
        turns_left=2,
        play_limit=1,
        clear=10,
        perfect=20,
    )
    model = LinearLeafValue(weights=np.zeros(DIM + 1), sigma=80.0)
    result = expectimax_with_stats(state, model, time_budget_ms=1000)
    assert result.complete
    assert result.card is not None and result.card.name == "a"
    assert isinstance(result.utility, float)


# ---------------------------------------------------------------- 模拟器/搜索同源
@pytest.mark.parametrize(
    "buffs",
    [
        {"condition_turns": 3, "perfect_condition_turns": 2},
        {"metamorphosis": "performance"},
        {"metamorphosis": "preparation"},
        {"poor_condition_turns": 2},
        {
            "condition_turns": 1,
            "perfect_condition_turns": 1,
            "metamorphosis": "performance",
            "poor_condition_turns": 1,
        },
    ],
)
def test_lesson_and_expectimax_score_the_same_new_mechanics(
    buffs: dict[str, object],
) -> None:
    """LessonSim 改了三条结算后，expectimax 的镜像实现必须同步。"""
    card = CardSpec("测试卡", 2, 41)
    sim = LessonSim(
        [card], LessonConfig(turns=5, stamina=30, target_clear=100), rng_seed=0
    )
    for name, value in buffs.items():
        setattr(sim.buffs, name, value)
    expected = sim._card_award(card)
    state = state_from_sim(sim)
    outcomes = apply_card(state, card)
    assert len(outcomes) == 1
    assert outcomes[0][1].score - state.score == expected


def test_new_condition_buffs_tick_down_at_turn_end_in_both_engines() -> None:
    sim = LessonSim(
        [CardSpec("测试卡", 1, 10)],
        LessonConfig(turns=3, stamina=10, target_clear=10),
        rng_seed=0,
    )
    sim.buffs.condition_turns = 2
    sim.buffs.perfect_condition_turns = 2
    sim.buffs.poor_condition_turns = 2
    before = state_from_sim(sim)
    sim.step(None)  # SKIP 结束本回合
    ended = end_turn_state(before)
    assert sim.buffs.condition_turns == ended.condition_turns == 1
    assert sim.buffs.perfect_condition_turns == ended.perfect_condition_turns == 1
    assert sim.buffs.poor_condition_turns == ended.poor_condition_turns == 1
    assert ended.metamorphosis == before.metamorphosis
