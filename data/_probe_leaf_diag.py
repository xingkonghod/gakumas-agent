import sys
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import eval_expectimax as ee, eval_known_draw as ekd
from gkagent.sim.expectimax import AnalyticLeafValue, search_beam, state_from_sim
from gkagent.sim.lesson import LessonSim

deck, config = ee.build_deck("small"), ee.make_config("small")
model = AnalyticLeafValue(sigma=60)
for seed in (0,1,2):
    sim = LessonSim(deck, config, rng_seed=seed)
    print(f"=== seed {seed} deck={len(deck)} turns={config.turns} clear={config.target_clear} perfect={config.target_perfect}")
    turn = 0
    while not sim.done:
        actions = sim.legal_actions()
        if actions == [None]:
            sim.step(None); continue
        state = state_from_sim(sim)
        mu, sigma = model.predict(state)
        res = search_beam(state, model, width=4, deadline_ms=200)
        print(f" T{sim.turns_left} score={sim.score} stamina={sim.stamina} hand={[c.name for c in sim.hand]} | leaf mu={mu:.1f} V={res.utility:.3f} plan={list(res.sequence)} first={res.card.name if res.card else None}")
        ekd._execute_plan(sim, list(res.sequence))
        turn += 1
        if turn > 20: break
    print(f" final score={sim.score} tier={sim.reward_tier}")
