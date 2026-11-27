# -*- coding: utf-8 -*-
"""一次性（T3 实时验收辅助）：监控 traffic.jsonl 的新 StepAuditionStart，
每出现一场新考试立即跑 build_exam_setup.py --current，让 bot 下一帧重载候选。

只读 traffic + 写 out/exam_setup.json（生产正常产物）；不改游戏/采集。
用法：python data/_t3_watch.py [max_minutes]
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")
PY = ROOT / ".venv" / "Scripts" / "python.exe"
MAX_MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 35.0


def count_audition_starts() -> int:
    if not TRAFFIC.is_file():
        return 0
    n = 0
    with open(TRAFFIC, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "StepAuditionStart" in line:
                n += 1
    return n


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    base = count_audition_starts()
    print(f"[t3-watch] start, existing StepAuditionStart={base}", flush=True)
    deadline = time.monotonic() + MAX_MIN * 60
    seen = base
    while time.monotonic() < deadline:
        time.sleep(3)
        try:
            n = count_audition_starts()
        except OSError:
            continue
        if n > seen:
            seen = n
            ts = time.strftime("%H:%M:%S")
            print(f"[t3-watch] {ts} NEW exam #{n} -> build_exam_setup --current", flush=True)
            r = subprocess.run(
                [str(PY), str(ROOT / "scripts" / "build_exam_setup.py"), "--current"],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120,
            )
            tail = (r.stdout or "").strip().splitlines()
            for ln in tail[-6:]:
                print(f"[t3-watch]   {ln}", flush=True)
            if r.returncode != 0:
                print(f"[t3-watch]   exit={r.returncode} err={(r.stdout or '')[-300:]}", flush=True)
    print("[t3-watch] deadline reached, exit", flush=True)


if __name__ == "__main__":
    main()