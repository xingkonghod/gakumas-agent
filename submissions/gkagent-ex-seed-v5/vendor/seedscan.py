"""Running seed_scan over all seeds in the background: one process per range, polled without waiting.

    job = Scan(k, pre, seen, skip, pool, turns, procs=N)     starts at once
    job.poll()            None while a process still runs; then the sorted list of matching seeds
    job.stop()            ends the processes that still run (by their own handles)

The kernel is ``seed_scan`` (``seed_scan.exe`` on Windows): the one beside this file is used as is
(shipped prebuilt for Windows); otherwise it is built from seed_scan.c into a temp directory with
the first of gcc / clang / cl found (or the compiler named by EXSEED_CC).

Extracted from UIHorizon-v2.2b vendor/bench/seedscan.py (AGPL-3.0-or-later), kernel-dir renamed.
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "seed_scan.c"
_KERNEL_DIR = Path(tempfile.gettempdir()) / "gkagent-ex-seed-kernel"
EXE = _KERNEL_DIR / ("seed_scan.exe" if os.name == "nt" else "seed_scan")
LOCAL_EXE = HERE / ("seed_scan.exe" if os.name == "nt" else "seed_scan")
NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


def kernel():
    """The path of the kernel: the shipped one beside this file, else a temp-dir build, else a fresh build."""
    if LOCAL_EXE.exists():
        if os.name != "nt" and not os.access(LOCAL_EXE, os.X_OK):
            os.chmod(LOCAL_EXE, 0o755)
        return LOCAL_EXE
    if EXE.exists():
        if os.name != "nt" and not os.access(EXE, os.X_OK):
            os.chmod(EXE, 0o755)
        return EXE
    _KERNEL_DIR.mkdir(parents=True, exist_ok=True)
    cmds = []
    cc = os.environ.get("EXSEED_CC")
    if cc:
        cmds.append([cc, "-O3", str(SRC), "-o", str(EXE)])
    cmds += [["clang", "-O3", str(SRC), "-o", str(EXE)],
             ["gcc", "-O3", str(SRC), "-o", str(EXE)],
             ["cl", "/nologo", "/O2", str(SRC), "/Fe:" + str(EXE)]]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, check=True, cwd=str(_KERNEL_DIR), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, **NO_WINDOW)
            except (OSError, subprocess.CalledProcessError):
                continue
            if EXE.exists():
                return EXE
    return None


class Scan:
    def __init__(self, k, pre, seen, skip, pool=None, turns=None, procs=None, lo=0, hi=1 << 32):
        exe = kernel()
        if exe is None:
            raise RuntimeError("no seed_scan kernel and no C compiler (gcc / clang / cl)")
        names = {v: i for i, v in enumerate(sorted(set(pre)))}
        if len(names) > 255 or any(x not in names for x in seen):
            raise ValueError("observed cards not in the deck")
        ints = lambda xs: ",".join(str(names[x]) for x in xs) or "-"               # noqa: E731
        procs = max(1, int(procs or (os.cpu_count() or 2) - 1))
        self.started = time.perf_counter()
        self.seconds = None
        self.dir = tempfile.mkdtemp(prefix="exseed_scan_")
        self.jobs = []
        step = -(-(hi - lo) // procs)
        for i in range(procs):
            a, b = lo + i * step, min(hi, lo + (i + 1) * step)
            if a >= b:
                break
            args = [str(exe), str(int(k)), ints(pre), ints(seen), ints([x for x in skip if x in names]), str(a), str(b)]
            if pool and turns:
                args += [",".join(str(int(t)) for t in pool), ",".join(str(int(t)) for t in turns)]
            out = open(os.path.join(self.dir, f"{i}.txt"), "w")
            self.jobs.append((subprocess.Popen(args, stdout=out, stderr=subprocess.DEVNULL, **NO_WINDOW), out))
        self._result = None
        atexit.register(self.stop)

    def poll(self):
        if self._result is not None:
            return self._result
        if any(p.poll() is None for p, _f in self.jobs):
            return None
        seeds = []
        for i, (p, f) in enumerate(self.jobs):
            f.close()
            if p.returncode != 0:
                raise RuntimeError(f"seed_scan exited with {p.returncode}")
            for line in open(os.path.join(self.dir, f"{i}.txt")):
                if line.strip() and not line.startswith("#"):
                    seeds.append(int(line))
        self.seconds = time.perf_counter() - self.started
        shutil.rmtree(self.dir, ignore_errors=True)
        self._result = sorted(seeds)
        return self._result

    def stop(self):
        if self._result is not None:
            return
        for p, f in self.jobs:
            if p.poll() is None:
                p.terminate()
            f.close()
        shutil.rmtree(self.dir, ignore_errors=True)