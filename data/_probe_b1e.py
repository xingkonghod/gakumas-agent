"""B1 probe 4: full-depth beam vs within on one seed, with generous budget."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd

from gkagent.sim.expectimax import AnalyticLeafValue, search_beam, state_from_sim
from gkagent.sim.lesson import LessonSim


def run(seed: int, budget: float, depth: int | None = None) -> None:
    deck = ee.build_deck("small")
    config = ee.make_config("small")
    sim = LessonSim(deck, config, rng_seed=seed)
    weights = AnalyticLeafValue(score_tiebreak=1e-3)
    rows = []
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            sim.step(None)
            continue
        state = state_from_sim(sim, known_deck_order=True)
        t0 = time.perf_counter()
        result = search_beam(
            state,
            weights,
            width=4,
            depth=depth,
            deadline_ms=budget,
            branching=10,
        )
        ms = (time.perf_counter() - t0) * 1000
        rows.append(
            (len(sim.hand), tuple(c.name for c in sim.hand), result.sequence,
             result.depth_reached, result.complete, round(ms))
        )
        ekd._execute_plan(sim, list(result.sequence))
    print(f"seed={seed} beam depth={depth} budget={budget} score={sim.score}")
    for row in rows:
        print("  ", row)
    within = ekd.play(deck, config, seed, known=True, policy="within", budget_ms=200)
    print(f"  within={within['score']}")


def main() -> None:
    run(1, 2000.0, depth=5)
    run(6, 2000.0, depth=5)


if __name__ == "__main__":
    main()
