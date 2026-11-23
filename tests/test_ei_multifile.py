"""B11 r9：train_ei_policy 多文件混合（small+large）纯增量单测。

覆盖（单文件默认行为逐位不变是硬约束）：
* 单文件 golden 回归：固定合成数据 + 固定超参 → 权重逐位等于改前参照
  （2026-11-23 改前跑 ``data/_r9_multifile_baseline.py`` 留的 sha256/权重值），
  meta 不新增键（无 multi_file）、sources 顺序不变；
* 多文件拼接：按给出顺序 vstack、行数求和、group 偏移防跨文件碰撞、
  seed 保持原值、全局 std 归一化、教师占比对拼接池下采样仍精确；
* --demos 同样支持多文件；meta.multi_file 逐文件明细 + sources 全列；
* 确定性（同参重跑逐位相同）；seed 块重叠告警；CLI 参数校验。

不落盘（除 tmp_path）、不依赖 out/ 研究产物（合成 npz，与 r2 测试同构造）。
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

import train_ei_policy as tep

from gkagent.sim.policy_mlp import INPUT_DIM, PolicyMLP


def _save_synthetic_npz(
    path: Path,
    *,
    n: int,
    n_seeds: int,
    label_std: float,
    seed0: int,
    scenario: str = "small",
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
        meta_json=np.asarray(
            json.dumps({"kind": "synthetic", "args": {"scenario": scenario}})
        ),
    )


def _load_npz(path: Path) -> dict:
    doc = np.load(path, allow_pickle=False)
    return {
        "X": doc["X"],
        "y": doc["y"],
        "seed": doc["seed"],
        "group": doc["group"],
    }


# ---------------------------------------------------------------- 单文件逐位不变


def test_single_file_golden_weights_unchanged(tmp_path: Path) -> None:
    """改前参照（data/_r9_multifile_baseline.py，sha256 28efed56…）逐位回归。

    合成数据/超参与参照脚本完全一致；golden 权重是改前代码的输出，
    任何默认路径的语义/数值漂移都会在这里失败（bit-identical 纪律）。
    """
    sp = tmp_path / "sp.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(sp, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    out = tmp_path / "single.json"
    code = tep.main(
        [
            "--selfplay", str(sp), "--demos", str(dm),
            "--teacher-frac", "0.15", "--round", "6", "--epochs", "20",
            "--hidden", "192", "96", "--out", str(out),
        ]
    )
    assert code == 0
    model = PolicyMLP.load(out)
    assert float(model.w1[0, 0]) == 0.033346793894540955
    assert float(model.w2[3, 7]) == -0.017056899569703052
    assert float(model.out_b[0]) == 0.0025696842933170187
    assert float(model.mean[5]) == 0.018621309210687217
    mix = model.meta["mix"]
    assert mix["selfplay_rows"] == 850
    assert mix["demo_rows"] == 150
    assert mix["teacher_frac_actual"] == pytest.approx(0.15, abs=1e-9)
    assert mix["selfplay_adv_std"] == pytest.approx(11.986734728455223, rel=1e-12)
    # 单文件 meta 不新增键、sources 顺序不变（selfplay 在前、demos 在后）
    assert "multi_file" not in model.meta
    assert model.meta["sources"] == [str(sp), str(dm)]


def test_single_file_bc_golden_unchanged(tmp_path: Path) -> None:
    """纯 BC（--demos 单文件）默认路径同样逐位不变（参照 sha256 b43dc14d…）。"""
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    out = tmp_path / "bc.json"
    code = tep.main(["--demos", str(dm), "--epochs", "20", "--out", str(out)])
    assert code == 0
    model = PolicyMLP.load(out)
    assert model.meta["task"] == "B11 expert-iteration round1"
    assert model.meta["mix"]["demo_rows"] == 300
    assert model.meta["mix"]["selfplay_rows"] == 0
    assert "multi_file" not in model.meta
    assert model.meta["sources"] == [str(dm)]
    # 与改前参照同配方：train MSE 0.1781（4 位小数口径）
    assert model.meta["train_metrics"]["final_mse"] == pytest.approx(0.1781, abs=5e-5)


# ---------------------------------------------------------------- 多文件拼接


def test_multifile_selfplay_concat_order_and_groups(tmp_path: Path) -> None:
    """白盒 _load_many：按给出顺序拼接、group 偏移防碰撞、seed 保持原值。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    da, db = _load_npz(a), _load_npz(b)
    combined = tep._load_many([a, b])
    assert combined["X"].shape[0] == 900
    assert np.array_equal(combined["X"], np.vstack([da["X"], db["X"]]))
    assert np.array_equal(combined["y"], np.concatenate([da["y"], db["y"]]))
    assert np.array_equal(combined["seed"], np.concatenate([da["seed"], db["seed"]]))
    # group：两文件原本都是 0..k → 拼接后不得有跨文件碰撞
    ga = combined["group"][:500]
    gb = combined["group"][500:]
    assert np.array_equal(ga, da["group"])  # 第一个文件不动
    assert not (set(ga.tolist()) & set(gb.tolist()))
    assert gb.min() > ga.max()
    # 同文件内决策分组关系不变（偏移是常量）
    assert np.array_equal(gb - gb.min(), db["group"] - db["group"].min())
    assert len(combined["files"]) == 2
    assert combined["files"][1]["scenario"] == "large"


