"""锁定后搜索路径回放核对：best_score vs 路径真实终局分。探针不提交。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
os.environ["GKMS_ROOT"] = str(ROOT / "data" / "GKMSMainWheel")
os.environ["GKMSCLIGPU_LIB"] = str(ROOT / "data" / "GKMSMainWheel" / "GakumasCLI" / "native" / "build" / "gkmscore.dll")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gkbench import engine  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

engine.setup()
nat, ns = engine.native()
pr = engine.prior()
seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {}
with (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r
PID = "AS-227HBGHS"
seed = int(seeds["problems"][PID][0]["seed"])
lo = expand_loadout(saves[PID]["loadout"])

# 冒烟里锁定前的动作（T1 play1, T2 drink3, T2 play0）→ 第3回合开始
prefix = [("play", 1), ("drink", 3), ("play", 0)]
s, _ = engine.build(lo, seed)
for a in prefix:
    s.step(a, observe=False)
print("turn:", s.turn, "score:", s.state.score, "hand:", [c['produce_card_id'] for c in s.deck.hand])

for sec in (1.0, 4.0):
    t0 = time.perf_counter()
    path, st = ns.policy_search(s, deadline=sec, seed=182, variant="gnrpa", stabilization=3, prior=pr)
    print(f"search {sec}s: best={st['best_score']} exp={st['expansions']} pathlen={len(path)} "
          f"wall={time.perf_counter() - t0:.2f}s")
    s2 = s.clone()
    ok = True
    for i, a in enumerate(path):
        legal = [tuple(x) for x in s2.legal_actions()]
        if tuple(a) not in legal and a[0] != "select":
            print(f"  replay DIVERGE at {i}: {a} legal={legal[:8]} turn={s2.turn}")
            ok = False
            break
        s2.step(tuple(a), observe=False)
    if ok:
        print(f"  replay final={s2.state.score} finished={s2.finished} vs best={st['best_score']} "
              f"{'MATCH' if s2.state.score == st['best_score'] else 'DIFF'}")
    print("  path[:16]:", path[:16])