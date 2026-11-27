"""gnrpa-spec 探针5b（不提交）：确认 status=2=稳定化早停——distill 同例 stabilization=1 vs 3。"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
V3 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v3"
os.environ["GKMS_ROOT"] = str(ROOT / "data" / "GKMSMainWheel")
for k in ("GKMSCLIGPU_LIB", "GKMS_NATIVE_LIB", "UINET_NATIVE_LIB"):
    os.environ[k] = str(V3 / "vendor" / "gkmscore.dll")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
from gkbench import engine
engine.setup()
from gkbench.save import expand_loadout
from GakumasCLI.scenario.hif import build_hif_loadout_session
from GakumasCLI.scenario import policy_search as PS
DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line); saves[str(r.get("id"))] = r
nat, ns = engine.native(); master = engine.master()
distill = PS.load_prior(str(ROOT / "data" / "_gnrpa_prior_distill.json"))
lo = expand_loadout(saves["AS-WDKWQYW5"]["loadout"])
sess, _ = build_hif_loadout_session(master, lo, 3601220)
for stab in (3, 1):
    ns._cache = None; ns._root_prior = None
    path, st = ns.policy_search(sess, transitions=2_000_000, seed=182, variant="gnrpa",
                                stabilization=stab, prior=distill)
    print(f"stab={stab} status={st['status']} best={st['best_score']:,} exp={st['expansions']:,} "
          f"top_calls={st['top_level_calls']} rollouts={st['rollouts']} wall={st['elapsed_seconds']:.2f}", flush=True)