def test_multifile_single_path_equals_single_file(tmp_path: Path) -> None:
    """--selfplay 只给一个路径（nargs 列表长度 1）= 原单文件路径，逐位相同。"""
    sp = tmp_path / "sp.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(sp, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    outs = []
    for name in ("one.json", "two.json"):
        out = tmp_path / name
        assert tep.main(
            [
                "--selfplay", str(sp), "--demos", str(dm),
                "--teacher-frac", "0.15", "--epochs", "20", "--out", str(out),
            ]
        ) == 0
        outs.append(PolicyMLP.load(out))
    assert np.array_equal(outs[0].w1, outs[1].w1)
    assert np.array_equal(outs[0].out_w, outs[1].out_w)
    assert "multi_file" not in outs[0].meta


def test_multifile_mix_teacher_frac_exact(tmp_path: Path) -> None:
    """small+large 自对弈拼接后，教师占比仍确定性下采样到精确 0.15。"""
    sp_small = tmp_path / "small.npz"
    sp_large = tmp_path / "large.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(sp_small, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(sp_large, n=350, n_seeds=35, label_std=24.0, seed0=900000, scenario="large")
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    out = tmp_path / "v9.json"
    code = tep.main(
        [
            "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
            "--teacher-frac", "0.15", "--round", "9", "--epochs", "5",
            "--out", str(out),
        ]
    )
    assert code == 0
    model = PolicyMLP.load(out)
    mix = model.meta["mix"]
    # 850 自对弈（500+350 全保）→ max_d = int(850×0.15/0.85) = 150
    assert mix["selfplay_rows"] == 850
    assert mix["demo_rows"] == 150
    assert mix["teacher_frac_actual"] == pytest.approx(0.15, abs=1e-9)
    assert model.meta["task"] == "B11 expert-iteration round9"


