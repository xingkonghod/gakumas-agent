# -*- coding: utf-8 -*-
"""gkmsps pilot 驱动（lead 接管 pilot 死掉的监视器）：等内存 → prior 消融 → 主 gen 1000 局。
完成后写 _gkmsps_drive_status.json；后续（npz/训练/门）由 gkmsps-pilot 智能体续做。探针不提交。"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


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


def wait_ram(need: float, timeout_s: float = 3 * 3600) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        fg = free_gb()
        print(f"[{time.strftime('%H:%M:%S')}] free {fg:.2f} GB (need {need:.1f})", flush=True)
        if fg >= need:
            return True
        time.sleep(90)
    return False


def run(args: list[str]) -> int:
    print("+ " + " ".join(args), flush=True)
    return subprocess.call(args, cwd=str(ROOT))


def main() -> int:
    status = {"started": time.strftime("%Y-%m-%d %H:%M:%S")}
    sp = ROOT / "data" / "_gkmsps_drive_status.json"

    # 1. 等内存（15.4GB 机器 + 用户应用 + v2 托管并行约束；消融 workers=3 需 3.0GB）
    if not wait_ram(3.0, 4 * 3600):
        status["error"] = "timeout waiting RAM (4h)"
        sp.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1

    # 2. prior 消融（50v50，workers=8；内存不够则重试）
    ab_ok = False
    for attempt in range(6):
        rc = run([PY, "-B", r"data\_gkmsps_prior_ablate.py", "--workers", "3"])
        if rc == 0:
            ab_ok = True
            break
        print(f"ablate rc={rc}，等 90s 重试", flush=True)
        if not wait_ram(3.0, 1800):
            break
    if not ab_ok:
        status["error"] = "ablation failed"
        sp.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    ab = json.loads((ROOT / "data" / "_gkmsps_labels_ab" / "ablation.json").read_text(encoding="utf-8"))
    winner = ab["winner"]
    status["ablation"] = {k: ab[k] for k in ("prior_on", "prior_off", "mean_diff_off_minus_on",
                                             "wins_off", "wins_on", "ties", "winner", "paired_seed_match")}
    print(f"prior winner = {winner}", flush=True)

    # 3. 主 gen 1000 局（workers 按空闲内存定，留 1.5GB 余量，安全阀 2.5h）
    if not wait_ram(3.0, 1800):
        status["error"] = "timeout waiting RAM for gen"
        sp.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    workers = min(8, max(3, int((free_gb() - 1.5) / 0.5)))
    rc = run([PY, "-B", r"data\_gkmsps_gen_run.py",
              "--out", r"data\_gkmsps_labels", "--shard", "pilot1",
              "--episodes", "1000", "--workers", str(workers),
              "--worlds", "8", "--transitions", "5000",
              "--pool", r"data\_gkmsps_pool\pool.bench.v1.jsonl",
              "--prior", winner, "--max-hours", "2.5"])
    status["gen_rc"] = rc
    status["gen_workers"] = workers
    status["gen_prior"] = winner
    status["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    sp.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"gen rc={rc}; status -> {sp}", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
