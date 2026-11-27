"""M6 阶段2 ② sim 配对门：SAFE 饮料子集 ×2 seed，喝(auto) vs 不喝(off)。不提交。

4 arm：greedy/expectimax-analytic × auto/off（local_bench --drinks）。
配对按 (problem, seed)；cluster bootstrap 按题重抽（同题两 seed 一起），10000 次
95% percentile CI。greedy 不喝饮料（无 drink 启发式）= 阴性对照。
内存守卫：free < 0.9GB 退出。
"""
import ctypes
import io
import json
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]


class _MEM(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


mem = _MEM()
mem.dwLength = ctypes.sizeof(_MEM)
ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
free_gb = mem.ullAvailPhys / 1024**3
print(f"free memory: {free_gb:.2f} GB", flush=True)
if free_gb < 0.9:
    raise SystemExit("BLOCKED: free memory < 0.9GB")

SUBSET = ROOT / "data/_drinks_gate2_problems.json"
ARMS = [
    ("greedy", "off"), ("greedy", "auto"),
    ("expectimax-analytic", "off"), ("expectimax-analytic", "auto"),
]
outs = {}
for algo, mode in ARMS:
    out = ROOT / f"data/_gate2_{algo}_{mode}.json"
    outs[(algo, mode)] = out
    print(f"\n=== arm {algo} {mode} ===", flush=True)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/local_bench.py"),
         "--problems", str(SUBSET), "--algos", algo, "--drinks", mode,
         "--episodes", "2", "--seed-base", "1000", "--out", str(out)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        print(proc.stdout[-2000:]); print(proc.stderr[-2000:])
        raise SystemExit(f"arm {algo} {mode} failed rc={proc.returncode}")
    tail = [l for l in proc.stdout.splitlines() if l.strip()][-6:]
    print("\n".join(tail), flush=True)

import numpy as np  # noqa: E402

def episodes(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(e["problem"], int(e["seed"])): e for e in data["episodes"]}

result = {"free_gb_at_start": round(free_gb, 2), "subset_problems": len(json.loads(SUBSET.read_text(encoding='utf-8'))), "algos": {}}
rng = np.random.default_rng(20261126)
for algo in ("greedy", "expectimax-analytic"):
    off = episodes(outs[(algo, "off")])
    auto = episodes(outs[(algo, "auto")])
    keys = sorted(set(off) & set(auto))
    by_problem = {}
    for k in keys:
        by_problem.setdefault(k[0], []).append(int(auto[k]["score"]) - int(off[k]["score"]))
    problems = sorted(by_problem)
    prob_mean = np.array([np.mean(by_problem[p]) for p in problems])
    diffs = np.array([d for p in problems for d in by_problem[p]])
    boots = np.array([
        rng.choice(prob_mean, size=len(problems), replace=True).mean()
        for _ in range(10000)
    ])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    crashes_auto = sum(1 for k in keys if not auto[k].get("finished", True))
    crashes_off = sum(1 for k in keys if not off[k].get("finished", True))
    result["algos"][algo] = {
        "episodes": len(keys), "problems": len(problems),
        "mean_off": float(np.mean([int(off[k]["score"]) for k in keys])),
        "mean_auto": float(np.mean([int(auto[k]["score"]) for k in keys])),
        "mean_diff": float(diffs.mean()),
        "ci95": [float(lo), float(hi)],
        "wins": int((diffs > 0).sum()), "losses": int((diffs < 0).sum()),
        "ties": int((diffs == 0).sum()),
        "crashes_auto": crashes_auto, "crashes_off": crashes_off,
        "pass_lower_gt0": bool(lo > 0),
    }
    print(f"\n{algo}: mean_diff={diffs.mean():.1f} CI95=[{lo:.1f},{hi:.1f}] "
          f"wins={(diffs>0).sum()} losses={(diffs<0).sum()} ties={(diffs==0).sum()} "
          f"crashes={crashes_auto}/{crashes_off}", flush=True)

(ROOT / "data/_drinks_gate2_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nwritten data/_drinks_gate2_result.json", flush=True)
