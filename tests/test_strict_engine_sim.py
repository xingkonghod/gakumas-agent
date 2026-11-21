"""整局模拟器回归：搜索引擎在完整培育局里不许回退 rules、不许卡死。

对应真机规则（用户 2026-11-21）：bot 不许回退 rules。这里用无画面 ``ProduceSim``
跑「8 周 + 1 场考试」的完整培育局，训练和考试都用真 ``LessonPolicy`` 适配器；
搜索引擎一旦无法决策应当抛 ``RuleFallbackBlocked``（测试里会被计数并判失败），
而不是悄悄改用规则引擎。

用 ``scripts/sim_engine_ab.py`` 的同一套适配器，保证离线 A/B 与回归口径一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sim_engine_ab as ab


def test_full_produce_episode_never_falls_back_to_rules() -> None:
    import sim_produce as sp

    from gkagent.data.card_table import CardTable
    from gkagent.sim.produce import ProduceConfig

    deck_raw = sp.build_deck(rich=True)
    pool_specs = [sp._spec_from_row(row) for row in sp.build_pool(rich=True)]
    table = CardTable()
    config = ProduceConfig(reward_pick="best", weeks=8, exam_weeks=(7,))
    strategy = ab.strategy_from_params(ab.WARM_STRATEGY)

    for engine in ("rules", "expectimax"):
        row = ab.run_episode(
            engine=engine,
            deck_raw=deck_raw,
            pool_specs=pool_specs,
            table=table,
            seed=9999,
            budget_ms=20.0,
            config=config,
            strategy=strategy,
        )
        assert row["blocked"] == "", f"{engine} 触发了 RuleFallbackBlocked：{row['blocked']}"
        assert row["error"] == "", f"{engine} 跑模拟局异常：{row['error']}"
        assert row["decisions"] > 10, f"{engine} 决策数太少：{row['decisions']}"
        assert row["total"] is not None and row["total"] > 0
        # 8 周模拟局：正常应 <1s（expectimax 20ms 预算）；给足余量防 CI 抖动。
        assert row["seconds"] < 60
