"""Ablation: wiki 机制修正逐项的「评价点 P50」变化（300 局/组，固定 seed）。"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sim_produce as sp

from gkagent.sim.produce import (
    ProduceConfig,
    ProduceSim,
    StrategyParams,
    eval_value,
    strategy_from_params,
)

EPISODES = 300
DECK = [sp._spec_from_row(row) for row in sp.build_deck(rich=True)]
POOL = [sp._spec_from_row(row) for row in sp.build_pool(rich=True)]
STRATEGY = strategy_from_params(StrategyParams())

OLD = {
    "exam_rank_mode": "attribute",
    "exam_turns_mid": 12,
    "exam_turns_final": 12,
    "exam_turns_final_logic": 12,
    "training_cost": 10,
    "training_use_current_stamina": False,
    "perfect_stamina_refund": False,
    "rest_gain_ratio": 0.0,
    "rest_gain": 24,
    "stance_costs": False,
    "support_lesson_bonus": 0.0,
}
NEW = {
    "exam_rank_mode": "score",
    "exam_turns_mid": 9,
    "exam_turns_final": 12,
    "exam_turns_final_logic": 11,
    "training_cost": 0,
    "training_use_current_stamina": True,
    "perfect_stamina_refund": True,
    "rest_gain_ratio": 0.7,
    "stance_costs": True,
    "support_lesson_bonus": 0.2,
}


def p50(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * 0.5)]


def run(name: str, overrides: dict) -> dict:
    values = []
    for seed in range(EPISODES):
        config = ProduceConfig(**{**OLD, **overrides})
        sim = ProduceSim(DECK, config=config, rng_seed=seed)
        sim.reward_pool = POOL
        result = sim.run(STRATEGY)
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"):
                rank = row["exam"]["rank"]
                break
        values.append(eval_value(result.total, rank, result.exam_score))
    row = {
        "name": name,
        "p50": p50(values),
        "mean": statistics.fmean(values),
        "p10": sorted(values)[int((len(values) - 1) * 0.1)],
        "p90": sorted(values)[int((len(values) - 1) * 0.9)],
    }
    print(row)
    return row


if __name__ == "__main__":
    rows = [run("old_all", {})]
    rows.append(run("new_all", NEW))
    single = {
        "exam_rank_score": {"exam_rank_mode": "score"},
        "training_no_entry_current_stamina": {
            "training_cost": 0,
            "training_use_current_stamina": True,
        },
        "rest_70pct": {"rest_gain_ratio": 0.7},
        "perfect_stamina_refund": {"perfect_stamina_refund": True},
        "exam_turns_9_12_11": {
            "exam_turns_mid": 9,
            "exam_turns_final": 12,
            "exam_turns_final_logic": 11,
        },
        "stance_costs": {"stance_costs": True},
        "support_lesson_bonus": {"support_lesson_bonus": 0.2},
    }
    for name, override in single.items():
        rows.append(run(name, override))
    base = rows[0]["p50"]
    print("\nP50 deltas vs old_all:")
    for row in rows[1:]:
        print(f"  {row['name']:40s} P50 {row['p50']:7.0f} ({row['p50'] - base:+.0f})")
