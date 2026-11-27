"""Probe (not committed): GNRPA search-quality grid on cached mid-game snapshots.

Snapshots are pickled native sessions (walk v4ref to lock+turn>=SNAP_TURN once, reuse afterwards),
so each config costs only the searches. Reports per-problem best/mean and pooled stats.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import random
import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
SUB_V5 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v5"
SNAP = ROOT / "out" / "_v5_snaps"
SNAP.mkdir(exist_ok=True)


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
from GakumasCLI.native.native_search import NativeSearch  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

TARGETS = [("AS-AXME8QK2", 1409380188), ("AS-WDKWQYW5", 988313260),
           ("AS-BZXB28YJ", 1875523773), ("AS-3EW6E6HV", 153762096),
           ("AS-YSNBNDV4", 1381267152), ("AS-5KZSXANK", 448199597),
           ("AS-PPHWPMPP", 1052677781), ("AS-B8ZWDS3J", 1710874307)]
SNAP_TURN = 4
K = 4
OUT = ROOT / "out" / "_v5_engine_grid.json"
CONFIGS = []
for lv in (2, 3, 4):
    for it in (8, 16):
        for st in (3, 5):
            CONFIGS.append((f"l{lv}i{it}s{st}", dict(levels=lv, iterations=it, stabilization=st,
                                                     transitions=500_000)))
CONFIGS.append(("l3i16s3_1m", dict(levels=3, iterations=16, stabilization=3, transitions=1_000_000)))
CONFIGS.append(("l4i16s3_1m", dict(levels=4, iterations=16, stabilization=3, transitions=1_000_000)))


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
        sp = SNAP / f"{pid}_{seed}.pkl"
        key = f"{pid}/{seed}"
        if key in res:
            continue
        if sp.exists():
            session, turn, lock_turn = pickle.loads(sp.read_bytes())
        else:
            t0 = time.perf_counter()
            snap = walk(pid, seed)
            if snap is None:
                print(f"{key}: no lock", flush=True)
                continue
            session, turn, lock_turn = snap
            try:
                sp.write_bytes(pickle.dumps(snap))
            except Exception as e:  # noqa: BLE001
                print("  snapshot pickle failed:", e, flush=True)
            print(f"[{key}] snapshot turn={turn} lock={lock_turn} walk={time.perf_counter()-t0:.0f}s",
                  flush=True)
        entry = {"turn": turn, "lock_turn": lock_turn, "cfgs": {}}
        for name, p in CONFIGS:
            scores, times, status = [], [], []
            for i in range(K):
                sd = 182 + 7919 * i
                t1 = time.perf_counter()
                try:
                    s2 = pickle.loads(pickle.dumps(session))     # fresh core per search
                    path, st = ns.policy_search(s2, transitions=p["transitions"], deadline=12.0,
                                                seed=sd, variant="gnrpa", levels=p["levels"],
                                                iterations=p["iterations"],
                                                stabilization=p["stabilization"], prior=None)
                except Exception as e:  # noqa: BLE001
                    print(f"  {name} sd{i} REFUSED {type(e).__name__}: {e}", flush=True)
                    continue
                times.append(time.perf_counter() - t1)
                status.append(int(st.get("status", -1)))
                if path:
                    sc = replay(session, path)
                    if sc is not None:
                        scores.append(sc)
            best = max(scores) if scores else None
            entry["cfgs"][name] = {"params": p, "scores": scores, "best": best,
                                   "mean": round(statistics.mean(scores)) if scores else None,
                                   "secs": round(statistics.mean(times), 2) if times else None,
                                   "status": status}
            print(f"  {key} {name:<12} best={best if best is None else format(best, ',')} "
                  f"mean={entry['cfgs'][name]['mean']} secs={entry['cfgs'][name]['secs']}", flush=True)
        res[key] = entry
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved", OUT)


if __name__ == "__main__":
    main()