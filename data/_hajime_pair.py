"""f2-hajime-tune 离线配对门：gkagent-ex-seed-v2h（hajime 特化）vs v2（基线）vs seedlock（榜首口径）。

方法（_f2exv3_pair.py 同口径）：hajime 48 题 × 2 生成种子（public_seeds=false，无 dev 种子；
s_k = random.Random(f"{pid}/hajime/{k}").randrange(1,2^31)，确定性可复现），每题同 seed 同负载窗口
背靠背跑各配置（配对），worlds 同 rng（f"{pid}/{seed}/world"）。裁判 = gkbench.referee 真实 obs 管线
（GKMS native rules 69）。合法性 Referee.IllegalAction 零触发；回放核分 bad_routes 计数；
bootstrap 10000 重采样 95% CI（种子 20261125）。上界 = 已知种子单次 2M GNRPA + 引擎贪心（参考）。

门（DoD B）：v2h 均分显著 ≥ v2（CI 下界 > 0）且失锁率下降；目标逼近 seedlock 口径。
分层：lesson（33 题，无属性池）/ audition（15 题，有属性池）。

增量落盘 + resume：每局一行 JSONL（_hajime_pair_rows[_shard].jsonl），重跑跳过已完成 (pid,seed,cfg)。
shard：--shard i/n 把 (题,种子) 配对清单切 n 份跑第 i 份（内存允许时双进程并行，≤3 局同时）。

用法：
    .venv\\Scripts\\python.exe data\\_hajime_pair.py hajime [configs_csv] [shard_i] [shard_n] [bounds01]
    .venv\\Scripts\\python.exe data\\_hajime_pair.py hif [configs_csv]      # hif core8 抽查（v2h 误投不回归）
    .venv\\Scripts\\python.exe data\\_hajime_pair.py summary                # 只汇总已有 rows
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

SUB_SL = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-seedlock"
SUB_V2 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v2"
SUB_V2H = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v2h"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SL = _load_module("algo_seedlock", SUB_SL / "algo.py")
V2 = _load_module("algo_exv2", SUB_V2 / "algo.py")
V2H = _load_module("algo_exv2h", SUB_V2H / "algo.py")

from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee, IllegalAction  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from GakumasCLI.scenario.exam_session import greedy_policy  # noqa: E402

HAJIME = {d["id"]: d for d in json.loads(
    (ROOT / "data" / "bench_local" / "problems_hajime.json").read_text(encoding="utf-8"))}
LESSON = {p for p, d in HAJIME.items() if str(d["archive"]["loadout"].get("round")) == "lesson"}
AUDITION = set(HAJIME) - LESSON

DL_HIF = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
HIF_SEEDS = json.loads((DL_HIF / "seeds.json").read_text(encoding="utf-8"))
HIF_SAVES = {}
with (DL_HIF / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        HIF_SAVES[str(r.get("id"))] = r
PIDS_HIF_CORE = ["AS-2AXJNW8X", "AS-323ADZVK", "AS-8MY3XH4R", "AS-ADDTACFE",
                 "AS-227HBGHS", "AS-23D5RE8A", "AS-33JYSHDF", "AS-93WKA9BK"]

# 投稿口径：v2/v2h budget 10 procs 16（submission step_seconds=10，params={}）；
# seedlock budget 5 procs 8（其 submission step_seconds=5，procs 缺省 8）。
CONFIGS = {
    "v2": {"cls": "v2", "budget": 10.0, "params": {"procs": 16, "report": 0, "forced_play": 0}},
    "v2h": {"cls": "v2h", "budget": 10.0, "params": {"procs": 16, "report": 0}},
    "v2hfp0": {"cls": "v2h", "budget": 10.0, "params": {"procs": 16, "report": 0, "short_forced_play": 0}},
    "v2hg2": {"cls": "v2h", "budget": 10.0, "params": {"procs": 16, "report": 0, "short_greedy": 2}},
    "seedlock": {"cls": "sl", "budget": 5.0, "params": {"procs": 8, "report": 0}},
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


def wait_free(min_mb=1100, cap_s=1800):
    # 托管 40312fcb77a0 在跑（parallel 3）：free<0.6GB 绝不起跑（暂停 90s 让托管喘气）；
    # 0.6–1.1GB 等 30s 一轮，超 cap 才谨慎起跑。
    t0 = time.perf_counter()
    while True:
        f = free_mb()
        if f >= min_mb:
            return f
        if f < 600:
            print(f"  [mem-guard] free {f:.0f}MB < 600MB, pause 90s for hosted ...", flush=True)
            time.sleep(90)
            continue
        if time.perf_counter() - t0 > cap_s:
            print(f"  [mem] cap expired, free {f:.0f}MB (>=600), proceed cautiously", flush=True)
            return f
        print(f"  [mem] free {f:.0f}MB < {min_mb}MB, wait 30s ...", flush=True)
        time.sleep(30)


def gen_seed(pid, k):
    return random.Random(f"{pid}/hajime/{k}").randrange(1, 1 << 31)


def make_algo(cfg):
    c = CONFIGS[cfg]
    cls = {"v2": V2.ExSeedV2Algo, "v2h": V2H.ExSeedV2hAlgo, "sl": SL.SeedLockAlgo}[c["cls"]]
    return cls(**c["params"])


def play(pid, seed, cfg, loadout):
    c = CONFIGS[cfg]
    lo = expand_loadout(loadout)
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
    if c["cls"] in ("v2", "v2h"):
        mirror = getattr(g, "mirror", None)
        locked_seed = int(mirror.session.config.seed) if mirror is not None else None
        scan_hits, rescans = g.n_cands, getattr(g, "rescans", None)
        short_exam = getattr(algo, "short_exam", None)
        fp_eff = getattr(algo, "fp_eff", None)
    else:
        mirror = getattr(algo, "mirror", None)
        locked_seed = int(mirror.config.seed) if mirror is not None else None
        scan_hits = len(g.cands) if g.cands is not None else None
        rescans = g.rescans
        short_exam, fp_eff = None, None
    pool = getattr(algo, "pool", None)
    tr = getattr(g, "tracker", None)
    dts_sorted = sorted(dts)
    over_ms = c["budget"] * 1200 + 50
    row = {"pid": pid, "cfg": cfg, "seed": seed, "score": int(ref.score), "finished": bool(ref.finished),
           "decisions": n, "err": err, "state": g.state, "lock_turn": g.lock_turn,
           "seed_found": locked_seed == seed, "locked_seed": locked_seed,
           "scan_s": g.scan_s, "scan_hits": scan_hits, "rescans": rescans,
           "short_exam": short_exam, "fp_eff": fp_eff, "hard_rule": hard, "counts": dict(g.counts),
           "target": pool.target if pool is not None else None,
           "adopted": pool.stats["adopted"] if pool is not None else None,
           "bad_routes": pool.stats.get("bad_routes") if pool is not None else None,
           "searches": pool.stats["searches"] if pool is not None else None,
           "transitions": pool.stats["transitions"] if pool is not None else None,
           "tails": pool.stats.get("tails") if pool is not None else None,
           "think_s": round(sum(dts), 1), "wall_s": round(wall, 1),
           "max_ms": round(max(dts) * 1000) if dts else 0,
           "p95_ms": round(dts_sorted[min(len(dts) - 1, int(0.95 * len(dts)))] * 1000) if dts else 0,
           "over_steps": sum(1 for x in dts if x * 1000 > over_ms),
           "why": g.why, "near": getattr(g, "near", None),
           "tr_open": getattr(tr, "open", None), "tr_seen": len(tr.seen) if tr is not None else None}
    del algo, ref
    gc.collect()
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


def ab_block(by, pairs, nm, base):
    pairs = [(p, s) for (p, s) in pairs if (p, s, nm) in by and (p, s, base) in by]
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


def rows_path(shard_i, shard_n):
    suffix = "" if shard_n <= 1 else f"_{shard_i}of{shard_n}"
    return ROOT / "data" / f"_hajime_pair_rows{suffix}.jsonl"


def load_rows(paths):
    by = {}
    for p in paths:
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    by[(r["pid"], r["seed"], r["cfg"])] = r
    return by


def summarize(by, pairs, names, tag):
    summary = {}
    for nm in names:
        rs = [by[(p, s, nm)] for (p, s) in pairs if (p, s, nm) in by]
        if not rs:
            continue
        summary[nm] = {"n": len(rs), "dist": dist([r["score"] for r in rs]),
                       "lock_rate": round(sum(1 for r in rs if r["seed_found"]) / len(rs), 4),
                       "lost_after_lock": sum(1 for r in rs if r["state"] == "lost"),
                       "failed": sum(1 for r in rs if r["state"] == "failed"),
                       "mean_lock_turn": round(sum(r["lock_turn"] or 99 for r in rs) / len(rs), 2),
                       "mean_wall_s": round(sum(r["wall_s"] for r in rs) / len(rs), 1),
                       "over_steps": sum(r["over_steps"] for r in rs),
                       "max_ms": max(r["max_ms"] for r in rs),
                       "bad_routes": sum(r["bad_routes"] or 0 for r in rs),
                       "errors": sum(1 for r in rs if r["err"] or not r["finished"])}
    ab = {}
    for nm in names:
        for base in names:
            if nm == base:
                continue
            key = f"{nm}_vs_{base}"
            ab[key] = {"overall": ab_block(by, pairs, nm, base),
                       "lesson": ab_block(by, [(p, s) for (p, s) in pairs if p in LESSON], nm, base),
                       "audition": ab_block(by, [(p, s) for (p, s) in pairs if p in AUDITION], nm, base)}
    out = {"summary": summary, "ab": ab, "n_pairs": len(pairs)}
    p = ROOT / "data" / f"_hajime_pair_{tag}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False), flush=True)
    for key in ab:
        print(f"AB {key} overall:", json.dumps({k: ab[key]["overall"][k] for k in
              ("n", "mean_delta", "ci95", "pos", "neg", "zero", "collapse_lt50pct_pairmax")}, ensure_ascii=False), flush=True)
    print("saved:", p, flush=True)
    return out


def bounds_for(pid, seed, loadout):
    lo = expand_loadout(loadout)
    wait_free()
    master = engine.master()
    nat, ns = engine.native()
    sess, _ = build_hif_loadout_session(master, lo, seed)
    ns._cache = None
    _p, st = ns.policy_search(sess, transitions=2_000_000, seed=182, variant="gnrpa", stabilization=3)
    ub = int(st["best_score"])
    gs = sess.clone()
    while not gs.finished:
        choice = greedy_policy(gs, list(gs.deck.hand))
        gs.step(("end",) if choice is None else ("play", int(choice)), observe=False)
    row = {"pid": pid, "seed": seed, "gnrpa_ub_2M": ub, "greedy": int(gs.state.score)}
    del sess, gs
    gc.collect()
    return row


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "hajime"
    if mode == "summary":
        paths = sorted((ROOT / "data").glob("_hajime_pair_rows*.jsonl"))
        by = load_rows(paths)
        pairs = sorted({(p, s) for (p, s, _c) in by})
        names = sorted({c for (_p, _s, c) in by})
        summarize(by, pairs, names, "summary")
        return
    if mode == "hif":
        names = (sys.argv[2] if len(sys.argv) > 2 else "v2,v2h").split(",")
        pairs, loadouts = [], {}
        for pid in PIDS_HIF_CORE:
            if pid not in HIF_SAVES:
                continue
            seed = int(HIF_SEEDS["problems"][pid][0]["seed"]) if pid in HIF_SEEDS["problems"] else gen_seed(pid, 0)
            pairs.append((pid, seed))
            loadouts[pid] = HIF_SAVES[pid]["loadout"]
        rp = ROOT / "data" / "_hajime_pair_rows_hif.jsonl"
        by = load_rows([rp])
        with rp.open("a", encoding="utf-8") as f:
            for (pid, seed) in pairs:
                for nm in names:
                    if (pid, seed, nm) in by:
                        print(f"[skip] {pid}/{seed}/{nm}", flush=True)
                        continue
                    row = play(pid, seed, nm, loadouts[pid])
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    by[(pid, seed, nm)] = row
                    print(json.dumps(row, ensure_ascii=False), flush=True)
        summarize(by, pairs, names, "hif")
        return

    names = (sys.argv[2] if len(sys.argv) > 2 else "v2,v2h,seedlock").split(",")
    shard_i = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    shard_n = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    do_bounds = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    for nm in names:
        if nm not in CONFIGS:
            raise SystemExit(f"unknown config {nm}; known: {list(CONFIGS)}")
    pids = sorted(HAJIME)
    pairs = [(pid, gen_seed(pid, k)) for pid in pids for k in (0, 1)]
    pairs = [ps for i, ps in enumerate(pairs) if i % shard_n == shard_i]
    rp = rows_path(shard_i, shard_n)
    by = load_rows([rp])
    bp = ROOT / "data" / f"_hajime_pair_bounds{'' if shard_n <= 1 else f'_{shard_i}of{shard_n}'}.jsonl"
    bounds = {}
    if bp.is_file():
        for line in bp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                bounds[(r["pid"], r["seed"])] = r
    print(f"[start] shard {shard_i}/{shard_n}: {len(pairs)} pairs × {names}, rows={rp.name}, "
          f"done={len(by)}, free={free_mb():.0f}MB", flush=True)
    with rp.open("a", encoding="utf-8") as f, bp.open("a", encoding="utf-8") as bf:
        for (pid, seed) in pairs:
            loadout = HAJIME[pid]["archive"]["loadout"]
            if do_bounds and (pid, seed) not in bounds:
                b = bounds_for(pid, seed, loadout)
                bf.write(json.dumps(b, ensure_ascii=False) + "\n")
                bf.flush()
                bounds[(pid, seed)] = b
                print(f"[bound] {pid}/{seed}: ub2M={b['gnrpa_ub_2M']:,} greedy={b['greedy']:,}", flush=True)
            for nm in names:
                if (pid, seed, nm) in by:
                    print(f"[skip] {pid}/{seed}/{nm}", flush=True)
                    continue
                row = play(pid, seed, nm, loadout)
                if (pid, seed) in bounds:
                    row.update({k: bounds[(pid, seed)][k] for k in ("gnrpa_ub_2M", "greedy")})
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                by[(pid, seed, nm)] = row
                print(json.dumps(row, ensure_ascii=False), flush=True)
    all_pairs = [(pid, gen_seed(pid, k)) for pid in pids for k in (0, 1)]
    all_by = load_rows(sorted((ROOT / "data").glob("_hajime_pair_rows*.jsonl")))
    summarize(all_by, all_pairs, names, f"gate{'' if shard_n <= 1 else f'_s{shard_i}'}")


if __name__ == "__main__":
    main()