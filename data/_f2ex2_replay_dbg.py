"""调试 GNRPA 路径回放：逐步用 session.step（裁判口径），打印分歧点。探针不提交。"""
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
group = seeds["problems"][PID][0]
seed = int(group["seed"])
lo = expand_loadout(saves[PID]["loadout"])
session, meta = engine.build(lo, seed)
path, st = ns.policy_search(session, transitions=50000, seed=182, variant="gnrpa", stabilization=3, prior=pr)
print("best:", st["best_score"], "path len:", len(path))

s2, _ = engine.build(lo, seed)
for i, a in enumerate(path):
    legal = [tuple(x) for x in s2.legal_actions()]
    if tuple(a) not in legal and a[0] != "select":
        print(f"DIVERGE at step {i}: action={a} turn={s2.turn} score={s2.state.score}")
        print("  legal:", legal)
        print("  hand:", [c['produce_card_id'] for c in s2.deck.hand])
        print("  playable:", s2.observe().get("playable"), "stamina:", s2.state.stamina)
        print("  path around:", path[max(0, i - 4):i + 4])
        break
    try:
        s2.step(tuple(a), observe=False)
    except Exception as e:  # noqa: BLE001
        print(f"STEP ERROR at {i}: {a} -> {type(e).__name__}: {e}")
        break
else:
    print("replay finished, score:", s2.state.score, "finished:", s2.finished)

# 对比：native 核心自己走这条路径（如果接口允许）
print("--- native session replay ---")
from GakumasCLI.native import portable as P  # noqa: E402
s3, _ = engine.build(lo, seed)
nat.load_round(s3)
nat.import_bytes(P.encode_session(s3))
print("native core loaded; trying nat.step interface:", [m for m in dir(nat) if "step" in m or "play" in m or "action" in m])