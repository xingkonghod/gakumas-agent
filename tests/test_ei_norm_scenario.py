"""B11 r10：train_ei_policy --norm-by-scenario（按场景 std 归一化）纯增量单测。

覆盖（默认行为逐位不变是硬约束）：
* 多文件默认 golden 回归：固定合成数据 + 固定超参 → 权重逐位等于改前参照
  （2026-11-23 改前跑 ``data/_r10_norm_baseline.py`` 留的 sha256 c5d48db7…/权重值）；
  单文件 golden 由 test_ei_multifile.py 锁定（28efed56… / b43dc14d…）；
* 开关开着单文件 = 关着逐位相同（单文件路径不受影响）；
* 多文件开关正确性：各文件按自身 std 归一化（白盒 y 逐位核对）、
  mix.norm_by_scenario/scenario_std、multi_file.norm_std、selfplay_adv_std=None；
* 能量份额：按场景归一化后 small/large 能量份额 ≈ 行数份额（std 都回 1），
  显著高于全局 std 口径的 small 份额（r9 稀释修复的代理指标，R9_ANALYSIS §2/§6）；
* 输入侧标准化不变（单变量 = 标签归一化口径，mean/scale 逐位相同）；
* 示范不受影响（demos 明细无 norm_std）；下采样用全量文件 std；
  同 scenario 多文件逐文件 std；scenario 缺失记 unknown；确定性；开关 golden。

不落盘（除 tmp_path）、不依赖 out/ 研究产物（合成 npz，与 r9 测试同构造）。
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
    scenario: str | None = "small",
) -> None:
    rng = np.random.default_rng(seed0)
    X = rng.normal(size=(n, INPUT_DIM))
    y = rng.normal(scale=label_std, size=n)
    seed = np.asarray([seed0 + i % n_seeds for i in range(n)], dtype=np.int64)
    group = np.arange(n, dtype=np.int64) // 5
    args: dict = {}
    if scenario is not None:
        args["scenario"] = scenario
    np.savez_compressed(
        path,
        X=X,
        y=y,
        seed=seed,
        group=group,
        meta_json=np.asarray(json.dumps({"kind": "synthetic", "args": args})),
    )


def _load_npz(path: Path) -> dict:
    doc = np.load(path, allow_pickle=False)
    return {
        "X": doc["X"],
        "y": doc["y"],
        "seed": doc["seed"],
        "group": doc["group"],
    }


def _make_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    """与 data/_r10_norm_baseline.py 完全同配方的合成数据。"""
    sp_small = tmp_path / "small.npz"
    sp_large = tmp_path / "large.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(sp_small, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(
        sp_large, n=700, n_seeds=70, label_std=24.0, seed0=900000, scenario="large"
    )
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    return sp_small, sp_large, dm


# ---------------------------------------------------------------- 默认逐位不变


def test_multifile_default_golden_weights_unchanged(tmp_path: Path) -> None:
    """改前参照（data/_r10_norm_baseline.py，sha256 c5d48db7…）逐位回归。

    多文件默认 = 拼接后全局 std；r10 开关不得改变此路径的任何数值。
    """
    sp_small, sp_large, dm = _make_pair(tmp_path)
    out = tmp_path / "multi_default.json"
    code = tep.main(
        [
            "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
            "--teacher-frac", "0.15", "--round", "9", "--epochs", "20",
            "--hidden", "192", "96", "--out", str(out),
        ]
    )
    assert code == 0
    model = PolicyMLP.load(out)
    assert float(model.w1[0, 0]) == 0.025941969684607144
    assert float(model.w2[3, 7]) == -0.013745121166488605
    assert float(model.out_b[0]) == 0.0023747093248217797
    assert float(model.mean[5]) == -0.025950658553890376
    mix = model.meta["mix"]
    assert mix["selfplay_rows"] == 1550
    assert mix["demo_rows"] == 273
    assert mix["selfplay_adv_std"] == pytest.approx(18.179251096366713, rel=1e-12)
    # 默认路径 meta 不新增键
    assert "norm_by_scenario" not in mix
    assert "scenario_std" not in mix
    assert all("norm_std" not in f for f in model.meta["multi_file"]["selfplay"])


def test_flag_on_single_file_bit_identical(tmp_path: Path) -> None:
    """单文件路径不受开关影响：开着/关着权重与 meta 逐位相同。"""
    sp = tmp_path / "sp.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(sp, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    models = []
    for name, extra in (("off.json", []), ("on.json", ["--norm-by-scenario"])):
        out = tmp_path / name
        assert tep.main(
            [
                "--selfplay", str(sp), "--demos", str(dm),
                "--teacher-frac", "0.15", "--epochs", "20", "--out", str(out),
                *extra,
            ]
        ) == 0
        models.append(PolicyMLP.load(out))
    for attr in ("mean", "scale", "w1", "b1", "w2", "b2", "out_w", "out_b"):
        assert np.array_equal(getattr(models[0], attr), getattr(models[1], attr))
    assert models[0].meta == models[1].meta
    assert "norm_by_scenario" not in models[1].meta["mix"]


# ---------------------------------------------------------------- 开关正确性


def test_flag_on_per_file_std_whitebox(tmp_path: Path) -> None:
    """白盒 _load_many：各文件 y 逐位等于 原始y/自身std（不是全局 std）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    da, db = _load_npz(a), _load_npz(b)
    combined = tep._load_many([a, b], norm_by_scenario=True)
    assert combined["norm_by_scenario"] is True
    ya = da["y"] / max(float(da["y"].std()), 1e-6)
    yb = db["y"] / max(float(db["y"].std()), 1e-6)
    assert np.array_equal(combined["y"][:500], ya)
    assert np.array_equal(combined["y"][500:], yb)
    # 归一化后各文件 std 回到 1
    assert float(combined["y"][:500].std()) == pytest.approx(1.0, rel=1e-12)
    assert float(combined["y"][500:].std()) == pytest.approx(1.0, rel=1e-12)
    # X/seed/group 拼接不受开关影响
    plain = tep._load_many([a, b])
    assert np.array_equal(combined["X"], plain["X"])
    assert np.array_equal(combined["seed"], plain["seed"])
    assert np.array_equal(combined["group"], plain["group"])
    # 逐文件明细补 norm_std（= 实际除数）
    assert combined["files"][0]["norm_std"] == pytest.approx(float(da["y"].std()), rel=1e-12)
    assert combined["files"][1]["norm_std"] == pytest.approx(float(db["y"].std()), rel=1e-12)
    assert combined["scenario_std"] == {
        "small": [float(da["y"].std())],
        "large": [float(db["y"].std())],
    }


