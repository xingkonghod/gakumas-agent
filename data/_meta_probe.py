"""Probe: public_meta per core problem (probe, not committed) — 用于按考试规模分配起点数。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
import os  # noqa: E402
os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

DL = ROOT / "data/bench_local/gkbench_dl/hif"
ids = json.loads((ROOT / "out" / "_hif_ids.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r
out = []
for pid in ids:
    lo = expand_loadout(saves[pid]["loadout"])
    ref = Referee(lo, 1)
    m = ref.public_meta()
    out.append({"id": pid, **{k: m.get(k) for k in ("limit_turn", "score_cap", "produce_id",
                                                    "step_type", "plan_type", "round_label", "criteria")}})
for r in out:
    print(json.dumps(r, ensure_ascii=False))
from collections import Counter
print("score_cap:", Counter(r["score_cap"] for r in out).most_common())
print("limit_turn:", Counter(r["limit_turn"] for r in out).most_common())
print("step_type:", Counter(r["step_type"] for r in out).most_common())
(ROOT / "data" / "_meta_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")