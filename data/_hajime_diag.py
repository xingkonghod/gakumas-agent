"""hajime 回退诊断探针（f2-hajime-tune）：v2 vs seedlock 的扫描/锁定行为对比。不提交。

mode=scan：候数量 vs 已见抽牌数（v2 口径 pool/types[:mutable]），lesson/audition 各样题。
mode=game：同 seed 背靠背整局（gkbench.referee 真裁判），v2fp0 / v2fp1 / seedlock，
           记 state/lock_turn/why/counts/scan_hits/score（_f2exv3_pair.py 同口径）。

用法：
    .venv\\Scripts\\python.exe data\\_hajime_diag.py scan [pids_csv]
    .venv\\Scripts\\python.exe data\\_hajime_diag.py game [pids_csv] [seed_k] [configs_csv]
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


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SL = _load_module("algo_seedlock", SUB_SL / "algo.py")
V2 = _load_module("algo_exv2", SUB_V2 / "algo.py")
SUB_V2H = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v2h"
V2H = _load_module("algo_exv2h", SUB_V2H / "algo.py")

from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee, IllegalAction  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

PROBLEMS = ROOT / "data" / "bench_local" / "problems_hajime.json"
DOCS = {d["id"]: d for d in json.loads(PROBLEMS.read_text(encoding="utf-8"))}

CONFIGS = {
    "v2fp0": {"cls": "v2", "budget": 10.0, "params": {"procs": 12, "report": 0, "forced_play": 0}},
    "v2fp1": {"cls": "v2", "budget": 10.0, "params": {"procs": 12, "report": 0, "forced_play": 1}},
    "seedlock": {"cls": "sl", "budget": 5.0, "params": {"procs": 12, "report": 0}},
    "v2h": {"cls": "v2h", "budget": 10.0, "params": {"procs": 12, "report": 0}},
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


def wait_free(min_mb=900, cap_s=900):
    t0 = time.perf_counter()
    while True:
        f = free_mb()
        if f >= min_mb:
            return f
        if f < 600:
            print(f"  [mem-guard] free {f:.0f}MB < 600MB, pause 90s ...", flush=True)
            time.sleep(90)
            continue
        if time.perf_counter() - t0 > cap_s:
            print(f"  [mem] cap expired, free {f:.0f}MB (>=600), proceed cautiously", flush=True)
            return f
        print(f"  [mem] free {f:.0f}MB < {min_mb}MB, wait 30s ...", flush=True)
        time.sleep(30)


def gen_seed(pid, k=0):
    return random.Random(f"{pid}/hajime/{k}").randrange(1, 1 << 31)


def scan_mode(pids):
    import draws
    import opening
    import seedscan
    master = engine.master()
    out = {}
    for pid in pids:
        lo = expand_loadout(DOCS[pid]["archive"]["loadout"])
        wait_free()
        opens = [opening.opening(master, lo, s) for s in (11, 0x9E3779B9, 123456789, 987654321, 55555, 4242424242)]
        inv_ok = all(o[0] == opens[0][0] and o[1] == opens[0][1] for o in opens)
        pre, k = opens[0][0], opens[0][1]
        pool, mutable = opening.turn_pool(opens[0][2])
        values = opens[0][2].deck.audition_parameter_values
        inv = draws.invariant_hand([[c["produce_card_id"] for c in o[2].deck.hand] for o in opens])
        seed = gen_seed(pid)
        sess, meta = engine.build(lo, seed)
        H0 = [c["produce_card_id"] for c in sess.deck.hand]
        D = [c["produce_card_id"] for c in sess.deck.deck]
        types = [int(t) for t in (sess.deck.turn_parameter_types or [])]
        info = {"pid": pid, "stage": DOCS[pid]["archive"]["meta"].get("stage"),
                "turns": DOCS[pid]["archive"]["meta"].get("turns"),
                "opening_seed_invariant": inv_ok, "pre_n": len(pre), "k": k,
                "pool": pool, "mutable": mutable, "values": values,
                "limit_turn": meta.get("limit_turn"), "score_cap": meta.get("score_cap"),
                "types": types, "H0": H0, "deck_n": len(D), "seed": seed,
                "distinct_pre": len(set(pre)), "scans": []}
        print(json.dumps({x: info[x] for x in ("pid", "stage", "turns", "opening_seed_invariant", "pre_n",
                                               "distinct_pre", "k", "pool", "mutable", "values", "limit_turn",
                                               "score_cap", "types", "deck_n")}, ensure_ascii=False), flush=True)
        for n in (0, 3, 6, 9):
            if n > len(D):
                break
            tr = draws.Draws(pre, inv)
            obs = {"hand": [{"id": x} for x in H0 + D[:n]], "deck": [{"id": x} for x in D[n:]]}
            tr.update(obs)
            turns_f = types[:mutable] if pool else None
            t0 = time.perf_counter()
            scan = seedscan.Scan(k, pre, list(tr.seen), list(tr.skip.elements()), pool, turns_f,
                                 procs=8, hi=1 << 31)
            while scan.poll() is None:
                time.sleep(0.05)
            hits = scan.poll()
            row = {"extra_draws": n, "seen": len(tr.seen), "skip": list(tr.skip.elements()),
                   "cands": len(hits), "scan_s": round(time.perf_counter() - t0, 2), "true_in": seed in hits}
            info["scans"].append(row)
            print(f"  draws+{n} seen={len(tr.seen)}: cands={len(hits):,} scan={row['scan_s']}s true_in={seed in hits}",
                  flush=True)
            del scan
        out[pid] = info
        del sess, opens
        gc.collect()
    p = ROOT / "data" / "_hajime_diag_scan.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", p, flush=True)


def make_algo(cfg):
    c = CONFIGS[cfg]
    cls = {"v2": V2.ExSeedV2Algo, "v2h": V2H.ExSeedV2hAlgo, "sl": SL.SeedLockAlgo}[c["cls"]]
    return cls(**c["params"])


def play(pid, seed, cfg):
    c = CONFIGS[cfg]
    lo = expand_loadout(DOCS[pid]["archive"]["loadout"])
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
        n_cands, rescans = g.n_cands, getattr(g, "rescans", None)
    else:
        mirror = getattr(algo, "mirror", None)
        locked_seed = int(mirror.config.seed) if mirror is not None else None
        n_cands = len(g.cands) if g.cands is not None else None
        rescans = g.rescans
    pool = getattr(algo, "pool", None)
    row = {"pid": pid, "cfg": cfg, "seed": seed, "score": int(ref.score), "finished": bool(ref.finished),
           "decisions": n, "err": err, "state": g.state, "lock_turn": g.lock_turn,
           "seed_found": locked_seed == seed, "scan_s": g.scan_s, "scan_hits": n_cands,
           "rescans": rescans, "hard_rule": hard, "counts": dict(g.counts),
           "target": pool.target if pool is not None else None,
           "adopted": pool.stats["adopted"] if pool is not None else None,
           "bad_routes": pool.stats.get("bad_routes") if pool is not None else None,
           "wall_s": round(wall, 1), "max_ms": round(max(dts) * 1000) if dts else 0,
           "over_steps": sum(1 for x in dts if x * 1000 > c["budget"] * 1200 + 50),
           "why": g.why, "near": getattr(g, "near", None)}
    del algo, ref
    gc.collect()
    return row


def game_mode(pids, seed_k, cfgs):
    rows = []
    for pid in pids:
        seed = gen_seed(pid, seed_k)
        for cfg in cfgs:
            row = play(pid, seed, cfg)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    p = ROOT / "data" / f"_hajime_diag_game_k{seed_k}.json"
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", p, flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    default_pids = "AS-GZP54V4T,AS-WNAX63AN,AS-X8NXKZXW,AS-DDCRRSTM"
    pids = (sys.argv[2] if len(sys.argv) > 2 else default_pids).split(",")
    pids = [p for p in pids if p in DOCS]
    if mode == "scan":
        scan_mode(pids)
    else:
        k = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        cfgs = (sys.argv[4] if len(sys.argv) > 4 else "v2fp0,v2fp1,seedlock").split(",")
        game_mode(pids, k, cfgs)