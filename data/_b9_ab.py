"""B9 A/B 配对分析：hif 30 题 × 2 seed，P 道具 off vs auto。

配对口径（与 B8 相同）：同一 (problem, seed) 两条 episode 的分数差；
bootstrap 95% CI（按题整体重采样，固定 seed 可复现）；胜负平计数。
只读这次新跑的两份 JSON，输出 markdown 片段（docs 用）。
"""

from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "bench_local"


def episodes(path: Path) -> dict[tuple[str, int], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = {}
    for episode in payload["episodes"]:
        rows[(episode["problem"], int(episode["seed"]))] = episode
    return rows


def paired(off_path: Path, auto_path: Path, label: str) -> dict:
    off = episodes(off_path)
    auto = episodes(auto_path)
    keys = sorted(set(off) & set(auto))
    deltas = [auto[key]["score"] - off[key]["score"] for key in keys]
    wins = sum(1 for d in deltas if d > 0)
    losses = sum(1 for d in deltas if d < 0)
    ties = sum(1 for d in deltas if d == 0)
    mean_off = statistics.fmean(off[key]["score"] for key in keys)
    mean_auto = statistics.fmean(auto[key]["score"] for key in keys)
    mean_delta = statistics.fmean(deltas)
    # 按题整体 bootstrap（30 题，每题 2 seed 一起重采样）
    by_problem: dict[str, list[int]] = {}
    for key, delta in zip(keys, deltas):
        by_problem.setdefault(key[0], []).append(delta)
    problems = sorted(by_problem)
    rng = random.Random(20261122)
    samples = []
    for _ in range(10000):
        picked = [rng.choice(problems) for _ in problems]
        values = [d for problem in picked for d in by_problem[problem]]
        samples.append(statistics.fmean(values))
    samples.sort()
    lo = samples[int(0.025 * len(samples))]
    hi = samples[int(0.975 * len(samples)) - 1]
    total_off = sum(off[key]["score"] for key in keys)
    total_auto = sum(auto[key]["score"] for key in keys)
    ratio = (mean_auto / mean_off - 1.0) if mean_off else 0.0
    result = {
        "label": label,
        "games": len(keys),
        "problems": len(problems),
        "mean_off": mean_off,
        "mean_auto": mean_auto,
        "mean_delta": mean_delta,
        "ratio": ratio,
        "ci_low": lo,
        "ci_high": hi,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "total_off": total_off,
        "total_auto": total_auto,
        "max_gain": max(deltas),
        "max_loss": min(deltas),
    }
    return result


def main() -> int:
    runs = [
        ("greedy", BENCH / "ab_pitems_off_b9.json", BENCH / "ab_pitems_auto_b9.json"),
        (
            "expectimax",
            BENCH / "ab_pitems_exp_off_b9.json",
            BENCH / "ab_pitems_exp_auto_b9.json",
        ),
    ]
    lines = ["# B9 P 道具 A/B（hif 30 题 × 2 seed = 60 局，配对，off vs auto）", ""]
    lines.append(
        "| 引擎 | 局 | 题 | off 均值 | auto 均值 | Δ均值 | Δ% | 95% CI | 胜/负/平 | 最大 +/− |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---:|---:|")
    for label, off_path, auto_path in runs:
        if not off_path.is_file() or not auto_path.is_file():
            lines.append(f"| {label} | — | — | （缺文件） | | | | | | |")
            continue
        result = paired(off_path, auto_path, label)
        lines.append(
            f"| {result['label']} | {result['games']} | {result['problems']} | "
            f"{result['mean_off']:.1f} | {result['mean_auto']:.1f} | "
            f"{result['mean_delta']:+.1f} | {result['ratio']:+.2%} | "
            f"[{result['ci_low']:+.1f}, {result['ci_high']:+.1f}] | "
            f"{result['wins']}/{result['losses']}/{result['ties']} | "
            f"{result['max_gain']:+.0f} / {result['max_loss']:+.0f} |"
        )
    lines.append("")
    lines.append(
        "口径：裁判=我们的 LessonSim（不是 gkbench GKMS 引擎），题集 hif 505 道里 "
        "可映射 30 道（`--sample 30 --sample-seed 0`），种子 1000/1001 自选；配对 Δ 按"
        "(problem, seed) 逐局相减，CI 为按题整体重采样 10000 次的 percentile bootstrap。"
    )
    path = BENCH / "ab_pitems_b9.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
