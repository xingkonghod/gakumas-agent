"""One-state UINet value-head probe (throwaway evidence for the report)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import local_bench as lb

from gkagent.sim import uinet

rows, index, refs = lb.load_card_table()
raws = lb.load_problems()
spec = lb.build_problem(raws[0], rows, index, refs)
sim = lb.LessonSim(list(spec.deck), spec.config, rng_seed=1000)
obs = lb.sim_to_uiobs(sim, spec, decision=0, played=[])
out = uinet.predict(obs)
payload = {
    "problem": spec.pid,
    "kind": spec.kind,
    "state": "turn 1, start of episode, seed 1000",
    "action": list(out.action),
    "probs": [round(value, 4) for value in out.probs],
    "score_quantiles_real_game_scale": out.score_quantiles,
    "sim_actual_final_score_uinet": 25196,
    "sim_actual_final_score_greedy": 22569,
    "note": "分位预测是 UINet 训练分布（真实 GKMS）的分值尺度；LessonSim 同题实际分只有 2.2-2.5 万。",
}
out_path = ROOT / "data" / "bench_local" / "_uinet_value_probe.json"
out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=1))
