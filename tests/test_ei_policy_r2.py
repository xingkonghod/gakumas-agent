"""B11 渐退式专家迭代第 2 轮（教师←学生 / 门基线←学生 / large 配对）离线单测。

覆盖（全部纯增量口径，第 1 轮默认行为不变）：
* ``build_ei_dataset --mode demos --teacher-net``：教师=学生网逐决策记录，
  软目标同口径、硬规矩禁跳 → 教师 SKIP 剔除恒 0、确定性、selfplay 模式拒收；
  不带 --teacher-net 的 beam 示范默认路径不变；
* ``eval_ei --baseline-net``：门基线=上一轮学生（teacher_net 臂），默认仍 beam；
  同模型自比 = 逐位中性（CI 下界 0 → CONTINUE）；
* ``train_ei_policy --teacher-frac 0.15 --round 2``：确定性下采样到精确占比、
  meta.task 轮次；默认 round1 口径不变；
* large 场景（31 张 / 9 回合真机口径）：net 跑局确定、精确重放优势标签、
  eval_ei / selfplay CLI 冒烟。

不落盘（除 tmp_path）、不依赖真机/采集数据（牌组来自 tracked card_table.json）。
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
import eval_ei as eei
import eval_expectimax as ee
import eval_known_draw as ekd
import train_ei_policy as tep

from gkagent.sim.leaf_mlp import DIM as LEAF_DIM
from gkagent.sim.lesson import CardSpec, LessonConfig
from gkagent.sim.policy_data import advantage_samples, demo_samples, play_selfplay
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


def _config(turns: int = 3) -> LessonConfig:
    return LessonConfig(
        turns=turns, stamina=6, target_clear=40, target_perfect=80,
        hand_size=3, plays_per_turn=1,
    )


def _score_model() -> PolicyMLP:
    """手工权重：输出 = 候选牌白值分 → argmax = 挑高分牌（与 r1 测试同构造）。"""
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


def _load_npz(path: Path) -> dict:
    doc = np.load(path, allow_pickle=False)
    return {
        "X": doc["X"],
        "y": doc["y"],
        "seed": doc["seed"],
        "group": doc["group"],
        "meta": json.loads(str(doc["meta_json"])),
    }


def _save_synthetic_npz(
    path: Path, *, n: int, n_seeds: int, label_std: float, seed0: int
) -> None:
    rng = np.random.default_rng(seed0)
    X = rng.normal(size=(n, INPUT_DIM))
    y = rng.normal(scale=label_std, size=n)
    seed = np.asarray([seed0 + i % n_seeds for i in range(n)], dtype=np.int64)
    group = np.arange(n, dtype=np.int64) // 5
    np.savez_compressed(
        path,
        X=X,
        y=y,
        seed=seed,
        group=group,
        meta_json=np.asarray(json.dumps({"kind": "synthetic"})),
    )


# ---------------------------------------------------------------- 教师←学生网示范


def test_teacher_net_demos_cli_soft_targets(tmp_path: Path) -> None:
    model_path = _score_model().save(tmp_path / "teacher.json")
    out = tmp_path / "demos.npz"
    code = bed.main(
        [
            "--mode", "demos", "--teacher-net", str(model_path),
            "--games", "3", "--seed", "400000", "--out", str(out),
        ]
    )
    assert code == 0
    data = _load_npz(out)
    meta = data["meta"]
    assert meta["teacher_kind"] == "net"
    assert meta["excluded_teacher_skip"] == 0  # 硬规矩：net 教师有牌绝不 SKIP
    assert meta["n_samples"] > 0
    assert data["X"].shape == (meta["n_samples"], INPUT_DIM)
    # 软目标同口径：每组 +1 / −1/(k−1)，组和为 0
    for group in np.unique(data["group"]):
        mask = data["group"] == group
        y = data["y"][mask]
        k = int(mask.sum())
        assert k >= 2
        assert float(y.max()) == 1.0
        assert float(y.sum()) == pytest.approx(0.0, abs=1e-9)
        assert np.allclose(y[y < 1.0], -1.0 / (k - 1))


def test_teacher_net_demos_deterministic(tmp_path: Path) -> None:
    model_path = _score_model().save(tmp_path / "teacher.json")
    outs = []
    for name in ("a.npz", "b.npz"):
        out = tmp_path / name
        assert bed.main(
            [
                "--mode", "demos", "--teacher-net", str(model_path),
                "--games", "2", "--seed", "400000", "--out", str(out),
            ]
        ) == 0
        outs.append(_load_npz(out))
    assert np.array_equal(outs[0]["X"], outs[1]["X"])
    assert np.array_equal(outs[0]["y"], outs[1]["y"])


def test_teacher_net_rejected_in_selfplay_mode(tmp_path: Path) -> None:
    model_path = _score_model().save(tmp_path / "teacher.json")
    with pytest.raises(SystemExit) as excinfo:
        bed.main(
            [
                "--mode", "selfplay", "--teacher-net", str(model_path),
                "--student-model", str(model_path),
                "--games", "1", "--out", str(tmp_path / "x.npz"),
            ]
        )
    assert excinfo.value.code == 2


def test_teacher_net_demo_peak_is_net_choice() -> None:
    """白盒：net 教师示范的软目标峰值 = 教师自己出的牌（逐决策 net_action）。"""
    deck, config = _deck(), _config(turns=4)
    model = _score_model()
    sim, _row = play_selfplay(deck, config, 400000, model)
    assert sim.decisions
    assert all(record.action is not None for record in sim.decisions)
    seen = 0
    for record in sim.decisions:
        sample = demo_samples(record)
        if sample is None:
            assert len(record.playable) < 2  # 只允许强制决策被剔除
            continue
        _X, y, _meta = sample
        assert int(np.argmax(y)) == record.playable.index(record.action)
        seen += 1
    assert seen > 0


def test_beam_demos_default_path_unchanged(tmp_path: Path) -> None:
    """不带 --teacher-net：仍是 beam 教师（第 1 轮默认口径）。"""
    out = tmp_path / "beam_demos.npz"
    code = bed.main(
        [
            "--mode", "demos", "--games", "2", "--seed", "100000",
            "--budget-ms", "10", "--out", str(out),
        ]
    )
    assert code == 0
    meta = _load_npz(out)["meta"]
    assert meta["teacher_kind"] == "beam"
    assert meta["n_samples"] > 0


# ---------------------------------------------------------------- 门基线←学生网


def test_eval_ei_baseline_net_gate(tmp_path: Path) -> None:
    """门基线=上一轮学生：强学生 vs 弱学生应显著正 → PASS，JSON 记基线。"""
    net_path = _score_model().save(tmp_path / "v2.json")
    base_path = _anti_score_model().save(tmp_path / "v1.json")
    json_path = tmp_path / "eval.json"
    code = eei.main(
        [
            "--net-model", str(net_path), "--baseline-net", str(base_path),
            "--games", "6", "--seed", "3000",
            "--no-within", "--no-greedy", "--beam-budget-ms", "10",
            "--json", str(json_path),
        ]
    )
    assert code == 0  # PASS
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    verdict = doc["verdicts"]["unknown"]
    assert verdict["baseline"] == "teacher_net"
    assert verdict["gate_pass"] is True
    assert verdict["ci_low"] > 0
    table = doc["results"]["unknown"]
    assert "teacher_net" in table
    assert verdict["teacher_mean"] == table["teacher_net"]["mean"]
    assert verdict["beam_mean"] == table["beam_analytic"]["mean"]
    # 基线臂确实是另一个模型：弱学生均分显著低于强学生
    assert table["teacher_net"]["mean"] < table["net"]["mean"]


def test_eval_ei_default_gate_still_beam(tmp_path: Path) -> None:
    net_path = _score_model().save(tmp_path / "v1.json")
    json_path = tmp_path / "eval.json"
    eei.main(
        [
            "--net-model", str(net_path),
            "--games", "4", "--seed", "3000",
            "--no-within", "--no-greedy", "--beam-budget-ms", "10",
            "--json", str(json_path),
        ]
    )
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    verdict = doc["verdicts"]["unknown"]
    assert verdict["baseline"] == "beam_analytic"
    assert verdict["baseline_model"] is None
    assert "teacher_net" not in doc["results"]["unknown"]
    assert verdict["teacher_mean"] == doc["results"]["unknown"]["beam_analytic"]["mean"]


def test_eval_ei_same_model_baseline_neutral(tmp_path: Path) -> None:
    """候选=基线（同一模型）：两臂逐位相同 → Δ=0、CI 下界 0 → CONTINUE。"""
    net_path = _score_model().save(tmp_path / "v1.json")
    json_path = tmp_path / "eval.json"
    code = eei.main(
        [
            "--net-model", str(net_path), "--baseline-net", str(net_path),
            "--games", "4", "--seed", "3000",
            "--no-within", "--no-greedy", "--beam-budget-ms", "10",
            "--json", str(json_path),
        ]
    )
    assert code == 1  # CONTINUE（非 inferior 不算过）
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    table = doc["results"]["unknown"]
    assert table["net"]["scores"] == table["teacher_net"]["scores"]
    verdict = doc["verdicts"]["unknown"]
    assert verdict["delta"] == 0.0
    assert verdict["ci_low"] == 0.0
    assert verdict["ties"] == 4
    assert verdict["gate_pass"] is False


# ---------------------------------------------------------------- 训练（占比 / 轮次）


def test_train_mix_teacher_frac_015_round2(tmp_path: Path) -> None:
    selfplay = tmp_path / "selfplay.npz"
    demos = tmp_path / "demos.npz"
    _save_synthetic_npz(selfplay, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(demos, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    out = tmp_path / "v2.json"
    code = tep.main(
        [
            "--selfplay", str(selfplay), "--demos", str(demos),
            "--teacher-frac", "0.15", "--round", "2", "--epochs", "5",
            "--out", str(out),
        ]
    )
    assert code == 0
    model = PolicyMLP.load(out)
    mix = model.meta["mix"]
    # 确定性下采样：max_d = int(850×0.15/0.85) = 150 → 占比精确 0.15
    assert mix["demo_rows"] == 150
    assert mix["selfplay_rows"] == 850
    assert mix["teacher_frac_actual"] == pytest.approx(0.15, abs=1e-9)
    assert model.meta["task"] == "B11 expert-iteration round2"


def test_train_bc_default_round1_unchanged(tmp_path: Path) -> None:
    demos = tmp_path / "demos.npz"
    _save_synthetic_npz(demos, n=200, n_seeds=40, label_std=1.0, seed0=100000)
    out = tmp_path / "v0.json"
    code = tep.main(
        ["--demos", str(demos), "--epochs", "5", "--out", str(out)]
    )
    assert code == 0
    model = PolicyMLP.load(out)
    assert model.meta["task"] == "B11 expert-iteration round1"
    assert model.meta["mix"]["demo_rows"] == 200
    assert model.meta["mix"]["selfplay_rows"] == 0
    assert model.meta["mix"]["teacher_frac_actual"] == 1.0


# ---------------------------------------------------------------- large 场景配对


def test_large_scenario_deck_and_config() -> None:
    deck = ee.build_deck("large")
    config = ee.make_config("large")
    assert len(deck) == 31
    assert config.turns == 9
    assert config.stamina == 60
    assert config.target_clear == 300
    assert config.target_perfect == 450


def test_net_plays_large_deterministic() -> None:
    deck, config = ee.build_deck("large"), ee.make_config("large")
    model = _score_model()
    row_a = ekd.play(deck, config, 2000, known=False, policy="net", net_model=model)
    row_b = ekd.play(deck, config, 2000, known=False, policy="net", net_model=model)
    assert row_a == row_b
    assert row_a["fallbacks"] == 0
    assert row_a["decisions"] > 0


def test_large_advantage_replay_on_policy() -> None:
    """large 下精确重放优势标签同样成立：分支终局分 = 原局终局分、均值 0。"""
    deck, config = ee.build_deck("large"), ee.make_config("large")
    model = _score_model()
    sim, row = play_selfplay(deck, config, 300000, model)
    assert sim.decisions
    for record in sim.decisions[:2]:
        _X, y, meta = advantage_samples(
            deck, config, 300000, record, lambda current: net_action(current, model)
        )
        assert float(y.sum()) == pytest.approx(0.0, abs=1e-9)
        assert meta["finals"][record.action] == row["score"]


def test_eval_ei_large_cli_smoke(tmp_path: Path) -> None:
    net_path = _score_model().save(tmp_path / "v1.json")
    json_path = tmp_path / "eval_large.json"
    code = eei.main(
        [
            "--net-model", str(net_path), "--baseline-net", str(net_path),
            "--scenario", "large", "--games", "2", "--seed", "2000",
            "--no-within", "--no-greedy", "--beam-budget-ms", "10",
            "--json", str(json_path),
        ]
    )
    assert code == 1  # 同模型自比 = 中性 → CONTINUE
    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["args"]["scenario"] == "large"
    table = doc["results"]["unknown"]
    assert table["net"]["scores"] == table["teacher_net"]["scores"]
    assert len(table["beam_analytic"]["scores"]) == 2


def test_selfplay_large_cli_smoke(tmp_path: Path) -> None:
    model_path = _score_model().save(tmp_path / "v1.json")
    out = tmp_path / "selfplay_large.npz"
    code = bed.main(
        [
            "--mode", "selfplay", "--student-model", str(model_path),
            "--scenario", "large", "--games", "1", "--seed", "300000",
            "--out", str(out),
        ]
    )
    assert code == 0
    data = _load_npz(out)
    assert data["meta"]["n_samples"] > 0
    for group in np.unique(data["group"]):
        y = data["y"][data["group"] == group]
        assert float(y.sum()) == pytest.approx(0.0, abs=1e-9)