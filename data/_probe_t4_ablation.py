"""T4 ablation after fixing `_execute_plan` (throwaway analysis for B1 docs).

Same-seed paired comparison of beam tuning knobs on the small scenario, with the
corrected plan runner (no more losing a turn when the hand empties).
"""

from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd

N = 60
SEED = 0
DECK, CONFIG = ee.build_deck("small"), ee.make_config("small")


def run(label, *, known, **kwargs):
    rows = [
        ekd.play(DECK, CONFIG, SEED + offset, known=known, budget_ms=100.0, **kwargs)
        for offset in range(N)
    ]
    scores = [row["score"] for row in rows]
    stat = ekd.summarize(rows)
    print(
        f"{label:<18} mean={stat['mean']:6.1f} p50={stat['p50']:5.0f} "
        f"clear={stat['clear_rate'] * 100:5.1f}% perfect={stat['perfect_rate'] * 100:5.1f}%"
    )
    return scores


def paired(label, scores, base):
    deltas = [value - baseline for value, baseline in zip(scores, base)]
    mean = sum(deltas) / len(deltas)
    half = 1.96 * statistics.stdev(deltas) / math.sqrt(len(deltas))
    print(
        f"  {label:<16} vs default: Δmean={mean:+.1f} "
        f"95%CI[{mean - half:+.1f},{mean + half:+.1f}] "
        f"胜/平/负={sum(d > 0 for d in deltas)}/{sum(d == 0 for d in deltas)}/"
        f"{sum(d < 0 for d in deltas)}"
    )


def main() -> None:
    for known in (False, True):
        print(f"== {'known' if known else 'unknown'} ==")
        default = run(
            "beam default", known=known, policy="beam", width=4, branching=None,
            score_tiebreak=0.0,
        )
        tuned = run(
            "beam tb+br10", known=known, policy="beam", width=4, branching=10,
            score_tiebreak=1e-3,
        )
        tie = run(
            "beam tb only", known=known, policy="beam", width=4, branching=None,
            score_tiebreak=1e-3,
        )
        branch = run(
            "beam br10 only", known=known, policy="beam", width=4, branching=10,
            score_tiebreak=0.0,
        )
        paired("tb+br10", tuned, default)
        paired("tb only", tie, default)
        paired("br10 only", branch, default)


if __name__ == "__main__":
    main()
