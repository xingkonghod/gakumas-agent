import sys
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import eval_expectimax as ee, eval_known_draw as ekd
from gkagent.sim.expectimax import AnalyticLeafValue, search_beam, state_from_sim, expectimax_with_stats
from gkagent.sim.lesson import LessonSim, greedy_policy
deck, config = ee.build_deck("small"), ee.make_config("small")
model = AnalyticLeafValue(sigma=60)

def count_plays(sim):
    return sum(1 for row in sim.trace if row.get("plays"))

# within
sim = LessonSim(deck, config, rng_seed=0)
while not sim.done:
    actions = sim.legal_actions()
    if actions == [None]: sim.step(None); continue
    state = state_from_sim(sim)
    res = expectimax_with_stats(state, model, time_budget_ms=100)
    idx = next((i for i,c in enumerate(sim.hand) if c == res.card), None)
    if idx is None or idx not in actions: idx = greedy_policy(sim)
    sim.step(idx)
print("within score", sim.score, "plays", count_plays(sim), "trace", [(r["turns_left"], r["plays"], r["score"]) for r in sim.trace])
sim2 = LessonSim(deck, config, rng_seed=0)
while not sim2.done:
    actions = sim2.legal_actions()
    if actions == [None]: sim2.step(None); continue
    state = state_from_sim(sim2)
    res = search_beam(state, model, width=4, deadline_ms=200)
    print("beam plan", list(res.sequence), "V", round(res.utility,3))
    ekd._execute_plan(sim2, list(res.sequence))
print("beam score", sim2.score, "plays", count_plays(sim2), "trace", [(r["turns_left"], r["plays"], r["score"]) for r in sim2.trace])
