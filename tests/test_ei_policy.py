"""B11 渐退式专家迭代（policy_mlp / policy_data / harness net 分支）离线单测。

覆盖：
* 决策特征（104 状态 + 33 动作）维度/确定性/牌间区分；
* 学生网 save/load、argmax 选牌、合成数据可训练、维度校验；
* **用户硬规矩**：有可出牌绝不 SKIP、全付不起才 SKIP、无静默回退；
* 决策记录只记真实决策；**精确重放逐字段等价**（失配抛错不静默）；
* 优势标签均值 0、on-policy（分支延续 = 原局终局分）、对 rollout 策略敏感；
* 教师示范软目标与剔除规则；
* ``eval_known_draw.play`` 的 net/greedy 分支 + **默认行为逐位不变**。

全部不落盘（除 tmp_path）、不依赖真机/采集数据。
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_known_draw as ekd

from gkagent.sim.expectimax import state_from_sim
from gkagent.sim.leaf_mlp import DIM as LEAF_DIM
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim, greedy_policy
from gkagent.sim.policy_data import (
    DecisionRecordingSim,
    advantage_samples,
    demo_samples,
    play_selfplay,
    replay_to,
    verify_replay,
)
from gkagent.sim.policy_mlp import (
    ACTION_DIM,
    ACTION_FEATURE_NAMES,
    INPUT_DIM,
    PolicyMLP,
    action_features,
    decision_features,
    net_action,
    ranking_accuracy,
    train_policy_mlp,
)


def _deck() -> list[CardSpec]:
    return [
        CardSpec("大1", 2, 30),
        CardSpec("大2", 2, 28),
        CardSpec("小1", 0, 5),
        CardSpec("小2", 0, 6),
        CardSpec("小3", 1, 12),
        CardSpec("小4", 1, 10),
    ]


def _config(turns: int = 3) -> LessonConfig:
    return LessonConfig(
        turns=turns, stamina=6, target_clear=40, target_perfect=80,
        hand_size=3, plays_per_turn=1,
    )


def _score_model() -> PolicyMLP:
    """手工权重：输出 = 候选牌白值分（card_score 动作特征）→ argmax = 挑高分牌。"""
    w1 = np.zeros((INPUT_DIM, 1))
    w1[LEAF_DIM + 0, 0] = 1.0  # ACTION_FEATURE_NAMES[0] = card_score
    return PolicyMLP(
        mean=np.zeros(INPUT_DIM),
        scale=np.ones(INPUT_DIM),
        w1=w1,
        b1=np.zeros(1),
        w2=np.ones((1, 1)),
        b2=np.zeros(1),
        out_w=np.ones((1, 1)),
        out_b=np.zeros(1),
    )


def _anti_score_model() -> PolicyMLP:
    model = _score_model()
    model.out_w = -np.ones((1, 1))
    return model


def _greedy_record(deck, config, seed: int = 7):
    sim = DecisionRecordingSim(deck, config, rng_seed=seed)
    sim.run(greedy_policy)
    return sim


# ---------------------------------------------------------------- 特征


def test_decision_features_dim_and_finite() -> None:
    sim = LessonSim(_deck(), _config(), rng_seed=1)
    state = state_from_sim(sim)
    assert INPUT_DIM == LEAF_DIM + ACTION_DIM == 137
    assert len(ACTION_FEATURE_NAMES) == ACTION_DIM
    for card in state.hand:
        vector = decision_features(state, card)
        assert vector.shape == (INPUT_DIM,)
        assert np.all(np.isfinite(vector))


def test_decision_features_deterministic() -> None:
    sim = LessonSim(_deck(), _config(), rng_seed=2)
    state = state_from_sim(sim)
    card = state.hand[0]
    assert np.array_equal(decision_features(state, card), decision_features(state, card))


def test_decision_features_differ_by_card() -> None:
    sim = LessonSim(_deck(), _config(), rng_seed=3)
    state = state_from_sim(sim)
    vectors = [decision_features(state, card) for card in state.hand]
    assert not np.array_equal(vectors[0], vectors[1])


def test_action_features_cost_context() -> None:
    sim = LessonSim(_deck(), _config(), rng_seed=4)
    state = state_from_sim(sim)
    card = next(c for c in state.hand if c.cost > 0)
    features = action_features(state, card)
    names = list(ACTION_FEATURE_NAMES)
    available = float(state.stamina + state.vitality)
    cost = features[names.index("effective_cost")]
    assert cost == float(card.cost)  # normal 指針不改费用
    assert features[names.index("cost_over_available")] == pytest.approx(
        cost / max(available, 1.0)
    )
    assert features[names.index("affordable_margin")] == pytest.approx(available - cost)


# ---------------------------------------------------------------- 模型


def test_policy_mlp_save_load_roundtrip(tmp_path: Path) -> None:
    model = _score_model()
    model.meta = {"test": True}
    path = model.save(tmp_path / "policy.json")
    loaded = PolicyMLP.load(path)
    sim = LessonSim(_deck(), _config(), rng_seed=5)
    state = state_from_sim(sim)
    assert np.array_equal(model.score(state, state.hand), loaded.score(state, state.hand))
    assert loaded.meta == {"test": True}


def test_policy_mlp_load_rejects_wrong_format(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"format": "gkagent.other.v9"}', encoding="utf-8")
    with pytest.raises(ValueError, match="format"):
        PolicyMLP.load(path)


def test_policy_mlp_load_rejects_feature_mismatch(tmp_path: Path) -> None:
    path = _score_model().save(tmp_path / "policy.json")
    doc = __import__("json").loads(path.read_text(encoding="utf-8"))
    doc["action_feature_names"] = list(ACTION_FEATURE_NAMES[:-1]) + ["bogus"]
    path.write_text(__import__("json").dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="特征"):
        PolicyMLP.load(path)


def test_choose_argmax_picks_highest_score() -> None:
    sim = LessonSim(_deck(), _config(), rng_seed=6)
    state = state_from_sim(sim)
    cards = list(state.hand)
    choice = _score_model().choose(state, cards)
    assert cards[choice].score == max(card.score for card in cards)


def test_choose_requires_candidates() -> None:
    sim = LessonSim(_deck(), _config(), rng_seed=6)
    with pytest.raises(ValueError):
        _score_model().choose(state_from_sim(sim), [])


def test_train_policy_mlp_learns_synthetic_ranking() -> None:
    rng = np.random.default_rng(0)
    n = 400
    X = rng.normal(size=(n, INPUT_DIM))
    y = 2.0 * X[:, 7] + rng.normal(scale=0.05, size=n)
    groups = np.arange(n) // 4
    model, history = train_policy_mlp(X, y, hidden=(32, 16), epochs=200, seed=0)
    assert history["final_mse"] < 0.2
    assert ranking_accuracy(model, X, y, groups) > 0.9


def test_train_policy_mlp_rejects_wrong_dim() -> None:
    with pytest.raises(ValueError, match="特征维度"):
        train_policy_mlp(np.zeros((4, INPUT_DIM - 1)), np.zeros(4))
    with pytest.raises(ValueError, match="样本数"):
        train_policy_mlp(np.zeros((4, INPUT_DIM)), np.zeros(3))


# ---------------------------------------------------------------- 硬规矩


def test_net_action_never_skips_with_playable() -> None:
    sim = LessonSim(_deck(), _config(), rng_seed=8)
    # 反分数模型：故意偏好低分牌，但有牌可出时仍必须出牌（不许 SKIP）
    action = net_action(sim, _anti_score_model())
    assert action is not None
    assert action in sim.legal_actions()


def test_net_action_skips_when_no_playable() -> None:
    # 白盒构造「出牌次数用尽但手牌还在」的 [None] 态（体力见底会被模拟器
    # 判为永久终端 done，legal_actions() 返回 []，不是 SKIP 分支）
    sim = LessonSim(_deck(), _config(), rng_seed=9)
    sim.plays_this_turn = sim.plays_per_turn + sim.extra_plays
    assert sim.legal_actions() == [None]
    assert net_action(sim, _score_model()) is None


def test_selfplay_deterministic_same_seed() -> None:
    deck, config = _deck(), _config()
    sim_a, row_a = play_selfplay(deck, config, 11, _score_model())
    sim_b, row_b = play_selfplay(deck, config, 11, _score_model())
    assert row_a == row_b
    assert [r.action for r in sim_a.decisions] == [r.action for r in sim_b.decisions]


# ---------------------------------------------------------------- 记录 / 重放


def test_recording_sim_records_only_real_decisions() -> None:
    sim = _greedy_record(_deck(), _config())
    assert sim.decisions
    for record in sim.decisions:
        assert record.playable  # 真实决策必有可出牌
        assert record.action in record.legal
    # 前缀长度单调递增，且记录数 = 实际出牌决策数（自动 SKIP 不算）
    lengths = [len(record.prefix) for record in sim.decisions]
    assert lengths == sorted(lengths)


def test_replay_equivalence_field_by_field() -> None:
    deck, config = _deck(), _config()
    sim = _greedy_record(deck, config, seed=12)
    for record in sim.decisions:
        branch = replay_to(deck, config, 12, record.prefix)
        verify_replay(branch, record.state)  # 不抛错 = 逐字段全等
        assert state_from_sim(branch) == record.state


def test_verify_replay_raises_on_mismatch() -> None:
    deck, config = _deck(), _config()
    sim = _greedy_record(deck, config, seed=13)
    record = sim.decisions[0]
    branch = replay_to(deck, config, 13, record.prefix)
    with pytest.raises(RuntimeError, match="不一致"):
        verify_replay(branch, replace(record.state, score=record.state.score + 1))


def test_advantage_mean_zero() -> None:
    deck, config = _deck(), _config()
    sim = _greedy_record(deck, config, seed=14)
    for record in sim.decisions:
        _X, y, _meta = advantage_samples(deck, config, 14, record, greedy_policy)
        assert y.shape[0] == len(record.playable)
        assert float(y.sum()) == pytest.approx(0.0, abs=1e-9)


def test_advantage_on_policy_reproduces_game_final() -> None:
    """分支延续 = 学生自己打完：被选动作的分支终局分必须等于原局终局分。"""
    deck, config = _deck(), _config()
    model = _score_model()
    sim, row = play_selfplay(deck, config, 15, model)
    for record in sim.decisions:
        _X, _y, meta = advantage_samples(
            deck, config, 15, record, lambda current: net_action(current, model)
        )
        assert meta["finals"][record.action] == row["score"]


def test_advantage_sensitive_to_rollout_policy() -> None:
    """on-policy 的含义：换延续策略，优势标签跟着变（不是固定答案）。"""
    deck = [CardSpec("大", 2, 30)] * 2 + [CardSpec("小", 0, 5)] * 4
    config = LessonConfig(
        turns=3, stamina=6, target_clear=40, target_perfect=80,
        hand_size=3, plays_per_turn=1,
    )

    def inverse_policy(current: LessonSim):
        playable = [i for i in current.legal_actions() if i is not None]
        if not playable:
            return None
        return min(playable, key=lambda i: current.hand[i].score)

    # 找一个候选牌异质的决策（同名牌分支对称，优势恒 0，没有区分度）
    for seed in range(16, 40):
        sim = _greedy_record(deck, config, seed=seed)
        record = next(
            (
                r for r in sim.decisions
                if len({r.state.hand[i].score for i in r.playable}) >= 2
            ),
            None,
        )
        if record is not None:
            break
    assert record is not None, "构造牌组应能产生异质决策"
    _Xa, ya, _ = advantage_samples(deck, config, seed, record, greedy_policy)
    _Xb, yb, _ = advantage_samples(deck, config, seed, record, inverse_policy)
    assert not np.allclose(ya, yb)


def test_advantage_rejects_empty_playable() -> None:
    deck, config = _deck(), _config()
    sim = _greedy_record(deck, config, seed=17)
    record = replace(sim.decisions[0], legal=(None,))
    with pytest.raises(ValueError, match="可出牌"):
        advantage_samples(deck, config, 17, record, greedy_policy)


# ---------------------------------------------------------------- 教师示范


def test_demo_samples_soft_targets() -> None:
    deck, config = _deck(), _config()
    sim = _greedy_record(deck, config, seed=18)
    record = next(r for r in sim.decisions if len(r.playable) >= 2 and r.action is not None)
    sample = demo_samples(record)
    assert sample is not None
    X, y, meta = sample
    k = len(record.playable)
    assert X.shape == (k, INPUT_DIM)
    assert y[record.playable.index(record.action)] == 1.0
    assert float(y.sum()) == pytest.approx(0.0, abs=1e-9)
    assert meta["n"] == k


def test_demo_samples_excludes_forced_and_skip() -> None:
    deck, config = _deck(), _config()
    sim = _greedy_record(deck, config, seed=19)
    record = sim.decisions[0]
    forced = replace(record, legal=(record.playable[0], None), action=record.playable[0])
    assert demo_samples(forced) is None
    skipped = replace(record, action=None)
    assert demo_samples(skipped) is None


# ---------------------------------------------------------------- harness 接线


def test_ekd_play_net_runs_and_deterministic() -> None:
    deck, config = _deck(), _config(turns=4)
    model = _score_model()
    row_a = ekd.play(deck, config, 21, known=False, policy="net", net_model=model)
    row_b = ekd.play(deck, config, 21, known=False, policy="net", net_model=model)
    assert row_a == row_b
    assert row_a["fallbacks"] == 0
    assert row_a["decisions"] > 0


def test_ekd_play_net_requires_model() -> None:
    with pytest.raises(ValueError, match="net_model"):
        ekd.play(_deck(), _config(), 22, known=False, policy="net")


def test_ekd_play_net_never_skips_with_playable() -> None:
    deck, config = _deck(), _config(turns=4)
    instances: list[DecisionRecordingSim] = []

    def factory(d, c, rng_seed):
        sim = DecisionRecordingSim(d, c, rng_seed)
        instances.append(sim)
        return sim

    ekd.play(
        deck, config, 23, known=False, policy="net",
        net_model=_anti_score_model(), sim_factory=factory,
    )
    sim = instances[-1]
    assert sim.decisions
    # 记录点 = 有可出牌的决策；net 在这些点必须出牌（硬规矩）
    assert all(record.action is not None for record in sim.decisions)


def test_ekd_play_greedy_matches_sim_run() -> None:
    deck, config = _deck(), _config(turns=4)
    row = ekd.play(deck, config, 24, known=False, policy="greedy")
    sim = LessonSim(deck, config, rng_seed=24)
    score, _grade = sim.run(greedy_policy)
    assert row["score"] == float(score)


def test_ekd_play_default_behavior_unchanged() -> None:
    """net_model=None 的 within/beam 与不传 net_model 逐位相同（默认行为不变）。"""
    deck, config = _deck(), _config(turns=4)
    for policy in ("within", "beam"):
        baseline = ekd.play(deck, config, 25, known=False, policy=policy, budget_ms=50.0)
        with_none = ekd.play(
            deck, config, 25, known=False, policy=policy, budget_ms=50.0, net_model=None
        )
        assert baseline == with_none
