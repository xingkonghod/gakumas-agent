"""H.I.F 本地跑分分析：总体/分组/配对统计 + 与官方 3.5× 的对照。

用法::

    .venv\\Scripts\\python.exe data\\bench_local\\_analyze_hif.py
    .venv\\Scripts\\python.exe data\\bench_local\\_analyze_hif.py --bench <json> --problems <json>

只读 benchmark JSON / 题集 JSON，不联网、不改数据。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH = ROOT / "data" / "bench_local" / "leaderboard_hif.json"
DEFAULT_PROBLEMS = ROOT / "data" / "bench_local" / "problems_hif.json"
DEFAULT_OUT = ROOT / "data" / "bench_local" / "_analyze_hif.json"


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return float(ordered[min(rank - 1, len(ordered) - 1)])


def geo(values: list[float]) -> float:
    if not values:
        return float("nan")
    return math.exp(statistics.fmean(math.log(v) for v in values))


def bootstrap_ci(values: list[float], *, rounds: int = 5000, seed: int = 12345) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"))
    samples = [geo([values[rng.randrange(n)] for _ in range(n)]) for _ in range(rounds)]
    samples.sort()
    return samples[int(0.025 * rounds)], samples[int(0.975 * rounds) - 1]


def fmt_row(name: str, row: dict) -> str:
    return (
        f"{name:22s} n={row['episodes']:4d} mean={row['mean']:10.1f} "
        f"p50={row['p50']:9.1f} p90={row['p90']:10.1f} min={row['min']:8d} "
        f"max={row['max']:10d} step_mean={row['step_ms_mean']:8.2f} "
        f"step_p50={row['step_ms_p50']:8.2f} step_p90={row['step_ms_p90']:9.2f} "
        f"wall={row['wall_s']:10.2f}s fallback={row['fallback_rate']:.3f} "
        f"errors={row.get('errors', 0)}"
    )


def paired_stats(per_problem: dict, meta: dict, algo: str, base: str = "greedy") -> dict:
    ratios: list[float] = []
    wins = losses = ties = 0
    for row in per_problem.values():
        base_score = row.get(base)
        value = row.get(algo)
        if not base_score or not value or base_score <= 0 or value <= 0:
            continue
        ratios.append(value / base_score)
        if value > base_score:
            wins += 1
        elif value < base_score:
            losses += 1
        else:
            ties += 1
    lo, hi = bootstrap_ci(ratios)
    return {
        "problems": len(ratios),
        "geomean": round(geo(ratios), 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "median_ratio": round(statistics.median(ratios), 4) if ratios else None,
        "max_ratio": round(max(ratios), 4) if ratios else None,
        "min_ratio": round(min(ratios), 4) if ratios else None,
    }


def group_stats(
    per_problem: dict,
    meta: dict,
    episodes: list[dict],
    algos: list[str],
    *,
    field: str,
) -> dict:
    groups: dict[str, set[str]] = defaultdict(set)
    for pid, row in meta.items():
        groups[str(row.get(field))].add(pid)

    out: dict[str, dict] = {}
    for group, pids in sorted(groups.items()):
        pids &= set(per_problem)
        if not pids:
            continue
        cell: dict[str, object] = {"problems": len(pids)}
        scores_by_algo: dict[str, list[int]] = defaultdict(list)
        for ep in episodes:
            if ep["problem"] in pids:
                scores_by_algo[ep["algo"]].append(int(ep["score"]))
        for algo in algos:
            values = scores_by_algo.get(algo, [])
            if values:
                cell[algo] = {
                    "episodes": len(values),
                    "mean": round(statistics.fmean(values), 1),
                    "p50": round(pct(values, 50), 1),
                    "p90": round(pct(values, 90), 1),
                }
        base = cell.get("greedy")
        if isinstance(base, dict) and base.get("mean"):
            for algo in algos:
                if algo == "greedy":
                    continue
                value = cell.get(algo)
                if isinstance(value, dict):
                    value["ratio_mean"] = round(value["mean"] / base["mean"], 3)
        ratios = []
        for pid in pids:
            row = per_problem[pid]
            if row.get("greedy") and row.get("uinet"):
                ratios.append(row["uinet"] / row["greedy"])
        if ratios:
            cell["uinet_vs_greedy_per_problem_geomean"] = round(geo(ratios), 3)
            cell["uinet_vs_greedy_win_loss_tie"] = [
                sum(1 for pid in pids if per_problem[pid].get("uinet", 0) > per_problem[pid].get("greedy", 0)),
                sum(1 for pid in pids if per_problem[pid].get("uinet", 0) < per_problem[pid].get("greedy", 0)),
                sum(1 for pid in pids if per_problem[pid].get("uinet", 0) == per_problem[pid].get("greedy", 0)),
            ]
        out[group] = cell
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", type=Path, default=DEFAULT_BENCH)
    parser.add_argument("--problems", type=Path, default=DEFAULT_PROBLEMS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    data = json.loads(args.bench.read_text(encoding="utf-8"))
    raws = json.loads(args.problems.read_text(encoding="utf-8"))
    raws = raws if isinstance(raws, list) else (raws.get("problems") or raws.get("items") or [])
    meta = {}
    for raw in raws:
        scene = raw.get("scene") or {}
        loadout = (raw.get("archive") or {}).get("loadout") or {}
        meta[str(raw["id"])] = {
            "kind": scene.get("kind"),
            "stage": scene.get("stage"),
            "plan": scene.get("plan"),
            "round": loadout.get("round"),
            "produce": loadout.get("produce_id"),
            "core": bool(raw.get("core")),
        }

    episodes = data["episodes"]
    algos = list(data["algorithms"])
    per_problem = data["per_problem"]
    problems = data["problems"]

    print(f"bench={args.bench}")
    print(
        f"problems={problems['count']} selected / {problems['source_total']} source, "
        f"skipped={problems['skipped_count']}, seeds={data['seeds']}, "
        f"episodes/algo={data['episodes_per_algo']}"
    )
    print(
        f"selected plans={problems.get('plans')} kinds={problems.get('kinds')} "
        f"stages={problems.get('stages')} core={problems.get('core')} "
        f"produce={problems.get('uinet_produce')} step={problems.get('uinet_step')}"
    )
    print(f"uinet cold_start_ms={data.get('uinet', {}).get('cold_start_ms') if data.get('uinet') else None}")

    print("\n== overall ==")
    for algo in algos:
        print(fmt_row(algo, data["algorithms"][algo]))

    print("\n== ratios vs greedy (mean) ==")
    base_mean = data["algorithms"]["greedy"]["mean"]
    for algo in algos:
        if algo == "greedy":
            continue
        mean = data["algorithms"][algo]["mean"]
        print(f"{algo:22s} mean_ratio={mean / base_mean:.4f}x  ({mean:.1f} / {base_mean:.1f})")

    print("\n== paired per-problem vs greedy ==")
    pair = {}
    for algo in algos:
        if algo == "greedy":
            continue
        stats = paired_stats(per_problem, meta, algo)
        pair[algo] = stats
        print(
            f"{algo:22s} n={stats['problems']:3d} geomean={stats['geomean']:.4f}x "
            f"[95% CI {stats['ci95'][0]:.4f}, {stats['ci95'][1]:.4f}] "
            f"median={stats['median_ratio']:.4f}x min={stats['min_ratio']:.4f}x "
            f"max={stats['max_ratio']:.4f}x win/loss/tie="
            f"{stats['wins']}/{stats['losses']}/{stats['ties']}"
        )

    print("\n== paired per-episode vs greedy ==")
    ep_scores: dict[tuple[str, int], dict[str, int]] = defaultdict(dict)
    for ep in episodes:
        ep_scores[(ep["problem"], int(ep["seed"]))][ep["algo"]] = int(ep["score"])
    ep_pair = {}
    for algo in algos:
        if algo == "greedy":
            continue
        ratios = []
        wins = losses = ties = 0
        for row in ep_scores.values():
            base_score = row.get("greedy")
            value = row.get(algo)
            if base_score is None or value is None or base_score <= 0 or value <= 0:
                continue
            ratios.append(value / base_score)
            if value > base_score:
                wins += 1
            elif value < base_score:
                losses += 1
            else:
                ties += 1
        lo, hi = bootstrap_ci(ratios)
        ep_pair[algo] = {
            "episodes": len(ratios),
            "geomean": round(geo(ratios), 4),
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "ci95": [round(lo, 4), round(hi, 4)],
        }
        print(
            f"{algo:22s} n={len(ratios):4d} geomean={geo(ratios):.4f}x "
            f"[95% CI {lo:.4f}, {hi:.4f}] win/loss/tie={wins}/{losses}/{ties}"
        )

    print("\n== by kind ==")
    by_kind = group_stats(per_problem, meta, episodes, algos, field="kind")
    for group, cell in by_kind.items():
        print(json.dumps({group: cell}, ensure_ascii=False, sort_keys=True))

    print("\n== by plan ==")
    by_plan = group_stats(per_problem, meta, episodes, algos, field="plan")
    for group, cell in by_plan.items():
        print(json.dumps({group: cell}, ensure_ascii=False, sort_keys=True))

    print("\n== by stage ==")
    by_stage = group_stats(per_problem, meta, episodes, algos, field="stage")
    for group, cell in by_stage.items():
        print(json.dumps({group: cell}, ensure_ascii=False, sort_keys=True))

    print("\n== by core ==")
    by_core = group_stats(per_problem, meta, episodes, algos, field="core")
    for group, cell in by_core.items():
        print(json.dumps({str(group): cell}, ensure_ascii=False, sort_keys=True))

    print("\n== by produce ==")
    by_produce = group_stats(per_problem, meta, episodes, algos, field="produce")
    for group, cell in by_produce.items():
        print(json.dumps({str(group): cell}, ensure_ascii=False, sort_keys=True))

    print("\n== uinet vs greedy per-problem extremes ==")
    diffs = []
    for pid, row in per_problem.items():
        base_score = row.get("greedy")
        value = row.get("uinet")
        if base_score and value:
            diffs.append((value - base_score, value / base_score, pid, base_score, value))
    print("-- 5 lowest ratios --")
    for _delta, ratio, pid, base_score, value in sorted(diffs, key=lambda item: item[1])[:5]:
        m = meta.get(pid, {})
        print(
            f"  {pid} {m.get('stage')} plan={m.get('plan')} core={m.get('core')} "
            f"greedy={base_score:8.1f} uinet={value:8.1f} ratio={ratio:.3f}x"
        )
    print("-- 5 highest ratios --")
    for _delta, ratio, pid, base_score, value in sorted(diffs, key=lambda item: item[1], reverse=True)[:5]:
        m = meta.get(pid, {})
        print(
            f"  {pid} {m.get('stage')} plan={m.get('plan')} core={m.get('core')} "
            f"greedy={base_score:8.1f} uinet={value:8.1f} ratio={ratio:.3f}x"
        )

    print("\n== their leaderboard ==")
    print("  task/previous report: UINet 24,991 vs greedy 7,071 = 3.5x (their core set, GKMS native)")
    if pair.get("uinet"):
        print(
            f"  local per-problem geomean UINet/greedy = {pair['uinet']['geomean']:.4f}x; "
            f"mean ratio = {data['algorithms']['uinet']['mean'] / base_mean:.4f}x; "
            f"official/local mean-ratio gap = {(3.5 / (data['algorithms']['uinet']['mean'] / base_mean)):.2f}x"
        )
    ranked = sorted(algos, key=lambda name: data["algorithms"][name]["mean"], reverse=True)
    print("  local mean ranking: " + " > ".join(ranked))
    print("  official ranking: UINet >> greedy")

    result = {
        "bench": str(args.bench),
        "problems": problems,
        "algorithms": data["algorithms"],
        "pair_vs_greedy": pair,
        "episode_pair_vs_greedy": ep_pair,
        "by_kind": by_kind,
        "by_plan": by_plan,
        "by_stage": by_stage,
        "by_core": by_core,
        "by_produce": by_produce,
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nJSON: {args.out}")


if __name__ == "__main__":
    main()
