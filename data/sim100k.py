import sys, time
from concurrent.futures import ProcessPoolExecutor
sys.stdout.reconfigure(encoding="utf-8")

_G = {}

def _init():
    import sys
    sys.path.insert(0, r"D:\Games\gakumas-agent\src"); sys.path.insert(0, r"D:\Games\gakumas-agent\scripts")
    import sim_produce as sp
    _G["deck"] = [sp._spec_from_row(r) for r in sp.build_deck(rich=True)]
    _G["pool"] = [sp._spec_from_row(r) for r in sp.build_pool(rich=True)]

def run_batch(seeds):
    from gkagent.sim.produce import ProduceConfig, ProduceSim, strategy_optimal, eval_value
    deck, pool = _G["deck"], _G["pool"]
    out = []
    for seed in seeds:
        sim = ProduceSim(deck, config=ProduceConfig(reward_pick="best", schedule_source="official"), rng_seed=seed)
        sim.reward_pool = pool
        r = sim.run(strategy_optimal)
        t = sum(r.attrs)
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"): rank = row["exam"]["rank"]; break
        out.append((t, rank, eval_value(t, rank, t*2)))
    return out

if __name__ == "__main__":
    t0 = time.time(); N = 100000; CH = 500
    batches = [list(range(i, min(i+CH, N))) for i in range(0, N, CH)]
    rows = []
    with ProcessPoolExecutor(max_workers=20, initializer=_init) as ex:
        for part in ex.map(run_batch, batches):
            rows.extend(part)
    ts = sorted(r[0] for r in rows); es = sorted(r[2] for r in rows)
    from collections import Counter
    ranks = Counter(r[1] for r in rows)
    print(f"跑了 {len(rows)} 局，{time.time()-t0:.1f}s")
    print(f"三维: min={ts[0]} P10={ts[N//10]} P50={ts[N//2]} P90={ts[N*9//10]} P99={ts[N*99//100]} max={ts[-1]}")
    print(f"评价点: P10={es[N//10]} P50={es[N//2]} P90={es[N*9//10]} P99={es[N*99//100]} max={es[-1]}")
    print(f"名次分布: {dict(sorted(ranks.items()))}")
    for thr, name in ((4500,"C+"),(6000,"B"),(8000,"B+"),(10000,"A")):
        print(f"  {name}: {sum(1 for e in es if e>=thr)/len(es)*100:.1f}%")
