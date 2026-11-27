import sys, statistics
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import eval_known_draw as ekd, eval_expectimax as ee

deck, config = ee.build_deck("small"), ee.make_config("small")
for policy in ("within", "beam"):
    print(f"--- {policy} ---")
    for sigma in (10, 15, 20, 25, 30, 40, 60, 80):
        rows = []
        for seed in range(40):
            row = ekd.play(deck, config, seed, known=False, policy=policy, sigma=sigma, width=4, budget_ms=100)
            rows.append(row)
        st = ekd.summarize(rows)
        print(f"sigma={sigma:>4} mean={st['mean']:6.1f} p50={st['p50']:6.0f} p90={st['p90']:6.0f} clear={st['clear_rate']*100:5.1f}% perfect={st['perfect_rate']*100:5.1f}%")
