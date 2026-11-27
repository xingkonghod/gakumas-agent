"""候选数 vs 已见抽牌数（F0）：调 scan_min / hi。探针不提交。"""
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
sys.path.insert(0, str(ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed" / "vendor"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from gkbench import engine  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402
import draws  # noqa: E402
import opening  # noqa: E402
import seedscan  # noqa: E402

engine.setup()
master = engine.master()
seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {}
with (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r
PID = sys.argv[1] if len(sys.argv) > 1 else "AS-227HBGHS"
group = seeds["problems"][PID][0]
seed = int(group["seed"])
lo = expand_loadout(saves[PID]["loadout"])
opens = [opening.opening(master, lo, s) for s in (11, 0x9E3779B9, 123456789)]
pre, k = opens[0][0], opens[0][1]
pool, mutable = opening.turn_pool(opens[0][2])
inv = draws.invariant_hand([[c["produce_card_id"] for c in o[2].deck.hand] for o in opens])
session, meta = engine.build(lo, seed)
H0 = [c["produce_card_id"] for c in session.deck.hand]
D = [c["produce_card_id"] for c in session.deck.deck]
types = [int(t) for t in (session.deck.turn_parameter_types or [])]
print(f"pre={len(pre)} k={k} pool={pool} H0={H0} pile={len(D)} types={types}")

HI = int(sys.argv[2]) if len(sys.argv) > 2 else 1 << 31
for n in (0, 1, 2, 3, 4, 5, 6, 7):
    tr = draws.Draws(pre, inv)
    obs = {"hand": [{"id": x} for x in H0 + D[:n]], "deck": [{"id": x} for x in D[n:]]}
    tr.update(obs)
    t0 = time.perf_counter()
    scan = seedscan.Scan(k, pre, list(tr.seen), list(tr.skip.elements()), pool, types[:1], procs=16, hi=HI)
    while scan.poll() is None:
        time.sleep(0.05)
    hits = scan.poll()
    print(f"draws={n} seen={len(tr.seen)} skip={list(tr.skip.elements())}: "
          f"cands={len(hits)} scan={time.perf_counter() - t0:.2f}s true_in={seed in hits}")