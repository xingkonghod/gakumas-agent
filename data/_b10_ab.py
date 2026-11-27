"""B10 A/B 配对分析：hif 30 题 × 2 seed，P 道具 off vs auto（口径同 B8/B9）。"""

from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "bench_local"


def episodes(path: Path) -> dict[tuple[str, int], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {(e["problem"], int(e["seed"])): e for e in payload["episodes"]}


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
    by_problem: dict[str, list[int]] = {}
    for key, delta in zip(keys, deltas):
        by_problem.setdefault(key[0], []).append(delta)
    problems = sorted(by_problem)
    rng = random.Random(20261123)
    samples = []
    for _ in range(10000):
        picked = [rng.choice(problems) for _ in problems]
        values = [d for problem in picked for d in by_problem[problem]]
        samples.append(statistics.fmean(values))
    samples.sort()
    lo = samples[int(0.025 * len(samples))]
    hi = samples[int(0.975 * len(samples)) - 1]
    changed = sum(1 for d in deltas if d != 0)
    return {
        "label": label, "games": len(keys), "problems": len(problems),
        "mean_off": mean_off, "mean_auto": mean_auto, "mean_delta": mean_delta,
        "ratio": (mean_auto / mean_off - 1.0) if mean_off else 0.0,
        "ci_low": lo, "ci_high": hi,
        "wins": wins, "losses": losses, "ties": ties, "changed": changed,
        "max_gain": max(deltas), "max_loss": min(deltas),
    }


def main() -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    runs = [
        ("greedy", BENCH / "ab_pitems_off_b10.json", BENCH / "ab_pitems_auto_b10.json"),
        ("expectimax", BENCH / "ab_pitems_exp_off_b10.json", BENCH / "ab_pitems_exp_auto_b10.json"),
    ]
    lines = ["# B10 P 道具 A/B（hif 30 题 × 2 seed = 60 局，配对，off vs auto）", ""]
    lines.append("| 引擎 | 局 | 题 | off 均值 | auto 均值 | Δ均值 | Δ% | 95% CI | 胜/负/平 | 变化局 | 最大 +/− |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|")
    for label, off_path, auto_path in runs:
        if not off_path.is_file() or not auto_path.is_file():
            lines.append(f"| {label} | — | — | （缺文件） | | | | | | | |")
            continue
        r = paired(off_path, auto_path, label)
        lines.append(
            f"| {r['label']} | {r['games']} | {r['problems']} | {r['mean_off']:.1f} | "
            f"{r['mean_auto']:.1f} | {r['mean_delta']:+.1f} | {r['ratio']:+.2%} | "
            f"[{r['ci_low']:+.1f}, {r['ci_high']:+.1f}] | {r['wins']}/{r['losses']}/{r['ties']} | "
            f"{r['changed']}/{r['games']} | {r['max_gain']:+.0f} / {r['max_loss']:+.0f} |"
        )
    lines.append("")
    lines.append(
        "口径：裁判=我们的 LessonSim（不是 gkbench GKMS 引擎），题集 hif 505 道里 "
        "可映射 30 道（`--sample 30 --sample-seed 0`），种子 1000/1001 自选；配对 Δ 按"
        "(problem, seed) 逐局相减，CI 为按题整体重采样 10000 次的 percentile bootstrap。"
        "B10 的 auto 与 B9 auto 不可直接比（触发限定结构化 + 次数按道具计修正）。"
    )
    path = BENCH / "ab_pitems_b10.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())