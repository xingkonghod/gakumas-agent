import sys
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import eval_expectimax as ee
from gkagent.sim.expectimax import AnalyticLeafValue, _top_turn_plans, state_from_sim
from gkagent.sim.lesson import LessonSim
import random
deck, config = ee.build_deck("small"), ee.make_config("small")
sim = LessonSim(deck, config, rng_seed=0)
state = state_from_sim(sim)
model = AnalyticLeafValue(sigma=60)
print("hand:", [(c.name, c.cost, c.score) for c in sim.hand])
print("stamina", sim.stamina, "turns", sim.turns_left, "plays", sim.plays_this_turn)
plans = _top_turn_plans(state, model, limit=20, rng=random.Random(0), clock=__import__("time").perf_counter, deadline=__import__("time").perf_counter()+5)
for p in sorted(plans, key=lambda x: x.utility, reverse=True):
    print(f"V={p.utility:.3f} seq={list(p.sequence)} endscore={p.end_state.score} endstamina={p.end_state.stamina} endplays={p.end_state.plays_left} endturns={p.end_state.turns_left}")
