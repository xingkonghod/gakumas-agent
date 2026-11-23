"""B11 渐退式专家迭代：学生网训练（示范 BC / 70-30 混合）。

输入 = ``build_ei_dataset.py`` 的 npz（X/y/seed/group/meta_json）：

* ``--demos``：教师示范软目标（+1 / −1/(k−1)），单独用 = 行为克隆 warm start（v0）；
* ``--selfplay``：学生自对弈优势标签（原始 A），训练前按全局 std 归一化；
* ``--teacher-frac``：混合里教师样本占比（第 1 轮 0.3 = 摸索 70% + 老师 30%；
  第 2 轮 0.15，教师=上一轮学生网的示范）。按行数**确定性下采样**到精确比例
  （rng seed 固定），实际比例写进 meta。``--round`` 写进 meta.task（默认 1）。

切分：按 **seed 分组** 9:1（同局样本不跨 train/val，与 B2 训练同纪律）。
指标：train/val MSE + val 按决策分组的排序命中率（argmax 预测 == argmax 标签）。

用法::

    # v0：教师示范行为克隆
    .venv\\Scripts\\python.exe scripts\\train_ei_policy.py --demos out\\ei_r1_demos.npz \
        --out out\\ei_r1_v0_bc.json
    # v1：70% 自对弈 + 30% 示范
    .venv\\Scripts\\python.exe scripts\\train_ei_policy.py --selfplay out\\ei_r1_selfplay.npz \
        --demos out\\ei_r1_demos.npz --teacher-frac 0.3 --out out\\ei_r1_v1_mix.json
    # v2（第 2 轮）：85% v1 自对弈 + 15% v1 教师示范
    .venv\\Scripts\\python.exe scripts\\train_ei_policy.py --selfplay out\\ei_r2_selfplay.npz \
        --demos out\\ei_r2_demos.npz --teacher-frac 0.15 --round 2 --out out\\ei_r2_v2_mix.json
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

from gkagent.sim.policy_mlp import (
    INPUT_DIM,
    ranking_accuracy,
    train_policy_mlp,
)


def _load(path: Path) -> dict:
    doc = np.load(path, allow_pickle=False)
    meta = json.loads(str(doc["meta_json"]))
    return {
        "X": doc["X"],
        "y": doc["y"],
        "seed": doc["seed"],
        "group": doc["group"],
        "meta": meta,
        "path": str(path),
    }


def _subsample(data: dict, keep: int, rng: np.random.Generator) -> dict:
    n = data["X"].shape[0]
    if keep >= n:
        return data
    indices = np.sort(rng.choice(n, size=keep, replace=False))
    return {
        **data,
        "X": data["X"][indices],
        "y": data["y"][indices],
        "seed": data["seed"][indices],
        "group": data["group"][indices],
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="B11 学生网训练（BC / 混合）")
    parser.add_argument("--selfplay", type=Path, default=None)
    parser.add_argument("--demos", type=Path, default=None)
    parser.add_argument("--teacher-frac", type=float, default=0.3)
    parser.add_argument("--round", type=int, default=1, help="专家迭代轮次（写进模型 meta.task）")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--hidden", type=int, nargs=2, default=(96, 48))
    parser.add_argument("--epochs", type=int, default=400)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--l2", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--val-frac", type=float, default=0.1)
    args = parser.parse_args(argv)
    if args.selfplay is None and args.demos is None:
        parser.error("至少给一个 --selfplay / --demos")
    if not 0.0 <= args.teacher_frac <= 1.0:
        parser.error("--teacher-frac 必须在 [0,1]")

    started = time.perf_counter()
    rng = np.random.default_rng(args.seed)
    selfplay = _load(args.selfplay) if args.selfplay else None
    demos = _load(args.demos) if args.demos else None

    # ---- 按行数配教师占比（确定性下采样）----
    if selfplay is not None and demos is not None and 0.0 < args.teacher_frac < 1.0:
        n_s, n_d = selfplay["X"].shape[0], demos["X"].shape[0]
        f = args.teacher_frac
        max_d = int(n_s * f / (1.0 - f))
        max_s = int(n_d * (1.0 - f) / f)
        if n_d > max_d:
            demos = _subsample(demos, max_d, rng)
        elif n_s > max_s:
            selfplay = _subsample(selfplay, max_s, rng)

    parts: list[dict] = []
    kind_cols: list[np.ndarray] = []
    if selfplay is not None:
        std = float(selfplay["y"].std())
        selfplay = {**selfplay, "y": selfplay["y"] / max(std, 1e-6), "adv_std": std}
        parts.append(selfplay)
        kind_cols.append(np.zeros(selfplay["X"].shape[0], dtype=np.int64))
    if demos is not None:
        parts.append(demos)
        kind_cols.append(np.ones(demos["X"].shape[0], dtype=np.int64))
    X = np.vstack([part["X"] for part in parts])
    y = np.concatenate([part["y"] for part in parts])
    seed_col = np.concatenate([part["seed"] for part in parts])
    group_col = np.concatenate([part["group"] for part in parts])
    kind_col = np.concatenate(kind_cols)
    if X.shape[1] != INPUT_DIM:
        raise ValueError(f"数据特征维 {X.shape[1]} != {INPUT_DIM}（采集脚本版本不一致？）")

    # ---- 按 seed 分组切分 ----
    unique_seeds = np.unique(seed_col)
    rng.shuffle(unique_seeds)
    n_val = max(round(unique_seeds.size * args.val_frac), 1)
    val_seeds = set(unique_seeds[:n_val].tolist())
    val_mask = np.asarray([int(seed) in val_seeds for seed in seed_col])
    train_mask = ~val_mask
    if int(train_mask.sum()) < 16 or int(val_mask.sum()) < 8:
        raise ValueError("train/val 样本太少（seed 分组切分后）")

    model, history = train_policy_mlp(
        X[train_mask],
        y[train_mask],
        hidden=tuple(args.hidden),
        epochs=args.epochs,
        lr=args.lr,
        l2=args.l2,
        seed=args.seed,
    )
    val_pred = model.score_vector(X[val_mask])
    val_mse = float(np.mean((val_pred - y[val_mask]) ** 2))
    val_rank = ranking_accuracy(model, X[val_mask], y[val_mask], group_col[val_mask])
    train_rank = ranking_accuracy(model, X[train_mask], y[train_mask], group_col[train_mask])
    n_s_final = int((kind_col == 0).sum())
    n_d_final = int((kind_col == 1).sum())
    metrics = {
        "train": history,
        "val": {
            "n": int(val_mask.sum()),
            "mse": val_mse,
            "ranking_accuracy": val_rank,
        },
        "train_ranking_accuracy": train_rank,
        "mix": {
            "selfplay_rows": n_s_final,
            "demo_rows": n_d_final,
            "teacher_frac_actual": n_d_final / max(n_s_final + n_d_final, 1),
            "teacher_frac_target": args.teacher_frac,
            "selfplay_adv_std": (selfplay or {}).get("adv_std"),
        },
        "n_seeds": int(unique_seeds.size),
        "val_seeds": sorted(val_seeds),
        "elapsed_s": round(time.perf_counter() - started, 2),
    }
    model.meta = {
        **model.meta,
        "task": f"B11 expert-iteration round{args.round}",
        "sources": [part["path"] for part in parts],
        "val_metrics": metrics["val"],
        "train_metrics": history,
        "mix": metrics["mix"],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    model.save(args.out)
    print(
        f"样本 {X.shape[0]}（自对弈 {n_s_final} / 示范 {n_d_final}，"
        f"教师占比 {metrics['mix']['teacher_frac_actual']:.3f}）"
        f" train MSE={history['final_mse']:.4f} r²={history['r2']:.3f}"
        f" 排序命中 train={train_rank:.3f}"
    )
    print(
        f"val（{int(val_mask.sum())} 样本 / {n_val} seeds）MSE={val_mse:.4f} "
        f"排序命中={val_rank:.3f}  {metrics['elapsed_s']:.1f}s"
    )
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
