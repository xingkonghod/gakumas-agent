"""Ablate UINet observation fields on the 15 audition problems (throwaway).

Question: is the local gap driven by the missing observation fields (less info)
or by the simulator/training distribution mismatch?
Variants:
- full: our sim_to_uiobs (hand + zones + status + stance + exam)
- no_status: remove the buff statuses
- no_zones: remove deck/grave/lost/played (keep status)
- hand_only: only hand + num + legal (close to what uiobs.py reads on the live screen)
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import local_bench as lb

OUT = ROOT / "data" / "bench_local" / "_ablate_uinet_obs.json"
AUDITIONS = ROOT / "data" / "bench_local" / "_auditions15.json"
ORIGINAL = lb.sim_to_uiobs


def _wrap(mode: str):
    def convert(sim, spec, **kwargs):
        obs = dict(ORIGINAL(sim, spec, **kwargs))
        if mode in ("no_status", "hand_only"):
            obs["status"] = []
        if mode in ("no_zones", "hand_only"):
            for key in ("deck", "grave", "lost", "played", "hold", "ench", "drinks"):
                obs[key] = []
        if mode == "hand_only":
            obs["stance"] = [None, 0]
        return obs

    return convert


def _geo(values: list[float]) -> float:
    return math.exp(statistics.fmean(math.log(v) for v in values))


def _run(problems: Path, algos: list[str], out: Path) -> dict:
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        return lb.run_bench(
            problems_path=problems,
            episodes=3,
            seed_base=1000,
            algo_names=algos,
            budget_ms=300.0,
            limit=None,
            output=out,
        )


def main() -> None:
    raws = lb.load_problems()
    auditions = [
        raw for raw in raws if str((raw.get("scene") or {}).get("kind")) != "lesson"
    ]
    AUDITIONS.write_text(json.dumps(auditions, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"audition problems: {len(auditions)}")

    greedy = _run(AUDITIONS, ["greedy"], ROOT / "data" / "bench_local" / "_abl_greedy.json")
    base_mean = greedy["algorithms"]["greedy"]["mean"]
    print(f"greedy auditions mean={base_mean:.1f} n={greedy['algorithms']['greedy']['episodes']}")
    base_by_problem = greedy["per_problem"]

    results = {
        "greedy": greedy["algorithms"]["greedy"],
        "variants": {},
    }
    for mode in ("full", "no_status", "no_zones", "hand_only"):
        lb.sim_to_uiobs = _wrap(mode)
        try:
            summary = _run(
                AUDITIONS, ["uinet"], ROOT / "data" / "bench_local" / f"_abl_{mode}.json"
            )
        finally:
            lb.sim_to_uiobs = ORIGINAL
        row = summary["algorithms"]["uinet"]
        ratios = []
        for pid, values in summary["per_problem"].items():
            base = base_by_problem.get(pid, {}).get("greedy")
            value = values.get("uinet")
            if base and value and base > 0 and value > 0:
                ratios.append(value / base)
        results["variants"][mode] = {
            **row,
            "vs_greedy_mean_ratio": round(row["mean"] / base_mean, 4),
            "vs_greedy_geomean_ratio": round(_geo(ratios), 4),
        }
        print(
            f"{mode:10s} mean={row['mean']:8.1f} p50={row['p50']:7.1f} p90={row['p90']:8.1f} "
            f"step={row['step_ms_mean']:6.2f}ms "
            f"mean_ratio={row['mean'] / base_mean:.3f}x geomean={_geo(ratios):.3f}x "
            f"errors={row.get('errors', 0)}"
        )

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
