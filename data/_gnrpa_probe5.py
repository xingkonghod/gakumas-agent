"""gnrpa-spec 探针5（不提交）：L3③ distill status=2 早停病理根因（廉价，不深究）。

L1 门 distill 2 次 status=2（tail STATUS map=deadline，但 policy_search deadline=None）：
WDKWQYW5/3601220 exp=66733 wall0.12s；WNK6ARRZ/1063386126 exp=317852 wall0.77s（远低于 2M）。
重跑这 2 例 {p0, distill}，捕完整 stats（repetition_stops/rollouts/incomplete/incumbent/unsup/curve/n_keys）定早停原因。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
V3 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v3"
os.environ["GKMS_ROOT"] = str(ROOT / "data" / "GKMSMainWheel")
for k in ("GKMSCLIGPU_LIB", "GKMS_NATIVE_LIB", "UINET_NATIVE_LIB"):
    os.environ[k] = str(V3 / "vendor" / "gkmscore.dll")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.save import expand_loadout  # noqa: E402
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from GakumasCLI.scenario import policy_search as PS  # noqa: E402

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

CASES = [("AS-WDKWQYW5", 3601220), ("AS-WNK6ARRZ", 1063386126)]


def main():
    nat, ns = engine.native()
    master = engine.master()
    distill = PS.load_prior(str(ROOT / "data" / "_gnrpa_prior_distill.json"))
    out = []
    for pid, seed in CASES:
        lo = expand_loadout(saves[pid]["loadout"])
        sess, _ = build_hif_loadout_session(master, lo, seed)
        for nm, prior in (("p0", None), ("distill", distill)):
            ns._cache = None
            ns._root_prior = None
            path, st = ns.policy_search(sess, transitions=2_000_000, seed=182, variant="gnrpa",
                                        stabilization=3, prior=prior)
            keep = {k: st.get(k) for k in ("status", "best_score", "expansions", "rollouts",
                                           "incomplete_rollouts", "repetition_stops", "incumbent_updates",
                                           "adaptation_choices", "top_level_calls", "top_level_adaptations",
                                           "n_keys", "unsup_line", "unsup_info", "elapsed_seconds")}
            keep["curve_len"] = len(st.get("curve") or [])
            keep["curve_tail"] = (st.get("curve") or [])[-3:]
            keep["pid"], keep["seed"], keep["arm"] = pid, seed, nm
            out.append(keep)
            print(json.dumps(keep, ensure_ascii=False), flush=True)
        del sess
    (ROOT / "data" / "_gnrpa_probe5.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved data/_gnrpa_probe5.json", flush=True)


if __name__ == "__main__":
    main()