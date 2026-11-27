import sys, math, statistics as stt
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import eval_known_draw as ekd, eval_expectimax as ee

deck, config = ee.build_deck("small"), ee.make_config("small")
N = 60

def run(policy, **kw):
    return [ekd.play(deck, config, seed, known=False, policy=policy, budget_ms=200, width=4, **kw) for seed in range(N)]

def stats(rows):
    scores=[r["score"] for r in rows]
    return {"mean":sum(scores)/len(scores), "p50":ekd._percentile(scores,0.5),
            "clear":sum(r["clear"] for r in rows)/len(rows),
            "perfect":sum(r["perfect"] for r in rows)/len(rows)}

def ci(deltas):
    n=len(deltas); m=sum(deltas)/n
    if n<2: return m,0.0
    sd=stt.stdev(deltas)
    half=1.96*sd/math.sqrt(n)
    return m, half

within = run("within")
within_tb = run("within", score_tiebreak=1e-3)
beam0 = run("beam")
beam_tb = run("beam", score_tiebreak=1e-3)
beam_tb_br = run("beam", score_tiebreak=1e-3, branching=10)

for name, rows in (("within",within),("within+tb",within_tb),("beam",beam0),("beam+tb",beam_tb),("beam+tb+br10",beam_tb_br)):
    s=stats(rows); print(f"{name:<14} mean={s['mean']:6.1f} p50={s['p50']:5.0f} clear={s['clear']*100:5.1f}% perfect={s['perfect']*100:5.1f}%")

base=[r["score"] for r in beam0]
for name, rows in (("beam+tb",beam_tb),("beam+tb+br10",beam_tb_br)):
    deltas=[r["score"]-b for r,b in zip(rows,base)]
    m,h=ci(deltas)
    print(f"配对 {name} - beam: Δmean={m:+.1f} 95%CI[{m-h:+.1f},{m+h:+.1f}] 胜/平/负={sum(d>0 for d in deltas)}/{sum(d==0 for d in deltas)}/{sum(d<0 for d in deltas)}")
deltas=[r["score"]-b for r,b in zip(within_tb,[r["score"] for r in within])]
m,h=ci(deltas); print(f"配对 within+tb - within: Δmean={m:+.1f} 95%CI[{m-h:+.1f},{m+h:+.1f}]")
# beam 最优 vs within 的差距
best=max(stats(beam_tb_br)["mean"], stats(beam_tb)["mean"])
print(f"beam最佳 mean={best:.1f} vs within={stats(within)['mean']:.1f} → {best-stats(within)['mean']:+.1f} ({(best/stats(within)['mean']-1)*100:+.1f}%)")
