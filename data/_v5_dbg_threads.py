"""Probe (not committed): is parallel GNRPA on cloned sessions safe? capture worker exceptions."""
import importlib.util
import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
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

pid, seed = "AS-WDKWQYW5", 988313260
lo = expand_loadout(saves[pid]["loadout"])
algo = V5.ExSeedV5Algo(procs=16, report=0, starts=4, starts_hi=6, lock_trans=2000000,
                       step_trans=500000, scan_wait_mode="done", vote_sec_cap=0.8, rescan_open=1,
                       waves=1, pool_threads=1)
ref = Referee(lo, seed)
ctx = Ctx(ref, ref.loadout_public, 10.0, random.Random(f"{pid}/{seed}/algo"),
          random.Random(f"{pid}/{seed}/world"), algo, seed)
ctx.obs = ref.obs()
algo.begin(ctx)
n = 0
while not ref.finished and n < 60:
    ctx.obs = ref.obs()
    d = algo.decide(ctx)
    g = algo.g
    ref.step(d.action)
    n += 1
    if g.state == "locked" and g.mirror is not None:
        break
session = g.mirror.session
print("locked at turn", g.lock_turn, flush=True)

results = {}


def job(k, trans=500_000, sec=3.0):
    sd = 182 + 7919 * k
    try:
        c = session.clone()
        t0 = time.perf_counter()
        path, st = algo.ns.policy_search(c, transitions=trans, deadline=sec, seed=sd,
                                        variant="gnrpa", stabilization=3, prior=None)
        dt = time.perf_counter() - t0
        results[k] = ("ok", len(path), st.get("status"), st.get("best_score"), round(dt, 2))
    except Exception:  # noqa: BLE001
        results[k] = ("ERR", traceback.format_exc().strip().splitlines()[-1])


print("--- serial ---", flush=True)
for k in range(4):
    job(k)
print(results, flush=True)
results.clear()
print("--- parallel 4 threads ---", flush=True)
t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(job, range(4)))
print(f"wall={time.perf_counter()-t0:.2f}s", results, flush=True)
results.clear()
print("--- parallel 4 threads, clone in worker ---", flush=True)


def job2(k):
    try:
        c = session.clone()
        path, st = algo.ns.policy_search(c, transitions=500_000, deadline=3.0, seed=182 + 7919 * k,
                                        variant="gnrpa", stabilization=3, prior=None)
        results[k] = ("ok", len(path), st.get("status"), st.get("best_score"))
    except Exception:  # noqa: BLE001
        results[k] = ("ERR", traceback.format_exc().strip().splitlines()[-1])


t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(job2, range(4)))
print(f"wall={time.perf_counter()-t0:.2f}s", results, flush=True)
print("done")