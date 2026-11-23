"""B11 r7 设计变量：ε-greedy 探索采集（play_selfplay explore_eps）离线单测。

覆盖：
* ε=0 与原 argmax 自对弈**逐位不变**（默认行为回归）；
* ε>0 确定性（同 seed 同 eps 逐位相同）、与 argmax 路径不同（真的探索）；
* **硬规矩**：探索只在可出牌里选，有牌绝不 SKIP；
* 参数校验（[0,1]）；CLI 接线（selfplay 收、demos 拒）；
* 探索局的优势标签仍 on-policy（分支终局分 = 原局终局分）。

不落盘（除 tmp_path）、不依赖真机/采集数据。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_ei_dataset as bed

from gkagent.sim.leaf_mlp import DIM as LEAF_DIM
from gkagent.sim.lesson import CardSpec, LessonConfig
from gkagent.sim.policy_data import advantage_samples, play_selfplay
from gkagent.sim.policy_mlp import INPUT_DIM, PolicyMLP, net_action


def _deck() -> list[CardSpec]:
    return [
        CardSpec("大1", 2, 30),
        CardSpec("大2", 2, 28),
        CardSpec("小1", 0, 5),
        CardSpec("小2", 0, 6),
        CardSpec("小3", 1, 12),
        CardSpec("小4", 1, 10),
    ]


def _config(turns: int = 4) -> LessonConfig:
    return LessonConfig(
        turns=turns, stamina=8, target_clear=40, target_perfect=80,
        hand_size=3, plays_per_turn=1,
    )


def _score_model() -> PolicyMLP:
    w1 = np.zeros((INPUT_DIM, 1))
    w1[LEAF_DIM + 0, 0] = 1.0
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


def test_eps_zero_bit_identical_to_argmax() -> None:
    deck, config = _deck(), _config()
    model = _score_model()
    sim_a, row_a = play_selfplay(deck, config, 800000, model)
    sim_b, row_b = play_selfplay(deck, config, 800000, model, explore_eps=0.0)
    assert row_a == row_b
    assert [r.action for r in sim_a.decisions] == [r.action for r in sim_b.decisions]


def test_eps_positive_deterministic_and_differs() -> None:
    deck, config = _deck(), _config()
    model = _score_model()
    sim_a, row_a = play_selfplay(deck, config, 800001, model, explore_eps=0.5)
    sim_b, row_b = play_selfplay(deck, config, 800001, model, explore_eps=0.5)
    assert row_a == row_b
    assert [r.action for r in sim_a.decisions] == [r.action for r in sim_b.decisions]
    # 高 ε 下至少有些决策与 argmax 不同（真的在探索）
    sim_arg, _ = play_selfplay(deck, config, 800001, model)
    actions_arg = [r.action for r in sim_arg.decisions]
    actions_exp = [r.action for r in sim_a.decisions]
    assert actions_exp != actions_arg


def test_explore_never_skips_with_playable() -> None:
    deck, config = _deck(), _config()
    model = _score_model()
    for seed in range(800002, 800012):
        sim, _row = play_selfplay(deck, config, seed, model, explore_eps=1.0)
        assert sim.decisions
        for record in sim.decisions:
            assert record.action is not None  # 有可出牌绝不 SKIP（硬规矩）
            assert record.action in record.playable


def test_explore_eps_validation() -> None:
    deck, config = _deck(), _config()
    model = _score_model()
    with pytest.raises(ValueError, match="explore_eps"):
        play_selfplay(deck, config, 800003, model, explore_eps=-0.1)
    with pytest.raises(ValueError, match="explore_eps"):
        play_selfplay(deck, config, 800003, model, explore_eps=1.5)


def test_explore_advantage_still_on_policy() -> None:
    """探索局的被选动作分支终局分 = 原局终局分（标签口径不变）。"""
    deck, config = _deck(), _config()
    model = _score_model()
    sim, row = play_selfplay(deck, config, 800004, model, explore_eps=0.3)
    for record in sim.decisions:
        _X, _y, meta = advantage_samples(
            deck, config, 800004, record, lambda current: net_action(current, model)
        )
        assert meta["finals"][record.action] == row["score"]


def test_cli_selfplay_explore_eps(tmp_path: Path) -> None:
    model_path = _score_model().save(tmp_path / "student.json")
    out = tmp_path / "selfplay.npz"
    code = bed.main(
        [
            "--mode", "selfplay", "--student-model", str(model_path),
            "--games", "2", "--seed", "800000", "--explore-eps", "0.3",
            "--out", str(out),
        ]
    )
    assert code == 0
    doc = np.load(out, allow_pickle=False)
    meta = json.loads(str(doc["meta_json"]))
    assert meta["args"]["explore_eps"] == 0.3
    assert meta["n_samples"] > 0


def test_cli_demos_rejects_explore_eps(tmp_path: Path) -> None:
    model_path = _score_model().save(tmp_path / "teacher.json")
    with pytest.raises(SystemExit) as excinfo:
        bed.main(
            [
                "--mode", "demos", "--teacher-net", str(model_path),
                "--games", "1", "--explore-eps", "0.3",
                "--out", str(tmp_path / "x.npz"),
            ]
        )
    assert excinfo.value.code == 2