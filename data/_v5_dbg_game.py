"""Probe (not committed): full-game per-decision meta for one config (why is the pool empty?)."""
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
SUB_V5 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v5"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V5 = _load("algo_exv5", SUB_V5 / "algo.py")
from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402
import random  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

pid = sys.argv[1] if len(sys.argv) > 1 else "AS-WDKWQYW5"
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 988313260
cfg = sys.argv[3] if len(sys.argv) > 3 else "v4ref"
P = {"v4ref": dict(waves=1, pool_threads=1, pool_threads_hi=1),
     "par": dict(waves=0, pool_threads=2, pool_threads_hi=4),
     "rs": dict(waves=0, pool_threads=2, pool_threads_hi=4, root_scan=1),
     "rsdeep": dict(waves=0, pool_threads=2, pool_threads_hi=4, root_scan=1,
                    deep_trans=2000000, deep_waves=1)}[cfg]
lo = expand_loadout(saves[pid]["loadout"])
algo = V5.ExSeedV5Algo(procs=16, report=0, starts=4, starts_hi=6, lock_trans=2000000,
                       step_trans=500000, scan_wait_mode="done", vote_sec_cap=0.8, rescan_open=1, **P)
ref = Referee(lo, seed)
ctx = Ctx(ref, ref.loadout_public, 10.0, random.Random(f"{pid}/{seed}/algo"),
          random.Random(f"{pid}/{seed}/world"), algo, seed)
ctx.obs = ref.obs()
algo.begin(ctx)
t0 = time.perf_counter()
n = 0
while not ref.finished and n < 300:
    ctx.obs = ref.obs()
    d = algo.decide(ctx)
    g = algo.g
    m = d.meta
    print(f"step{n:02d} turn={ctx.obs['exam']['turn']} {g.state:<10} lock={g.lock_turn} "
          f"ms={m.get('ms')} mode={m.get('mode')} n={m.get('pool_searches')} "
          f"st={m.get('pool_status')} adopted={m.get('pool_adopted')} bad={m.get('pool_bad')} "
          f"tail={m.get('tail_status')} why={m.get('search_why') or m.get('pool_err') or ''}",
          flush=True)
    ref.step(d.action)
    n += 1
print(f"\nscore={int(ref.score):,} wall={time.perf_counter()-t0:.0f}s counts={g.counts} "
      f"pool={algo.pool.stats}")
try:
    if algo._ex is not None:
        algo._ex[1].shutdown(wait=False)
except Exception:  # noqa: BLE001
    pass