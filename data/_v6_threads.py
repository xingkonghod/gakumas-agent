"""Probe (not committed, OPENING_v6 ③): native GNRPA throughput vs concurrency + scan starvation.

Measures, on real locked mid-game states (dev seeds):
  * per-search elapsed for transitions=500k / 2M at concurrency 1/2/4/8/12/16/20/24 clones
    (each clone gets its own core tables -> exactly the production parallel path)
  * aggregate transitions/s and truncation rate (status != 0)
  * the same at concurrency 4/8 while 16 CPU-burner processes run (emulates pre-lock seed scan procs=16)

Output: out/_v6_threads.json (+ log lines).
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
SUB_V5 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v5"
OUT = ROOT / "out" / "_v6_threads.json"


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

DL = ROOT / "data/bench_local/gkbench_dl/hif"
seeds_doc = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

# deep final (12T) and shallow final states
TARGETS = ["AS-WDKWQYW5", "AS-5KZSXANK"]
SNAP_TURNS = [4, 8]
CONC = [1, 2, 4, 8, 12, 16, 20, 24]
TRANS = 500_000
REPEATS = 2


def walk(pid, seed, snap_turn, budget=10.0):
    lo = expand_loadout(saves[pid]["loadout"])
    algo = V5.ExSeedV5Algo(procs=16, report=0, starts=4, starts_hi=6, lock_trans=2000000,
                           step_trans=500000, scan_wait_mode="done", vote_sec_cap=0.8, rescan_open=1,
                           waves=1, pool_threads=1)
    ref = Referee(lo, seed)
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
            return g.mirror.session.clone(), int(ctx.obs["exam"]["turn"]), g.lock_turn
        ref.step(d.action)
        n += 1
    return None


def one(ns, session, k, trans):
    sd = 182 + 7919 * k
    try:
        c = session.clone()
        t0 = time.perf_counter()
        path, st = ns.policy_search(c, transitions=trans, deadline=10.0, seed=sd, variant="gnrpa",
                                    levels=2, iterations=8, stabilization=3, prior=None)
        wall = time.perf_counter() - t0
        return {"wall": round(wall, 3),
                "elapsed": round(float(st.get("elapsed_seconds") or 0), 3),
                "prep": round(float(st.get("prep_seconds") or 0), 3),
                "exp": int(st.get("expansions") or 0), "status": int(st.get("status") or 0),
                "n_path": len(path)}
    except Exception as e:  # noqa: BLE001
        return {"err": f"{type(e).__name__}: {e}"}


def batch(ns, session, n, trans):
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as ex:
        rows = list(ex.map(lambda k: one(ns, session, k, trans), range(n)))
    return {"conc": n, "wall": round(time.perf_counter() - t0, 3), "runs": rows}


def burners(n=16):
    code = "x=0\nwhile True:\n x=(x*x+1)%%2147483647\n"
    procs = [subprocess.Popen([sys.executable, "-c", code],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             for _ in range(n)]
    time.sleep(1.5)
    return procs


def main():
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    from GakumasCLI.native.native_search import NativeSearch
    ns = NativeSearch(engine.native()[0])
    for pid in TARGETS:
        rows = seeds_doc["problems"].get(pid) or []
        if not rows:
            continue
        seed = int(rows[0]["seed"])
        for snap in SNAP_TURNS:
            key = f"{pid}/t{snap}"
            if key in res:
                continue
            print(f"\n=== {key} (seed {seed}) ===", flush=True)
            s = walk(pid, seed, snap)
            if s is None:
                print("  no lock", flush=True)
                res[key] = {"no_lock": True}
                continue
            session, turn, lock_turn = s
            entry = {"turn": turn, "lock_turn": lock_turn, "trans": TRANS, "levels": []}
            for conc in CONC:
                vals = []
                for _r in range(REPEATS):
                    b = batch(ns, session, conc, TRANS)
                    vals.append(b)
                per = [(r["elapsed"], r["status"]) for b in vals for r in b["runs"] if "elapsed" in r]
                exps = sum(r["exp"] for b in vals for r in b["runs"] if "exp" in r)
                wall = statistics.mean(b["wall"] for b in vals)
                full = [e for e, st in per if st == 0]
                row = {"conc": conc, "wall_med": round(wall, 3),
                       "per_elapsed_med": round(statistics.median(full), 3) if full else None,
                       "per_elapsed_max": round(max(full), 3) if full else None,
                       "truncated": sum(1 for _e, st in per if st != 0),
                       "exp_sum": exps,
                       "trans_per_s": round(exps / wall) if wall > 0 else None,
                       "errs": sum(1 for b in vals for r in b["runs"] if "err" in r)}
                entry["levels"].append(row)
                print(f"  conc={conc:2d} wall={wall:6.2f}s per_med={row['per_elapsed_med']} "
                      f"trunc={row['truncated']} exp={exps:,} exp/s={row['trans_per_s']:,} "
                      f"errs={row['errs']}", flush=True)
            # scan starvation emulation: 16 burners + concurrency 4 and 8
            procs = burners(16)
            try:
                entry["starvation"] = []
                for conc in (4, 8):
                    b = batch(ns, session, conc, TRANS)
                    per = [r["elapsed"] for r in b["runs"] if "elapsed" in r]
                    exps = sum(r["exp"] for r in b["runs"] if "exp" in r)
                    row = {"conc": conc, "wall": b["wall"], "per_med": round(statistics.median(per), 3),
                           "exp_sum": exps, "trans_per_s": round(exps / b["wall"])}
                    entry["starvation"].append(row)
                    print(f"  [16 burners] conc={conc} wall={b['wall']:.2f}s per_med={row['per_med']} "
                          f"exp/s={row['trans_per_s']:,}", flush=True)
            finally:
                for p in procs:
                    p.kill()
                for p in procs:
                    p.wait()
            res[key] = entry
            OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved", OUT, flush=True)


if __name__ == "__main__":
    main()