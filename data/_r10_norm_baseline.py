"""r10 前置探针：改 train_ei_policy 之前，固定合成数据上跑默认路径，
留逐位参照（改后重跑同命令比 sha256）。一次性脚本，不提交。

两组参照：
* 单文件（与 data/_r9_multifile_baseline.py 完全同配方）——sha256 应仍等于
  r9 记录的 28efed56… / b43dc14d… / e668547c…（跨轮默认不变）；
* 多文件默认（全局 std）——r10 新增 --norm-by-scenario 不得改变默认多文件
  行为，这里留改前 golden（权重值写进 tests/test_ei_norm_scenario.py）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import train_ei_policy as tep
from gkagent.sim.policy_mlp import INPUT_DIM, PolicyMLP

OUT = ROOT / "out"


def save_synthetic(
    path: Path, *, n: int, n_seeds: int, label_std: float, seed0: int,
    scenario: str = "small",
) -> None:
    rng = np.random.default_rng(seed0)
    X = rng.normal(size=(n, INPUT_DIM))
    y = rng.normal(scale=label_std, size=n)
    seed = np.asarray([seed0 + i % n_seeds for i in range(n)], dtype=np.int64)
    group = np.arange(n, dtype=np.int64) // 5
    np.savez_compressed(
        path, X=X, y=y, seed=seed, group=group,
        meta_json=np.asarray(
            json.dumps({"kind": "synthetic", "args": {"scenario": scenario}})
        ),
    )


def main() -> None:
    # ---- 单文件参照（与 r9 探针同配方）----
    sp = OUT / "_r9_ref_sp.npz"
    dm = OUT / "_r9_ref_dm.npz"
    save_synthetic(sp, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    save_synthetic(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)

    single = OUT / "_r10_ref_single.json"
    assert tep.main([
        "--selfplay", str(sp), "--demos", str(dm),
        "--teacher-frac", "0.15", "--round", "6", "--epochs", "20",
        "--hidden", "192", "96", "--out", str(single),
    ]) == 0
    bc = OUT / "_r10_ref_bc.json"
    assert tep.main(["--demos", str(dm), "--epochs", "20", "--out", str(bc)]) == 0
    sp_only = OUT / "_r10_ref_sponly.json"
    assert tep.main([
        "--selfplay", str(sp), "--teacher-frac", "0.15", "--epochs", "20",
        "--out", str(sp_only),
    ]) == 0

    # ---- 多文件默认（全局 std）参照：r10 开关不得改变此路径 ----
    sp_small = OUT / "_r10_ref_sp_small.npz"
    sp_large = OUT / "_r10_ref_sp_large.npz"
    save_synthetic(sp_small, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    save_synthetic(sp_large, n=700, n_seeds=70, label_std=24.0, seed0=900000,
                   scenario="large")
    multi = OUT / "_r10_ref_multi_default.json"
    assert tep.main([
        "--selfplay", str(sp_small), str(sp_large), "--demos", str(dm),
        "--teacher-frac", "0.15", "--round", "9", "--epochs", "20",
        "--hidden", "192", "96", "--out", str(multi),
    ]) == 0

    for p in (single, bc, sp_only, multi):
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        print(f"{p.name}: sha256={h}")
    m = PolicyMLP.load(multi)
    print("multi-default golden w1[0,0] =", repr(float(m.w1[0, 0])))
    print("multi-default golden w2[3,7] =", repr(float(m.w2[3, 7])))
    print("multi-default golden out_b[0] =", repr(float(m.out_b[0])))
    print("multi-default golden mean[5] =", repr(float(m.mean[5])))
    print("multi-default mix:", m.meta["mix"])
    print("multi-default multi_file scenarios:",
          [f["scenario"] for f in m.meta["multi_file"]["selfplay"]])


if __name__ == "__main__":
    main()
