"""B2 学习叶子（leaf_mlp / leaf_data）的离线单测。

覆盖：
* 叶子特征维度/有限性/手牌归一化（训练与推理同分布的关键）；
* ``RecordingLessonSim`` 只在回合间记录叶子快照，标签 = 最终分 − 叶子分；
* MLP 叶子 save/load、predict/utility 契约（与解析式同式）；
* 搜索入口能直接用 MLP 叶子（无需改 expectimax）。

全部不落盘、不依赖真机/采集数据。
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.sim.expectimax import (
    end_turn_state,
    expectimax_with_stats,
    state_from_sim,
)
from gkagent.sim.leaf_data import (
    RecordingLessonSim,
    episode_samples,
    leaf_state_at_draw,
)
from gkagent.sim.leaf_mlp import (
    DIM,
    FEATURE_NAMES,
    MLPLeafValue,
    evaluate_utility_heads,
    features,
    train_mlp,
    train_utility_heads,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim, greedy_policy


def _deck() -> list[CardSpec]:
    return [
        CardSpec("攻1", 0, 12),
        CardSpec("攻2", 1, 18),
        CardSpec("攻3", 2, 25),
        CardSpec("攻4", 1, 20),
        CardSpec("攻5", 0, 10),
    ]


def _config(turns: int = 3) -> LessonConfig:
    return LessonConfig(turns=turns, stamina=20, target_clear=20, hand_size=3, plays_per_turn=1)


def _make_model(*, seed: int = 0) -> MLPLeafValue:
    rng = np.random.default_rng(seed)
    hidden1, hidden2 = 16, 8
    return MLPLeafValue(
        mean=np.zeros(DIM),
        scale=np.ones(DIM),
        w1=rng.normal(0.0, 0.1, size=(DIM, hidden1)),
        b1=np.zeros(hidden1),
        w2=rng.normal(0.0, 0.1, size=(hidden1, hidden2)),
        b2=np.zeros(hidden2),
        mu_w=rng.normal(0.0, 0.1, size=(hidden2, 1)),
        mu_b=np.zeros(1),
        sig_w=np.zeros((hidden2, 1)),
        sig_b=np.asarray([np.log(25.0)]),
        sigma=25.0,
        use_sigma_head=True,
    )


def test_feature_names_match_vector_dim() -> None:
    assert len(FEATURE_NAMES) == DIM
    sim = LessonSim(_deck(), _config(turns=2), rng_seed=1)
    state = end_turn_state(state_from_sim(sim))
    vector = features(state)
    assert vector.shape == (DIM,)
    assert np.isfinite(vector).all()
    assert np.array_equal(vector, features(state)), "叶子特征必须是纯函数"


def test_features_normalize_hand_into_discard() -> None:
    """带手牌的输入应先并入弃牌堆，再按叶子形态取特征（与 end_turn_state 同口径）。"""
    sim = LessonSim(_deck(), _config(turns=2), rng_seed=2)
    assert sim.hand, "开局应有手牌"
    state = state_from_sim(sim)
    leaf_with_hand = features(state)
    leaf_without = features(replace(state, hand=(), discard=state.discard + state.hand))
    assert np.array_equal(leaf_with_hand, leaf_without)
    assert np.isfinite(end_turn_state(state).score)


def test_recording_sim_runs_and_labels_are_remaining_score() -> None:
    sim = RecordingLessonSim(_deck(), _config(turns=3), rng_seed=3)
    while not sim.done:
        actions = sim.legal_actions()
        sim.step(greedy_policy(sim) if actions != [None] else None)
    # 3 回合课：回合 1→2、2→3 各记录一次；最后一回合不再抽牌。
    assert len(sim.leaf_states) == 2
    for state in sim.leaf_states:
        assert state.hand == ()
        assert state.turns_left in (1, 2)
    X, y, meta = episode_samples(sim)
    assert X.shape == (3, DIM), "2 个回合间叶子 + 1 个 turns_left=0 终局样本"
    assert y.shape == (3,)
    assert meta["n_samples"] == 3
    assert y[-1] == 0.0
    for state, label in zip(sim.leaf_states, y[:-1], strict=True):
        assert label == float(sim.score) - float(state.score)


def test_leaf_state_at_draw_matches_draw_entry_convention() -> None:
    """``leaf_state_at_draw`` 等价于「手牌清空、出牌数归零、好印象 -1」的抽牌前瞬时态。"""
    sim = LessonSim(_deck(), _config(turns=2), rng_seed=4)
    sim.step(greedy_policy(sim))
    mid = state_from_sim(sim)
    expected = end_turn_state(mid)
    # 手动推进到「回合结束、抽下一手之前」：弃手牌、回合 -1、回合末结算已发生。
    sim.discard.extend(sim.hand)
    sim.hand.clear()
    sim.turns_left -= 1
    recorded = leaf_state_at_draw(sim)
    assert recorded.turns_left == expected.turns_left
    assert recorded.score == expected.score
    assert recorded.discard == expected.discard
    assert recorded.deck == expected.deck
    assert recorded.plays_used == 0
    assert recorded.drinks_used_this_turn == 0
    assert recorded.hand == ()


def test_leaf_snapshot_includes_stance_boundary_release() -> None:
    """快照必须含温存→全力回合边界的解除收益（B5）。

    ``LessonSim._end_turn`` 在 ``_draw_hand()`` 之后才结算回合边界解除
    （熱意/固定元気/+1 出牌），而搜索侧 ``end_turn_state`` 把它算进叶子——
    快照点天然缺这块，``RecordingLessonSim`` 记录回合结束前指針后补上。
    训练/推理分布必须逐字段一致（2026-11-23 B2 重训前核对）。
    """
    from dataclasses import fields

    from gkagent.sim.stance import Stance, StanceState

    sim = RecordingLessonSim(_deck(), _config(turns=2), rng_seed=16)
    sim.stance = StanceState(stance=Stance.SAVE, save_level=2, full_power_point=10)
    pre = state_from_sim(sim)
    sim.step(None)  # SKIP → 回合结束：全力值 10 → 全力；温存 2 段階解除 +8 熱意/+5 固定元気/+1 出牌
    expected = end_turn_state(pre)
    assert expected.stance_state.stance != Stance.SAVE, "构造的场景必须触发回合边界解除"
    assert sim.leaf_states, "turns_left>0 的回合结束应记录叶子快照"
    leaf = sim.leaf_states[0]
    assert leaf.enthusiasm == expected.enthusiasm > 0
    assert leaf.vitality == expected.vitality
    assert leaf.extra_plays == expected.extra_plays == 1
    for f in fields(expected):
        assert getattr(leaf, f.name) == getattr(expected, f.name), f"字段 {f.name} 不一致"


def test_mlp_predict_utility_and_save_load(tmp_path: Path) -> None:
    model = _make_model(seed=5)
    sim = LessonSim(_deck(), _config(turns=2), rng_seed=6)
    state = end_turn_state(state_from_sim(sim))
    mu, sigma = model.predict(state)
    assert mu >= 0.0
    assert sigma > 0.0
    assert model.predict_vector(features(state)) == (mu, sigma)
    utility = model.utility(state)
    assert 0.0 <= utility <= 2.0 + 1e-9
    # 回合用完 → σ=0 且硬档位。
    done_state = replace(state, turns_left=0)
    assert model.predict(done_state) == (0.0, 0.0)

    path = tmp_path / "leaf.json"
    model.save(path)
    loaded = MLPLeafValue.load(path)
    assert loaded.predict(state) == (mu, sigma)
    assert loaded.to_payload()["feature_names"] == list(FEATURE_NAMES)


def test_utility_stays_in_tier_range() -> None:
    model = _make_model(seed=7)
    sim = LessonSim(_deck(), _config(turns=2), rng_seed=8)
    state = end_turn_state(state_from_sim(sim))
    values = [model.utility(state)]
    model.sigma = 2000.0
    values.append(model.utility(state))
    assert all(0.0 <= value <= 2.0 + 1e-9 for value in values)


def test_expectimax_accepts_mlp_leaf() -> None:
    model = _make_model(seed=9)
    sim = LessonSim(_deck(), _config(turns=2), rng_seed=10)
    state = state_from_sim(sim)
    result = expectimax_with_stats(state, model, time_budget_ms=200.0)
    assert result.card is None or result.card in sim.hand
    assert np.isfinite(result.utility)
    assert result.nodes > 0


def test_train_mlp_reduces_error_on_separable_synthetic_data() -> None:
    rng = np.random.default_rng(11)
    X = rng.normal(size=(256, DIM))
    weights = rng.normal(size=(DIM,))
    y = 20.0 + X @ weights
    model, history = train_mlp(
        X, y, hidden=(16, 8), epochs=800, lr=3e-3, sigma_epochs=50, seed=11
    )
    assert history["r2"] > 0.9
    prediction = np.asarray([model.predict_vector(row)[0] for row in X[:16]])
    assert np.corrcoef(prediction, y[:16])[0, 1] > 0.8


def test_utility_heads_train_save_and_load(tmp_path: Path) -> None:
    config = LessonConfig(
        turns=10, stamina=40, target_clear=40, hand_size=3, plays_per_turn=1
    )
    sim = RecordingLessonSim(_deck(), config, rng_seed=12)
    while not sim.done:
        actions = sim.legal_actions()
        sim.step(greedy_policy(sim) if actions != [None] else None)
    X, y, _meta = episode_samples(sim)
    assert X.shape[0] >= 3
    X_dup = np.vstack([X, X])
    y_dup = np.concatenate([y, y])

    model, _history = train_mlp(X_dup, y_dup, hidden=(8, 4), epochs=20, sigma_epochs=10)
    head = train_utility_heads(model, X_dup, y_dup, epochs=50)
    assert model.p_clear_w is not None and model.p_perfect_w is not None
    assert 0.0 <= head["clear_accuracy"] <= 1.0
    assert 0.0 <= head["perfect_brier"] <= 1.0
    state = end_turn_state(state_from_sim(sim))
    utility = model.utility(state)
    assert 0.0 <= utility <= 2.0 + 1e-9

    path = tmp_path / "leaf_util.json"
    model.save(path)
    loaded = MLPLeafValue.load(path)
    assert loaded.p_clear_w is not None
    assert loaded.utility(state) == utility
    metrics = evaluate_utility_heads(loaded, X_dup, y_dup)
    assert metrics["n"] == int((X_dup[:, FEATURE_NAMES.index("turns_left")] > 0).sum())


def test_load_without_probability_heads_falls_back_to_gaussian(tmp_path: Path) -> None:
    import json

    model = _make_model(seed=13)
    path = tmp_path / "leaf_gauss.json"
    model.save(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("p_clear_w", "p_clear_b", "p_perfect_w", "p_perfect_b"):
        payload.pop(key, None)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    loaded = MLPLeafValue.load(path)
    assert loaded.p_clear_w is None
    sim = LessonSim(_deck(), _config(turns=2), rng_seed=14)
    state = end_turn_state(state_from_sim(sim))
    assert 0.0 <= loaded.utility(state) <= 2.0 + 1e-9


def test_production_leaf_loader_supports_mlp(tmp_path: Path) -> None:
    """LessonPolicy 的 B2 叶子接线：显式 leaf_model 时用 ensemble(analytic, MLP)。"""
    from gkagent.policy.lesson import LessonPolicy
    from gkagent.sim.v_leaf import EnsembleLeafValue

    model = _make_model(seed=15)
    path = tmp_path / "b2_mlp.json"
    model.save(path)
    policy = LessonPolicy(
        params_path=tmp_path / "missing-params.json",
        params={"leaf_model": str(path), "leaf_model_weight": 0.3},
    )
    leaf = policy._leaf_value()
    assert isinstance(leaf, EnsembleLeafValue)
    assert isinstance(leaf.secondary, MLPLeafValue)
    assert abs(leaf.weight - 0.3) < 1e-9
    assert policy._leaf_value() is leaf, "叶子应缓存，不能每次决策重新读 JSON"

    # 坏路径不能抛异常（退回解析式/历史 ensemble），只能记 warning。
    policy_bad = LessonPolicy(
        params_path=tmp_path / "missing-params.json",
        params={"leaf_model": str(tmp_path / "nope.json")},
    )
    assert policy_bad._leaf_value() is not None

