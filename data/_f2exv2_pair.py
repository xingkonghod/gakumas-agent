"""f2-exv2 离线配对探针：ex-seed 基线 vs gkagent-ex-seed-v2（± fp0 等变体），F0 已知种子 ×
gkbench.referee 真实 obs 管线（同 _f2sl2_offline / _f2sl3b_ab 口径）。

每题同一负载窗口内背靠背跑 base + 各变体（同 seed 同 Referee 管线，worlds 同 rng），
报逐题终局分 + 均值 + 分布（min/p10/p25/med/max）+ 崩局数（<50% 配对最大值）+ bootstrap 95% CI。
合法性：Referee.IllegalAction 零触发；回放核分 bad_routes 计数（v2 池）。
上界：已知种子单次 2M-transition GNRPA（参考，RoutePool 累积可超）。探针不提交。

用法：
    .venv\\Scripts\\python.exe data\\_f2exv2_pair.py [configs_csv] [tag] [pids: core|monster|all|csv]
"""
from __future__ import annotations

import ctypes
import gc
import importlib.util
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

SUB_V2 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v2"
SUB_EX = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# v2 先导入：模块级自配置引擎路径（vendor DLL 与本机编通的同一份）
V2 = _load_module("algo_exv2", SUB_V2 / "algo.py")
EX = _load_module("algo_exseed", SUB_EX / "algo.py")

from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee, IllegalAction  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from GakumasCLI.scenario.exam_session import greedy_policy  # noqa: E402

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

PIDS_CORE = ["AS-2AXJNW8X", "AS-323ADZVK", "AS-8MY3XH4R", "AS-ADDTACFE",
             "AS-227HBGHS", "AS-23D5RE8A", "AS-33JYSHDF", "AS-93WKA9BK"]
PIDS_MONSTER = ["AS-5KZSXANK", "AS-AXME8QK2", "AS-WDKWQYW5", "AS-WNK6ARRZ", "AS-3ZT8ZKB6"]

CONFIGS = {
    # base = ex-seed 提交行为（step_seconds=5）
    "base": {"cls": "ex", "budget": 5.0, "params": {"procs": 16}},
    # v2 = core1 门口径（forced_play=1 显式；类缺省在 core1 后已按 A/B 结论改 0）
    "v2": {"cls": "v2", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 1}},
    "v2fp0": {"cls": "v2", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0}},
    "v2s3": {"cls": "v2", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 1, "starts": 3}},
    "v2st1m": {"cls": "v2", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 1, "step_trans": 1000000}},
    "v2fp0s3": {"cls": "v2", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0, "starts": 3}},
}


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_mb():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1048576


def wait_free(min_mb=2048, cap_s=900):
    t0 = time.perf_counter()
    while free_mb() < min_mb and time.perf_counter() - t0 < cap_s:
        print(f"  [mem] free {free_mb():.0f}MB < {min_mb}MB, wait 30s ...", flush=True)
        time.sleep(30)
    return free_mb()


def make_algo(cfg):
    c = CONFIGS[cfg]
    cls = EX.ExSeedAlgo if c["cls"] == "ex" else V2.ExSeedV2Algo
    return cls(**c["params"])


def play(pid, cfg):
    c = CONFIGS[cfg]
    seed = int(seeds["problems"][pid][0]["seed"])
    lo = expand_loadout(saves[pid]["loadout"])
    wait_free()
    algo = make_algo(cfg)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, c["budget"], random.Random(f"{pid}/0/algo"),
              random.Random(f"{pid}/0/world"), algo, seed)
    ctx.obs = ref.obs()
    t0 = time.perf_counter()
    algo.begin(ctx)
    err, dts, hard, n = None, [], 0, 0
    while not ref.finished and n < 300:
        if time.perf_counter() - t0 > 1200:
            err = "game wall > 1200s"
            break
        ctx.obs = ref.obs()
        ta = time.perf_counter()
        try:
            d = algo.decide(ctx)
        except Exception as e:  # noqa: BLE001
            err = f"decide {type(e).__name__}: {e}"
            break
        dts.append(time.perf_counter() - ta)
        hard += 1 if d.meta.get("hard_rule") else 0
        try:
            ref.step(d.action)
        except IllegalAction as e:  # noqa: BLE001
            err = f"illegal {e}"
            break
        except Exception as e:  # noqa: BLE001
            err = f"step {type(e).__name__}: {e}"
            break
        n += 1
    wall = time.perf_counter() - t0
    g = algo.g
    mirror = getattr(g, "mirror", None)
    locked_seed = int(mirror.session.config.seed) if mirror is not None else None
    pool = getattr(algo, "pool", None)
    dts_sorted = sorted(dts)
    over_ms = c["budget"] * 1200 + 50
    row = {"pid": pid, "cfg": cfg, "seed": seed, "score": int(ref.score), "finished": bool(ref.finished),
           "decisions": n, "err": err, "state": g.state, "lock_turn": g.lock_turn,
           "seed_found": locked_seed == seed, "scan_s": g.scan_s, "hard_rule": hard,
           "counts": dict(g.counts),
           "target": pool.target if pool is not None else getattr(g, "route_score", None),
           "adopted": pool.stats["adopted"] if pool is not None else None,
           "bad_routes": pool.stats["bad_routes"] if pool is not None else None,
           "searches": pool.stats["searches"] if pool is not None else None,
           "transitions": pool.stats["transitions"] if pool is not None else None,
           "tails": pool.stats["tails"] if pool is not None else None,
           "think_s": round(sum(dts), 1), "wall_s": round(wall, 1),
           "max_ms": round(max(dts) * 1000) if dts else 0,
           "p95_ms": round(dts_sorted[min(len(dts) - 1, int(0.95 * len(dts)))] * 1000) if dts else 0,
           "over_steps": sum(1 for x in dts if x * 1000 > over_ms),
           "why": g.why}
    del algo, ref
    return row


