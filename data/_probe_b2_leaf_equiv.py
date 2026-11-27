"""B2 重训前探针：leaf_state_at_draw 快照 vs end_turn_state 逐字段等价性。

训练分布（RecordingLessonSim 在 _draw_hand 入口的快照）必须与推理分布
（expectimax._Search.leaf 的 end_turn_state 输入）完全一致，否则模型学歪。
B3（SKIP 回体力）/B5（温存解除回合边界）/B9（modifier 倒计时）之后逐字段核对。
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
from gkagent.sim.expectimax import end_turn_state, state_from_sim
from gkagent.sim.leaf_data import RecordingLessonSim, leaf_state_at_draw
from gkagent.sim.lesson import greedy_policy


class ProbeSim(RecordingLessonSim):
    def __init__(self, *args, **kwargs):
        self.pre_states = []
        super().__init__(*args, **kwargs)

    def _end_turn(self, *, skipped: bool) -> None:
        self.pre_states.append(state_from_sim(self))
        super()._end_turn(skipped=skipped)


def main() -> None:
    import eval_known_draw as ekd

    deck, config = ee.build_deck("small"), ee.make_config("small")
    mismatch_fields: Counter[str] = Counter()
    mismatch_games = 0
    total_leaves = 0
    release_boundaries = 0
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    policy = sys.argv[2] if len(sys.argv) > 2 else "greedy"
    for offset in range(games):
        seed = 700_000 + offset
        if policy == "greedy":
            sim = ProbeSim(deck, config, rng_seed=seed)
            while not sim.done:
                actions = sim.legal_actions()
                sim.step(greedy_policy(sim) if actions != [None] else None)
        else:
            instances: list[ProbeSim] = []

            def factory(deck, config, rng_seed):
                s_ = ProbeSim(deck, config, rng_seed)
                instances.append(s_)
                return s_

            ekd.play(
                deck, config, seed, known=True, policy=policy, budget_ms=100.0,
                width=4, branching=None, score_tiebreak=1e-3, sim_factory=factory,
            )
            sim = instances[-1]
        # pre_states 与 leaf_states 一一对应（turns_left>0 的回合末才记录快照）
        assert len(sim.pre_states) >= len(sim.leaf_states)
        game_bad = False
        for pre, leaf in zip(sim.pre_states, sim.leaf_states):
            expected = end_turn_state(pre)
            total_leaves += 1
            if pre.stance_state.stance == "save" and expected.stance_state.stance != "save":
                release_boundaries += 1
            for f in fields(expected):
                a, b = getattr(leaf, f.name), getattr(expected, f.name)
                if a != b:
                    mismatch_fields[f.name] += 1
                    game_bad = True
                    if mismatch_fields[f.name] <= 2:
                        print(f"  seed={seed} field {f.name}: snap={a!r} expected={b!r}")
        if game_bad:
            mismatch_games += 1
    print(f"\n{games} games policy={policy}: leaves={total_leaves} save-release-boundaries={release_boundaries}")
    print(f"mismatch games {mismatch_games}/{games}")
    print("per-field mismatch:", dict(mismatch_fields) or "NONE (fully equivalent)")


if __name__ == "__main__":
    main()
