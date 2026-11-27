"""r9 前置探针：改 train_ei_policy 之前，固定合成数据上跑单文件默认路径，
留逐位参照（改后重跑同命令比 sha256）。一次性脚本，不提交。"""
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


def save_synthetic(path: Path, *, n: int, n_seeds: int, label_std: float, seed0: int) -> None:
    rng = np.random.default_rng(seed0)
    X = rng.normal(size=(n, INPUT_DIM))
    y = rng.normal(scale=label_std, size=n)
    seed = np.asarray([seed0 + i % n_seeds for i in range(n)], dtype=np.int64)
    group = np.arange(n, dtype=np.int64) // 5
    np.savez_compressed(
        path, X=X, y=y, seed=seed, group=group,
        meta_json=np.asarray(json.dumps({"kind": "synthetic", "args": {"scenario": "small"}})),
    )


def main() -> None:
    sp = OUT / "_r9_ref_sp.npz"
    dm = OUT / "_r9_ref_dm.npz"
    save_synthetic(sp, n=850, n_seeds=100, label_std=12.0, seed0=300000)
    save_synthetic(dm, n=300, n_seeds=40, label_std=1.0, seed0=400000)

    single = OUT / "_r9_ref_single.json"
    assert tep.main([
        "--selfplay", str(sp), "--demos", str(dm),
        "--teacher-frac", "0.15", "--round", "6", "--epochs", "20",
        "--hidden", "192", "96", "--out", str(single),
    ]) == 0
    bc = OUT / "_r9_ref_bc.json"
    assert tep.main(["--demos", str(dm), "--epochs", "20", "--out", str(bc)]) == 0
    sp_only = OUT / "_r9_ref_sponly.json"
    assert tep.main([
        "--selfplay", str(sp), "--teacher-frac", "0.15", "--epochs", "20", "--out", str(sp_only),
    ]) == 0

    for p in (single, bc, sp_only):
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        print(f"{p.name}: sha256={h}")
    m = PolicyMLP.load(single)
    print("golden w1[0,0] =", repr(float(m.w1[0, 0])))
    print("golden w2[3,7] =", repr(float(m.w2[3, 7])))
    print("golden out_b[0] =", repr(float(m.out_b[0])))
    print("golden mean[5] =", repr(float(m.mean[5])))
    print("mix:", m.meta["mix"])


if __name__ == "__main__":
    main()
