"""版本B（自锁种子 + GKMS 全知搜索）本地整局冒烟：真裁判，算法不拿种子。探针不提交。"""
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
HERE = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed"
spec = importlib.util.spec_from_file_location("ex_seed_algo", HERE / "algo.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {}
with (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

PID = sys.argv[1] if len(sys.argv) > 1 else "AS-227HBGHS"
SI = int(sys.argv[2]) if len(sys.argv) > 2 else 0
group = seeds["problems"][PID][SI]
seed = int(group["seed"])
lo = expand_loadout(saves[PID]["loadout"])

algo = m.ExSeedAlgo(procs=12)
ref = Referee(lo, seed)
ctx = Ctx(ref, ref.loadout_public, 5.0, random.Random("a"), random.Random("w"), algo, seed)
assert not hasattr(ctx, "seed"), "sees_seed=False 不应拿种子"
ctx.obs = ref.obs()
t_begin = time.perf_counter()
algo.begin(ctx)
print(f"begin: {time.perf_counter() - t_begin:.2f}s  pre={len(algo.pre)} k={algo.k} pool={algo.pool_attr}")
steps = []
t_game = time.perf_counter()
while not ref.finished and ref.decisions < 300:
    obs = ref.obs()
    ctx.obs = obs
    t0 = time.perf_counter()
    d = algo.decide(ctx)
    ms = (time.perf_counter() - t0) * 1000
    ref.step(d.action)
    steps.append((obs["exam"]["turn"], d.action, ms, d.meta))
    if "error" in d.meta:
        print("ERROR:", d.meta["error"])
g = algo.g
print(f"题 {PID}#{SI} 真种子={seed}: 终局 {ref.score:,}  决策 {len(steps)}  总耗时 {time.perf_counter() - t_game:.1f}s")
print(f"state={g.state} lock_turn={g.lock_turn} locked_seed={g.locked_seed} "
      f"scan_s={g.scan_s} n_cands={g.n_cands} cut_n={g.cut_n} why={g.why}")
print("种子核对:", "MATCH" if g.locked_seed == seed else ("MISMATCH" if g.locked_seed else "NOT LOCKED"))
errs = [s for s in steps if "error" in s[3]]
ends = [s for s in steps if s[1][0] == "end"]
modes = {}
for s in steps:
    modes[s[3].get("mode")] = modes.get(s[3].get("mode"), 0) + 1
print(f"错误 {len(errs)}，end {len(ends)}，modes={modes}，最大步 {max(s[2] for s in steps):.0f}ms")
for t, a, ms, meta in steps[:10]:
    print(f"  T{t} {a} {ms:.0f}ms mode={meta.get('mode')} state={meta.get('seed_state')} "
          f"lock={meta.get('lock_turn')} target={meta.get('target')} cands={meta.get('candidates')}")
for t, a, ms, meta in steps:
    if ms > 4500:
        print(f"  SLOW T{t} {a} {ms:.0f}ms meta={json.dumps(meta, ensure_ascii=False)[:300]}")
print("B SMOKE OK")