def test_flag_on_meta_records_scenario_std(tmp_path: Path) -> None:
    sp_small, sp_large, dm = _make_pair(tmp_path)
    out = tmp_path / "v10.json"
    assert tep.main(
        [
            "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
            "--teacher-frac", "0.15", "--round", "10", "--epochs", "5",
            "--norm-by-scenario", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    mix = model.meta["mix"]
    assert mix["norm_by_scenario"] is True
    assert mix["selfplay_adv_std"] is None  # 无单一全局除数
    small_std = float(_load_npz(sp_small)["y"].std())
    large_std = float(_load_npz(sp_large)["y"].std())
    assert mix["scenario_std"]["small"] == [pytest.approx(small_std, rel=1e-12)]
    assert mix["scenario_std"]["large"] == [pytest.approx(large_std, rel=1e-12)]
    assert model.meta["task"] == "B11 expert-iteration round10"
    files = model.meta["multi_file"]["selfplay"]
    assert [f["scenario"] for f in files] == ["small", "large"]
    assert files[0]["norm_std"] == pytest.approx(small_std, rel=1e-12)
    assert files[1]["norm_std"] == pytest.approx(large_std, rel=1e-12)
    # 占比/行数口径不变（单变量 = 归一化）
    assert mix["selfplay_rows"] == 1550
    assert mix["demo_rows"] == 273
    assert mix["teacher_frac_actual"] == pytest.approx(0.15, abs=1e-3)


def test_flag_on_energy_share_restored(tmp_path: Path) -> None:
    """能量份额（Σy² 代理，R9_ANALYSIS §2）：按场景归一化后 ≈ 行数份额，
    显著高于全局 std 口径的 small 份额（稀释修复）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=700, n_seeds=70, label_std=24.0, seed0=900000, scenario="large")
    da, db = _load_npz(a), _load_npz(b)

    def share(y: np.ndarray) -> float:
        e_small = float(np.sum(y[:850] ** 2))
        e_large = float(np.sum(y[850:] ** 2))
        return e_small / (e_small + e_large)

    raw = np.concatenate([da["y"], db["y"]])
    global_norm = raw / max(float(raw.std()), 1e-6)
    by_scenario = tep._load_many([a, b], norm_by_scenario=True)["y"]
    row_share = 850 / 1550
    # 全局 std：small 能量被 large 大尺度稀释（~23%）
    assert share(global_norm) < row_share - 0.15
    # 按场景：两边 std 都回 1 → 能量份额 ≈ 行数份额（~55%）
    assert share(by_scenario) == pytest.approx(row_share, abs=0.04)
    assert share(by_scenario) > share(global_norm) + 0.15


def test_flag_on_input_normalization_unchanged(tmp_path: Path) -> None:
    """单变量纪律：开关只改标签归一化，X 侧 mean/scale 逐位不变。"""
    sp_small, sp_large, dm = _make_pair(tmp_path)
    models = []
    for name, extra in (("off.json", []), ("on.json", ["--norm-by-scenario"])):
        out = tmp_path / name
        assert tep.main(
            [
                "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
                "--teacher-frac", "0.15", "--epochs", "5", "--out", str(out),
                *extra,
            ]
        ) == 0
        models.append(PolicyMLP.load(out))
    assert np.array_equal(models[0].mean, models[1].mean)
    assert np.array_equal(models[0].scale, models[1].scale)
    # 标签口径确实变了（权重不同，否则开关没生效）
    assert not np.array_equal(models[0].w1, models[1].w1)


def test_flag_on_demos_not_normalized(tmp_path: Path) -> None:
    """示范软目标（±1 口径）不做 std 归一化：demos 明细无 norm_std。"""
    sp = tmp_path / "sp.npz"
    dm1 = tmp_path / "dm1.npz"
    dm2 = tmp_path / "dm2.npz"
    _save_synthetic_npz(sp, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(dm1, n=150, n_seeds=30, label_std=1.0, seed0=400000)
    _save_synthetic_npz(dm2, n=150, n_seeds=30, label_std=1.0, seed0=420000)
    out = tmp_path / "v10.json"
    assert tep.main(
        [
            "--selfplay", str(sp), "--demos", str(dm1), str(dm2),
            "--teacher-frac", "0.15", "--epochs", "5",
            "--norm-by-scenario", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    demos_files = model.meta["multi_file"]["demos"]
    assert all("norm_std" not in f for f in demos_files)
    # 自对弈单文件 → 开关不影响（无 multi_file.selfplay、mix 无新键）
    assert "selfplay" not in model.meta["multi_file"]
    assert "norm_by_scenario" not in model.meta["mix"]


def test_flag_on_subsample_uses_full_file_std(tmp_path: Path) -> None:
    """示范不足 → 自对弈池下采样；逐文件 std 仍按加载时全量文件计算。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    _save_synthetic_npz(dm, n=100, n_seeds=20, label_std=1.0, seed0=400000)
    out = tmp_path / "v10.json"
    assert tep.main(
        [
            "--selfplay", str(a), str(b), "--demos", str(dm),
            "--teacher-frac", "0.15", "--epochs", "5",
            "--norm-by-scenario", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    mix = model.meta["mix"]
    # max_s = int(100×0.85/0.15) = 566（与 r9 全局口径同下采样行为）
    assert mix["selfplay_rows"] == 566
    assert mix["demo_rows"] == 100
    # scenario_std 是全量文件 std，不是下采样后的
    assert mix["scenario_std"]["small"] == [
        pytest.approx(float(_load_npz(a)["y"].std()), rel=1e-12)
    ]
    assert mix["scenario_std"]["large"] == [
        pytest.approx(float(_load_npz(b)["y"].std()), rel=1e-12)
    ]
    # multi_file 记输入文件明细（下采样前）
    assert [f["n_rows"] for f in model.meta["multi_file"]["selfplay"]] == [500, 400]


def test_flag_on_same_scenario_two_files(tmp_path: Path) -> None:
    """同 scenario 两个文件：各按自身 std（不是合并 std），列表按拼接顺序。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=6.0, seed0=500000)
    da, db = _load_npz(a), _load_npz(b)
    combined = tep._load_many([a, b], norm_by_scenario=True)
    assert np.array_equal(combined["y"][:500], da["y"] / float(da["y"].std()))
    assert np.array_equal(combined["y"][500:], db["y"] / float(db["y"].std()))
    assert combined["scenario_std"]["small"] == [
        pytest.approx(float(da["y"].std()), rel=1e-12),
        pytest.approx(float(db["y"].std()), rel=1e-12),
    ]


def test_flag_on_missing_scenario_unknown(tmp_path: Path) -> None:
    """npz meta 缺 args.scenario → scenario_std 键记 unknown（不猜场景）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000, scenario=None)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    combined = tep._load_many([a, b], norm_by_scenario=True)
    assert "unknown" in combined["scenario_std"]
    assert combined["files"][0]["scenario"] is None


def test_flag_on_deterministic(tmp_path: Path) -> None:
    sp_small, sp_large, dm = _make_pair(tmp_path)
    models = []
    for name in ("r1.json", "r2.json"):
        out = tmp_path / name
        assert tep.main(
            [
                "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
                "--teacher-frac", "0.15", "--round", "10", "--epochs", "10",
                "--norm-by-scenario", "--out", str(out),
            ]
        ) == 0
        models.append(PolicyMLP.load(out))
    for attr in ("mean", "scale", "w1", "b1", "w2", "b2", "out_w", "out_b"):
        assert np.array_equal(getattr(models[0], attr), getattr(models[1], attr))


def test_flag_on_golden_weights(tmp_path: Path) -> None:
    """开关路径 golden（改后参照，data/_r10_norm_baseline.py 同配方 + 开关）：
    锁定按场景归一化的数值行为，后续改动不得静默漂移。"""
    sp_small, sp_large, dm = _make_pair(tmp_path)
    out = tmp_path / "v10.json"
    assert tep.main(
        [
            "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
            "--teacher-frac", "0.15", "--round", "10", "--epochs", "20",
            "--hidden", "192", "96", "--norm-by-scenario", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    assert float(model.w1[0, 0]) == 0.026403637620654404
    assert float(model.w2[3, 7]) == -0.014429346735432608
    assert float(model.out_b[0]) == 0.0024298799254141275
    # X 侧与默认 golden 逐位相同（单变量 = 标签口径）
    assert float(model.mean[5]) == -0.025950658553890376
