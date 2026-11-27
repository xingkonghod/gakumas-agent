"""B1 probe 2: does frontier_value actually rerank the truncated beam?"""

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
    search_beam,
    state_from_sim,
)
from gkagent.sim.lesson import LessonSim


class Fake:
    def __init__(self, fn):
        self.fn = fn
        self.calls = []

    def utility(self, state):
        self.calls.append(state)
        return self.fn(state)

    def predict(self, state):
        return 0.0, 0.0


def main() -> None:
    sim = LessonSim(ee.build_deck("small"), ee.make_config("small"), rng_seed=1)
    state = state_from_sim(sim, known_deck_order=True)
    model = AnalyticLeafValue(score_tiebreak=1e-3)
    base = search_beam(
        state, model, width=4, depth=2, deadline_ms=200, branching=10
    )
    print("base", base.card, base.sequence, base.utility, base.depth_reached)
    const = Fake(lambda s: 0.0)
    out = search_beam(
        state,
        model,
        width=4,
        depth=2,
        deadline_ms=200,
        branching=10,
        frontier_value=const,
    )
    print("const", out.card, out.sequence, out.utility, out.depth_reached, "calls", len(const.calls))
    high = Fake(lambda s: float(s.score) + float(s.turns_left))
    out2 = search_beam(
        state,
        model,
        width=4,
        depth=2,
        deadline_ms=200,
        branching=10,
        frontier_value=high,
    )
    print("high", out2.card, out2.sequence, out2.utility, out2.depth_reached, "calls", len(high.calls))
    for call in high.calls:
        print("  frontier state: score", call.score, "turns", call.turns_left, "hand", len(call.hand))


if __name__ == "__main__":
    main()
