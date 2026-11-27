"""prior 开/关对比（F0 第3回合，GNRPA 1s/4s）。探针不提交。"""
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
pr = engine.prior()
seeds = json.loads((ROOT / "data/bench_local/gkbench_dl/hif/seeds.json").read_text(encoding="utf-8"))
saves = {str(json.loads(l)["id"]): json.loads(l)
         for l in (ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl").read_text(encoding="utf-8").splitlines()}
lo = expand_loadout(saves["AS-227HBGHS"]["loadout"])
s, _ = engine.build(lo, int(seeds["problems"]["AS-227HBGHS"][0]["seed"]))
for a in [("play", 1), ("drink", 3), ("play", 0)]:
    s.step(a, observe=False)
for label, prior in (("prior", pr), ("no-prior", None)):
    for sec in (1.0, 4.0):
        ns._cache = None
        path, st = ns.policy_search(s, deadline=sec, seed=182, variant="gnrpa", stabilization=3, prior=prior)
        s2 = s.clone()
        for a in path:
            s2.step(tuple(a), observe=False)
        print(f"{label} {sec}s: best={st['best_score']} replay={s2.state.score} exp={st['expansions']}")