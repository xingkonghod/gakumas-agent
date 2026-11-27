"""B1 probe: instrument beam depth/complete on the small scenario (throwaway)."""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    RolloutLeafValue,
    search_beam,
    state_from_sim,
)
from gkagent.sim.lesson import LessonSim


def play_beam(seed, *, budget=100.0, width=4, branch=10, tiebreak=1e-3, model=None):
    sim = LessonSim(ee.build_deck("small"), ee.make_config("small"), rng_seed=seed)
    model = model or AnalyticLeafValue(score_tiebreak=tiebreak)
    rows = []
    fallbacks = 0
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            sim.step(None)
            continue
        state = state_from_sim(sim, known_deck_order=True)
        t0 = time.perf_counter()
        result = search_beam(
            state,
            model,
            width=width,
            deadline_ms=budget * 2,
            branching=branch,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        rows.append(
            {
                "depth": result.depth_reached,
                "complete": result.complete,
                "ms": elapsed,
                "end_turns": result.end_state.turns_left if result.end_state else None,
            }
        )
        fallbacks += ekd._execute_plan(sim, list(result.sequence))
    return {
        "score": sim.score,
        "fallbacks": fallbacks,
        "depth": [r["depth"] for r in rows],
        "complete": [r["complete"] for r in rows],
        "ms": [r["ms"] for r in rows],
        "end_turns": [r["end_turns"] for r in rows],
    }


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    within = []
    beam = []
    for seed in range(n):
        w = ekd.play(
            ee.build_deck("small"),
            ee.make_config("small"),
            seed,
            known=True,
            policy="within",
            budget_ms=200.0,
        )
        b = play_beam(seed)
        within.append(w["score"])
        beam.append(b["score"])
        print(
            f"seed={seed:02d} within={w['score']:.0f} beam={b['score']:.0f} "
            f"depth={b['depth']} complete={b['complete']} "
            f"ms={[round(x, 1) for x in b['ms']]} end_turns={b['end_turns']} "
            f"fb={b['fallbacks']}"
        )
    print(f"within mean={statistics.mean(within):.1f} beam mean={statistics.mean(beam):.1f}")


if __name__ == "__main__":
    main()
