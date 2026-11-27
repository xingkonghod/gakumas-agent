import sys
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import eval_expectimax as ee
from gkagent.sim.expectimax import AnalyticLeafValue, search_beam, state_from_sim
from gkagent.sim.lesson import LessonSim, greedy_policy

class Wrapped:
    def __init__(self, eps=1e-3, sigma=60.0):
        self.base = AnalyticLeafValue(sigma=sigma); self.eps = eps
    def predict(self, s): return self.base.predict(s)
    def utility(self, s):
        base = self.base.utility(s); mu,_ = self.base.predict(s)
        scale = max(float(getattr(s,'perfect',0) or getattr(s,'clear',0) or 1),1.0)
        return base + self.eps*(float(s.score)+mu)/scale

def play_beam(deck, config, seed, *, width, branching, budget, eps):
    sim = LessonSim(deck, config, rng_seed=seed)
    model = Wrapped(eps=eps)
    import math
    from gkagent.sim.expectimax import reshuffle_from_sim
    while not sim.done:
        acts = sim.legal_actions()
        if acts == [None]: sim.step(None); continue
        st = state_from_sim(sim)
        res = search_beam(st, model, width=width, branching=branching, deadline_ms=budget)
        seq = list(res.sequence)
        for name in seq:
            acts = sim.legal_actions()
            if not sim.hand or acts == [None]: break
            idx = next((i for i,c in enumerate(sim.hand) if c.name == name), None)
            if idx is None or idx not in acts: idx = greedy_policy(sim)
            if idx is None: break
            sim.step(idx)
        if not sim.done and sim.legal_actions() != [None]: sim.step(None)
    return sim.score, sim.reward_tier

deck, config = ee.build_deck("small"), ee.make_config("small")
for width in (4, 8):
  for branching in (3, 6, 10):
    for budget in (200.0, 500.0):
        scores=[]; tiers=[]
        for seed in range(30):
            s,t = play_beam(deck, config, seed, width=width, branching=branching, budget=budget, eps=1e-3)
            scores.append(s); tiers.append(t)
        mean=sum(scores)/len(scores); p50=sorted(scores)[len(scores)//2]
        clear=sum(1 for t in tiers if t>=1)/len(tiers); perfect=sum(1 for t in tiers if t>=2)/len(tiers)
        print(f"w={width} branch={branching:>2} budget={budget:>4.0f} mean={mean:6.1f} p50={p50:5.0f} clear={clear*100:5.1f}% perfect={perfect*100:5.1f}%")
