"""Probe (not committed, OPENING_v6 ⑤): can tail_exact complete with 3 turns left?

For dev-seed games: lock, walk to turn = limit-2 (3 turns left) and turn = limit-1 (2 turns left),
snapshot the mirror session, then run tail_exact with threads 8/16, seconds 8, node_cap 20M.
Report: status, wall, nodes, path_len, terminal score -- complete vs deadline.

Usage: .venv\\Scripts\\python.exe data\\_v6_tail3.py [probe|walk] [extra topics]
Writes out/_v6_tail3.json.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
SUB_V6 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v6"
OUT = ROOT / "out" / "_v6_tail3.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V6 = _load("algo_exv6", SUB_V6 / "algo.py")
from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402
from GakumasCLI.native import tail_native as TN  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
seeds_doc = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

# 12 回合决赛深局 + 9 回合中期（都要真锁上再测）
TARGETS = ["AS-WDKWQYW5", "AS-5KZSXANK", "AS-BZXB28YJ", "AS-3EW6E6HV", "AS-AXME8QK2"]
CONFIGS = [(8, 8.0, 20_000_000), (16, 8.0, 20_000_000), (8, 8.0, 40_000_000)]


class _Cal:
    """借用 v6 algo 的 tail 时钟纪元校准（DLL steady_clock 纪元随编译器不同）。"""
    def __init__(self):
        self.algo = V6.ExSeedV6Algo(report=0)
        self.algo._load()

    def bind(self, session):
        self.algo._calibrate_tail(TN, session)


def calibrate():
    nat = engine.native()[0]
    TN._bind(nat)
    return nat


def walk_to(pid, seed, want_left, budget=10.0):
    """走到 turns_left == want_left 的锁定状态，返回 (session, turn, limit, score_so_far, lock)。"""
    lo = expand_loadout(saves[pid]["loadout"])
    algo = V6.ExSeedV6Algo(procs=16, report=0, max_starts=24)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, budget, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    algo.begin(ctx)
    n = 0
    while not ref.finished and n < 400:
        ctx.obs = ref.obs()
        exam = ctx.obs.get("exam") or {}
        turn, limit = int(exam.get("turn") or 0), int(exam.get("limit") or 0)
        if limit and limit - turn + 1 == want_left:
            g = algo.g
            if g.state == "locked" and g.mirror is not None:
                return g.mirror.session.clone(), turn, limit, int(ref.score), g.lock_turn
            return None
        d = algo.decide(ctx)
        ref.step(d.action)
        n += 1
    return None


def tail(session, nat, threads, seconds, node_cap, cal=None):
    if cal is not None:
        cal.bind(session)
    t0 = time.perf_counter()
    path, score, st = TN.tail_exact(session, seconds=seconds, nat=nat, threads=threads,
                                    node_cap=node_cap, tt_capacity=1 << 23)
    dt = time.perf_counter() - t0
    return {"threads": threads, "want_s": seconds, "node_cap": node_cap,
            "score": int(score), "status": st.get("status"),
            "status_name": {0: "complete", 1: "node_cap", 2: "deadline"}.get(st.get("status"), st.get("status")),
            "nodes": st.get("nodes"), "wall_s": round(dt, 2), "path_len": len(path)}


def main():
    nat = calibrate()
    cal = _Cal()
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for pid in TARGETS:
        rows = seeds_doc["problems"].get(pid) or []
        if not rows:
            continue
        seed = int(rows[0]["seed"])
        for left in (3, 2):
            key = f"{pid}/{left}"
            if key in res:
                continue
            if only and only not in key:
                continue
            print(f"\n=== {key} (seed {seed}) ===", flush=True)
            snap = walk_to(pid, seed, left)
            if snap is None:
                print("  no locked snapshot", flush=True)
                res[key] = {"no_snapshot": True}
                continue
            session, turn, limit, score, lock = snap
            entry = {"turn": turn, "limit": limit, "score_so_far": score, "lock_turn": lock, "runs": []}
            print(f"  snapshot turn={turn}/{limit} turns_left={left} lock={lock} score={score:,}", flush=True)
            for threads, seconds, cap in CONFIGS:
                r = tail(session.clone(), nat, threads, seconds, cap, cal)
                entry["runs"].append(r)
                print(f"   {r}", flush=True)
            res[key] = entry
            OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved", OUT, flush=True)


if __name__ == "__main__":
    main()