import sys
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import eval_known_draw as ekd, eval_expectimax as ee
from gkagent.sim.expectimax import AnalyticLeafValue

class Wrapped:
    def __init__(self, eps, sigma=60.0):
        self.base = AnalyticLeafValue(sigma=sigma); self.eps = eps
    def predict(self, s):
        return self.base.predict(s)
    def utility(self, s):
        base = self.base.utility(s)
        mu, _ = self.base.predict(s)
        scale = max(float(getattr(s, 'perfect', 0) or getattr(s, 'clear', 0) or 1), 1.0)
        return base + self.eps * (float(s.score) + mu) / scale

deck, config = ee.build_deck("small"), ee.make_config("small")
orig = ekd.AnalyticLeafValue
for eps in (0.0, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2):
    ekd.AnalyticLeafValue = (lambda _eps=eps, sigma=60.0: Wrapped(_eps, sigma))
    for policy in ("within", "beam"):
        rows = [ekd.play(deck, config, seed, known=False, policy=policy, sigma=60.0, width=4, budget_ms=100) for seed in range(40)]
        st = ekd.summarize(rows)
        print(f"eps={eps:<6} {policy:<6} mean={st['mean']:6.1f} p50={st['p50']:6.0f} clear={st['clear_rate']*100:5.1f}% perfect={st['perfect_rate']*100:5.1f}% fb={st['fallbacks']}")
    ekd.AnalyticLeafValue = orig
