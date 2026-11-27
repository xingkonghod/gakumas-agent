"""core_tail 精确尾搜索验证（F0 第3回合局面）。探针不提交。"""
from __future__ import annotations
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
from GakumasCLI.native.tail_native import tail_exact
t0 = time.perf_counter()
p, sc, st = tail_exact(s, seconds=5.0, nat=nat, threads=4)
print(f"tail: status={st['status']} score={sc} nodes={st['nodes']} leaves={st['leaves']} "
      f"pathlen={len(p)} wall={time.perf_counter() - t0:.2f}s")
s2 = s.clone()
for a in p:
    s2.step(tuple(a), observe=False)
print("replay:", s2.state.score, "finished:", s2.finished, "MATCH" if s2.state.score == sc else "DIFF")