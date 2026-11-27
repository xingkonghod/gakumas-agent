"""v6 离线配对门（探针，不提交）：v5 原调度 vs v6 预算内自适应波次（准入控制）。

同题同 seed 背靠背（承 _v5_pair.py 口径），bootstrap 10000 CI。门：Δ 的 CI 下界 > 0 且 over 不恶化。
用法：.venv\\Scripts\\python.exe data\\_v6_pair.py <configs> <tag> [pairs: smoke|monster|mid|all|v4check]
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
SUB_V5 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v5"
SUB_V6 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v6"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V5 = _load_module("algo_exv5", SUB_V5 / "algo.py")
V6 = _load_module("algo_exv6", SUB_V6 / "algo.py")
from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee, IllegalAction  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
seeds_doc = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

_BASE = {"procs": 16, "report": 0, "forced_play": 0, "starts": 4, "starts_hi": 6,
         "lock_trans": 2000000, "step_trans": 500000, "scan_wait_mode": "done",
         "vote_sec_cap": 0.8, "rescan_open": 1}
CONFIGS = {
    # v5 托管同口径（waves=2 / 决赛 4 线程 / 其余 2 线程 / portfolio）
    "v5ref": {"mod": "v5", "budget": 10.0,
              "params": dict(_BASE, waves=2, waves_hi=0, pool_threads=2, pool_threads_hi=4,
                             portfolio="2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8")},
    # v4 逐位复现（v6 代码路径）
    "v4check": {"mod": "v6", "budget": 10.0,
                "params": dict(_BASE, waves=1, waves_hi=0, pool_threads=1, pool_threads_hi=1,
                               portfolio="", max_starts=0)},
    # v6 缺省：预算内自适应波次，每步上限 24 起点，4 线程
    "v6": {"mod": "v6", "budget": 10.0,
           "params": dict(_BASE, waves=0, waves_hi=0, pool_threads=4, pool_threads_hi=4,
                          portfolio="2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8",
                          max_starts=24, admit_mult=1.25, admit_pad=0.10, dl_mult=1.5)},
    # 上限 32（更激进，看墙钟/分数）
    "v6c32": {"mod": "v6", "budget": 10.0,
              "params": dict(_BASE, waves=0, waves_hi=0, pool_threads=4, pool_threads_hi=4,
                             portfolio="2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8",
                             max_starts=32, admit_mult=1.25, admit_pad=0.10, dl_mult=1.5)},
    # 上限 16（保守）
    "v6c16": {"mod": "v6", "budget": 10.0,
              "params": dict(_BASE, waves=0, waves_hi=0, pool_threads=4, pool_threads_hi=4,
                             portfolio="2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8",
                             max_starts=16, admit_mult=1.25, admit_pad=0.10, dl_mult=1.5)},
}

MONSTER = ["AS-WDKWQYW5", "AS-AXME8QK2", "AS-BZXB28YJ", "AS-YSNBNDV4", "AS-QV6QCSN9",
           "AS-B8ZWDS3J", "AS-PPHWPMPP"]
MID = ["AS-AXME8QK2", "AS-YSNBNDV4", "AS-3G6FFZZT"]
CONTROL = ["AS-3EW6E6HV", "AS-3ZT8ZKB6", "AS-5KZSXANK", "AS-VH8WYE6J"]


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


def pairs_for(which):
    if which == "smoke":
        return [("AS-AXME8QK2", 1409380188), ("AS-WDKWQYW5", 988313260)]
    if which == "smoke3":
        return [("AS-AXME8QK2", 1409380188), ("AS-WDKWQYW5", 988313260), ("AS-BZXB28YJ", 1875523773)]
    if which == "v4check":
        return [("AS-WDKWQYW5", 988313260)]
    ids = {"monster": MONSTER, "mid": MID, "all": MONSTER + CONTROL,
           "control": CONTROL}[which]
    out = []
    for pid in ids:
        for row in (seeds_doc["problems"].get(pid) or []):
            out.append((pid, int(row["seed"])))
    return out


def _wait_free(min_mb=900, cap_s=1200):
    t0 = time.perf_counter()
    while free_mb() < min_mb:
        print(f"  [mem-guard] free {free_mb():.0f}MB ...", flush=True)
        time.sleep(30)
        if time.perf_counter() - t0 > cap_s:
            return


def make_algo(cfg_name):
    c = CONFIGS[cfg_name]
    mod = V5 if c["mod"] == "v5" else V6
    cls = mod.ExSeedV5Algo if c["mod"] == "v5" else mod.ExSeedV6Algo
    return cls(**c["params"])


def play(pid, seed, cfg_name):
    c = CONFIGS[cfg_name]
    lo = expand_loadout(saves[pid]["loadout"])
    _wait_free()
    algo = make_algo(cfg_name)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, c["budget"], random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    t0 = time.perf_counter()
    algo.begin(ctx)
    err, dts, n = None, [], 0
    pool_searches, pool_trunc, expect_ms = [], 0, []
    while not ref.finished and n < 300:
        if time.perf_counter() - t0 > 2400:
            err = "game wall > 2400s"
            break
        ctx.obs = ref.obs()
        ta = time.perf_counter()
        try:
            d = algo.decide(ctx)
        except Exception as e:  # noqa: BLE001
            err = f"decide {type(e).__name__}: {e}"
            break
        dts.append(time.perf_counter() - ta)
        m = d.meta or {}
        if m.get("pool_searches") is not None:
            pool_searches.append(int(m["pool_searches"]))
        if m.get("pool_truncated"):
            pool_trunc += int(m["pool_truncated"])
        if m.get("pool_expect_ms"):
            expect_ms.append(int(m["pool_expect_ms"]))
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
    over_ms = c["budget"] * 1200 + 50
    row = {"pid": pid, "cfg": cfg_name, "seed": seed, "score": int(ref.score),
           "finished": bool(ref.finished), "decisions": n, "err": err, "state": g.state,
           "lock_turn": g.lock_turn, "seed_found": locked_seed == seed, "scan_s": g.scan_s,
           "counts": dict(g.counts),
           "adopted": pool.stats["adopted"] if pool is not None else None,
           "bad_routes": pool.stats["bad_routes"] if pool is not None else None,
           "searches": pool.stats["searches"] if pool is not None else None,
           "think_s": round(sum(dts), 1), "wall_s": round(wall, 1),
           "mean_pool_searches": round(sum(pool_searches) / len(pool_searches), 1) if pool_searches else None,
           "pool_truncated": pool_trunc,
           "expect_ms_last": expect_ms[-1] if expect_ms else None,
           "max_ms": round(max(dts) * 1000) if dts else 0,
           "p95_ms": round(sorted(dts)[min(len(dts) - 1, int(0.95 * len(dts)))] * 1000) if dts else 0,
           "over_steps": sum(1 for x in dts if x * 1000 > over_ms), "why": g.why}
    try:
        if algo._ex is not None:
            algo._ex[1].shutdown(wait=False)
    except Exception:  # noqa: BLE001
        pass
    del algo, ref
    gc.collect()
    return row


def boot_ci(deltas, iters=10000, seed=20261127):
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def _save(out_path, names, pairs, rows):
    by = {(r["pid"], int(r["seed"]), r["cfg"]): r for r in rows}
    summary, ab = {}, {}
    all_names = ["v5ref"] + [n for n in names if n != "v5ref"]
    for nm in all_names:
        rs = [by[(p, s, nm)] for (p, s) in pairs if (p, s, nm) in by]
        if not rs:
            continue
        summary[nm] = {
            "n": len(rs), "mean_score": round(sum(r["score"] for r in rs) / len(rs)),
            "lock_rate": sum(1 for r in rs if r["seed_found"]) / len(rs),
            "mean_think_s": round(sum(r["think_s"] for r in rs) / len(rs), 1),
            "mean_wall_s": round(sum(r["wall_s"] for r in rs) / len(rs), 1),
            "mean_pool_searches": round(sum((r.get("mean_pool_searches") or 0) for r in rs) / len(rs), 1),
            "pool_truncated": sum(r.get("pool_truncated") or 0 for r in rs),
            "over_steps": sum(r["over_steps"] for r in rs),
            "max_ms": max(r["max_ms"] for r in rs),
            "bad_routes": sum((r.get("bad_routes") or 0) for r in rs),
            "errors": sum(1 for r in rs if r["err"] or not r["finished"]),
        }
    for nm in all_names:
        if nm == "v5ref":
            continue
        ap = [(p, s) for (p, s) in pairs if (p, s, nm) in by and (p, s, "v5ref") in by]
        if not ap:
            continue
        deltas = [by[(p, s, nm)]["score"] - by[(p, s, "v5ref")]["score"] for (p, s) in ap]
        lo, hi = boot_ci(deltas)
        ab[nm] = {"n": len(deltas), "mean_delta": round(sum(deltas) / len(deltas), 1),
                  "ci95": [lo, hi], "pos": sum(1 for d in deltas if d > 0),
                  "neg": sum(1 for d in deltas if d < 0), "zero": sum(1 for d in deltas if d == 0),
                  "per_pair": {f"{p}/{s}": d for (p, s), d in zip(ap, deltas)},
                  "think_ratio": round(sum(by[(p, s, nm)]["think_s"] for (p, s) in ap)
                                       / max(1e-9, sum(by[(p, s, "v5ref")]["think_s"] for (p, s) in ap)), 2)}
    out = {"configs": {nm: {"mod": CONFIGS[nm]["mod"], "params": CONFIGS[nm]["params"],
                            "budget": CONFIGS[nm]["budget"]}
                       for nm in all_names if nm in CONFIGS},
           "pairs": [list(p) for p in pairs], "rows": rows, "summary": summary, "ab_vs_v5": ab,
           "ab_vs_v4": {nm: v for nm, v in ab.items()}}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    names = (sys.argv[1] if len(sys.argv) > 1 else "v5ref,v6").split(",")
    tag = sys.argv[2] if len(sys.argv) > 2 else "smoke"
    which = sys.argv[3] if len(sys.argv) > 3 else "smoke"
    pairs = [p for p in pairs_for(which) if p[0] in saves]
    out_path = ROOT / f"data/_v6_pair_{tag}.json"
    rows = []
    if out_path.exists():
        try:
            rows = json.loads(out_path.read_text(encoding="utf-8")).get("rows", [])
            print(f"resume: {len(rows)} rows", flush=True)
        except Exception:  # noqa: BLE001
            rows = []
    done = {(r["pid"], int(r["seed"]), r["cfg"]) for r in rows}
    for (pid, seed) in pairs:
        for nm in names:
            if (pid, seed, nm) in done:
                continue
            row = play(pid, seed, nm)
            rows.append(row)
            done.add((pid, seed, nm))
            print(json.dumps(row, ensure_ascii=False), flush=True)
            _save(out_path, names, pairs, rows)
        gc.collect()
    _save(out_path, names, pairs, rows)
    print("saved:", out_path, flush=True)
    print(json.dumps(json.loads(out_path.read_text(encoding="utf-8"))["summary"], ensure_ascii=False, indent=1))
    print(json.dumps(json.loads(out_path.read_text(encoding="utf-8"))["ab_vs_v5"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()