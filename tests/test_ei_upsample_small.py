"""B11 r11：train_ei_policy --upsample-small（small 自对弈上采样）纯增量单测。

R9_ANALYSIS §6 候选②落地：训练时把 small 自对弈行重复 N 份，提升 small 优化能量
份额（与 --norm-by-scenario 叠加 →~66%），给 small 更多预算在漂移后的特征位置
重新学准精细行为。覆盖（默认行为逐位不变是硬约束）：

* 多文件默认 golden 回归：固定合成数据 + 固定超参 → 权重逐位等于 r10 改前参照
  （与 test_ei_norm_scenario.py 同 golden，证明 scenario_col/_subsample 改动不动默认路径）；
* 开关关（=1）与不给出逐位相同；默认 meta 不新增 upsample_small 键；
* 白盒 _upsample_small：small 行 ×N、large 不动、seed/group 保持（不泄漏）；
* 能量份额：norm-by-scenario + ×2 后 small 能量份额显著升高（→~66%，含示范）；
* 上采样在教师占比下采样**之后**：teacher-frac 作用于基础池，base_small_rows 是下采样后；
* 单文件路径（meta.args.scenario）也能上采样；无 small 行时原样返回；factor 校验；
* 确定性；上采样路径 golden（锁定数值行为，后续改动不得静默漂移）。

不落盘（除 tmp_path）、不依赖 out/ 研究产物（合成 npz，与 r9/r10 测试同构造）。
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
    """与 r10 测试完全同配方的合成数据（small 850 / large 700 / demos 300）。"""
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
    """默认（upsample=1）多文件全局 std golden 与 r10 改前参照逐位相同。

    证明 scenario_col 跟踪 / _subsample 切片改动不改变默认训练路径的任何数值。
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
    # 默认路径 meta 不新增 upsample 键
    assert "upsample_small" not in mix


def test_upsample_off_bit_identical(tmp_path: Path) -> None:
    """--upsample-small 1 与不给出：权重与 meta 逐位相同。"""
    sp_small, sp_large, dm = _make_pair(tmp_path)
    models = []
    for name, extra in (("off.json", []), ("one.json", ["--upsample-small", "1"])):
        out = tmp_path / name
        assert tep.main(
            [
                "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
                "--teacher-frac", "0.15", "--epochs", "10",
                "--norm-by-scenario", "--out", str(out), *extra,
            ]
        ) == 0
        models.append(PolicyMLP.load(out))
    for attr in ("mean", "scale", "w1", "b1", "w2", "b2", "out_w", "out_b"):
        assert np.array_equal(getattr(models[0], attr), getattr(models[1], attr))
    assert models[0].meta == models[1].meta
    assert "upsample_small" not in models[1].meta["mix"]


# ---------------------------------------------------------------- 白盒正确性


def test_upsample_whitebox_rows_and_no_leakage(tmp_path: Path) -> None:
    """_upsample_small：small 行 ×N、large 不动；重复行保持原 seed/group（不泄漏）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    combined = tep._load_many([a, b], norm_by_scenario=True)
    sc = combined["scenario_col"]
    up = tep._upsample_small(combined, 2, sc)
    # small 500→1000，large 400 不动，总 1400
    assert up["X"].shape[0] == 1400
    assert int((up["scenario_col"] == "small").sum()) == 1000
    assert int((up["scenario_col"] == "large").sum()) == 400
    # 前 900 行（原拼接）逐位不变
    assert np.array_equal(up["X"][:900], combined["X"])
    assert np.array_equal(up["y"][:900], combined["y"])
    assert np.array_equal(up["seed"][:900], combined["seed"])
    assert np.array_equal(up["group"][:900], combined["group"])
    # 追加的 500 行 = small 行副本（seed/group 与原 small 一致 → 同 seed 侧不泄漏）
    small_idx = np.where(sc == "small")[0]
    assert np.array_equal(up["seed"][900:], combined["seed"][small_idx])
    assert np.array_equal(up["group"][900:], combined["group"][small_idx])
    assert np.array_equal(up["X"][900:], combined["X"][small_idx])
    # factor<=1 原样返回
    assert tep._upsample_small(combined, 1, sc) is combined


def test_upsample_large_only_noop(tmp_path: Path) -> None:
    """无 small 行（纯 large）→ 上采样原样返回（不猜场景）。"""
    b = tmp_path / "b.npz"
    c = tmp_path / "c.npz"
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    _save_synthetic_npz(c, n=300, n_seeds=30, label_std=24.0, seed0=910000, scenario="large")
    combined = tep._load_many([b, c], norm_by_scenario=True)
    up = tep._upsample_small(combined, 3, combined["scenario_col"])
    assert up["X"].shape[0] == 700
    assert np.array_equal(up["X"], combined["X"])


def test_upsample_factor3(tmp_path: Path) -> None:
    """×3：small 行重复 3 份（追加 2 份副本）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=200, n_seeds=20, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=100, n_seeds=10, label_std=24.0, seed0=900000, scenario="large")
    combined = tep._load_many([a, b], norm_by_scenario=True)
    up = tep._upsample_small(combined, 3, combined["scenario_col"])
    assert up["X"].shape[0] == 200 * 3 + 100
    assert int((up["scenario_col"] == "small").sum()) == 600


