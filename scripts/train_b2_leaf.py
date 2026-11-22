"""B2 叶子训练：在采集的「叶子状态特征 → 后续得分」样本上训练 MLP 叶子。

训练/验证按 **seed 分组切分**（同一局的叶子样本不跨切分，避免泄漏）。
同时拟合一个 ridge 线性基线（仅打印 r²/MSE 作对照，不用于评测）。

用法::

    .venv\\Scripts\\python.exe scripts\\train_b2_leaf.py \
        --data out\\b2_leaf_beam_known.npz out\\b2_leaf_within.npz \
        --out data\\knowledge\\b2_leaf_mlp_small.json --report out\\b2_leaf_train_report.json

    # 换网络规模
    .venv\\Scripts\\python.exe scripts\\train_b2_leaf.py --hidden 128 64 --epochs 800 --lr 8e-4 ...

输出模型 JSON（``leaf_mlp.MLPLeafValue``）与训练报告；报告里带逐 ``turns_left``
的验证集 r²/MAE，便于判断它到底在哪些叶子状态上比解析式可信。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.sim.leaf_mlp import (
    DIM,
    FEATURE_NAMES,
    evaluate_utility_heads,
    train_mlp,
    train_utility_heads,
)


def _load(paths: list[Path]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    seeds: list[np.ndarray] = []
    metas: list[dict] = []
    for path in paths:
        with np.load(path, allow_pickle=False) as data:
            X = np.asarray(data["X"], dtype=np.float64)
            y = np.asarray(data["y"], dtype=np.float64)
            seed = np.asarray(data["seed"], dtype=np.int64)
            meta = json.loads(str(data["meta_json"].item()))
        if X.shape[1] != DIM:
            raise ValueError(f"{path}: 特征维度 {X.shape[1]} != {DIM}")
        if X.shape[0] != y.shape[0] or X.shape[0] != seed.shape[0]:
            raise ValueError(f"{path}: X/y/seed 行数不一致")
        xs.append(X)
        ys.append(y)
        seeds.append(seed)
        metas.append({"path": str(path), **meta})
    return np.vstack(xs), np.concatenate(ys), np.concatenate(seeds), metas


def _metrics(prediction: np.ndarray, target: np.ndarray) -> dict:
    residual = target - prediction
    ss_tot = float(np.sum((target - target.mean()) ** 2)) or 1.0
    return {
        "n": int(target.size),
        "mse": float(np.mean(residual**2)),
        "mae": float(np.mean(np.abs(residual))),
        "r2": 1.0 - float(np.sum(residual**2)) / ss_tot,
        "mean_target": float(target.mean()),
        "mean_prediction": float(prediction.mean()),
        "corr": float(np.corrcoef(prediction, target)[0, 1])
        if target.size > 1 and np.std(prediction) > 0
        else 0.0,
    }


def _ridge_baseline(X: np.ndarray, y: np.ndarray, X_val: np.ndarray, y_val: np.ndarray) -> dict:
    """闭式 ridge（特征标准化 + 截距）作为对照。"""
    mean = X.mean(axis=0)
    scale = X.std(axis=0)
    scale[scale < 1e-8] = 1.0

    def design(matrix: np.ndarray) -> np.ndarray:
        return np.hstack([(matrix - mean) / scale, np.ones((matrix.shape[0], 1))])

    A = design(X)
    penalty = np.eye(A.shape[1])
    penalty[-1, -1] = 0.0
    weights = np.linalg.solve(A.T @ A + penalty, A.T @ y)
    return {
        "train": _metrics(design(X) @ weights, y),
        "val": _metrics(design(X_val) @ weights, y_val),
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="B2 叶子 MLP 训练")
    parser.add_argument("--data", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--hidden", type=int, nargs=2, default=(64, 32))
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--l2", type=float, default=1e-4)
    parser.add_argument("--sigma-epochs", type=int, default=300)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--val-mod",
        type=int,
        default=10,
        help="验证集 seed 取模（seed %% val_mod == 0 → 验证）",
    )
    parser.add_argument(
        "--score-tiebreak",
        type=float,
        default=0.0,
        help="写进模型的平手项（beam 评测用 1e-3；within 评测用 0）",
    )
    parser.add_argument(
        "--utility-heads",
        action="store_true",
        help="额外训练 P(CLEAR)/P(PERFECT) logistic 头，utility 直接用档位概率",
    )
    parser.add_argument("--utility-epochs", type=int, default=400)
    args = parser.parse_args(argv)

    X, y, seed, metas = _load(args.data)
    is_val = (seed % max(args.val_mod, 2)) == 0
    X_train, y_train = X[~is_val], y[~is_val]
    X_val, y_val = X[is_val], y[is_val]
    if X_val.shape[0] == 0:
        raise SystemExit("验证集为空：请检查 --val-mod / seed 分布")
    print(
        f"样本 {X.shape[0]}（train {X_train.shape[0]} / val {X_val.shape[0]}），"
        f"标签 mean/std = {y.mean():.1f}/{y.std():.1f}，特征 {X.shape[1]} 维"
    )
    print("数据源:")
    for meta in metas:
        print(
            f"  - {meta['path']}: n={meta.get('n_samples')} policy={meta['args'].get('policy')} "
            f"known={meta['args'].get('known')} leaf_model={meta['args'].get('leaf_model')}"
        )

    started = time.perf_counter()
    model, history = train_mlp(
        X_train,
        y_train,
        hidden=(int(args.hidden[0]), int(args.hidden[1])),
        epochs=args.epochs,
        lr=args.lr,
        l2=args.l2,
        sigma_epochs=args.sigma_epochs,
        seed=args.seed,
    )
    elapsed = time.perf_counter() - started

    train_prediction = np.asarray(
        [model.predict_vector(row)[0] for row in X_train], dtype=np.float64
    )
    val_prediction = np.asarray([model.predict_vector(row)[0] for row in X_val], dtype=np.float64)
    train_metrics = _metrics(train_prediction, y_train)
    val_metrics = _metrics(val_prediction, y_val)
    ridge = _ridge_baseline(X_train, y_train, X_val, y_val)

    utility_heads = None
    if args.utility_heads:
        head_train = train_utility_heads(
            model, X_train, y_train, epochs=args.utility_epochs
        )
        head_val = evaluate_utility_heads(model, X_val, y_val)
        utility_heads = {"train": head_train, "val": head_val}
        print(
            f"档位头（val）：CLEAR acc={head_val['clear_accuracy']:.3f} "
            f"brier={head_val['clear_brier']:.3f}（真值率 {head_val['clear_rate']:.3f} / "
            f"预测均值 {head_val['clear_pred_mean']:.3f}）| PERFECT acc="
            f"{head_val['perfect_accuracy']:.3f} brier={head_val['perfect_brier']:.3f} "
            f"（真值率 {head_val['perfect_rate']:.3f} / 预测均值 {head_val['perfect_pred_mean']:.3f}）"
        )

    # 逐 turns_left 诊断：哪段叶子状态学得准 / 是否只学到"剩余回合"。
    turns_column = FEATURE_NAMES.index("turns_left")
    per_turns = {}
    for value in sorted({float(v) for v in X_val[:, turns_column]}):
        mask = X_val[:, turns_column] == value
        if int(mask.sum()) < 8:
            continue
        per_turns[str(int(value))] = _metrics(val_prediction[mask], y_val[mask])

    model.meta.update(
        {
            "method": "b2_on_policy_mlp_leaf",
            "data": [{"path": m["path"], "n": m.get("n_samples")} for m in metas],
            "val_mod": int(args.val_mod),
            "train_metrics": train_metrics,
            "val_metrics": val_metrics,
            "ridge_baseline": ridge,
            "utility_heads": utility_heads,
            "epochs": int(args.epochs),
            "lr": float(args.lr),
            "l2": float(args.l2),
            "train_seconds": round(elapsed, 1),
        }
    )
    model.score_tiebreak = float(args.score_tiebreak)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    model.save(args.out)
    report = {
        "args": vars(args)
        | {
            "data": [str(path) for path in args.data],
            "out": str(args.out),
            "report": str(args.report) if args.report else None,
        },
        "history": history,
        "train": train_metrics,
        "val": val_metrics,
        "ridge_baseline": ridge,
        "utility_heads": utility_heads,
        "val_per_turns_left": per_turns,
        "elapsed_s": round(elapsed, 1),
    }
    print(
        f"train r²={train_metrics['r2']:.3f} MSE={train_metrics['mse']:.1f} | "
        f"val r²={val_metrics['r2']:.3f} MSE={val_metrics['mse']:.1f} "
        f"MAE={val_metrics['mae']:.1f} corr={val_metrics['corr']:.3f} | "
        f"ridge val r²={ridge['val']['r2']:.3f} | {elapsed:.1f}s"
    )
    print(
        "val 逐 turns_left r²:",
        {key: round(value["r2"], 3) for key, value in per_turns.items()},
    )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告 → {args.report}")
    print(f"模型 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
