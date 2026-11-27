"""m1-fix3 (b) 离线配对门（不提交）：gkagent-ex-seed-v3 vs v3g（M1 消费图 graph-clean 门 + 失锁重扫）。

方法论承 data/_f2exv3_pair.py：本地真实裁判 gkbench.referee 同 seed 同负载窗口背靠背（配对），
worlds/algo 同 rng；bootstrap 10000 重采样 95% CI（种子 20261126）；崩局=<50% 配对 max；over_steps 阈值 12.05s。
题集：失锁怪物 AS-5KZSXANK/B38CARVV/VWAF2GDN/HTNFZWKG ×2 seed + 恢复集（graph-clean）抽样 12 题 ×1 seed。
门判定：锁定率上升 + 均分 CI 下界>0 + 崩局 0 + over_steps 不恶化；负结果如实（残差分布）。
增量保存（每对落盘），可中断续跑。不起托管、不杀进程；引擎单局串行；free<0.9GB sleep 60s。

用法：.venv\\Scripts\\python.exe data\\_m1b_pair.py [configs_csv] [tag] [which: monster|recovery|all|csv]
缺省 configs=v3,v3g  tag=g1  which=all
"""
from __future__ import annotations
import ctypes, gc, importlib.util, json, random, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
SUB_V3 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v3"
SUB_V3G = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v3g"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V3 = _load_module("algo_exv3", SUB_V3 / "algo.py")
V3G = _load_module("algo_exv3g", SUB_V3G / "algo.py")
from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee, IllegalAction  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line); saves[str(r.get("id"))] = r

PIDS_MONSTER = ["AS-5KZSXANK", "AS-B38CARVV", "AS-VWAF2GDN", "AS-HTNFZWKG"]
PIDS_RECOVERY = ["AS-2AXJNW8X", "AS-33JYSHDF", "AS-93WKA9BK", "AS-ADDTACFE", "AS-23D5RE8A",
                 "AS-C3Y5EFGV", "AS-D34KGR3N", "AS-GEAQANXF", "AS-8QSPBV48", "AS-499M4D9B",
                 "AS-FS37PVF9", "AS-8CCJHK74"]

_BASE = {"procs": 16, "report": 0, "forced_play": 0, "starts": 4,
         "lock_trans": 2000000, "scan_wait_mode": "done", "vote_sec_cap": 2.0}
CONFIGS = {
    "v3":  {"cls": "v3", "budget": 10.0, "params": dict(_BASE)},
    "v3g": {"cls": "v3g", "budget": 10.0, "params": dict(_BASE, rescan_open=1)},
    "v3g0": {"cls": "v3g", "budget": 10.0, "params": dict(_BASE, rescan_open=0)},  # 消融：=v3
}


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_mb():
    m = MEMORYSTATUSEX(); m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1048576


def wait_free(min_mb=900, cap_s=2400):
    t0 = time.perf_counter()
    while True:
        f = free_mb()
        if f >= min_mb:
            return f
        if f < 600:
            print(f"  [mem-guard] free {f:.0f}MB < 600MB, pause 90s ...", flush=True)
            time.sleep(90); continue
        if time.perf_counter() - t0 > cap_s:
            print(f"  [mem] cap expired, free {f:.0f}MB (>=600), proceed cautiously", flush=True)
            return f
        print(f"  [mem] free {f:.0f}MB < {min_mb}MB, wait 60s ...", flush=True)
        time.sleep(60)


def make_algo(cfg):
    c = CONFIGS[cfg]
    cls = V3.ExSeedV3Algo if c["cls"] == "v3" else V3G.ExSeedV3gAlgo
    return cls(**c["params"])


def seeds_for(pid, n_extra):
    out, k0 = [], 1
    if pid in seeds["problems"]:
        out.append((int(seeds["problems"][pid][0]["seed"]), "s0"))
    else:
        k0 = 0
    for k in range(k0, n_extra + 1):
        s = random.Random(f"{pid}/exv3/{k}").randrange(1, 1 << 31)
        out.append((s, f"s{k}"))
    return out


def play(pid, seed, cfg):
    c = CONFIGS[cfg]
    lo = expand_loadout(saves[pid]["loadout"])
    wait_free()
    algo = make_algo(cfg)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, c["budget"], random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    t0 = time.perf_counter()
    algo.begin(ctx)
    err, dts, hard, n = None, [], 0, 0
    while not ref.finished and n < 300:
        if time.perf_counter() - t0 > 1200:
            err = "game wall > 1200s"; break
        ctx.obs = ref.obs()
        ta = time.perf_counter()
        try:
            d = algo.decide(ctx)
        except Exception as e:  # noqa: BLE001
            err = f"decide {type(e).__name__}: {e}"; break
        dts.append(time.perf_counter() - ta)
        hard += 1 if d.meta.get("hard_rule") else 0
        try:
            ref.step(d.action)
        except IllegalAction as e:  # noqa: BLE001
            err = f"illegal {e}"; break
        except Exception as e:  # noqa: BLE001
            err = f"step {type(e).__name__}: {e}"; break
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
           "target": pool.target if pool is not None else getattr(g, "route_score", None),
           "adopted": pool.stats["adopted"] if pool is not None else None,
           "bad_routes": pool.stats["bad_routes"] if pool is not None else None,
           "searches": pool.stats["searches"] if pool is not None else None,
           "transitions": pool.stats["transitions"] if pool is not None else None,
           "think_s": round(sum(dts), 1), "wall_s": round(wall, 1),
           "max_ms": round(max(dts) * 1000) if dts else 0,
           "p95_ms": round(dts_sorted[min(len(dts) - 1, int(0.95 * len(dts)))] * 1000) if dts else 0,
           "over_steps": sum(1 for x in dts if x * 1000 > over_ms),
           "why": g.why}
    del algo, ref
    return row


