"""B1 probe 2b: inspect frontier states + real rollout utilities."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee

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


def main() -> None:
    sim = LessonSim(ee.build_deck("small"), ee.make_config("small"), rng_seed=1)
    state = state_from_sim(sim, known_deck_order=True)
    model = AnalyticLeafValue(score_tiebreak=1e-3)
    base = search_beam(
        state, model, width=4, depth=3, deadline_ms=200, branching=10
    )
    print("base card=", base.card.name, "seq=", base.sequence, "depth", base.depth_reached)
    rollout = RolloutLeafValue(
        sigma=60.0, score_tiebreak=1e-3, rollouts=1, policy="within", rollout_budget_ms=5.0
    )
    rec = Recorder(rollout)
    out = search_beam(
        state,
        model,
        width=4,
        depth=3,
        deadline_ms=200,
        branching=10,
        frontier_value=rec,
    )
    print("front card=", out.card.name, "seq=", out.sequence, "u=", out.utility)
    for i, (s, u) in enumerate(rec.states):
        print(
            f"  #{i} util={u:.4f} score={s.score} turns={s.turns_left} "
            f"stam={s.stamina} vit={s.vitality} hand={len(s.hand)} "
            f"deck={len(s.deck)} discard={len(s.discard)} known={len(s.known_draw)} "
            f"focus={s.focus} imp={s.impression} cond={s.condition_turns} "
            f"canon={hash(s.canonical()) & 0xFFFFFF:x}"
        )


if __name__ == "__main__":
    main()
