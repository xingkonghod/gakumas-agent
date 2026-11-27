"""gkmsps pilot prior 迷你消融（scope §5.1 步骤 2；我们的 glue，探针不提交）。

seedlock 实测 prior_generated_only 在本引擎有害（RESULTS.md:76），uinet Teacher 默认带它。
本消融：同池同 shard 名（=同 rng 流 → 逐 idx 同 loadout+seed 配对），50 局带默认 prior
vs 50 局 prior=None（glue 运行时 monkeypatch，不改引擎文件），w8/t5000。
比较均分 + fallbacks，赢家用于主 gen。

用法（root；先查空闲内存，(workers+1)×~0.5GB + 余量）：
    .venv\\Scripts\\python.exe -B data\\_gkmsps_prior_ablate.py --workers 8
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))          # import _gkmsps_gen_run（其 module 级已设引擎路径/DLL）

import _gkmsps_gen_run as GR                    # noqa: E402


def free_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / 2 ** 30


def arm_stats(path: Path) -> dict:
    eps = list(GR.G.read_episodes(path))
    n = len(eps)
    finals = [ep["final"] for ep in eps]
    return {
        "episodes": n,
        "mean_final": sum(finals) / n if n else 0.0,
        "min_final": min(finals) if finals else 0,
        "max_final": max(finals) if finals else 0,
        "fallbacks": sum(ep["fallbacks"] for ep in eps),
        "decisions": sum(len(ep["decisions"]) for ep in eps),
        "wall_s_sum": round(sum(ep["seconds"] for ep in eps), 1),
        "by_idx": {ep["idx"]: ep["final"] for ep in eps},
        "seeds_by_idx": {ep["idx"]: ep["seed"] for ep in eps},
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--episodes", type=int, default=50)
    ap.add_argument("--worlds", type=int, default=8)
    ap.add_argument("--transitions", type=int, default=5000)
    ap.add_argument("--pool", type=Path, default=ROOT / "data" / "_gkmsps_pool" / "pool.bench.v1.jsonl")
    ap.add_argument("--out-root", type=Path, default=ROOT / "data" / "_gkmsps_labels_ab")
    a = ap.parse_args()

    need = (a.workers + 1) * 0.5 + 1.0
    fg = free_gb()
    print(f"free {fg:.2f} GB; 需要 ~{need:.1f} GB（{a.workers} workers + 父进程 + 余量）", flush=True)
    if fg < need:
        print("内存不够，退出（等空闲再跑）", flush=True)
        return 2

    pool = a.pool.resolve()
    root = a.out_root.resolve()
    t0 = time.perf_counter()
    results = {}
    for prior in ("on", "off"):
        out = root / f"prior_{prior}"
        rc = GR.main(["--out", str(out), "--shard", "ab50", "--episodes", str(a.episodes),
                      "--workers", str(a.workers), "--worlds", str(a.worlds),
                      "--transitions", str(a.transitions), "--pool", str(pool), "--prior", prior])
        if rc:
            return rc
        results[prior] = arm_stats(out / "ab50.jsonl.zst")

    on, off = results["on"], results["off"]
    paired = sorted(set(on["by_idx"]) & set(off["by_idx"]))
    seed_match = sum(on["seeds_by_idx"][i] == off["seeds_by_idx"][i] for i in paired)
    diffs = [off["by_idx"][i] - on["by_idx"][i] for i in paired]
    wins_off = sum(d > 0 for d in diffs)
    wins_on = sum(d < 0 for d in diffs)
    summary = {
        "episodes_per_arm": a.episodes,
        "worlds": a.worlds, "transitions": a.transitions,
        "paired_episodes": len(paired),
        "paired_seed_match": seed_match,
        "prior_on": {k: v for k, v in on.items() if k not in ("by_idx", "seeds_by_idx")},
        "prior_off": {k: v for k, v in off.items() if k not in ("by_idx", "seeds_by_idx")},
        "mean_diff_off_minus_on": sum(diffs) / len(diffs) if diffs else 0.0,
        "wins_off": wins_off, "wins_on": wins_on, "ties": len(diffs) - wins_off - wins_on,
        "winner": "off" if off["mean_final"] > on["mean_final"] else
                  ("on" if on["mean_final"] > off["mean_final"] else
                   ("off" if off["fallbacks"] <= on["fallbacks"] else "on")),
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "ablation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
