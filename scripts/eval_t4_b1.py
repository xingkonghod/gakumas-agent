"""T4 / WORKPLAN B1：受控 policy-evaluation 叶子的配对评测。

同牌组、同 seed 配对跑三种策略：

* ``within``：生产的回合内 expectimax（解析式 V_leaf，当前默认）；
* ``beam``：跨回合 beam（width/branching 可调，解析式 V_leaf 排序）；
* ``beam+frontier``：只在 beam **最深端点**用执行同策略（``within``）rollout 重排
  （``search_beam(frontier_value=...)``；终局端点不 rollout）。

信息条件两种：``unknown``（只知牌库多重集）与 ``known``（``known_draw`` 已知牌序）。
输出均值/P50/CLEAR/PERFECT，以及相对 ``within`` 的**配对差**与 95% CI，并按
WORKPLAN B1 决策门判定：真实牌组 beam 均值 ≥ within 的 90%。

注意：``beam`` 的评测必须用修正后的 ``eval_known_draw._execute_plan``——计划把
当前手牌打空时 ``LessonSim`` 会自动结束回合，旧实现在循环后又补一个 SKIP，白丢
下一整个回合（2026-11-22 B1 查出的评测 bug，见 EXPECTIMAX「T4 修正」）。

用法::

    python scripts/eval_t4_b1.py --games 60
    python scripts/eval_t4_b1.py --games 60 --json out/t4_b1.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import eval_expectimax as ee
import eval_known_draw as ekd


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _paired_ci(deltas: list[float], z: float = 1.96) -> tuple[float, float]:
    """配对差的均值与 95% CI 半宽（大样本正态近似，与 T4 旧表同口径）。"""
    count = len(deltas)
    if count == 0:
        return 0.0, 0.0
    mean = _mean(deltas)
    if count < 2:
        return mean, 0.0
    half = z * statistics.stdev(deltas) / math.sqrt(count)
    return mean, half


def _run(
    deck,
    config,
    games: int,
    seed0: int,
    *,
    known: bool,
    policy: str,
    budget_ms: float,
    width: int,
    branching: int | None,
    score_tiebreak: float,
    frontier_rollout: bool,
    frontier_budget_ms: float,
) -> list[dict]:
    return [
        ekd.play(
            deck,
            config,
            seed0 + offset,
            known=known,
            policy=policy,
            budget_ms=budget_ms,
            width=width,
            branching=branching,
            score_tiebreak=score_tiebreak,
            frontier_rollout=frontier_rollout,
            frontier_budget_ms=frontier_budget_ms,
        )
        for offset in range(games)
    ]


def _table(rows: dict[str, list[dict]], within_key: str) -> dict:
    out: dict[str, dict] = {}
    base_scores = [row["score"] for row in rows[within_key]]
    for name, values in rows.items():
        stat = ekd.summarize(values)
        stat["scores"] = [row["score"] for row in values]
        deltas = [value - base for value, base in zip(stat["scores"], base_scores)]
        mean, half = _paired_ci(deltas)
        stat["vs_within"] = {
            "mean": mean,
            "ci_low": mean - half,
            "ci_high": mean + half,
            "wins": sum(1 for delta in deltas if delta > 0),
            "ties": sum(1 for delta in deltas if delta == 0),
            "losses": sum(1 for delta in deltas if delta < 0),
        }
        out[name] = stat
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument("--scenario", choices=("small", "large"), default="small")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--width", type=int, default=4)
    parser.add_argument(
        "--branching",
        type=int,
        default=0,
        help="beam 每层抽样分支数（0=默认 max(2,min(width,3))；修正 _execute_plan 后无显著收益）",
    )
    parser.add_argument("--budget-ms", type=float, default=100.0)
    parser.add_argument("--within-budget-ms", type=float, default=200.0)
    parser.add_argument("--score-tiebreak", type=float, default=1e-3)
    parser.add_argument("--frontier-budget-ms", type=float, default=5.0)
    parser.add_argument(
        "--no-frontier", action="store_true", help="跳过 beam+frontier 列（只跑 within/beam）"
    )
    parser.add_argument("--json", type=Path, default=None, help="把逐局分数与统计写到 JSON")
    args = parser.parse_args(argv)

    deck, config = ee.build_deck(args.scenario), ee.make_config(args.scenario)
    base = {
        "budget_ms": args.budget_ms,
        "width": args.width,
        "branching": args.branching or None,
        "score_tiebreak": args.score_tiebreak,
    }
    results: dict[str, dict[str, list[dict]]] = {}
    for info, known in (("unknown", False), ("known", True)):
        rows = {
            "within": _run(
                deck,
                config,
                args.games,
                args.seed,
                known=known,
                policy="within",
                budget_ms=args.within_budget_ms,
                width=args.width,
                branching=None,
                score_tiebreak=0.0,
                frontier_rollout=False,
                frontier_budget_ms=args.frontier_budget_ms,
            ),
            "beam": _run(
                deck,
                config,
                args.games,
                args.seed,
                known=known,
                policy="beam",
                frontier_rollout=False,
                frontier_budget_ms=args.frontier_budget_ms,
                **base,
            ),
        }
        if not args.no_frontier:
            rows["beam+frontier"] = _run(
                deck,
                config,
                args.games,
                args.seed,
                known=known,
                policy="beam",
                frontier_rollout=True,
                frontier_budget_ms=args.frontier_budget_ms,
                **base,
            )
        results[info] = _table(rows, "within")

    print(
        f"scenario={args.scenario} games={args.games} width={args.width} "
        f"branching={args.branching or '默认'} beam_budget={args.budget_ms:.0f}ms "
        f"within_budget={args.within_budget_ms:.0f}ms tiebreak={args.score_tiebreak:g} "
        f"frontier_budget={args.frontier_budget_ms:.0f}ms"
    )
    for info in ("unknown", "known"):
        print(f"\n== {info} ==")
        print(
            f"{'策略':<15}{'均值':>8}{'P50':>7}{'CLEAR':>8}{'PERFECT':>9}"
            f"{'vs within':>11}{'95% CI':>18}{'胜/平/负':>11}"
        )
        for name, stat in results[info].items():
            delta = stat["vs_within"]
            print(
                f"{name:<15}{stat['mean']:>8.1f}{stat['p50']:>7.0f}"
                f"{stat['clear_rate'] * 100:>7.1f}%{stat['perfect_rate'] * 100:>8.1f}%"
                f"{delta['mean']:>+11.1f}"
                f"  [{delta['ci_low']:>+6.1f},{delta['ci_high']:>+6.1f}]"
                f"{delta['wins']:>5d}/{delta['ties']:d}/{delta['losses']:<4d}"
            )

    gate_ok = True
    for info in ("unknown", "known"):
        within_mean = results[info]["within"]["mean"]
        for name in ("beam", "beam+frontier"):
            if name not in results[info]:
                continue
            ratio = results[info][name]["mean"] / within_mean if within_mean else 0.0
            ok = ratio >= 0.9
            gate_ok = gate_ok and ok
            print(
                f"[gate] {info:<7} {name:<13} beam/within = {ratio * 100:5.1f}% "
                f"→ {'PASS' if ok else 'FAIL'}（≥90%）"
            )
    print(f"\nB1 决策门：{'PASS' if gate_ok else 'FAIL'}")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "args": vars(args) | {"json": str(args.json) if args.json else None},
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"json → {args.json}")
    return 0 if gate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
