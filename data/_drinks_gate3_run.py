"""M6 阶段3① 饮料搜索预算杠杆单变量门。不提交。

4 杠杆 arm（root_only / drink_first / top2 / top3）各跑 SAFE 子集 ×2 seed auto，
配对基线 off（data/_gate2_expectimax-analytic_off.json——off 无饮料，杠杆无关，
复用阶段2 基线；none-lever 已验证与基线 auto 逐位一致）。
cluster bootstrap 按题重抽 10000 次 95% CI；**CI 下界>0 才采纳**。
greedy 阴性对照结构不变（杠杆只改 ExpectimaxPolicy，greedy 无搜索）。
内存守卫 free<0.9GB 退出。
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
OFF = ROOT / "data/_gate2_expectimax-analytic_off.json"
LEVERS = ["root_only", "drink_first", "top2", "top3"]

import numpy as np  # noqa: E402

off_data = json.loads(OFF.read_text(encoding="utf-8"))
off = {(e["problem"], int(e["seed"])): e for e in off_data["episodes"]}
rng = np.random.default_rng(20261126)
result = {"free_gb_at_start": round(free_gb, 2), "baseline_off_mean": float(
    np.mean([int(e["score"]) for e in off.values()])), "levers": {}}

for lever in LEVERS:
    out = ROOT / f"data/_gate3_auto_{lever}.json"
    print(f"\n=== lever {lever} ===", flush=True)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/local_bench.py"),
         "--problems", str(SUBSET), "--algos", "expectimax-analytic",
         "--drinks", "auto", "--drink-lever", lever,
         "--episodes", "2", "--seed-base", "1000", "--out", str(out)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        print(proc.stdout[-2000:]); print(proc.stderr[-2000:])
        raise SystemExit(f"lever {lever} failed rc={proc.returncode}")
    data = json.loads(out.read_text(encoding="utf-8"))
    auto = {(e["problem"], int(e["seed"])): e for e in data["episodes"]}
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
    fb_auto = sum(int(auto[k].get("fallbacks", 0)) for k in keys)
    fb_off = sum(int(off[k].get("fallbacks", 0)) for k in keys)
    dec_auto = sum(int(auto[k].get("decisions", 0)) for k in keys)
    drinks_auto = sum(
        sum(1 for x in str(auto[k].get("route", "")).split() if x.startswith("d"))
        for k in keys
    )
    row = {
        "episodes": len(keys), "problems": len(problems),
        "mean_auto": float(np.mean([int(auto[k]["score"]) for k in keys])),
        "mean_diff": float(diffs.mean()), "ci95": [float(lo), float(hi)],
        "wins": int((diffs > 0).sum()), "losses": int((diffs < 0).sum()),
        "ties": int((diffs == 0).sum()),
        "crashes_auto": sum(1 for k in keys if not auto[k].get("finished", True)),
        "fallbacks_auto": fb_auto, "fallbacks_off": fb_off,
        "fallback_rate_auto": round(fb_auto / max(dec_auto, 1), 4),
        "drink_steps_auto": drinks_auto,
        "adopt_ci_lower_gt0": bool(lo > 0),
    }
    result["levers"][lever] = row
    print(f"  {lever}: mean_diff={diffs.mean():.1f} CI95=[{lo:.1f},{hi:.1f}] "
          f"W{(diffs>0).sum()}/L{(diffs<0).sum()}/T{(diffs==0).sum()} "
          f"fallback={fb_auto}({row['fallback_rate_auto']*100:.1f}%) drinks={drinks_auto} "
          f"adopt={row['adopt_ci_lower_gt0']}", flush=True)
    (ROOT / "data/_drinks_gate3_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

print("\nwritten data/_drinks_gate3_result.json", flush=True)
