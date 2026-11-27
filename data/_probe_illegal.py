import sys
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import sim_engine_ab as ab
import sim_produce as sp
from gkagent.sim.produce import ProduceConfig, ProduceSim, strategy_from_params
from gkagent.policy.lesson import LessonPolicy
from gkagent.data.card_table import CardTable

deck_raw = sp.build_deck(rich=True); pool_raw = sp.build_pool(rich=True)
pool = [sp._spec_from_row(r) for r in pool_raw]
table = CardTable()
policy = LessonPolicy(engine="expectimax", params={"expectimax_budget_ms": 50.0})
policy._table = table
deck = [sp._spec_from_row(r) for r in deck_raw]
sim = ProduceSim(deck, config=ProduceConfig(reward_pick="best"), rng_seed=9000)
sim.reward_pool = pool
bad = []
def adapter(inner):
    st = ab._lesson_state(inner, exam=False)
    a = policy.decide(st)
    legal = [i for i in inner.legal_actions() if i is not None]
    if a.kind == "card" and a.index not in legal:
        bad.append({"kind": a.kind, "idx": a.index, "legal": legal,
                    "sim_plays": inner.plays_this_turn, "pol_plays": policy._plays_this_turn,
                    "reason": a.reason[:80], "turns_left": inner.turns_left,
                    "stamina": inner.stamina, "cards": [(i, c.name.split("#")[0], c.cost) for i, c in enumerate(inner.hand)]})
    if a.kind == "card" and a.index is not None and a.index in legal:
        policy.note_play(a.card); return a.index
    return None
sim.training_policy_fn = adapter
try:
    res = sim.run(strategy_from_params(ab.WARM_STRATEGY)); print("total", sum(res.attrs))
except Exception as exc:
    print("aborted:", repr(exc))
print("illegal", len(bad))
for row in bad[:4]: print(row)
