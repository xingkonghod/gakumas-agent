"""B1 probe 5b: per-step trace of beam execution."""

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
        f"T{sim.config.turns - sim.turns_left + 1} tl={sim.turns_left} "
        f"score={sim.score} stam={sim.stamina} plays={sim.plays_this_turn} "
        f"hand={[c.name[:5] for c in sim.hand]}"
    )


def play_names(sim: LessonSim, names) -> int:
    for name in names:
        actions = sim.legal_actions()
        print("    exec", name, "|", snapshot(sim), "| actions", actions)
        if not sim.hand or actions == [None]:
            break
        index = next((i for i, card in enumerate(sim.hand) if card.name == name), None)
        if index is None or index not in actions:
            index = ekd.greedy_policy(sim)
            if index is None:
                break
        sim.step(index)
    if not sim.done and sim.legal_actions() != [None]:
        print("    exec SKIP |", snapshot(sim))
        sim.step(None)
    return 0


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    deck = ee.build_deck("small")
    config = ee.make_config("small")
    sim = LessonSim(deck, config, rng_seed=seed)
    model = AnalyticLeafValue(score_tiebreak=1e-3)
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            print(" ", snapshot(sim), "SKIP")
            sim.step(None)
            continue
        state = state_from_sim(sim, known_deck_order=True)
        result = search_beam(state, model, width=4, deadline_ms=2000, branching=10)
        print(" ", snapshot(sim), "-> plan", result.sequence, "depth", result.depth_reached)
        play_names(sim, result.sequence)
    print(" final score", sim.score)


if __name__ == "__main__":
    main()