def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed); n = len(deltas)
    if n == 0:
        return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def dist(xs):
    xs = sorted(xs); n = len(xs)
    q = lambda p: xs[min(n - 1, int(p * n))]  # noqa: E731
    return {"min": xs[0], "p10": q(0.10), "p25": q(0.25), "med": q(0.50), "max": xs[-1],
            "mean": round(sum(xs) / n, 1)}


def ab_block(by, pairs, nm, base="v3"):
    deltas = [by[(p, s, nm)]["score"] - by[(p, s, base)]["score"] for (p, s) in pairs]
    lo, hi = boot_ci(deltas)
    collapses = {}
    for cfg in (base, nm):
        collapses[cfg] = sum(1 for (p, s) in pairs
                             if by[(p, s, cfg)]["score"] < 0.5 * max(by[(p, s, base)]["score"], by[(p, s, nm)]["score"]))
    return {"n": len(deltas), "mean_delta": round(sum(deltas) / len(deltas), 1) if deltas else 0.0,
            "ci95": [lo, hi], "pos": sum(1 for d in deltas if d > 0), "neg": sum(1 for d in deltas if d < 0),
            "zero": sum(1 for d in deltas if d == 0), "collapse_lt50pct_pairmax": collapses,
            "per_pair": {f"{p}/{s}": d for (p, s), d in zip(pairs, deltas)}}


def main():
    names = (sys.argv[1] if len(sys.argv) > 1 else "v3,v3g").split(",")
    tag = sys.argv[2] if len(sys.argv) > 2 else "g1"
    which = sys.argv[3] if len(sys.argv) > 3 else "all"
    if which == "monster":
        pids = PIDS_MONSTER
    elif which == "recovery":
        pids = PIDS_RECOVERY
    elif which == "all":
        pids = PIDS_MONSTER + PIDS_RECOVERY
    else:
        pids = which.split(",")
    pids = [p for p in pids if p in saves]
    for nm in names:
        if nm not in CONFIGS:
            raise SystemExit(f"unknown config {nm}; known {list(CONFIGS)}")
    if "v3" not in names:
        names.insert(0, "v3")
    pairs, monster_pairs, recovery_pairs = [], [], []
    pid_seeds = {}
    for pid in pids:
        n_extra = 1 if pid in PIDS_MONSTER else 0
        ss = seeds_for(pid, n_extra)
        pid_seeds[pid] = ss
        for (s, _lab) in ss:
            pairs.append((pid, s))
            (monster_pairs if pid in PIDS_MONSTER else recovery_pairs).append((pid, s))
    out_path = ROOT / f"data/_m1b_pair_{tag}.json"
    rows = []
    if out_path.exists():
        try:
            rows = json.loads(out_path.read_text(encoding="utf-8")).get("rows", [])
            print(f"resume: {len(rows)} rows loaded", flush=True)
        except Exception:  # noqa: BLE001
            rows = []
    done = {(r["pid"], r["seed"], r["cfg"]) for r in rows}
    for (pid, seed) in pairs:
        for nm in names:
            if (pid, seed, nm) in done:
                continue
            row = play(pid, seed, nm)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            _save(out_path, names, pids, pid_seeds, pairs, monster_pairs, recovery_pairs, rows)
        gc.collect()
    _save(out_path, names, pids, pid_seeds, pairs, monster_pairs, recovery_pairs, rows)
    print("saved:", out_path, flush=True)


def _save(out_path, names, pids, pid_seeds, pairs, monster_pairs, recovery_pairs, rows):
    by = {(r["pid"], r["seed"], r["cfg"]): r for r in rows}
    summary = {}
    for nm in names:
        rs = [by[(p, s, nm)] for (p, s) in pairs if (p, s, nm) in by]
        if not rs:
            continue
        summary[nm] = {"n": len(rs), "dist": dist([r["score"] for r in rs]),
                       "lock_rate": sum(1 for r in rs if r["seed_found"]) / len(rs),
                       "mean_lock_turn": sum(r["lock_turn"] or 99 for r in rs) / len(rs),
                       "mean_wall_s": round(sum(r["wall_s"] for r in rs) / len(rs), 1),
                       "over_steps": sum(r["over_steps"] for r in rs),
                       "max_ms": max(r["max_ms"] for r in rs),
                       "bad_routes": sum(r["bad_routes"] or 0 for r in rs),
                       "rescan_used": sum(1 for r in rs if r.get("rescan_used")),
                       "errors": sum(1 for r in rs if r["err"] or not r["finished"])}
    ab = {}
    for nm in names:
        if nm == "v3":
            continue
        mp = [(p, s) for (p, s) in monster_pairs if (p, s, nm) in by and (p, s, "v3") in by]
        rp = [(p, s) for (p, s) in recovery_pairs if (p, s, nm) in by and (p, s, "v3") in by]
        ap = [(p, s) for (p, s) in pairs if (p, s, nm) in by and (p, s, "v3") in by]
        ab[nm] = {"overall": ab_block(by, ap, nm) if ap else None,
                  "monster": ab_block(by, mp, nm) if mp else None,
                  "recovery": ab_block(by, rp, nm) if rp else None}
    out = {"configs": {nm: CONFIGS[nm] for nm in names}, "pids": pids, "pid_seeds": pid_seeds,
           "rows": rows, "summary": summary, "ab_vs_v3": ab}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()