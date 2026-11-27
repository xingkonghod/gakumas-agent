"""Probe (not committed): why did the v5 parallel search produce zero accepted routes?"""
import importlib.util
import json
import sys
import time
import traceback
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
    turn = int(ctx.obs["exam"]["turn"])
    meta = {k: v for k, v in d.meta.items() if k in ("mode", "pool_searches", "pool_threads",
                                                     "search_why", "target", "ms", "lock_turn", "tail_status")}
    print(f"step{n:02d} turn={turn} state={g.state} lock={g.lock_turn} ms={meta.get('ms')} "
          f"meta={meta}", flush=True)
    ref.step(d.action)
    n += 1
    if g.state == "locked" and g.mirror is not None:
        session = g.mirror.session
        print("  locked -> manual probe of parallel task", flush=True)
        clone = session.clone()
        try:
            path, st = algo.ns.policy_search(clone, transitions=500_000, deadline=3.0, seed=182,
                                             variant="gnrpa", stabilization=3, prior=None)
            print(f"  clone search OK path_len={len(path)} status={st.get('status')} "
                  f"score={st.get('best_score')} exp={st.get('expansions')}", flush=True)
        except Exception:  # noqa: BLE001
            print("  clone search FAILED:", flush=True)
            traceback.print_exc()
        try:
            clone2 = session.clone()
            clone2.step(tuple(ctx.obs["legal"][0]), observe=False)
            path, st = algo.ns.policy_search(clone2, transitions=500_000, deadline=3.0, seed=182,
                                             variant="gnrpa", stabilization=3, prior=None)
            print(f"  stepped-clone search OK path_len={len(path)} status={st.get('status')}", flush=True)
        except Exception:  # noqa: BLE001
            print("  stepped-clone search FAILED:", flush=True)
            traceback.print_exc()
        break
print("done")