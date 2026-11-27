"""B1 probe 5: per-turn trace of beam vs within on one seed."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd

from gkagent.sim.expectimax import AnalyticLeafValue, search_beam, state_from_sim
from gkagent.sim.lesson import LessonSim


def snapshot(sim: LessonSim) -> str:
    return (
        f"T{sim.config.turns - sim.turns_left + 1} score={sim.score} stam={sim.stamina} "
        f"vit={sim.vitality} focus={sim.buffs.focus} imp={sim.buffs.impression} "
        f"hand={[c.name[:6] for c in sim.hand]}"
    )


def run_within(seed: int) -> None:
    deck = ee.build_deck("small")
    config = ee.make_config("small")
    sim = LessonSim(deck, config, rng_seed=seed)
    print("== within ==")
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            print(" ", snapshot(sim), "SKIP")
            sim.step(None)
            continue
        state = state_from_sim(sim, known_deck_order=True)
        result = ekd.expectimax_with_stats(
            state,
            AnalyticLeafValue(score_tiebreak=1e-3),
            time_budget_ms=200.0,
        )
        print(" ", snapshot(sim), "-> play", result.card.name if result.card else None,
              "u=", round(result.utility, 4), "skip_u=", round(result.skip_utility, 4),
              "nodes=", result.nodes, "complete=", result.complete)
        index = ekd._card_index(sim, result.card) if result.card else None
        if index is None:
            index = ekd.greedy_policy(sim)
        sim.step(index)
    print(" final score", sim.score)


def run_beam(seed: int) -> None:
    deck = ee.build_deck("small")
    config = ee.make_config("small")
    sim = LessonSim(deck, config, rng_seed=seed)
    model = AnalyticLeafValue(score_tiebreak=1e-3)
    print("== beam ==")
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            print(" ", snapshot(sim), "SKIP")
            sim.step(None)
            continue
        state = state_from_sim(sim, known_deck_order=True)
        result = search_beam(
            state, model, width=4, deadline_ms=2000, branching=10
        )
        print(" ", snapshot(sim), "-> plan", result.sequence,
              "depth=", result.depth_reached, "u=", round(result.utility, 4),
              "ms=", round(result.elapsed_ms))
        ekd._execute_plan(sim, list(result.sequence))
    print(" final score", sim.score)


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    run_within(seed)
    run_beam(seed)


if __name__ == "__main__":
    main()
