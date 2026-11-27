"""版本A（GKMS PIMC expectimax）本地整局冒烟：真裁判 Referee + 本地 worlds。探针不提交。"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
os.environ["GKMS_ROOT"] = str(ROOT / "data" / "GKMSMainWheel")
os.environ["GKMSCLIGPU_LIB"] = str(ROOT / "data" / "GKMSMainWheel" / "GakumasCLI" / "native" / "build" / "gkmscore.dll")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gkbench import engine  # noqa: E402
from gkbench.referee import Referee  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

engine.setup()
HERE = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax"
spec = importlib.util.spec_from_file_location("algo_gkms", HERE / "algo_gkms.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {}
with (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

PID = sys.argv[1] if len(sys.argv) > 1 else "AS-227HBGHS"
MODE = sys.argv[2] if len(sys.argv) > 2 else "eval"
WORLDS = int(sys.argv[3]) if len(sys.argv) > 3 else 6
group = seeds["problems"][PID][0]
seed = int(group["seed"])
lo = expand_loadout(saves[PID]["loadout"])

algo = m.ExpectimaxAlgo(worlds=WORLDS, mode=MODE, threads=12)
ref = Referee(lo, seed)
ctx = Ctx(ref, ref.loadout_public, 5.0, random.Random("a"), random.Random("w"), algo, seed)
ctx.obs = ref.obs()
algo.begin(ctx)
steps = []
t_game = time.perf_counter()
while not ref.finished and ref.decisions < 300:
    obs = ref.obs()
    ctx.obs = obs
    t0 = time.perf_counter()
    d = algo.decide(ctx)
    ms = (time.perf_counter() - t0) * 1000
    res = ref.step(d.action)
    steps.append((obs["exam"]["turn"], d.action, ms, d.meta))
    if "error" in d.meta:
        print("ERROR meta:", d.meta["error"])
print(f"题 {PID} mode={MODE} worlds={WORLDS}: 终局 {ref.score:,}  决策 {len(steps)}  "
      f"总耗时 {time.perf_counter() - t_game:.1f}s")
errs = [s for s in steps if "error" in s[3]]
ends = [s for s in steps if s[1][0] == "end"]
print(f"错误 {len(errs)}，end 次数 {len(ends)}，最大步 {max(s[2] for s in steps):.0f}ms，"
      f"平均步 {sum(s[2] for s in steps) / len(steps):.0f}ms")
for t, a, ms, meta in steps[:6]:
    print(f"  T{t} {a} {ms:.0f}ms mode={meta.get('mode')} worlds={meta.get('worlds')} "
          f"sec={meta.get('seconds_per_search')}")
print("A SMOKE OK")