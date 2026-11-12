"""期末考试估分器：纯离线单元测试。"""

from __future__ import annotations

from gkagent.sim.exam_estimate import SimCard, estimate_score, simulate_once


def test_empty_deck_scores_zero() -> None:
    assert simulate_once([], turns=3) == 0.0


def test_greedy_plays_affordable_cards() -> None:
    deck = [SimCard("a", 10.0, 10) for _ in range(20)]
    # 3 回合，每回合 100 能量 → 每回合打 10 张（摸牌 3 张会限制，这里只验证有分）
    score = simulate_once(deck, turns=3, draw=3, energy_start=100, energy_per_turn=0)
    assert score > 0


def test_estimate_is_deterministic_with_seed() -> None:
    deck = [
        SimCard("a", 10.0, 10),
        SimCard("b", 25.0, 30),
        SimCard("c", 4.0, 5),
        SimCard("d", 0.0, 0),
    ] * 3
    first = estimate_score(deck, turns=4, trials=15, seed=7)
    second = estimate_score(deck, turns=4, trials=15, seed=7)
    assert first.mean == second.mean
    assert first.p10 <= first.mean <= first.p90


def test_more_turns_never_scores_less() -> None:
    deck = [SimCard("a", 10.0, 10)] * 10
    short = estimate_score(deck, turns=2, trials=15, seed=1)
    long = estimate_score(deck, turns=5, trials=15, seed=1)
    assert long.mean >= short.mean
