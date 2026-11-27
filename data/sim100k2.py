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
    out = []
    for seed in seeds:
        sim = ProduceSim(_G["deck"], config=ProduceConfig(reward_pick="best", schedule_source="official"), rng_seed=seed)
        sim.reward_pool = _G["pool"]
        r = sim.run(strategy_optimal)
        t = sum(r.attrs); ex = sim.last_exam or {}
        out.append((t, ex.get("rank", 3), ex.get("score", 0), eval_value(t, ex.get("rank", 3), ex.get("score", 0))))
    return out
if __name__ == "__main__":
    t0 = time.time(); N = 100000; CH = 500
    batches = [list(range(i, min(i+CH, N))) for i in range(0, N, CH)]
    rows = []
    with ProcessPoolExecutor(max_workers=20, initializer=_init) as ex:
        for part in ex.map(run_batch, batches): rows.extend(part)
    ts = sorted(r[0] for r in rows); es = sorted(r[3] for r in rows)
    from collections import Counter
    print(f"{N} 局 / {time.time()-t0:.1f}s")
    print(f"三维: P10 {ts[N//10]} P50 {ts[N//2]} P90 {ts[N*9//10]} max {ts[-1]}")
    print(f"评价点: P10 {es[N//10]} P50 {es[N//2]} P90 {es[N*9//10]} P99 {es[N*99//100]} max {es[-1]}")
    print(f"名次: {dict(sorted(Counter(r[1] for r in rows).items()))}")
    for thr,name in ((4500,"C+"),(6000,"B"),(8000,"B+"),(10000,"A"),(13000,"S")):
        print(f"  {name} {sum(1 for e in es if e>=thr)/N*100:.2f}%")
