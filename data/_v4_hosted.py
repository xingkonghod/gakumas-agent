"""v4 托管分块驱动（探针，不提交）。

理由（docs GKBENCH §11）：服务器 eval 注册表是内存 map，重启即清（404）；但已上传 episodes 落盘、
排行按 algo+rules 合并、同题同种子取最新 → 分块安全。**但「取最新」也意味着重跑会覆盖旧分**
（墙钟 anytime 非确定）→ 驱动只跑「缺的题」：每块前先查排行 run 列表 + 逐 run episodes 得 done 槽位，
只把仍有缺槽的题放进 `--only`。

用法：.venv\\Scripts\\python.exe data\\_v4_hosted.py [algo_name] [chunk] [max_chunks]
缺省 algo=gkagent-ex-seed-v4 chunk=4。
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "data" / "bench_repo"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
API = "https://hiro.matto.top/gkbench/api"
SET = "hif"
SEEDS = 2
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ALGO = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v4"
CHUNK = int(sys.argv[2]) if len(sys.argv) > 2 else 4
MAX_CHUNKS = int(sys.argv[3]) if len(sys.argv) > 3 else 200
PARALLEL = int(sys.argv[4]) if len(sys.argv) > 4 else 3
_tag = ALGO.rsplit("-", 1)[-1].capitalize()          # v4 → V4
ALGO_SPEC = rf"\Games\gakumas-agent\data\bench_repo\submissions\{ALGO}\algo.py:ExSeed{_tag}Algo"


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


def get(path, tries=6):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(API + path, timeout=60) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            time.sleep(5)
    raise RuntimeError("api fail " + path)


def done_slots():
    """所有本 algo 的 run episodes → {(id, slot)}。
    数据源用 /api/runs（新建 run 立即出现、episode 上传即见），不用排行行（实测有 ~1 分钟延迟，
    会害驱动重跑上一块的题并覆盖旧分）。不可达返回 None。"""
    try:
        d = get("/runs?set=" + SET)
        rows = d if isinstance(d, list) else d.get("runs", [])
    except Exception as e:  # noqa: BLE001
        print("runs fail:", e, flush=True)
        return None
    runs = [r for r in rows if str(r.get("algo", "")).endswith(":" + ALGO)]
    done = set()
    for r in runs:
        rn = r.get("run")
        if not rn:
            continue
        try:
            dd = get("/runs/" + rn)
        except Exception:  # noqa: BLE001
            continue
        for e in dd.get("episodes") or []:
            if e.get("finished") and e.get("score") is not None:
                done.add((e["id"], int(e["seed_index"])))
    return done


def main():
    ids = json.loads((ROOT / "out" / "_hif_ids.json").read_text(encoding="utf-8"))
    log = ROOT / "out" / f"_{ALGO}_hosted.log"
    t0 = time.time()
    prev_first, prev_done_n = None, -1
    for c in range(MAX_CHUNKS):
        f = free_mb()
        if f < 700:
            print(f"[mem] free {f:.0f}MB < 700MB, sleep 120s ...", flush=True)
            time.sleep(120)
        done = done_slots()
        if done is None:
            time.sleep(90)
            continue
        missing = [pid for pid in ids if not all((pid, s) in done for s in range(SEEDS))]
        if missing and missing[0] == prev_first and len(done) <= prev_done_n:
            # 上一块的局没被服务器登记（上传延迟/评测被清）：等一下再查，避免原地重跑覆盖旧分
            print(f"[guard] done 未增长（{len(done)}<= {prev_done_n}）且同一缺题，sleep 60s 重查", flush=True)
            time.sleep(60)
            continue
        prev_first, prev_done_n = (missing[0] if missing else None), len(done)
        print(f"=== chunk {c}: done_slots={len(done)} missing_problems={len(missing)} "
              f"free={f:.0f}MB elapsed={time.time()-t0:.0f}s ===", flush=True)
        if not missing:
            print("ALL DONE", flush=True)
            break
        take = missing[:CHUNK]
        cmd = [str(PY), "-m", "gkbench", "eval", "--set", SET, "--algo", ALGO_SPEC,
               "--seeds", str(SEEDS), "--parallel", str(PARALLEL), "--budget", "10",
               "--only", ",".join(take)]
        print("run:", " ".join(take), flush=True)
        ts = time.time()
        proc = subprocess.run(cmd, cwd=str(BENCH), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"\n===== chunk {c} {time.strftime('%H:%M:%S')} {' '.join(take)} =====\n{out}\n")
        tail = [ln for ln in out.strip().splitlines() if ln.strip()][-4:]
        print("\n".join(tail), flush=True)
        print(f"[chunk {c}] exit={proc.returncode} wall={time.time()-ts:.0f}s", flush=True)
        time.sleep(5)
    print("driver finished; total wall", round(time.time() - t0), "s", flush=True)


if __name__ == "__main__":
    main()
