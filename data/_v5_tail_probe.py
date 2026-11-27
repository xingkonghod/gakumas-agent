"""Probe (not committed): is the exact tail search better than GNRPA when started *early*?

From a mid-game snapshot, compare
  * GNRPA restarts (500k transitions, several seeds)  -> best terminal score
  * tail_exact (node_cap 20M, seconds 2/4/8, threads 4/8) -> best terminal score
If the exact tail wins from turn 3-4, "start the exact search earlier" is a real search lever.
"""
from __future__ import annotations

import importlib.util
import json
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
seeds_doc = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

TARGETS = ["AS-WDKWQYW5", "AS-AXME8QK2", "AS-BZXB28YJ", "AS-QV6QCSN9"]
snap_turn = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT = ROOT / "out" / "_v5_tail_probe.json"


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


def walk(pid, seed, budget=10.0):
    lo = expand_loadout(saves[pid]["loadout"])
    algo = V5.ExSeedV5Algo(procs=16, report=0, starts=4, starts_hi=6, lock_trans=2000000,
                           step_trans=500000, scan_wait_mode="done", vote_sec_cap=0.8, rescan_open=1,
                           waves=1, pool_threads=1)
    ref = Referee(lo, seed)
    import random
    ctx = Ctx(ref, ref.loadout_public, budget, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    algo.begin(ctx)
    n = 0
    while not ref.finished and n < 300:
        ctx.obs = ref.obs()
        d = algo.decide(ctx)
        g = algo.g
        if g.state == "locked" and g.mirror is not None and int(ctx.obs["exam"]["turn"]) >= snap_turn:
            return g.mirror.session.clone(), int(ctx.obs["exam"]["turn"]), g.lock_turn, int(ref.score)
        ref.step(d.action)
        n += 1
    return None


def tail(session, seconds, threads, node_cap=20_000_000):
    nat = engine.native()[0]
    TN._bind(nat)
    t0 = time.perf_counter()
    path, score, st = TN.tail_exact(session, seconds=seconds, nat=nat, threads=threads,
                                    node_cap=node_cap, tt_capacity=1 << 23)
    dt = time.perf_counter() - t0
    return {"score": int(score), "status": st.get("status"), "nodes": st.get("nodes"),
            "tt_hits": st.get("tt_hits"), "sec": round(dt, 2), "path_len": len(path)}


def gnrpa(session, trans, secs, sd, ns):
    try:
        path, st = ns.policy_search(session, transitions=trans, deadline=secs, seed=sd,
                                    variant="gnrpa", stabilization=3, prior=None)
    except Exception as e:  # noqa: BLE001
        return {"score": None, "why": f"{type(e).__name__}: {e}"}
    if not path:
        return {"score": None, "status": st.get("status")}
    return {"score": replay(session, path), "sec": round(float(st.get("elapsed_seconds") or 0), 2),
            "exp": st.get("expansions")}


def main():
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    ns = NativeSearch(engine.native()[0])
    for pid in TARGETS:
        rows = seeds_doc["problems"].get(pid) or []
        if not rows:
            continue
        row = rows[0]
        key = f"{pid}/{row['seed']}"
        if key in res:
            continue
        print(f"\n=== {key} snap_turn>={snap_turn} ===", flush=True)
        snap = walk(pid, int(row["seed"]))
        if snap is None:
            print("  no lock")
            continue
        session, turn, lock_turn, played = snap
        print(f"  snapshot turn={turn} lock={lock_turn} score_so_far={played:,}", flush=True)
        entry = {"turn": turn, "lock_turn": lock_turn, "score_so_far": played, "gnrpa": [], "tail": []}
        for i in range(8):
            r = gnrpa(session, 500_000, 4.0, 182 + 7919 * i, ns)
            entry["gnrpa"].append(r)
            print(f"   gnrpa sd{i}: {r}", flush=True)
        for threads in (4, 8):
            for seconds in (2.0, 4.0, 8.0):
                r = tail(session, seconds, threads)
                entry["tail"].append({"threads": threads, "want_sec": seconds, **r})
                print(f"   tail t{threads}/{seconds}s: {r}", flush=True)
        g = [x["score"] for x in entry["gnrpa"] if x.get("score")]
        t = [x["score"] for x in entry["tail"] if x.get("score")]
        print(f"  BEST gnrpa={max(g) if g else None:,} tail={max(t) if t else None:,}", flush=True)
        res[key] = entry
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved", OUT)


if __name__ == "__main__":
    main()