def boot_ci(deltas, iters=10000, seed=20261125):
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def dist(xs):
    xs = sorted(xs)
    n = len(xs)
    q = lambda p: xs[min(n - 1, int(p * n))]  # noqa: E731
    return {"min": xs[0], "p10": q(0.10), "p25": q(0.25), "med": q(0.50), "max": xs[-1],
            "mean": round(sum(xs) / n, 1)}


def main():
    names = (sys.argv[1] if len(sys.argv) > 1 else "base,v2").split(",")
    tag = sys.argv[2] if len(sys.argv) > 2 else "pair1"
    which = sys.argv[3] if len(sys.argv) > 3 else "core"
    if which == "core":
        pids = PIDS_CORE
    elif which == "monster":
        pids = PIDS_MONSTER
    elif which == "all":
        pids = PIDS_CORE + PIDS_MONSTER
    else:
        pids = which.split(",")
    pids = [p for p in pids if p in seeds["problems"] and p in saves]
    for nm in names:
        if nm not in CONFIGS:
            raise SystemExit(f"unknown config {nm}; known: {list(CONFIGS)}")
    if "base" not in names:
        names.insert(0, "base")

    nat, ns = engine.native()
    master = engine.master()
    # 上界（已知种子单次 2M GNRPA）+ 引擎贪心，每题一次
    bounds = {}
    for pid in pids:
        seed = int(seeds["problems"][pid][0]["seed"])
        lo = expand_loadout(saves[pid]["loadout"])
        wait_free()
        sess, _ = build_hif_loadout_session(master, lo, seed)
        ns._cache = None
        _p, st = ns.policy_search(sess, transitions=2_000_000, seed=182, variant="gnrpa", stabilization=3)
        ub = int(st["best_score"])
        gs = sess.clone()
        while not gs.finished:
            choice = greedy_policy(gs, list(gs.deck.hand))
            gs.step(("end",) if choice is None else ("play", int(choice)), observe=False)
        bounds[pid] = {"gnrpa_ub_2M": ub, "greedy": int(gs.state.score)}
        print(f"[bound] {pid}: ub2M={ub:,} greedy={int(gs.state.score):,}", flush=True)
        del sess, gs
        gc.collect()

    rows = []
    for pid in pids:
        for nm in names:
            row = play(pid, nm)
            row.update(bounds[pid])
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        gc.collect()

    by = {(r["pid"], r["cfg"]): r for r in rows}
    summary = {}
    for nm in names:
        rs = [by[(p, nm)] for p in pids]
        summary[nm] = {"dist": dist([r["score"] for r in rs]),
                       "lock_rate": sum(1 for r in rs if r["seed_found"]) / len(rs),
                       "mean_lock_turn": sum(r["lock_turn"] or 99 for r in rs) / len(rs),
                       "mean_wall_s": round(sum(r["wall_s"] for r in rs) / len(rs), 1),
                       "over_steps": sum(r["over_steps"] for r in rs),
                       "max_ms": max(r["max_ms"] for r in rs),
                       "bad_routes": sum(r["bad_routes"] or 0 for r in rs),
                       "errors": sum(1 for r in rs if r["err"] or not r["finished"])}
    ab = {}
    for nm in names:
        if nm == "base":
            continue
        deltas = [by[(p, nm)]["score"] - by[(p, "base")]["score"] for p in pids]
        lo, hi = boot_ci(deltas)
        collapses = {}
        for cfg in ("base", nm):
            collapses[cfg] = sum(1 for p in pids
                                 if by[(p, cfg)]["score"] < 0.5 * max(by[(p, "base")]["score"], by[(p, nm)]["score"]))
        ab[nm] = {"mean_delta": round(sum(deltas) / len(deltas), 1), "ci95": [lo, hi],
                  "pos": sum(1 for d in deltas if d > 0), "neg": sum(1 for d in deltas if d < 0),
                  "zero": sum(1 for d in deltas if d == 0),
                  "collapse_lt50pct_pairmax": collapses,
                  "per_pid": {p: d for p, d in zip(pids, deltas)}}
    out = {"configs": {nm: CONFIGS[nm] for nm in names}, "pids": pids, "bounds": bounds,
           "rows": rows, "summary": summary, "ab_vs_base": ab}
    out_path = ROOT / "data" / f"_f2exv2_{tag}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False), flush=True)
    print("AB:", json.dumps(ab, ensure_ascii=False), flush=True)
    print("saved:", out_path, flush=True)


if __name__ == "__main__":
    main()
