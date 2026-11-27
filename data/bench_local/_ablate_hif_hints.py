"""H.I.F 60 题样本上的 UINet 观测消融：考试提示（crit/permil）是否有帮助。

对照：
- full：60x2 跑分里的 UINet（完整 UIObs，含 H.I.F 题面的 parameters/permil）；
- zero_hints：同一观测，但 ``exam.permil=[1000,1000,1000]``、``exam.crit=[0,0,0]``。

只读 60x2 JSON 的题目/分数，不联网、不改数据。
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import local_bench as lb

BENCH = ROOT / "data" / "bench_local" / "leaderboard_hif_60x2.json"
PROBLEMS = ROOT / "data" / "bench_local" / "problems_hif.json"
OUT = ROOT / "data" / "bench_local" / "_ablate_hif_hints.json"


class ZeroHintsPolicy(lb.UinetPolicy):
    """把 UIObs 的 exam.permil/crit 还原成中性值，再看 UINet 分数。"""

    def decide(self, obs, sim):  # type: ignore[no-untyped-def]
        obs = dict(obs)
        obs["exam"] = dict(obs["exam"])
        obs["exam"]["permil"] = [1000, 1000, 1000]
        obs["exam"]["crit"] = [0, 0, 0]
        return super().decide(obs, sim)


def main() -> None:
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    ids = bench["problems"]["ids"]
    full_scores = {}
    greedy_scores = {}
    for ep in bench["episodes"]:
        key = (ep["problem"], int(ep["seed"]))
        if ep["algo"] == "uinet":
            full_scores[key] = int(ep["score"])
        elif ep["algo"] == "greedy":
            greedy_scores[key] = int(ep["score"])

    rows = {str(row["id"]): row for row in json.loads(PROBLEMS.read_text(encoding="utf-8"))}
    card_rows, card_index, refs = lb.load_card_table()
    specs = [lb.build_problem(rows[pid], card_rows, card_index, refs) for pid in ids]

    zero_scores = {}
    for spec in specs:
        for seed in (1000, 1001):
            policy = ZeroHintsPolicy()
            episode = lb.run_episode(spec, seed, policy)
            zero_scores[(spec.pid, seed)] = episode.score
            print(f"  {spec.pid} seed={seed} zero_hints={episode.score}", file=sys.stderr)

    keys = sorted(set(full_scores) & set(zero_scores) & set(greedy_scores))
    full = [full_scores[key] for key in keys]
    zero = [zero_scores[key] for key in keys]
    greedy = [greedy_scores[key] for key in keys]
    ratios_full = [f / g for f, g in zip(full, greedy, strict=True) if g > 0 and f > 0]
    ratios_zero = [z / g for z, g in zip(zero, greedy, strict=True) if g > 0 and z > 0]
    ratios_zero_vs_full = [z / f for z, f in zip(zero, full, strict=True) if f > 0 and z > 0]

    def geo(values):
        return math.exp(statistics.fmean(math.log(v) for v in values)) if values else float("nan")

    result = {
        "sample": "60x2 (seeds 1000,1001)",
        "episodes": len(keys),
        "full": {
            "mean": round(statistics.fmean(full), 1),
            "greedy_mean": round(statistics.fmean(greedy), 1),
            "mean_ratio": round(statistics.fmean(full) / statistics.fmean(greedy), 4),
            "geomean_ratio": round(geo(ratios_full), 4),
        },
        "zero_hints": {
            "mean": round(statistics.fmean(zero), 1),
            "greedy_mean": round(statistics.fmean(greedy), 1),
            "mean_ratio": round(statistics.fmean(zero) / statistics.fmean(greedy), 4),
            "geomean_ratio": round(geo(ratios_zero), 4),
        },
        "zero_vs_full": {
            "mean_ratio": round(statistics.fmean(zero) / statistics.fmean(full), 4),
            "geomean_ratio": round(geo(ratios_zero_vs_full), 4),
            "wins": sum(1 for z, f in zip(zero, full, strict=True) if z > f),
            "losses": sum(1 for z, f in zip(zero, full, strict=True) if z < f),
            "ties": sum(1 for z, f in zip(zero, full, strict=True) if z == f),
        },
        "scores": {f"{pid}:{seed}": {"full": full_scores[(pid, seed)], "zero": zero, "greedy": greedy_scores[(pid, seed)]} for (pid, seed), zero in zero_scores.items()},
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "scores"}, ensure_ascii=False, indent=1))
    print(f"JSON: {OUT}")


if __name__ == "__main__":
    main()
