"""tail 时钟纪元测定：DLL steady_clock vs Python monotonic / time。探针不提交。"""
from __future__ import annotations
import ctypes as C
import json, os, sys, time
from pathlib import Path
ROOT = Path(r"D:\Games\gakumas-agent")
os.environ["GKMS_ROOT"] = str(ROOT / "data" / "GKMSMainWheel")
os.environ["GKMSCLIGPU_LIB"] = str(ROOT / "data" / "GKMSMainWheel" / "GakumasCLI" / "native" / "build" / "gkmscore.dll")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gkbench import engine
from gkbench.save import expand_loadout
engine.setup()
nat, ns = engine.native()
seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {str(json.loads(l)["id"]): json.loads(l)
         for l in (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").read_text(encoding="utf-8").splitlines()}
lo = expand_loadout(saves["AS-227HBGHS"]["loadout"])
s, _ = engine.build(lo, int(seeds["problems"]["AS-227HBGHS"][0]["seed"]))
for a in [("play", 1), ("drink", 3), ("play", 0)]:
    s.step(a, observe=False)

from GakumasCLI.native import tail_native as TN
from GakumasCLI.native import portable as P
print("python monotonic:", time.monotonic(), "time.time:", time.time())
TN._bind(nat)
own = s.search_tables()
try:
    for label, now in (("monotonic", time.monotonic()), ("time.time", time.time())):
        params = TN.TailParams(node_cap=20_000_000, deadline=now + 2.0, tt_capacity=1 << 23,
                               use_tt=1, threads=4, items_per_thread=0, pad=0)
        r = TN.TailResult()
        t0 = time.perf_counter()
        rc = nat.lib.gk_tail_exact(own.core, C.byref(params), C.byref(r))
        print(f"deadline via {label}: rc={rc} ({TN.STATUS.get(rc)}) wall={time.perf_counter() - t0:.2f}s "
              f"score={r.best_score} nodes={r.nodes}")
finally:
    own.free()