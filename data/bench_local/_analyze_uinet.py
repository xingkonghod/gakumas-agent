"""Analyze the greedy / uinet / expectimax-ensemble benchmark JSON (throwaway)."""

from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "data" / "bench_local" / "leaderboard_uinet.json"
PROBLEMS = ROOT / "data" / "bench_local" / "problems_hajime.json"


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return float(ordered[min(rank - 1, len(ordered) - 1)])


def geo(values: list[float]) -> float:
    return math.exp(statistics.fmean(math.log(v) for v in values))


def bootstrap_ci(values: list[float], *, rounds: int = 5000) -> tuple[float, float]:
    rng = random.Random(12345)
    n = len(values)
    samples = []
    for _ in range(rounds):
        picks = [values[rng.randrange(n)] for _ in range(n)]
        samples.append(geo(picks))
    samples.sort()
    return samples[int(0.025 * rounds)], samples[int(0.975 * rounds) - 1]


def main() -> None:
    data = json.loads(BENCH.read_text(encoding="utf-8"))
    raws = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    raws = raws if isinstance(raws, list) else (raws.get("problems") or raws.get("items"))
    kind_of = {str(raw["id"]): str((raw.get("scene") or {}).get("kind")) for raw in raws}

    episodes = data["episodes"]
    by_algo_kind: dict[tuple[str, str], list[int]] = defaultdict(list)
    decisions_by_algo_kind: dict[tuple[str, str], list[int]] = defaultdict(list)
    for ep in episodes:
        key = (ep["algo"], kind_of[ep["problem"]])
        by_algo_kind[key].append(int(ep["score"]))
        decisions_by_algo_kind[key].append(int(ep["decisions"]))

    print("== overall ==")
    for name, row in data["algorithms"].items():
        print(
            f"{name:22s} n={row['episodes']:3d} mean={row['mean']:9.1f} p50={row['p50']:8.1f} "
            f"p90={row['p90']:8.1f} min={row['min']:6d} max={row['max']:7d} "
            f"step_mean={row['step_ms_mean']:7.2f} step_p50={row['step_ms_p50']:7.2f} "
            f"step_p90={row['step_ms_p90']:7.2f} fallback={row['fallback_rate']:.3f} "
            f"errors={row.get('errors', 0)}"
        )

    print("\n== by kind (mean / median / n) ==")
    kinds = ["lesson", "mid", "final"]
    algos = list(data["algorithms"])
    for kind in kinds:
        cells = []
        for algo in algos:
            values = by_algo_kind.get((algo, kind), [])
            cells.append(
                f"{algo}: {statistics.fmean(values):8.1f} / {statistics.median(values):7.1f} "
                f"/ {len(values):3d}"
                if values
                else f"{algo}: -"
            )
        print(f"{kind:7s} " + " | ".join(cells))

    print("\n== turns/decisions by kind ==")
    for kind in kinds:
        for algo in algos:
            dec = decisions_by_algo_kind.get((algo, kind), [])
            if dec:
                print(f"{kind:7s} {algo:22s} decisions/ep={statistics.fmean(dec):6.2f}")

    print("\n== paired per-problem vs greedy ==")
    per_problem = data["per_problem"]
    for algo in algos:
        if algo == "greedy":
            continue
        ratios: list[float] = []
        wins = losses = ties = 0
        for pid, row in per_problem.items():
            base = row.get("greedy")
            value = row.get(algo)
            if base is None or value is None or base <= 0 or value <= 0:
                continue
            ratios.append(value / base)
            if value > base:
                wins += 1
            elif value < base:
                losses += 1
            else:
                ties += 1
        lo, hi = bootstrap_ci(ratios)
        print(
            f"{algo:22s} problems={len(ratios)} geomean={geo(ratios):.3f}x "
            f"[95% CI {lo:.3f}, {hi:.3f}] win/loss/tie={wins}/{losses}/{ties}"
        )

    print("\n== paired per-problem vs greedy by kind ==")
    for kind in kinds:
        for algo in algos:
            if algo == "greedy":
                continue
            ratios = []
            for pid, row in per_problem.items():
                if kind_of.get(pid) != kind:
                    continue
                base = row.get("greedy")
                value = row.get(algo)
                if base and value and base > 0 and value > 0:
                    ratios.append(value / base)
            if ratios:
                print(
                    f"{kind:7s} {algo:22s} n={len(ratios):2d} geomean={geo(ratios):.3f}x "
                    f"mean_ratio={statistics.fmean(ratios):.3f}x"
                )

    print("\n== per-episode wins vs greedy ==")
    ep_scores: dict[tuple[str, str, int], dict[str, int]] = defaultdict(dict)
    for ep in episodes:
        ep_scores[(ep["problem"], ep["seed"], 0)][ep["algo"]] = int(ep["score"])
    for algo in algos:
        if algo == "greedy":
            continue
        wins = losses = ties = 0
        for row in ep_scores.values():
            base = row.get("greedy")
            value = row.get(algo)
            if base is None or value is None:
                continue
            if value > base:
                wins += 1
            elif value < base:
                losses += 1
            else:
                ties += 1
        print(f"{algo:22s} episode win/loss/tie = {wins}/{losses}/{ties}")

    print("\n== biggest per-problem diffs uinet vs greedy ==")
    diffs = []
    for pid, row in per_problem.items():
        base = row.get("greedy")
        value = row.get("uinet")
        if base and value:
            diffs.append((value - base, pid, kind_of.get(pid), base, value))
    for delta, pid, kind, base, value in sorted(diffs)[:5]:
        print(f"  {pid} {kind:7s} greedy={base:8.1f} uinet={value:8.1f} delta={delta:+9.1f}")
    for delta, pid, kind, base, value in sorted(diffs, reverse=True)[:5]:
        print(f"  {pid} {kind:7s} greedy={base:8.1f} uinet={value:8.1f} delta={delta:+9.1f}")

    print("\n== scores per algo/kind, quantiles ==")
    for kind in kinds:
        for algo in algos:
            values = by_algo_kind.get((algo, kind), [])
            if values:
                print(
                    f"{kind:7s} {algo:22s} n={len(values):3d} mean={statistics.fmean(values):8.1f} "
                    f"p50={pct(values, 50):7.1f} p90={pct(values, 90):8.1f}"
                )


if __name__ == "__main__":
    main()
