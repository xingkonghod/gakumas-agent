"""Probe (not committed): does GNRPA config (levels/iterations/stabilization/transitions) find
better routes from the SAME state?  This decides the "search quality" lever (not sample count).

For each target problem: walk v4ref to lock, snapshot, then for each config run K seeds and report
best/mean terminal score + cost. Paired on identical states -> direct comparison.
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
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
from GakumasCLI.native import tail_native as TN  # noqa: E402
from GakumasCLI.native.native_search import NativeSearch  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r
seeds_doc = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))

TARGETS = [("AS-AXME8QK2", 1409380188), ("AS-WDKWQYW5", 988313260),
           ("AS-BZXB28YJ", 1875523773), ("AS-3EW6E6HV", 153762096),
           ("AS-YSNBNDV4", 1381267152), ("AS-5KZSXANK", 448199597)]
SNAP_TURN = 4
K = 3
CONFIGS = [
    ("base_l2i8s3", dict(levels=2, iterations=8, stabilization=3, transitions=500_000)),
    ("l3i8s3", dict(levels=3, iterations=8, stabilization=3, transitions=500_000)),
    ("l3i4s3", dict(levels=3, iterations=4, stabilization=3, transitions=500_000)),
    ("l2i8s5", dict(levels=2, iterations=8, stabilization=5, transitions=500_000)),
    ("l2i16s3", dict(levels=2, iterations=16, stabilization=3, transitions=500_000)),
    ("l2i8s3_2m", dict(levels=2, iterations=8, stabilization=3, transitions=2_000_000)),
    ("l3i8s3_2m", dict(levels=3, iterations=8, stabilization=3, transitions=2_000_000)),
]
OUT = ROOT / "out" / "_v5_engine_probe.json"


def replay(session, route):
    c = session.clone()
    try:
        for a in route:
            if c.finished:
                break
            c.step(tuple(a), observe=False)
    except Exception:  # noqa: BLE001
        return None
    return int(c.state.score) if c.finished else None


def walk(pid, seed):
    lo = expand_loadout(saves[pid]["loadout"])
    algo = V5.ExSeedV5Algo(procs=16, report=0, starts=4, starts_hi=6, lock_trans=2000000,
                           step_trans=500000, scan_wait_mode="done", vote_sec_cap=0.8, rescan_open=1,
                           waves=1, pool_threads=1, pool_threads_hi=1, root_scan=0)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, 10.0, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    algo.begin(ctx)
    n = 0
    while not ref.finished and n < 300:
        ctx.obs = ref.obs()
        d = algo.decide(ctx)
        g = algo.g
        if g.state == "locked" and g.mirror is not None and int(ctx.obs["exam"]["turn"]) >= SNAP_TURN:
            return g.mirror.session.clone(), int(ctx.obs["exam"]["turn"]), g.lock_turn
        ref.step(d.action)
        n += 1
    return None


def main():
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    ns = NativeSearch(engine.native()[0])
    for pid, seed in TARGETS:
        key = f"{pid}/{seed}"
        if key in res:
            continue
        t0 = time.perf_counter()
        snap = walk(pid, seed)
        if snap is None:
            print(f"{key}: no lock", flush=True)
            continue
        session, turn, lock_turn = snap
        print(f"\n=== {key} snapshot turn={turn} lock={lock_turn} walk={time.perf_counter()-t0:.0f}s ===",
              flush=True)
        entry = {"turn": turn, "lock_turn": lock_turn, "cfgs": {}}
        for name, p in CONFIGS:
            scores, times, status = [], [], []
            for i in range(K):
                sd = 182 + 7919 * i
                t1 = time.perf_counter()
                try:
                    path, st = ns.policy_search(session, transitions=p["transitions"], deadline=12.0,
                                                seed=sd, variant="gnrpa", levels=p["levels"],
                                                iterations=p["iterations"],
                                                stabilization=p["stabilization"], prior=None)
                except Exception as e:  # noqa: BLE001
                    print(f"  {name} sd{i} REFUSED {type(e).__name__}: {e}", flush=True)
                    continue
                dt = time.perf_counter() - t1
                times.append(dt)
                status.append(int(st.get("status", -1)))
                if path:
                    scores.append(replay(session, path))
            best = max(scores) if scores else None
            entry["cfgs"][name] = {"params": p, "scores": scores, "best": best,
                                   "mean": round(statistics.mean(scores)) if scores else None,
                                   "secs": round(statistics.mean(times), 2) if times else None,
                                   "status": status}
            print(f"  {name:<12} best={best if best is None else format(best, ',')} "
                  f"mean={entry['cfgs'][name]['mean']} secs={entry['cfgs'][name]['secs']} "
                  f"scores={scores}", flush=True)
        res[key] = entry
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved", OUT)


if __name__ == "__main__":
    main()