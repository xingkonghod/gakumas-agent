"""GKMS 引擎冒烟（f2-ex2）：gkbench.engine 接入 + F0 已知种子建局 + GNRPA + worlds 导出/导入。探针不提交。"""
from __future__ import annotations

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

t0 = time.perf_counter()
engine.setup()
print(f"setup: {time.perf_counter() - t0:.2f}s")
t0 = time.perf_counter()
nat, ns = engine.native()
print(f"native: {time.perf_counter() - t0:.2f}s rules={nat.exam_rules_version} rules_ok={ns.rules_ok}")
pr = engine.prior()
print("prior ok:", pr is not None)
print("provenance:", engine.provenance())

from gkbench.save import expand_loadout  # noqa: E402

seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {}
with (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

PID = sys.argv[1] if len(sys.argv) > 1 else "AS-227HBGHS"
TRANS = int(sys.argv[2]) if len(sys.argv) > 2 else 50000
group = seeds["problems"][PID][0]
seed = int(group["seed"])
check = group["check"]
lo = expand_loadout(saves[PID]["loadout"])
print(f"题 {PID} seed={seed} check.hand={check['hand']}")

t0 = time.perf_counter()
session, meta = engine.build(lo, seed)
print(f"build: {time.perf_counter() - t0:.2f}s limit_turn={meta.get('limit_turn')} npc={meta.get('npc_count')}")
hand = [c["produce_card_id"] for c in session.deck.hand]
print("engine hand:", hand)
print("hand MATCH" if hand == check["hand"] else "hand MISMATCH")

t0 = time.perf_counter()
path, st = ns.policy_search(session, transitions=TRANS, seed=182, variant="gnrpa", stabilization=3, prior=pr)
print(f"GNRPA: {time.perf_counter() - t0:.2f}s status={st['status']} best={st['best_score']} "
      f"exp={st['expansions']} roll={st['rollouts']} unsup={st.get('unsup_line')}/{st.get('unsup_info')}")
print("path[:12]:", path[:12])

s2, _ = engine.build(lo, seed)
score = None
try:
    for a in path:
        if a[0] == "play":
            s2.play(int(a[1]))
        elif a[0] == "drink":
            s2.use_drink(int(a[1]))
        elif a[0] == "end":
            s2.end_turn()
        elif a[0] == "select":
            s2.select(list(a[1]))
    score = s2.state.score
except Exception as e:  # noqa: BLE001
    print("replay error:", type(e).__name__, e)
print("replay score:", score, "vs search best:", st["best_score"],
      "finished:", s2.observe().get("finished"))

from gkbench.worlds import export_world, import_world, sample_world  # noqa: E402

w = sample_world(session, random.Random(42))
b = export_world(w)
w2 = import_world(b)
print(f"world roundtrip: {len(b)} bytes, public obs equal: {w2.observe() == w.observe()}")
print("world deck order differs from true:",
      [c["produce_card_id"] for c in w.deck.deck] != [c["produce_card_id"] for c in session.deck.deck])
print("SMOKE OK")