# ---------------------------------------------------------------- 能量份额


def test_upsample_energy_share_restored(tmp_path: Path) -> None:
    """能量份额（Σy² 代理，R9_ANALYSIS §2/§6）：norm-by-scenario + ×2 后
    small 能量份额显著升高（自对弈内 →~71%，含示范 →~66%）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(a, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=700, n_seeds=70, label_std=24.0, seed0=900000, scenario="large")
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    combined = tep._load_many([a, b], norm_by_scenario=True)
    sc = combined["scenario_col"]
    y_base = combined["y"]
    e_small_base = float(np.sum(y_base[sc == "small"] ** 2))
    e_large = float(np.sum(y_base[sc == "large"] ** 2))
    share_base = e_small_base / (e_small_base + e_large)
    up = tep._upsample_small(combined, 2, sc)
    y_up = up["y"]
    sc_up = up["scenario_col"]
    e_small_up = float(np.sum(y_up[sc_up == "small"] ** 2))
    share_up = e_small_up / (e_small_up + e_large)
    # 自对弈内 small 份额：~55% → ~71%（×2）
    assert share_base == pytest.approx(850 / 1550, abs=0.04)
    assert share_up == pytest.approx(1700 / 2400, abs=0.04)
    assert share_up > share_base + 0.12
    # 含示范（±1 软目标，能量 ~0.5/行）的总 small 份额 →~66%
    demos = tep._load_many([dm])
    e_demos = float(np.sum(demos["y"] ** 2))
    total_share = e_small_up / (e_small_up + e_large + e_demos)
    assert 0.60 < total_share < 0.72


# ---------------------------------------------------------------- meta / 流程


def test_upsample_meta_records(tmp_path: Path) -> None:
    sp_small, sp_large, dm = _make_pair(tmp_path)
    out = tmp_path / "v11.json"
    assert tep.main(
        [
            "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
            "--teacher-frac", "0.15", "--round", "11", "--epochs", "5",
            "--norm-by-scenario", "--upsample-small", "2", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    mix = model.meta["mix"]
    info = mix["upsample_small"]
    assert info["factor"] == 2
    assert info["base_selfplay_rows"] == 1550
    assert info["base_small_rows"] == 850
    assert info["post_selfplay_rows"] == 2400
    assert info["post_small_rows"] == 1700
    assert info["post_large_rows"] == 700
    assert mix["selfplay_rows"] == 2400
    assert mix["demo_rows"] == 273
    assert model.meta["task"] == "B11 expert-iteration round11"
    # 上采样后教师占比（行数）下降（teacher-frac 作用于基础池）
    assert mix["teacher_frac_target"] == 0.15
    assert mix["teacher_frac_actual"] == pytest.approx(273 / 2673, rel=1e-9)


def test_upsample_after_subsample(tmp_path: Path) -> None:
    """示范不足 → 基础自对弈池先下采样，再上采样 small；base_small_rows 是下采样后。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(a, n=500, n_seeds=50, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=400, n_seeds=40, label_std=24.0, seed0=900000, scenario="large")
    _save_synthetic_npz(dm, n=100, n_seeds=20, label_std=1.0, seed0=400000)
    out = tmp_path / "v11.json"
    assert tep.main(
        [
            "--selfplay", str(a), str(b), "--demos", str(dm),
            "--teacher-frac", "0.15", "--epochs", "5",
            "--norm-by-scenario", "--upsample-small", "2", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    info = model.meta["mix"]["upsample_small"]
    # max_s = int(100×0.85/0.15) = 566（基础池下采样，与 r10 同口径）
    assert info["base_selfplay_rows"] == 566
    assert info["base_small_rows"] < 500  # 下采样去掉部分 small
    assert info["post_selfplay_rows"] == 566 + info["base_small_rows"]
    assert model.meta["mix"]["demo_rows"] == 100


def test_upsample_single_file(tmp_path: Path) -> None:
    """单文件自对弈（meta.args.scenario=small）也能上采样（无 scenario_col 走 meta）。"""
    sp = tmp_path / "sp.npz"
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(sp, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    out = tmp_path / "v11.json"
    assert tep.main(
        [
            "--selfplay", str(sp), "--demos", str(dm),
            "--teacher-frac", "0.15", "--epochs", "5",
            "--upsample-small", "2", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    info = model.meta["mix"]["upsample_small"]
    assert info["base_small_rows"] == 850
    assert info["post_small_rows"] == 1700
    assert model.meta["mix"]["selfplay_rows"] == 1700


def test_upsample_no_seed_leakage_split(tmp_path: Path) -> None:
    """重复行保持原 seed → unique seed 集合不变（seed 分组切分副本与原件同侧，不泄漏）。"""
    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    _save_synthetic_npz(a, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    _save_synthetic_npz(b, n=700, n_seeds=70, label_std=24.0, seed0=900000, scenario="large")
    combined = tep._load_many([a, b], norm_by_scenario=True)
    base_unique = set(combined["seed"].tolist())
    up = tep._upsample_small(combined, 2, combined["scenario_col"])
    # 上采样只重复行，不引入新 seed → unique 集合逐位不变（切分不泄漏的结构保证）
    assert set(up["seed"].tolist()) == base_unique
    assert up["X"].shape[0] == 2400
    # 每个 small seed 的行数翻倍（副本与原件同 seed）
    base_small_seeds = combined["seed"][combined["scenario_col"] == "small"]
    up_small_seeds = up["seed"][up["scenario_col"] == "small"]
    assert len(up_small_seeds) == 2 * len(base_small_seeds)
    # 训练端到端：mix 行数反映上采样，val 指标存在（切分正常完成）
    dm = tmp_path / "dm.npz"
    _save_synthetic_npz(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)
    out = tmp_path / "v11.json"
    assert tep.main(
        [
            "--selfplay", str(a), str(b), "--demos", str(dm),
            "--teacher-frac", "0.15", "--epochs", "5",
            "--norm-by-scenario", "--upsample-small", "2", "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    assert model.meta["mix"]["selfplay_rows"] == 2400
    assert model.meta["val_metrics"]["n"] > 0


def test_upsample_deterministic(tmp_path: Path) -> None:
    sp_small, sp_large, dm = _make_pair(tmp_path)
    models = []
    for name in ("r1.json", "r2.json"):
        out = tmp_path / name
        assert tep.main(
            [
                "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
                "--teacher-frac", "0.15", "--round", "11", "--epochs", "10",
                "--norm-by-scenario", "--upsample-small", "2", "--out", str(out),
            ]
        ) == 0
        models.append(PolicyMLP.load(out))
    for attr in ("mean", "scale", "w1", "b1", "w2", "b2", "out_w", "out_b"):
        assert np.array_equal(getattr(models[0], attr), getattr(models[1], attr))


def test_upsample_factor_validation(tmp_path: Path) -> None:
    sp_small, sp_large, dm = _make_pair(tmp_path)
    with pytest.raises(SystemExit):
        tep.main(
            [
                "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
                "--upsample-small", "0", "--out", str(tmp_path / "x.json"),
            ]
        )


def test_upsample_golden_weights(tmp_path: Path) -> None:
    """上采样路径 golden（norm-by-scenario + ×2，改后参照）：锁定数值行为。"""
    sp_small, sp_large, dm = _make_pair(tmp_path)
    out = tmp_path / "v11.json"
    assert tep.main(
        [
            "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
            "--teacher-frac", "0.15", "--round", "11", "--epochs", "20",
            "--hidden", "192", "96", "--norm-by-scenario", "--upsample-small", "2",
            "--out", str(out),
        ]
    ) == 0
    model = PolicyMLP.load(out)
    assert float(model.w1[0, 0]) == 0.02639146372949935
    assert float(model.w2[3, 7]) == -0.015410064137722558
    assert float(model.out_b[0]) == 0.0024720164827694477
    assert float(model.mean[5]) == -0.013271357581492204
