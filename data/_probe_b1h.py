"""B1 probe 6: is frontier rollout ever invoked (known beam, corrected harness)?"""

from __future__ import annotations

import sys
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


class Recorder:
    def __init__(self, inner):
        self.inner = inner
        self.states = []

    def utility(self, state):
        value = self.inner.utility(state)
        self.states.append((state, value))
        return value

    def predict(self, state):
        return self.inner.predict(state)


def run(seed: int) -> None:
    deck = ee.build_deck("small")
    config = ee.make_config("small")
    sim = LessonSim(deck, config, rng_seed=seed)
    model = AnalyticLeafValue(score_tiebreak=1e-3)
    rec = Recorder(
        RolloutLeafValue(
            sigma=60.0,
            score_tiebreak=1e-3,
            rollouts=1,
            policy="within",
            rollout_budget_ms=5.0,
        )
    )
    rows = []
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            sim.step(None)
            continue
        state = state_from_sim(sim, known_deck_order=True)
        result = search_beam(
            state,
            model,
            width=4,
            deadline_ms=200,
            branching=10,
            frontier_value=rec,
        )
        rows.append((result.depth_reached, result.complete))
        ekd._execute_plan(sim, list(result.sequence))
    utils = [round(u, 3) for _, u in rec.states]
    print(f"seed={seed} score={sim.score} decisions={rows} frontier_calls={len(utils)}")
    print("  frontier utils:", utils)


def main() -> None:
    for seed in range(8):
        run(seed)


if __name__ == "__main__":
    main()
