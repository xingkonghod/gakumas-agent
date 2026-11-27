"""v5 离线配对门（探针，不提交）：v4ref（v4 原调度）vs 预算饱和/并行多起点变体。

同题同 seed 背靠背（承 _v4_pair.py / _m1b_pair.py 口径），bootstrap 10000 CI。
门：均分 Δ 的 CI 下界 > 0 且 over_steps 不恶化。用法：
    .venv\\Scripts\\python.exe data\\_v5_pair.py <configs,逗号分隔> <tag> [pairs: monster|mid|all|smoke]
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


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V5 = _load_module("algo_exv5", SUB_V5 / "algo.py")
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

# v4 同口径缺省（v4 托管那次）：starts4/starts_hi6/lock2M/step500k/done/vote0.8/rescan1/fp0/prior0
_BASE = {"procs": 16, "report": 0, "forced_play": 0, "starts": 4, "starts_hi": 6,
         "lock_trans": 2000000, "step_trans": 500000, "scan_wait_mode": "done",
         "vote_sec_cap": 0.8, "rescan_open": 1,
         "waves": 1, "waves_hi": 0, "pool_threads": 1, "pool_threads_hi": 1}
CONFIGS = {
    # v4 原调度（逐位）：一波 starts 串行、均分 deadline
    "v4ref": {"budget": 10.0, "params": dict(_BASE, waves=1, pool_threads=1)},
    # 搜索质量：GNRPA 嵌套参数（引擎缺省 l2/i8/s3）→ 固定状态探针里 i16/s5 明显更强
    "q": {"budget": 10.0, "params": dict(_BASE, iterations=16, stabilization=5)},
    # 搜索质量 + 预算饱和并行（组合臂）
    "qf": {"budget": 10.0, "params": dict(_BASE, iterations=16, stabilization=5,
                                          waves=0, pool_threads=2, pool_threads_hi=4)},
    # 搜索配置组合（portfolio），**v4 调度不变**（waves=1/串行）→ 墙钟与 v4 相同
    "p1": {"budget": 10.0, "params": dict(_BASE, portfolio="2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8")},
    # portfolio + 锁定前候选镜像投票（真后验 PIMC）
    "p1mv": {"budget": 10.0, "params": dict(_BASE, portfolio="2/8/3,2/8/5,2/16/3,2/16/5,3/8/5,2/4/8",
                                            mirror_vote=1)},
    # 搜索配置组合（portfolio）+ 预算饱和并行：逐波轮换 (levels,iterations,stabilization)
    "pf": {"budget": 10.0, "params": dict(_BASE, portfolio="2/8/3,2/8/5,2/16/3,2/16/5",
                                          waves=0, pool_threads=2, pool_threads_hi=4)},
    "q_t3": {"budget": 10.0, "params": dict(_BASE, iterations=16, stabilization=5, tail_turns=3)},
    # 串行多波次：填满 t_end，但一波只跑 starts 个起点
    "fill": {"budget": 10.0, "params": dict(_BASE, waves=0, pool_threads=1)},
    # 并行多波次：一波 starts 个起点并行（决赛 4 线程、其余 2）
    "par": {"budget": 10.0, "params": dict(_BASE, waves=0, pool_threads=2, pool_threads_hi=4)},
    # 并行多波次 + 根动作枚举（每个合法首动作各完整续搜一次）
    "rs": {"budget": 10.0, "params": dict(_BASE, waves=0, pool_threads=2, pool_threads_hi=4,
                                          root_scan=1)},
    # 根动作枚举 + 深浅混合（第一波 2M 深搜，其余 500k 快探索）
    "rsdeep": {"budget": 10.0, "params": dict(_BASE, waves=0, pool_threads=2, pool_threads_hi=4,
                                              root_scan=1, deep_trans=2000000, deep_waves=1)},
    # 并行多波次（全 4 线程）
    "par4": {"budget": 10.0, "params": dict(_BASE, waves=0, pool_threads=4, pool_threads_hi=4)},
    # 并行 + 精确尾 3 回合
    "par_t3": {"budget": 10.0, "params": dict(_BASE, waves=0, pool_threads=2, pool_threads_hi=4,
                                              tail_turns=3)},
    # 根动作枚举 + 深混合 + 精确尾 3
    "rsdeep_t3": {"budget": 10.0, "params": dict(_BASE, waves=0, pool_threads=2, pool_threads_hi=4,
                                                 root_scan=1, deep_trans=2000000, deep_waves=1,
                                                 tail_turns=3)},
    # 并行 + 决赛锁定前投票加深（v5 原候选）
    "par_vote": {"budget": 10.0, "params": dict(_BASE, waves=0, pool_threads=2, pool_threads_hi=4,
                                                vote_sec_cap_hi=2.0)},
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


def wait_free(min_mb=900, cap_s=1200):
    t0 = time.perf_counter()
    while True:
        f = free_mb()
        if f >= min_mb:
            return f
        print(f"  [mem-guard] free {f:.0f}MB, wait 60s ...", flush=True)
        time.sleep(60)
        if time.perf_counter() - t0 > cap_s:
            return f


def pairs_for(which):
    if which == "smoke":
        return [("AS-AXME8QK2", 1409380188), ("AS-WDKWQYW5", 988313260)]
    if which == "smokeA":
        return [("AS-AXME8QK2", 1409380188), ("AS-BZXB28YJ", 1875523773)]
    if which == "smokeB":
        return [("AS-WDKWQYW5", 988313260), ("AS-3EW6E6HV", 153762096)]
    out = []
    ids = {"monster": MONSTER, "mid": MID, "all": MONSTER + CONTROL,
           "control": CONTROL}[which]
    for pid in ids:
        for row in (seeds_doc["problems"].get(pid) or []):
            out.append((pid, int(row["seed"])))
    return out


def play(pid, seed, cfg):
    c = CONFIGS[cfg]
    lo = expand_loadout(saves[pid]["loadout"])
    wait_free()
    algo = V5.ExSeedV5Algo(**c["params"])
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, c["budget"], random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    t0 = time.perf_counter()
    algo.begin(ctx)
    err, dts, hard, n = None, [], 0, 0
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
           "graph_clean": getattr(g, "graph_clean", None), "rescan_used": getattr(g, "rescan_used", False),
           "counts": dict(g.counts),
           "adopted": pool.stats["adopted"] if pool is not None else None,
           "bad_routes": pool.stats["bad_routes"] if pool is not None else None,
           "searches": pool.stats["searches"] if pool is not None else None,
           "transitions": pool.stats["transitions"] if pool is not None else None,
           "think_s": round(sum(dts), 1), "wall_s": round(wall, 1),
           "max_ms": round(max(dts) * 1000) if dts else 0,
           "p95_ms": round(dts_sorted[min(len(dts) - 1, int(0.95 * len(dts)))] * 1000) if dts else 0,
           "over_steps": sum(1 for x in dts if x * 1000 > over_ms),
           "why": g.why}
    try:
        if algo._ex is not None:
            algo._ex[1].shutdown(wait=False)
    except Exception:  # noqa: BLE001
        pass
    del algo, ref
    gc.collect()
    return row


def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def main():
    names = (sys.argv[1] if len(sys.argv) > 1 else "v4ref,par").split(",")
    tag = sys.argv[2] if len(sys.argv) > 2 else "smoke"
    which = sys.argv[3] if len(sys.argv) > 3 else "smoke"
    pairs = [p for p in pairs_for(which) if p[0] in saves]
    out_path = ROOT / f"data/_v5_pair_{tag}.json"
    rows = []
    if out_path.exists():
        try:
            rows = json.loads(out_path.read_text(encoding="utf-8")).get("rows", [])
            print(f"resume: {len(rows)} rows", flush=True)
        except Exception:  # noqa: BLE001
            rows = []
    done = {(r["pid"], int(r["seed"]), r["cfg"]) for r in rows}
    # 复用其它 tag 文件里同 config 的既有行（同 seed / 同参数 = 确定式），避免重跑基线
    for p in sorted(ROOT.glob("data/_v5_pair_*.json")):
        if p == out_path:
            continue
        try:
            other = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for r in other.get("rows", []):
            if r.get("cfg") not in set(names) | {"v4ref"}:
                continue
            key = (r["pid"], int(r["seed"]), r["cfg"])
            if key in done or (r["pid"], int(r["seed"])) not in pairs:
                continue
            rows.append(dict(r))
            done.add(key)
            print(f"reuse {key} from {p.name}", flush=True)
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


def _save(out_path, names, pairs, rows):
    by = {(r["pid"], int(r["seed"]), r["cfg"]): r for r in rows}
    all_names = ["v4ref"] + [n for n in names if n != "v4ref"]
    summary, ab = {}, {}
    for nm in all_names:
        rs = [by[(p, s, nm)] for (p, s) in pairs if (p, s, nm) in by]
        if not rs:
            continue
        summary[nm] = {
            "n": len(rs), "mean_score": round(sum(r["score"] for r in rs) / len(rs)),
            "lock_rate": sum(1 for r in rs if r["seed_found"]) / len(rs),
            "mean_think_s": round(sum(r["think_s"] for r in rs) / len(rs), 1),
            "mean_wall_s": round(sum(r["wall_s"] for r in rs) / len(rs), 1),
            "mean_transitions": round(sum((r.get("transitions") or 0) for r in rs) / len(rs)),
            "mean_searches": round(sum((r.get("searches") or 0) for r in rs) / len(rs)),
            "mean_adopted": round(sum((r.get("adopted") or 0) for r in rs) / len(rs), 1),
            "over_steps": sum(r["over_steps"] for r in rs),
            "max_ms": max(r["max_ms"] for r in rs),
            "bad_routes": sum((r.get("bad_routes") or 0) for r in rs),
            "errors": sum(1 for r in rs if r["err"] or not r["finished"]),
        }
    for nm in all_names:
        if nm == "v4ref":
            continue
        ap = [(p, s) for (p, s) in pairs if (p, s, nm) in by and (p, s, "v4ref") in by]
        if not ap:
            continue
        deltas = [by[(p, s, nm)]["score"] - by[(p, s, "v4ref")]["score"] for (p, s) in ap]
        lo, hi = boot_ci(deltas)
        ab[nm] = {"n": len(deltas), "mean_delta": round(sum(deltas) / len(deltas), 1),
                  "ci95": [lo, hi], "pos": sum(1 for d in deltas if d > 0),
                  "neg": sum(1 for d in deltas if d < 0), "zero": sum(1 for d in deltas if d == 0),
                  "per_pair": {f"{p}/{s}": d for (p, s), d in zip(ap, deltas)},
                  "think_ratio": round(sum(by[(p, s, nm)]["think_s"] for (p, s) in ap)
                                       / max(1e-9, sum(by[(p, s, "v4ref")]["think_s"] for (p, s) in ap)), 2)}
    out = {"configs": {nm: CONFIGS[nm] for nm in all_names if nm in CONFIGS},
           "pairs": [list(p) for p in pairs], "rows": rows, "summary": summary, "ab_vs_v4": ab}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()