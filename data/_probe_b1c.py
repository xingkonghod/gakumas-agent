"""B1 probe 3: single-seed end-to-end comparison of analytic vs frontier rollout."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd


def main() -> None:
    deck = ee.build_deck("small")
    config = ee.make_config("small")
    for seed in range(8):
        common = dict(
            known=True,
            policy="beam",
            budget_ms=100.0,
            width=4,
            score_tiebreak=1e-3,
            branching=10,
        )
        base = ekd.play(deck, config, seed, **common)
        front = ekd.play(deck, config, seed, **common, frontier_rollout=True)
        fixed = ekd.play(
            deck, config, seed, **common, frontier_rollout=True, beam_depth=3
        )
        fixed_base = ekd.play(deck, config, seed, **common, beam_depth=3)
        print(
            f"seed={seed} base={base['score']:.0f} front={front['score']:.0f} "
            f"fixedbase={fixed_base['score']:.0f} fixedfront={fixed['score']:.0f}"
        )


if __name__ == "__main__":
    main()
