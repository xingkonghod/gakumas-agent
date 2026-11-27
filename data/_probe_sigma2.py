import sys
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import eval_expectimax as ee, eval_known_draw as ekd
from gkagent.sim.expectimax import AnalyticLeafValue, expectimax_with_stats, state_from_sim
from gkagent.sim.lesson import LessonSim
deck, config = ee.build_deck("small"), ee.make_config("small")
sim = LessonSim(deck, config, rng_seed=0)
state = state_from_sim(sim)
for sigma in (10.0, 30.0, 60.0):
    m = AnalyticLeafValue(sigma=sigma)
    mu, s = m.predict(state)
    res = expectimax_with_stats(state, m, time_budget_ms=100)
    print(f"sigma={sigma} mu={mu:.1f} pred_sigma={s} util_leaf={m.utility(state):.3f} best={res.card.name if res.card else None} util={res.utility:.3f}")
    for name, val in res.actions:
        print(f"   {name}: {val:.3f}")
