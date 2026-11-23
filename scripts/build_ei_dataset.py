"""B11 渐退式专家迭代：数据采集（教师示范 / 学生自对弈优势标签）。

两种模式（第 1 轮数据 = 70% 自对弈 + 30% 教师示范，比例在训练脚本里配）：

* ``--mode demos``：教师跑局，记录每个决策点；教师出的牌 +1、其余
  −1/(k−1) 软目标。k=1 强制决策 / 教师有牌却 SKIP 的决策剔除并计数。
  教师默认 = beam（width4/100ms/tiebreak1e-3，默认 unknown 信息，与 B2-R
  处置后的 T2 候选同档）；**第 2 轮起可 ``--teacher-net <model>`` 把教师换成
  上一轮学生网**（渐退式专家迭代：过门后教师←学生），走 ``net_action``
  逐决策记录（硬规矩禁跳 → 不会出现「教师有牌却 SKIP」剔除），软目标同口径。
* ``--mode selfplay --student-model ...``：学生 argmax 自对弈（硬规矩禁跳），
  每个决策点对每张可出牌做**精确重放分支**（``policy_data.advantage_samples``），
  分支后用**当前学生**打完 → ``A = R − mean(R)``（on-policy 优势标签）。
  ``--explore-eps ε``（r7 设计变量）：采集时 ε-greedy 探索（概率 ε 随机选可出牌，
  扩状态覆盖），标签口径与硬规矩不变；0=argmax 逐位不变。

seed 纪律（与评测段错开）：demos 默认 100000 起、selfplay 默认 200000 起；
评测确认段 3000–3119 / 选择段 2000–2079 不参与采集。第 2 轮：教师←v1 示范
seed 400000 起、v1 自对弈 seed 300000 起（与第 1 轮采集段错开）。

用法::

    .venv\\Scripts\\python.exe scripts\\build_ei_dataset.py --mode demos --games 400 \
        --out out\\ei_r1_demos.npz
    .venv\\Scripts\\python.exe scripts\\build_ei_dataset.py --mode selfplay --games 800 \
        --student-model out\\ei_r1_v0_bc.json --out out\\ei_r1_selfplay.npz
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

from gkagent.sim.expectimax import AnalyticLeafValue, search_beam, state_from_sim
from gkagent.sim.policy_data import (
    DecisionRecordingSim,
    advantage_samples,
    demo_samples,
    play_selfplay,
)
from gkagent.sim.policy_mlp import PolicyMLP, net_action


def _teacher_game(
    deck, config, seed: int, *, args, leaf: AnalyticLeafValue
) -> tuple[DecisionRecordingSim, dict]:
    """beam 教师跑一局（与 ekd.play 的 beam 分支同口径：每回合计划 + 修正执行器）。"""
    sim = DecisionRecordingSim(deck, config, rng_seed=seed)
    fallbacks = 0
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            sim.step(None)
            continue
        state = state_from_sim(sim, known_deck_order=args.known)
        result = search_beam(
            state,
            leaf,
            width=args.width,
            deadline_ms=args.budget_ms * 2,
            branching=args.branching or None,
        )
        fallbacks += ekd._execute_plan(sim, list(result.sequence))
    return sim, {
        "score": float(sim.score),
        "clear": 1.0 if sim.score >= config.target_clear else 0.0,
        "perfect": 1.0 if sim.score >= config.target_perfect else 0.0,
        "fallbacks": fallbacks,
        "decisions": len(sim.decisions),
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="B11 专家迭代数据采集（示范/自对弈优势）")
    parser.add_argument("--mode", choices=("demos", "selfplay"), required=True)
    parser.add_argument("--games", type=int, default=400)
    parser.add_argument("--seed", type=int, default=None, help="默认 demos=100000 / selfplay=200000")
    parser.add_argument("--scenario", choices=("small", "large"), default="small")
    parser.add_argument("--student-model", type=Path, default=None, help="selfplay 模式必填")
    parser.add_argument(
        "--teacher-net", type=Path, default=None,
        help="demos 模式：教师=学生网（第 2 轮渐退教师←上一轮学生），逐决策 net_action 记录",
    )
    parser.add_argument("--known", action="store_true", help="教师用 known_draw 全知（默认 unknown）")
    parser.add_argument("--budget-ms", type=float, default=100.0)
    parser.add_argument("--width", type=int, default=4)
    parser.add_argument("--branching", type=int, default=0)
    parser.add_argument("--score-tiebreak", type=float, default=1e-3)
    parser.add_argument("--sigma", type=float, default=60.0)
    parser.add_argument(
        "--label-stride", type=int, default=1,
        help="selfplay：每 N 个决策标一个（1=全标；优势标签成本 = 每决策 k 次重放+rollout）",
    )
    parser.add_argument(
        "--explore-eps", type=float, default=0.0,
        help="selfplay：ε-greedy 探索采集（r7 设计变量，扩状态覆盖；0=argmax 逐位不变）",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.seed is None:
        args.seed = 100_000 if args.mode == "demos" else 200_000
    if args.mode == "selfplay" and args.student_model is None:
        parser.error("--mode selfplay 需要 --student-model")
    if args.teacher_net is not None and args.mode != "demos":
        parser.error("--teacher-net 只用于 --mode demos（selfplay 用 --student-model）")
    if args.explore_eps != 0.0 and args.mode != "selfplay":
        parser.error("--explore-eps 只用于 --mode selfplay（教师示范必须 argmax）")
    if not 0.0 <= args.explore_eps <= 1.0:
        parser.error("--explore-eps 必须在 [0,1]")

    deck, config = ee.build_deck(args.scenario), ee.make_config(args.scenario)
    student = PolicyMLP.load(args.student_model) if args.student_model else None
    teacher_net = PolicyMLP.load(args.teacher_net) if args.teacher_net else None
    leaf = AnalyticLeafValue(sigma=args.sigma, score_tiebreak=args.score_tiebreak)
    print(
        f"mode={args.mode} scenario={args.scenario} games={args.games} "
        f"seeds={args.seed}..{args.seed + args.games - 1} "
        + (
            (
                f"teacher=net({args.teacher_net})"
                if teacher_net is not None
                else f"teacher=beam(width={args.width}, {args.budget_ms:.0f}ms, "
                f"tiebreak={args.score_tiebreak:g}, known={args.known})"
            )
            if args.mode == "demos"
            else f"student={args.student_model} label_stride={args.label_stride} "
            f"explore_eps={args.explore_eps:g}"
        )
    )

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    seeds: list[np.ndarray] = []
    groups: list[np.ndarray] = []
    final_scores: list[float] = []
    n_decisions = 0
    excluded_forced = 0
    excluded_teacher_skip = 0
    fallbacks = 0
    started = time.perf_counter()
    for offset in range(args.games):
        seed = args.seed + offset
        if args.mode == "demos":
            if teacher_net is not None:
                # 教师=学生网：net_action 逐决策（硬规矩禁跳），软目标同口径
                sim, row = play_selfplay(deck, config, seed, teacher_net)
            else:
                sim, row = _teacher_game(deck, config, seed, args=args, leaf=leaf)
            fallbacks += int(row.get("fallbacks", 0))
        else:
            sim, row = play_selfplay(
                deck, config, seed, student, explore_eps=args.explore_eps
            )
        final_scores.append(row["score"])
        for decision_index, record in enumerate(sim.decisions):
            n_decisions += 1
            if args.mode == "demos":
                sample = demo_samples(record)
                if sample is None:
                    if len(record.playable) < 2:
                        excluded_forced += 1
                    else:
                        excluded_teacher_skip += 1
                    continue
                X, y, _meta = sample
            else:
                if decision_index % max(args.label_stride, 1) != 0:
                    continue
                X, y, _meta = advantage_samples(
                    deck, config, seed, record,
                    lambda current: net_action(current, student),
                )
            group_id = offset * 1000 + decision_index
            xs.append(X)
            ys.append(y)
            seeds.append(np.full(X.shape[0], seed, dtype=np.int64))
            groups.append(np.full(X.shape[0], group_id, dtype=np.int64))
        if offset == 0 or (offset + 1) % 100 == 0:
            print(
                f"  {offset + 1}/{args.games} 局，样本 {sum(v.shape[0] for v in xs)}，"
                f"{time.perf_counter() - started:.0f}s",
                flush=True,
            )

    if not xs:
        print("没有采到样本", file=sys.stderr)
        return 1
    X = np.vstack(xs)
    y = np.concatenate(ys)
    elapsed = time.perf_counter() - started
    meta = {
        "kind": args.mode,
        "teacher_kind": (
            ("net" if teacher_net is not None else "beam")
            if args.mode == "demos"
            else "student"
        ),
        "args": {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in vars(args).items()
        },
        "n_samples": int(X.shape[0]),
        "n_games": int(args.games),
        "n_decisions": int(n_decisions),
        "excluded_forced": int(excluded_forced),
        "excluded_teacher_skip": int(excluded_teacher_skip),
        "fallbacks": int(fallbacks),
        "final_score_mean": float(np.mean(final_scores)),
        "final_score_std": float(np.std(final_scores)),
        "label_mean": float(y.mean()),
        "label_std": float(y.std()),
        "elapsed_s": round(elapsed, 2),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        X=X.astype(np.float64),
        y=y.astype(np.float64),
        seed=np.concatenate(seeds),
        group=np.concatenate(groups),
        meta_json=np.asarray(json.dumps(meta, ensure_ascii=False)),
    )
    print(
        f"样本 {X.shape[0]}（{args.games} 局 / {n_decisions} 决策，{elapsed:.1f}s）"
        f" 标签 mean={y.mean():.3f} std={y.std():.3f}"
        f" 最终分 mean={np.mean(final_scores):.1f}"
    )
    if args.mode == "demos":
        print(f"剔除：强制决策 {excluded_forced} / 教师有牌却 SKIP {excluded_teacher_skip}")
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
