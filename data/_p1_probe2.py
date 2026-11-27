"""P1-1 探针 2：评测牌组的指針相关字段 / のんびり来源卡是否在牌组（一次性，不提交）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

import eval_expectimax as ee

for scenario in ("small", "large"):
    deck = ee.build_deck(scenario)
    print(f"=== {scenario} deck {len(deck)} ===")
    for c in deck:
        flags = []
        if c.preservation:
            flags.append(f"preservation={c.preservation}")
        if c.full_power_point:
            flags.append(f"full_power_point={c.full_power_point}")
        if c.strong_level:
            flags.append(f"strong={c.strong_level}")
        if c.extra_play:
            flags.append(f"extra_play={c.extra_play}")
        if c.full_power_scale:
            flags.append(f"full_power_scale={c.full_power_scale}")
        if flags:
            print(f"  {c.name}: cost={c.cost} score={c.score} {' '.join(flags)}")
    names = {c.name for c in deck}
    for leisure_name in ("悠闲自在的人", "走走停停，继续前进", "从天台看到的景色", "俯瞰群星的启明星", "悠闲地睡个好觉"):
        print(f"  leisure card {leisure_name!r} in deck: {leisure_name in names}")
