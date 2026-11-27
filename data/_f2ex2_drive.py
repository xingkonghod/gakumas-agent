"""f2-ex2 跑分驱动：顺序跑 A hif( resume ) → A hajime → B hif → B hajime，
网络中断/连续出错自动 backoff + --resume 续跑，直到每阶段 done==total。探针不提交。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(r"D:\Games\gakumas-agent")
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
CLI = ROOT / "data" / "GKMSMainWheel" / "GakumasCLI"
SERVER = "https://hiro.matto.top/gkbench"
TOK = (Path.home() / ".config/gkbench/token").read_text().strip()
ENV = dict(os.environ,
           GKMS_ROOT=str(ROOT / "data" / "GKMSMainWheel"),
           GKMSCLIGPU_LIB=str(CLI / "native" / "build" / "gkmscore.dll"),
           PYTHONPATH=str(ROOT / "data" / "bench_repo"),
           PYTHONIOENCODING="utf-8")
EX = r"..\..\bench_repo\submissions\gkagent-expectimax\algo.py:ExpectimaxAlgo:worlds=6,mode=eval,threads=4,use_prior=0"
SD = r"..\..\bench_repo\submissions\gkagent-ex-seed\algo.py:ExSeedAlgo:procs=8,use_prior=0"
STAGES = [
    ("a_hif", "hif", EX, "3671171720ab"),
    ("a_hajime", "hajime", EX, None),
    ("b_hif", "hif", SD, None),
    ("b_hajime", "hajime", SD, None),
]


def status(ev):
    try:
        j = httpx.get(f"{SERVER}/api/evals/{ev}", headers={"Authorization": f"Bearer {TOK}"}, timeout=60).json()
        return len(j.get("done") or []), int(j.get("total") or 0)
    except Exception:  # noqa: BLE001
        return -1, -1


def core_ids(setname):
    cfg = next((x for x in httpx.get(f"{SERVER}/api/sets", timeout=60).json()
                if x.get("set") == setname), {})
    return cfg.get("core") or []


for name, setname, spec, ev in STAGES:
    log = ROOT / "data" / f"_f2ex2_eval_{name}.log"
    for attempt in range(12):
        cmd = [PY, "-m", "gkbench", "eval", "--set", setname, "--algo", spec, "--seeds", "2", "--parallel", "6"]
        if ev:
            # resume 客户端按全集枚举槽位；用 --only 核心题单过滤回 eval 的原 scope
            cmd += ["--resume", ev, "--only", ",".join(core_ids(setname))]
        print(f"=== {name} attempt {attempt} eval={ev} {time.strftime('%H:%M:%S')} ===", flush=True)
        with open(log, "ab") as lf:
            lf.write(f"\n=== attempt {attempt} {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode("utf-8"))
            lf.flush()
            try:
                subprocess.call(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(CLI), env=ENV)
            except Exception as e:  # noqa: BLE001
                print(f"  driver: subprocess error {e}", flush=True)
        text = log.read_text(encoding="utf-8", errors="replace")
        ids = re.findall(r"评测 ([0-9a-f]{12})", text)
        if ids:
            ev = ids[-1]
        done, total = status(ev) if ev else (-1, -1)
        print(f"  {name}: done={done}/{total}", flush=True)
        if done >= total and total > 0:
            break
        wait = min(300, 30 * (2 ** min(attempt, 4)))
        print(f"  未完成，{wait}s 后续跑", flush=True)
        time.sleep(wait)
    print(f"=== {name} FINISHED done={done}/{total} ===", flush=True)
print("ALL DONE", flush=True)