"""B2 数据集采集：用搜索策略自对弈生成「叶子状态 → 后续实际得分」监督样本。

teacher = 全知（``--known``，``known_draw`` 已知牌序）或未知信息的 beam/within
搜索策略；student = 之后训练的叶子价值 ``leaf_mlp.MLPLeafValue``。

样本定义（见 ``src/gkagent/sim/leaf_data.py``）：

* 输入 = 叶子形态 ``ExpectState``（``end_turn_state`` 之后：手牌并入弃牌堆、
  好印象已结算、buff 已倒计时、回合数 -1）的 104 维结构化特征；
* 标签 = 该局最终分 − 叶子状态分数（on-policy 实际后续得分）；
* 自然打满回合的局额外补 ``turns_left=0`` 终局样本（标签 0）。

B1 修正后的执行器（``eval_known_draw.py::_execute_plan``）保证 beam 计划不会白丢
回合，这是旧学习叶子失败的一个系统性坑。

用法::

    # 全知 beam teacher（默认推荐；teacher 看得到牌序）
    .venv\\Scripts\\python.exe scripts\\build_b2_dataset.py --games 1500 --policy beam \
        --known --out out\\b2_leaf_beam_known.npz

    # 未知信息 within 自对弈（便宜；给 ensemble/对照用）
    .venv\\Scripts\\python.exe scripts\\build_b2_dataset.py --games 4000 --policy within \
        --out out\\b2_leaf_within.npz

    # 第二轮自对弈（用第一轮模型当策略）
    .venv\\Scripts\\python.exe scripts\\build_b2_dataset.py --games 3000 --policy within \
        --leaf-model data\\knowledge\\b2_leaf_mlp_small.json --out out\\b2_leaf_within_r2.npz
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
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd

from gkagent.sim.leaf_data import RecordingLessonSim, episode_samples


def _sim_factory(instances: list[RecordingLessonSim]):
    def factory(deck, config, rng_seed):
        sim = RecordingLessonSim(deck, config, rng_seed)
        instances.append(sim)
        return sim

    return factory


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="B2 叶子状态数据集采集（搜索策略自对弈）")
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=100_000, help="起始 rng seed（训练/评测要错开）")
    parser.add_argument("--scenario", choices=("small", "large"), default="small")
    parser.add_argument("--policy", choices=("within", "beam"), default="beam")
    parser.add_argument(
        "--known", action="store_true", help="teacher 使用 known_draw 全知牌序（全知 teacher）"
    )
    parser.add_argument(
        "--budget-ms",
        type=float,
        default=None,
        help="单次决策预算（默认 within=200 / beam=100，同 B1 harness）",
    )
    parser.add_argument("--width", type=int, default=4)
    parser.add_argument("--branching", type=int, default=0, help="beam 每层抽样分支（0=默认）")
    parser.add_argument(
        "--score-tiebreak",
        type=float,
        default=1e-3,
        help="平手项（beam teacher 用 1e-3，与 B1 最强配置一致；within 会被忽略）",
    )
    parser.add_argument(
        "--leaf-model", type=Path, default=None, help="自对弈迭代：用已有 MLP 叶子当策略"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    budget = args.budget_ms
    if budget is None:
        budget = 200.0 if args.policy == "within" else 100.0
    leaf_model = None
    if args.leaf_model is not None:
        from gkagent.sim.leaf_mlp import MLPLeafValue

        leaf_model = MLPLeafValue.load(args.leaf_model)
        leaf_model.score_tiebreak = float(args.score_tiebreak)
        print(f"自对弈策略叶子 = {args.leaf_model}（tiebreak={leaf_model.score_tiebreak:g}）")

    deck, config = ee.build_deck(args.scenario), ee.make_config(args.scenario)
    print(
        f"scenario={args.scenario} deck={len(deck)} turns={config.turns} "
        f"policy={args.policy} known={args.known} games={args.games} budget={budget:.0f}ms "
        f"width={args.width} branching={args.branching or '默认'} "
        f"tiebreak={args.score_tiebreak:g}"
    )

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    seeds: list[int] = []
    leaf_scores: list[np.ndarray] = []
    final_scores: list[float] = []
    fallbacks = 0
    started = time.perf_counter()
    for offset in range(args.games):
        seed = args.seed + offset
        instances: list[RecordingLessonSim] = []
        row = ekd.play(
            deck,
            config,
            seed,
            known=args.known,
            policy=args.policy,
            budget_ms=budget,
            width=args.width,
            branching=args.branching or None,
            score_tiebreak=args.score_tiebreak,
            leaf_model=leaf_model,
            sim_factory=_sim_factory(instances),
        )
        sim = instances[-1]
        X, y, _meta = episode_samples(sim)
        fallbacks += int(row["fallbacks"])
        final_scores.append(float(row["score"]))
        if X.shape[0] == 0:
            continue
        xs.append(X)
        ys.append(y)
        seeds.append(np.full(X.shape[0], seed, dtype=np.int64))
        leaf_scores.append(np.asarray([state.score for state in sim.leaf_states], dtype=np.float64))
        if offset == 0 or (offset + 1) % 200 == 0:
            print(
                f"  {offset + 1}/{args.games} 局，样本 {sum(v.size for v in ys)}，"
                f"{time.perf_counter() - started:.0f}s",
                flush=True,
            )

    if not xs:
        print("没有采到样本", file=sys.stderr)
        return 1
    X = np.vstack(xs)
    y = np.concatenate(ys)
    seed_col = np.concatenate(seeds)
    leaf_score_col = np.concatenate(leaf_scores)
    elapsed = time.perf_counter() - started
    meta = {
        "args": vars(args) | {"budget_ms": budget, "out": str(args.out), "leaf_model": str(args.leaf_model) if args.leaf_model else None},
        "n_samples": int(X.shape[0]),
        "games": int(args.games),
        "feature_dim": int(X.shape[1]),
        "fallbacks": int(fallbacks),
        "label_mean": float(y.mean()),
        "label_std": float(y.std()),
        "final_score_mean": float(np.mean(final_scores)),
        "final_score_std": float(np.std(final_scores)),
        "elapsed_s": round(elapsed, 2),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        X=X.astype(np.float64),
        y=y.astype(np.float64),
        seed=seed_col,
        leaf_score=leaf_score_col,
        meta_json=np.asarray(json.dumps(meta, ensure_ascii=False)),
    )
    print(
        f"样本 {X.shape[0]}（{args.games} 局，{elapsed:.1f}s，fallbacks={fallbacks}）"
        f" 标签 mean={y.mean():.1f} std={y.std():.1f} 最终分 mean={np.mean(final_scores):.1f}"
    )
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
