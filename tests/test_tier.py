from __future__ import annotations

from gkagent.data.tier import plan_upgrades, tier_of


def test_tier_lookup() -> None:
    assert tier_of("仓本千奈") == "SS"
    assert tier_of("ふわふわでワクワク") == "SS"
    assert tier_of("unknown") == "?"


def test_plan_upgrades() -> None:
    owned = [("仓本千奈", 40), ("unknown", 10), ("ふわふわでワクワク", 20)]
    plan = plan_upgrades(owned, limit=2)
    assert len(plan) == 2
    assert plan[0].score >= plan[1].score
    assert all(t.score > 0 for t in plan)
