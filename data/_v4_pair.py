"""v4 预算利用率离线门（探针，不提交）：v3 每步 transitions 帽 500k 先行于 10s 墙钟 → 预算剩余。

假设：GNRPA transitions 帽（step_trans=500k/起点）在 ~1s 内跑完，而每起点分到 2.5s+ →
每步浪费 50-70% 墙钟。加深 transitions（1M/2M）应把预算吃满、路线更优（RoutePool 只采纳更高分，
机制上单调安全）。
门：同题同 seed 背靠背配对（承 _m1b_pair.py 口径），bootstrap CI10000；看 均分Δ + think_s/max_ms/over。
用法：.venv\\Scripts\\python.exe data\\_v4_pair.py [configs] [tag] [pairs: quick|monster|six]
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
SUB_V3 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v3"
SUB_V3G = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v3g"
SUB_V5 = ROOT / "data/bench_repo/submissions/gkagent-ex-seed-v5"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V3 = _load_module("algo_exv3", SUB_V3 / "algo.py")
V3G = _load_module("algo_exv3g", SUB_V3G / "algo.py")
_V5 = None


def _v5_mod():
    global _V5
    if _V5 is None:
        _V5 = _load_module("algo_exv5", SUB_V5 / "algo.py")
    return _V5
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
        r = json.loads(line)
        saves[str(r.get("id"))] = r

_BASE = {"procs": 16, "report": 0, "forced_play": 0, "starts": 4,
         "lock_trans": 2000000, "scan_wait_mode": "done", "vote_sec_cap": 2.0}
CONFIGS = {
    "v3":   {"cls": "v3", "budget": 10.0, "params": dict(_BASE)},
    "v3g":  {"cls": "v3g", "budget": 10.0, "params": dict(_BASE, rescan_open=1)},
    "s1m":  {"cls": "v3g", "budget": 10.0, "params": dict(_BASE, rescan_open=1, step_trans=1000000)},
    "s2m":  {"cls": "v3g", "budget": 10.0, "params": dict(_BASE, rescan_open=1, step_trans=2000000)},
    "s2mL4": {"cls": "v3g", "budget": 10.0, "params": dict(_BASE, rescan_open=1,
                                                           step_trans=2000000, lock_trans=4000000)},
    # 起点数杠杆：transitions 每起点固定、墙钟有 5-8× 余量（step_trans=500k ≈ 0.4-0.8s/搜索），
    # 每步 10s 预算非约束 → starts 翻倍=多摸盆地（RoutePool 只采纳更高终局分 → 机制单调安全）。
    "s6":  {"cls": "v3g", "budget": 10.0, "params": dict(_BASE, rescan_open=1, starts=6)},
    "s8":  {"cls": "v3g", "budget": 10.0, "params": dict(_BASE, rescan_open=1, starts=8)},
    # v5 = v4（规模自适应起点）+ 规模自适应锁定前投票深度（12 回合决赛 vote 2.0）
    "v5":  {"cls": "v5", "budget": 10.0, "params": dict(_BASE, rescan_open=1, starts_hi=6,
                                                         vote_sec_cap=0.8, vote_sec_cap_hi=2.0)},
    "v5t": {"cls": "v5", "budget": 10.0, "params": dict(_BASE, rescan_open=1, starts_hi=6,
                                                         vote_sec_cap=0.8, vote_sec_cap_hi=2.0,
                                                         tail_turns=3)},
    "v5b": {"cls": "v5", "budget": 10.0, "params": dict(_BASE, rescan_open=1, starts_hi=8,
                                                         vote_sec_cap=0.8, vote_sec_cap_hi=2.0)},
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


def wait_free(min_mb=900, cap_s=1200):
    t0 = time.perf_counter()
    while True:
        f = free_mb()
        if f >= min_mb:
            return f
        if f < 600:
            print(f"  [mem-guard] free {f:.0f}MB < 600MB, pause 90s ...", flush=True)
        time.sleep(90 if f < 600 else 60)
        if time.perf_counter() - t0 > cap_s:
            print(f"  [mem] cap expired, free {f:.0f}MB, proceed cautiously", flush=True)
            return f


def make_algo(cfg):
    c = CONFIGS[cfg]
    if c["cls"] == "v3":
        cls = V3.ExSeedV3Algo
    elif c["cls"] == "v5":
        cls = _v5_mod().ExSeedV5Algo
    else:
        cls = V3G.ExSeedV3gAlgo
    return cls(**c["params"])


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
        if time.perf_counter() - t0 > 1800:
            err = "game wall > 1800s"
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
    del algo, ref
    return row


def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def load_baseline():
    """复用既有 v3 基线行（同 harness 同 seed 确定式）→ 省掉基线重跑。"""
    out = {}
    for fn in ("data/_m1b_pair_gm.json", "data/_f2exv3_diag1.json"):
        p = ROOT / fn
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in d.get("rows", []):
            if r.get("cfg") == "v3" and r.get("err") is None and r.get("finished"):
                out[(r["pid"], int(r["seed"]))] = r
    return out


def main():
    names = (sys.argv[1] if len(sys.argv) > 1 else "s1m,s2m,s2mL4").split(",")
    tag = sys.argv[2] if len(sys.argv) > 2 else "b1"
    which = sys.argv[3] if len(sys.argv) > 3 else "six"
    if which == "monster":
        pairs = [("AS-5KZSXANK", 448199597), ("AS-B38CARVV", 1712522393),
                 ("AS-VWAF2GDN", 1333413270), ("AS-HTNFZWKG", 1966520935)]
    elif which == "six":
        pairs = [("AS-5KZSXANK", 448199597), ("AS-B38CARVV", 1712522393),
                 ("AS-VWAF2GDN", 1333413270), ("AS-HTNFZWKG", 1966520935),
                 ("AS-3G6FFZZT", 1665611653), ("AS-P8ZJTXNA", 1124647124)]
    elif which == "five":
        # 全部有 diag1 v3 基线；5KZSXANK=已证最优回归位，其余=低 oracle 比例/晚锁
        pairs = [("AS-5KZSXANK", 448199597), ("AS-3G6FFZZT", 1665611653),
                 ("AS-P8ZJTXNA", 1124647124), ("AS-QV6QCSN9", 991324286),
                 ("AS-VH8WYE6J", 102578817)]
    elif which == "three":
        # 三个 12 回合决赛题（都有 s6=v4 等价行）：测 v5 vote2 / v5t vote2+tail3
        pairs = [("AS-5KZSXANK", 448199597), ("AS-QV6QCSN9", 991324286),
                 ("AS-P8ZJTXNA", 1124647124)]
    elif which == "eight":
        pairs = [("AS-5KZSXANK", 448199597), ("AS-5KZSXANK", 661272730),
                 ("AS-B38CARVV", 1712522393), ("AS-B38CARVV", 912951460),
                 ("AS-VWAF2GDN", 1333413270), ("AS-VWAF2GDN", 29542526),
                 ("AS-HTNFZWKG", 1966520935), ("AS-HTNFZWKG", 41444314)]
    else:
        raise SystemExit(f"unknown pair set {which}")
    pairs = [p for p in pairs if p[0] in saves]
    baseline = load_baseline()
    out_path = ROOT / f"data/_v4_pair_{tag}.json"
    rows = []
    if out_path.exists():
        try:
            rows = json.loads(out_path.read_text(encoding="utf-8")).get("rows", [])
            print(f"resume: {len(rows)} rows", flush=True)
        except Exception:  # noqa: BLE001
            rows = []
    done = {(r["pid"], int(r["seed"]), r["cfg"]) for r in rows}
    # 复用其它 tag 文件里同 config 的既有行（同 seed / 同参数 = 确定式），避免重跑基线
    for p in sorted(ROOT.glob("data/_v4_pair_*.json")):
        if p == out_path:
            continue
        try:
            other = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for r in other.get("rows", []):
            if r.get("cfg") not in names:
                continue
            key = (r["pid"], int(r["seed"]), r["cfg"])
            if key in done or (r["pid"], int(r["seed"])) not in pairs:
                continue
            rows.append(dict(r))
            done.add(key)
    # 基线行搬进本次结果文件（便于统一汇总）
    for (pid, seed) in pairs:
        if (pid, seed, "v3") in done:
            continue
        b = baseline.get((pid, seed))
        if b is not None:
            rows.append(dict(b))
            done.add((pid, seed, "v3"))
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
    all_names = ["v3"] + [n for n in names if n != "v3"]
    summary = {}
    for nm in all_names:
        rs = [by[(p, s, nm)] for (p, s) in pairs if (p, s, nm) in by]
        if not rs:
            continue
        summary[nm] = {
            "n": len(rs),
            "mean_score": round(sum(r["score"] for r in rs) / len(rs)),
            "lock_rate": sum(1 for r in rs if r["seed_found"]) / len(rs),
            "mean_think_s": round(sum(r["think_s"] for r in rs) / len(rs), 1),
            "mean_wall_s": round(sum(r["wall_s"] for r in rs) / len(rs), 1),
            "mean_transitions": round(sum((r.get("transitions") or 0) for r in rs) / len(rs)),
            "mean_adopted": round(sum((r.get("adopted") or 0) for r in rs) / len(rs), 1),
            "over_steps": sum(r["over_steps"] for r in rs),
            "max_ms": max(r["max_ms"] for r in rs),
            "bad_routes": sum((r.get("bad_routes") or 0) for r in rs),
            "errors": sum(1 for r in rs if r["err"] or not r["finished"]),
        }
    ab = {}
    for nm in all_names:
        if nm == "v3":
            continue
        ap = [(p, s) for (p, s) in pairs if (p, s, nm) in by and (p, s, "v3") in by]
        if not ap:
            continue
        deltas = [by[(p, s, nm)]["score"] - by[(p, s, "v3")]["score"] for (p, s) in ap]
        lo, hi = boot_ci(deltas)
        ab[nm] = {
            "n": len(deltas), "mean_delta": round(sum(deltas) / len(deltas), 1),
            "ci95": [lo, hi], "pos": sum(1 for d in deltas if d > 0),
            "neg": sum(1 for d in deltas if d < 0), "zero": sum(1 for d in deltas if d == 0),
            "per_pair": {f"{p}/{s}": d for (p, s), d in zip(ap, deltas)},
            "think_ratio": round(sum(by[(p, s, nm)]["think_s"] for (p, s) in ap)
                                 / max(1e-9, sum(by[(p, s, "v3")]["think_s"] for (p, s) in ap)), 2),
        }
    out = {"configs": {nm: CONFIGS[nm] for nm in all_names if nm in CONFIGS},
           "pairs": [list(p) for p in pairs], "rows": rows, "summary": summary, "ab_vs_v3": ab}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()