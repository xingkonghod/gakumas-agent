"""f2-sl2 探针 1：修 GNRPA 路径回放 bug + 确认核分 + 重搜缓存口径。不提交。

冒烟脚本 _f2sl_engine_smoke.py 的回放用 s2.play/use_drink/end_turn/select 直调，
报 "illegal action play 0"。本探针对比三种回放：
  A 冒烟直调（复现 bug，定位第一个失败动作）
  B 正规 session.step(action, observe=False)（solver.replay_session / RoutePool.replay 同口径）
  C 步进后重搜（ns._cache=None 强制重导入，teacher.py 同口径）+ 路径核分
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
os.environ.setdefault("GKMSCLIGPU_LIB", str(ROOT / "data" / "_f2sl_tools" / "kernel" / "gkmscore.dll"))
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

from gkbench import engine  # noqa: E402

engine.setup()
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

PID = sys.argv[1] if len(sys.argv) > 1 else "AS-227HBGHS"
TRANS = int(sys.argv[2]) if len(sys.argv) > 2 else 50000

seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {}
with (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r
group = seeds["problems"][PID][0]
seed = int(group["seed"])
lo = expand_loadout(saves[PID]["loadout"])
master = engine.master()
nat, ns = engine.native()
print(f"rules={nat.exam_rules_version} pid={PID} seed={seed}")

session, meta = build_hif_loadout_session(master, lo, seed)
hand = [c["produce_card_id"] for c in session.deck.hand]
print("hand:", hand, "MATCH" if hand == group["check"]["hand"] else "MISMATCH")
print("legal at root:", session.legal_actions())

prior = engine.prior()
t0 = time.perf_counter()
ns._cache = None
path, stats = ns.policy_search(session, transitions=TRANS, seed=182, variant="gnrpa",
                               stabilization=3, prior=prior)
dt = time.perf_counter() - t0
print(f"GNRPA {dt:.2f}s status={stats['status']} best={stats['best_score']} "
      f"exp={stats['expansions']} roll={stats['rollouts']} rate={stats['expansions']/max(dt,1e-9):.0f}/s")
print("path[:10]:", path[:10])

# A 冒烟直调（复现）
sA, _ = build_hif_loadout_session(master, lo, seed)
errA = None
for i, a in enumerate(path):
    try:
        if a[0] == "play":
            sA.play(int(a[1]))
        elif a[0] == "drink":
            sA.use_drink(int(a[1]))
        elif a[0] == "end":
            sA.end_turn()
        elif a[0] == "select":
            sA.select(list(a[1]))
    except Exception as e:
        errA = f"step#{i} {a}: {type(e).__name__}: {e}"
        break
print("A 直调:", errA or f"ok score={sA.state.score}")

# B 正规 step 回放
sB = session.clone()
t0 = time.perf_counter()
errB = None
for i, a in enumerate(path):
    try:
        sB.step(tuple(a), observe=False)
    except Exception as e:
        errB = f"step#{i} {a}: {type(e).__name__}: {e}"
        break
dtB = time.perf_counter() - t0
scoreB = int(sB.state.score)
print(f"B step回放: {errB or 'ok'} score={scoreB} finished={sB.finished} "
      f"vs best={stats['best_score']} {'SCORE_MATCH' if scoreB == stats['best_score'] else 'SCORE_DIFF'} ({dtB*1000:.0f}ms)")

# C 步进 3 个动作后重搜（缓存失效口径）
sC = session.clone()
prefix = []
for a in path[:3]:
    sC.step(tuple(a), observe=False)
    prefix.append(tuple(a))
ns._cache = None
t0 = time.perf_counter()
path2, st2 = ns.policy_search(sC, transitions=TRANS, seed=182 + 1009, variant="gnrpa",
                              stabilization=3, prior=prior)
dt2 = time.perf_counter() - t0
sC2 = sC.clone()
for a in path2:
    sC2.step(tuple(a), observe=False)
print(f"C 重搜 {dt2:.2f}s best={st2['best_score']} replay={int(sC2.state.score)} "
      f"{'MATCH' if int(sC2.state.score) == st2['best_score'] else 'DIFF'} finished={sC2.finished}")

# D 无 prior 对照
ns._cache = None
path3, st3 = ns.policy_search(session, transitions=TRANS, seed=182, variant="gnrpa", stabilization=3)
sD = session.clone()
for a in path3:
    sD.step(tuple(a), observe=False)
print(f"D 无prior best={st3['best_score']} replay={int(sD.state.score)} "
      f"{'MATCH' if int(sD.state.score) == st3['best_score'] else 'DIFF'}")

out = {"pid": PID, "seed": seed, "trans": TRANS, "best": stats["best_score"],
       "replay_score": scoreB, "replay_err": errB, "direct_err": errA,
       "research_best": st2["best_score"], "noprior_best": st3["best_score"],
       "rate": stats["expansions"] / max(dt, 1e-9)}
(ROOT / "data" / "_f2sl2_replay.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("written _f2sl2_replay.json")