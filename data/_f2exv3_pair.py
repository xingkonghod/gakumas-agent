"""f2-exv3 离线配对探针：gkagent-ex-seed-v2（榜首基线）vs gkagent-ex-seed-v3（更多起点 / 更深锁定步 /
去墙钟扫描等待），F0 已知种子 × gkbench.referee 真实 obs 管线（同 _f2exv2_pair 口径）。

多 dev 种子扩样（降单种子方差）：每题 F0 dev 种子 s0 + 生成种子 s1..（monster 2 个额外 / core 1 个额外，
生成种子 = random.Random(f"{pid}/exv3/{k}").randrange(1,2^31)，确定性可复现）。每题同 seed 同负载窗口内
背靠背跑各配置（配对），worlds 同 rng。报逐 (题,种子) 终局分 + 均值 + 分布 + 崩局数 + bootstrap 95% CI
（overall / monster / core 分层）。合法性：Referee.IllegalAction 零触发；回放核分 bad_routes 计数。
上界：已知种子单次 2M-transition GNRPA（参考，RoutePool 累积可超）。探针不提交。

用法：
    .venv\\Scripts\\python.exe data\\_f2exv3_pair.py [configs_csv] [tag] [which: core|monster|all] [extra_monster] [extra_core]
    缺省 configs=v2,v3  tag=pair1  which=all  extra_monster=2  extra_core=1
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

SUB_V3 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v3"
SUB_V2 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v2"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# v3 先导入：模块级自配置引擎路径（vendor DLL 与 v2 同一份，MD5 核对一致）
V3 = _load_module("algo_exv3", SUB_V3 / "algo.py")
V2 = _load_module("algo_exv2", SUB_V2 / "algo.py")

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

# v2 = 榜首提交行为（starts=2 / lock_trans=1M / wall / fp0）；v3 = 缺省杠杆（starts=4 / lock2M / done）。
# 消融：v3s2（只 lock2M+done，不加起点）/ v3w（starts4+lock2M 但 wall）/ v3l1（starts4+done 但 lock1M）。
CONFIGS = {
    "v2":   {"cls": "v2", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0}},
    "v3":   {"cls": "v3", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0,
                                                     "starts": 4, "lock_trans": 2000000, "scan_wait_mode": "done"}},
    "v3s2": {"cls": "v3", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0,
                                                     "starts": 2, "lock_trans": 2000000, "scan_wait_mode": "done"}},
    "v3w":  {"cls": "v3", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0,
                                                     "starts": 4, "lock_trans": 2000000, "scan_wait_mode": "wall"}},
    "v3l1": {"cls": "v3", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0,
                                                     "starts": 4, "lock_trans": 1000000, "scan_wait_mode": "done"}},
    # v3vote：v3 缺省 + 锁定前 worlds 搜索更深（vote_sec_cap 2.0）——攻失锁题低 oracle 比例（早期回合损失）
    "v3vote": {"cls": "v3", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0,
                                                       "starts": 4, "lock_trans": 2000000, "scan_wait_mode": "done",
                                                       "vote_sec_cap": 2.0}},
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


def wait_free(min_mb=1300, cap_s=2400):
    # lead 批准 (b)：起跑阈值 ~1.3GB（串行单局峰值 0.8-1GB）；硬守卫 free<0.6GB 暂停 90s 让 pilot 喘气
    # （pilot train numpy 全批量内存会涨，防 OOM），<0.6GB 绝不起跑（无视 cap）。600-1300MB 超 cap 才谨慎起跑。
    t0 = time.perf_counter()
    while True:
        f = free_mb()
        if f >= min_mb:
            return f
        if f < 600:
            print(f"  [mem-guard] free {f:.0f}MB < 600MB, pause 90s for pilot ...", flush=True)
            time.sleep(90)
            continue
        if time.perf_counter() - t0 > cap_s:
            print(f"  [mem] cap expired, free {f:.0f}MB (>=600), proceed cautiously", flush=True)
            return f
        print(f"  [mem] free {f:.0f}MB < {min_mb}MB, wait 30s ...", flush=True)
        time.sleep(30)


def make_algo(cfg):
    c = CONFIGS[cfg]
    cls = V2.ExSeedV2Algo if c["cls"] == "v2" else V3.ExSeedV3Algo
    return cls(**c["params"])


def seeds_for(pid, n_extra):
    # 有 F0 dev 种子：s0=dev + 生成 s1..s{n_extra}；无 dev 种子（core 120 中 31 题）：全生成 s0..s{n_extra}。
    # 共 n_extra+1 个种子。生成种子确定性可复现，loadout 来自 saves.json（core 120 全覆盖）。
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
    if n == 0:
        return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def dist(xs):
    xs = sorted(xs)
    n = len(xs)
    q = lambda p: xs[min(n - 1, int(p * n))]  # noqa: E731
    return {"min": xs[0], "p10": q(0.10), "p25": q(0.25), "med": q(0.50), "max": xs[-1],
            "mean": round(sum(xs) / n, 1)}


def ab_block(by, pairs, nm, base="v2"):
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
    names = (sys.argv[1] if len(sys.argv) > 1 else "v2,v3").split(",")
    tag = sys.argv[2] if len(sys.argv) > 2 else "pair1"
    which = sys.argv[3] if len(sys.argv) > 3 else "all"
    extra_monster = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    extra_core = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    if which == "core":
        pids = PIDS_CORE
    elif which == "monster":
        pids = PIDS_MONSTER
    elif which == "all":
        pids = PIDS_CORE + PIDS_MONSTER
    else:
        pids = which.split(",")
    pids = [p for p in pids if p in saves]   # 只需 loadout；dev 种子缺失的题用生成种子
    for nm in names:
        if nm not in CONFIGS:
            raise SystemExit(f"unknown config {nm}; known: {list(CONFIGS)}")
    if "v2" not in names:
        names.insert(0, "v2")

    # (pid, seed) 配对清单 + 分层
    pairs, monster_pairs, core_pairs = [], [], []
    pid_seeds = {}
    for pid in pids:
        n_extra = extra_monster if pid in PIDS_MONSTER else extra_core
        ss = seeds_for(pid, n_extra)
        pid_seeds[pid] = ss
        for (s, _lab) in ss:
            pairs.append((pid, s))
            (monster_pairs if pid in PIDS_MONSTER else core_pairs).append((pid, s))

    nat, ns = engine.native()
    master = engine.master()
    # 上界（已知种子单次 2M GNRPA）+ 引擎贪心，每 (题,种子) 一次
    bounds = {}
    for (pid, seed) in pairs:
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
        bounds[f"{pid}/{seed}"] = {"gnrpa_ub_2M": ub, "greedy": int(gs.state.score)}
        print(f"[bound] {pid}/{seed}: ub2M={ub:,} greedy={int(gs.state.score):,}", flush=True)
        del sess, gs
        gc.collect()

    rows = []
    for (pid, seed) in pairs:
        for nm in names:
            row = play(pid, seed, nm)
            row.update(bounds[f"{pid}/{seed}"])
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        gc.collect()

    by = {(r["pid"], r["seed"], r["cfg"]): r for r in rows}
    summary = {}
    for nm in names:
        rs = [by[(p, s, nm)] for (p, s) in pairs]
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
        if nm == "v2":
            continue
        ab[nm] = {"overall": ab_block(by, pairs, nm),
                  "monster": ab_block(by, monster_pairs, nm),
                  "core": ab_block(by, core_pairs, nm)}
    out = {"configs": {nm: CONFIGS[nm] for nm in names}, "pids": pids,
           "pid_seeds": {p: pid_seeds[p] for p in pids}, "bounds": bounds,
           "rows": rows, "summary": summary, "ab_vs_v2": ab}
    out_path = ROOT / "data" / f"_f2exv3_{tag}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False), flush=True)
    print("AB:", json.dumps(ab, ensure_ascii=False), flush=True)
    print("saved:", out_path, flush=True)


if __name__ == "__main__":
    main()