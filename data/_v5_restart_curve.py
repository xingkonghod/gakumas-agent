"""Probe (not committed): restart curve — how many independent GNRPA restarts are worth it.

Plays a v4 game until it locks (then a couple of decisions), snapshots the exact session,
and measures the terminal-score distribution of independent searches from that state at
several transition caps. This decides the v5 search-scheduling mechanism (waves/threads).
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
SUB_V4 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v4"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V4 = _load("algo_exv4", SUB_V4 / "algo.py")
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

TARGETS = ["AS-WDKWQYW5", "AS-AXME8QK2", "AS-QQ6J5S39", "AS-QV6QCSN9",
           "AS-BZXB28YJ", "AS-YSNBNDV4", "AS-P8ZJTXNA", "AS-3EW6E6HV"]
snap_turn = int(sys.argv[1]) if len(sys.argv) > 1 else 4
OUT = ROOT / "out" / "_v5_restart_curve.json"


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


def walk_to_snapshot(pid, seed):
    """Play v4 (budget 6s) until locked & turn >= snap_turn, return (session clone, turn, lock_turn)."""
    lo = expand_loadout(saves[pid]["loadout"])
    algo = V4.ExSeedV4Algo(procs=16, report=0, starts=4, starts_hi=6, lock_trans=2000000,
                           step_trans=500000, scan_wait_mode="done", vote_sec_cap=0.8, rescan_open=1)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, 6.0, __import__("random").Random(f"{pid}/{seed}/algo"),
              __import__("random").Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    algo.begin(ctx)
    snap = None
    n = 0
    while not ref.finished and n < 300:
        ctx.obs = ref.obs()
        d = algo.decide(ctx)
        g = algo.g
        if g.state == "locked" and g.mirror is not None and int(ctx.obs["exam"]["turn"]) >= snap_turn:
            snap = (g.mirror.session.clone(), int(ctx.obs["exam"]["turn"]), g.lock_turn)
            break
        ref.step(d.action)
        n += 1
    if snap is None:
        return None
    return snap


def curve(session, specs):
    """specs: list of (label, transitions, seconds, n). Returns {label: [scores...]} + timing."""
    out = {}
    for label, trans, secs, n in specs:
        scores, times, exps = [], [], []
        for i in range(n):
            sd = 182 + 7919 * i
            t0 = time.perf_counter()
            try:
                path, st = session_search(session, trans, secs, sd)
            except Exception as e:  # noqa: BLE001
                print(f"    {label} sd={sd} refused: {type(e).__name__}: {e}", flush=True)
                continue
            dt = time.perf_counter() - t0
            if not path:
                print(f"    {label} sd={sd} no path status={st.get('status')}", flush=True)
                continue
            sc = replay(session, path)
            scores.append(sc)
            times.append(dt)
            exps.append(int(st.get("expansions") or 0))
        out[label] = {"scores": scores, "times": [round(t, 2) for t in times],
                      "expansions": exps,
                      "max": max(scores) if scores else None,
                      "mean": round(statistics.mean(scores)) if scores else None}
    return out


def session_search(session, trans, secs, sd):
    from GakumasCLI.native.native_search import NativeSearch
    ns = NativeSearch(engine.native()[0])
    return ns.policy_search(session, transitions=trans, deadline=secs, seed=sd,
                            variant="gnrpa", stabilization=3, prior=None)


def main():
    results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for pid in TARGETS:
        rows = seeds_doc["problems"].get(pid) or []
        if not rows:
            print(f"{pid}: no dev seed, skip")
            continue
        for row in rows[:1]:
            key = f"{pid}/{row['seed']}"
            if key in results:
                continue
            seed = int(row["seed"])
            print(f"\n=== {key} (dev seed, walk to turn>={snap_turn}) ===", flush=True)
            t0 = time.perf_counter()
            snap = walk_to_snapshot(pid, seed)
            if snap is None:
                print("  could not lock, skip")
                continue
            session, turn, lock_turn = snap
            print(f"  snapshot at turn={turn} lock_turn={lock_turn} walk={time.perf_counter()-t0:.1f}s", flush=True)
            specs = [("t500k", 500_000, 4.0, 12),
                     ("t250k", 250_000, 2.5, 8),
                     ("t2m", 2_000_000, 10.0, 4)]
            res = curve(session, specs)
            for label, d in res.items():
                if not d["scores"]:
                    continue
                print(f"  {label}: n={len(d['scores'])} max={d['max']:,} mean={d['mean']:,} "
                      f"min={min(d['scores']):,} med={statistics.median(d['scores']):,.0f} "
                      f"t={statistics.mean(d['times']):.2f}s exp={statistics.mean(d['expansions']):,.0f} "
                      f"scores={sorted(d['scores'], reverse=True)[:6]}")
            results[key] = {"turn": turn, "lock_turn": lock_turn, "curve": res}
            OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved", OUT)


if __name__ == "__main__":
    main()