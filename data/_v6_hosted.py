"""v6 托管驱动（探针，不提交）。用法：
    .venv\\Scripts\\python.exe data\\_v6_hosted.py gate [parallel]      # 15 题小样（--only）
    .venv\\Scripts\\python.exe data\\_v6_hosted.py full [parallel]      # 全量 240 槽（不带 --only，单 run）
    .venv\\Scripts\\python.exe data\\_v6_hosted.py resume <eval> [parallel]
注意：**不要重跑已结算的槽**（同题同种子「取最新」会覆盖旧分）；full 只在没跑过时用。
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "bench_repo"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
ALGO = "gkagent-ex-seed-v6"
ALGO_SPEC = rf"\Games\gakumas-agent\data\bench_repo\submissions\{ALGO}\algo.py:ExSeedV6Algo"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 门：10 个大决赛 + 3 个 MID + 3 个 lock>=4 怪题（每题目 2 个保密种子 = 30 槽）
GATE_IDS = [
    "AS-3EW6E6HV",   # 14.2M/11.4M 最大分
    "AS-3ZT8ZKB6",   # 12.2M/12.3M
    "AS-5KZSXANK",   # 11.8M 决赛
    "AS-YGF972ZK",   # 14.6M 决赛
    "AS-BZXB28YJ",   # 缺口 1.7M
    "AS-WDKWQYW5",   # 最大缺口 3.7M
    "AS-QQ6J5S39",   # 锁定前期怪物
    "AS-P8ZJTXNA",   # 12k 候选 monster（over 源）
    "AS-B8ZWDS3J",   # 缺口 1.0M
    "AS-XPRY8BRF",   # 5.3M 决赛
    "AS-AXME8QK2",   # MID 9.3M
    "AS-3G6FFZZT",   # MID 缺口 0.82M（且 1 槽失锁）
    "AS-YZESXMWW",   # MID 缺口 0.59M
    "AS-QV6QCSN9",   # lock>=4/5
    "AS-X9GNYH3W",   # lock 5/5
]


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


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "gate"
    par = "6"
    resume = None
    if mode == "resume":
        resume = sys.argv[2]
        if len(sys.argv) > 3:
            par = sys.argv[3]
    elif len(sys.argv) > 2:
        par = sys.argv[2]
    f = free_mb()
    print(f"free={f:.0f}MB mode={mode} parallel={par}", flush=True)
    if f < 700:
        print("内存不足 700MB，先等 120s", flush=True)
        time.sleep(120)
    cmd = [str(PY), "-m", "gkbench", "eval", "--set", "hif", "--algo", ALGO_SPEC,
           "--seeds", "2", "--parallel", par, "--budget", "10"]
    tag = mode
    if mode == "gate":
        cmd += ["--only", ",".join(GATE_IDS)]
    elif mode == "resume":
        # gkbench 的 --resume 会遍历**全部 505 题**（不按核心题单）→ 必须用 --only 限定到 120 核心题，
        # 否则会跑出 928 个非核心格子（服务器 404）并可能污染 run 的 n/均分。
        core = json.loads((ROOT / "out" / "_hif_core_ids.json").read_text(encoding="utf-8"))
        cmd += ["--resume", resume, "--only", ",".join(core)]
    log = ROOT / "out" / f"_v6_{tag.replace('/', '_')}_hosted.log"
    print("run:", " ".join(cmd), flush=True)
    t0 = time.time()
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n===== {mode} {time.strftime('%H:%M:%S')} master-run =====\n")
        fh.flush()
        proc = subprocess.Popen(cmd, cwd=str(BENCH), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", bufsize=1)
        for line in proc.stdout:  # type: ignore[union-attr]
            sys.stdout.write(line)
            sys.stdout.flush()
            fh.write(line)
            fh.flush()
        proc.wait()
    print(f"[{mode}] exit={proc.returncode} wall={time.time()-t0:.0f}s log={log}", flush=True)


if __name__ == "__main__":
    main()