def test_multifile_demos_concat_and_meta(tmp_path: Path) -> None:
    """--demos 多文件：拼接 + 下采样；meta.multi_file 明细 + sources 全列。"""
    sp = tmp_path / "sp.npz"
    dm1 = tmp_path / "dm1.npz"
    dm2 = tmp_path / "dm2.npz"
    _save_synthetic_npz(sp, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(dm1, n=150, n_seeds=30, label_std=1.0, seed0=400000)
    _save_synthetic_npz(dm2, n=150, n_seeds=30, label_std=1.0, seed0=420000)
    out = tmp_path / "v9.json"
    code = tep.main(
        [
            "--selfplay", str(sp), "--demos", str(dm1), str(dm2),
            "--teacher-frac", "0.15", "--round", "9", "--epochs", "5",
            "--out", str(out),
        ]
    )
    assert code == 0
    model = PolicyMLP.load(out)
    mix = model.meta["mix"]
    assert mix["selfplay_rows"] == 850
    assert mix["demo_rows"] == 150  # 300 示范下采样到 150
    assert mix["teacher_frac_actual"] == pytest.approx(0.15, abs=1e-9)
    assert model.meta["sources"] == [str(sp), str(dm1), str(dm2)]
    multi = model.meta["multi_file"]
    assert "selfplay" not in multi  # 自对弈单文件 → 不记
    assert [f["path"] for f in multi["demos"]] == [str(dm1), str(dm2)]
    assert multi["demos"][0]["n_rows"] == 150
    assert multi["demos"][1]["seed_min"] == 420000


def test_multifile_meta_records_scenario_and_seed_blocks(tmp_path: Path) -> None:
    sp_small = tmp_path / "small.npz"
    sp_large = tmp_path / "large.npz"
    _save_synthetic_npz(sp_small, n=500, n_seeds=50, label_std=12.0, seed0=700000)
    _save_synthetic_npz(sp_large, n=350, n_seeds=35, label_std=24.0, seed0=900000, scenario="large")
    out = tmp_path / "v9.json"
    assert tep.main(
        [
            "--selfplay", str(sp_small), str(sp_large),
            "--teacher-frac", "0.15", "--epochs", "5", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    files = model.meta["multi_file"]["selfplay"]
    assert [f["scenario"] for f in files] == ["small", "large"]
    assert (files[0]["seed_min"], files[0]["seed_max"]) == (700000, 700049)
    assert (files[1]["seed_min"], files[1]["seed_max"]) == (900000, 900034)
    assert files[0]["n_rows"] == 500
    assert files[1]["n_rows"] == 350


def test_multifile_global_std_normalization(tmp_path: Path) -> None:
    """优势归一化 = 拼接后全局 std（与单文件「全局 std」同口径）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    out = tmp_path / "v9.json"
    assert tep.main(
        ["--selfplay", str(a), str(b), "--epochs", "5", "--out", str(out)]
    ) == 0
    model = PolicyMLP.load(out)
    expected_std = float(np.concatenate([_load_npz(a)["y"], _load_npz(b)["y"]]).std())
    assert model.meta["mix"]["selfplay_adv_std"] == pytest.approx(expected_std, rel=1e-12)
    # 不是任一单文件 std（两文件尺度不同）
    assert expected_std != pytest.approx(_load_npz(a)["y"].std(), rel=1e-3)


def test_multifile_subsample_combined_pool(tmp_path: Path) -> None:
    """示范不足时，下采样作用于拼接后的自对弈池（small+large 一起缩）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    _save_synthetic_npz(dm, n=100, n_seeds=20, label_std=1.0, seed0=400000)
    out = tmp_path / "v9.json"
    assert tep.main(
        [
            "--selfplay", str(a), str(b), "--demos", str(dm),
            "--teacher-frac", "0.15", "--epochs", "5", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    mix = model.meta["mix"]
    # max_s = int(100×0.85/0.15) = 566
    assert mix["selfplay_rows"] == 566
    assert mix["demo_rows"] == 100
    assert mix["teacher_frac_actual"] == pytest.approx(0.15, abs=1e-3)
    # multi_file 记的是输入文件明细（下采样前）
    assert [f["n_rows"] for f in model.meta["multi_file"]["selfplay"]] == [500, 400]


def test_multifile_deterministic(tmp_path: Path) -> None:
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=350, n_seeds=35, label_std=24.0, seed0=900000, scenario="large")
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    models = []
    for name in ("r1.json", "r2.json"):
        out = tmp_path / name
        assert tep.main(
            [
                "--selfplay", str(a), str(b), "--demos", str(dm),
                "--teacher-frac", "0.15", "--round", "9", "--epochs", "10",
                "--out", str(out),
            ]
        ) == 0
        models.append(PolicyMLP.load(out))
    for attr in ("mean", "scale", "w1", "b1", "w2", "b2", "out_w", "out_b"):
        assert np.array_equal(getattr(models[0], attr), getattr(models[1], attr))


def test_multifile_seed_overlap_warns(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """seed 块重叠 → 告警（不泄漏：同 seed 进同一 train/val 侧），训练仍成功。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=300020)  # 与 a 重叠
    out = tmp_path / "v9.json"
    assert tep.main(
        ["--selfplay", str(a), str(b), "--epochs", "5", "--out", str(out)]
    ) == 0
    captured = capsys.readouterr()
    assert "seed 块有重叠" in captured.out


def test_multifile_cli_requires_values(tmp_path: Path) -> None:
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(dm, n=200, n_seeds=40, label_std=1.0, seed0=400000)
    with pytest.raises(SystemExit) as excinfo:
        tep.main(["--selfplay", "--demos", str(dm), "--out", str(tmp_path / "x.json")])
    assert excinfo.value.code == 2
    with pytest.raises(SystemExit) as excinfo:
        tep.main(["--out", str(tmp_path / "x.json")])
    assert excinfo.value.code == 2
