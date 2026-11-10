from __future__ import annotations

from collections.abc import Sequence

from gkagent.contract.models import Card, Observation
from gkagent.policy.router import Recommendation
from gkagent.policy.search import SearchPolicy


def _obs(cards: list[Card], raw: dict | None = None) -> Observation:
    return Observation(frame_id=0, ts_ms=0, hand=cards, raw=raw or {})


def _card(
    cost: int | None,
    *,
    kind: str | None = "cards",
    playable: bool = True,
    card_id: str = "c",
) -> Card:
    return Card(card_id=card_id, cost=cost, kind=kind, playable=playable)


class _FakeSim:
    def __init__(self, scores: Sequence[float] | None) -> None:
        self.scores = scores
        self.calls = 0

    def score_hand(self, obs: Observation) -> Sequence[float] | None:
        self.calls += 1
        return self.scores


def _assert_valid(rec: Recommendation, hand_size: int) -> None:
    assert isinstance(rec, Recommendation)
    assert 0 <= rec.index < hand_size
    assert 0.0 <= rec.confidence <= 1.0
    assert isinstance(rec.reason, str) and rec.reason


def test_prefers_system_suggestion() -> None:
    obs = _obs([_card(1, kind="attack"), _card(3, kind="suggestions")])
    rec = SearchPolicy().recommend(obs)
    assert rec is not None
    _assert_valid(rec, 2)
    assert rec.index == 1
    assert rec.confidence == 0.9
    assert rec.reason == "系统推荐"


def test_suggestion_flag_in_raw() -> None:
    obs = _obs(
        [_card(1, kind="attack"), _card(2)],
        {"suggested": [False, True]},
    )
    rec = SearchPolicy().recommend(obs)
    assert rec is not None
    assert rec.index == 1
    assert rec.reason == "系统推荐"


def test_uses_cost_efficiency() -> None:
    # 同为 attack，1 费比 3 费效率高。
    obs = _obs([_card(3, kind="attack", card_id="a"), _card(1, kind="attack", card_id="b")])
    rec = SearchPolicy().recommend(obs)
    assert rec is not None
    _assert_valid(rec, 2)
    assert rec.index == 1
    assert "费用效率" in rec.reason


def test_unplayable_cards_are_skipped() -> None:
    obs = _obs([_card(1, playable=False), _card(2, kind="useless", playable=False)])
    assert SearchPolicy().recommend(obs) is None


def test_no_hand_returns_none() -> None:
    assert SearchPolicy().recommend(_obs([])) is None


def test_ap_budget_excludes_expensive_cards() -> None:
    obs = _obs([_card(3, kind="attack"), _card(1, kind="buff")], {"ap": 1})
    rec = SearchPolicy().recommend(obs)
    assert rec is not None
    assert rec.index == 1

    obs_none = _obs([_card(3, kind="attack"), _card(2, kind="buff")], {"ap": 1})
    assert SearchPolicy().recommend(obs_none) is None


def test_zero_cost_is_safe() -> None:
    obs = _obs([_card(0, kind="attack"), _card(2, kind="attack")])
    rec = SearchPolicy().recommend(obs)
    assert rec is not None
    _assert_valid(rec, 2)
    assert rec.index == 0


def test_greedy_two_step_returns_legal_recommendation() -> None:
    obs = _obs(
        [
            _card(2, kind="attack", card_id="a"),
            _card(1, kind="buff", card_id="b"),
            _card(1, kind="attack", card_id="c"),
        ],
        {"ap": 3},
    )
    rec = SearchPolicy().recommend(obs)
    assert rec is not None
    _assert_valid(rec, 3)


def test_simulator_scores_win() -> None:
    sim = _FakeSim([0.1, 5.0, 0.2])
    rec = SearchPolicy(sim).recommend(_obs([_card(1), _card(3), _card(2)]))
    assert rec is not None
    assert sim.calls == 1
    assert rec.index == 1
    assert "模拟" in rec.reason
    _assert_valid(rec, 3)


def test_callable_simulator() -> None:
    calls: list[int] = []

    def scorer(obs: Observation) -> list[float]:
        calls.append(len(obs.hand))
        return [9.0, 0.5]

    rec = SearchPolicy(scorer).recommend(_obs([_card(1), _card(2)]))
    assert rec is not None
    assert calls == [2]
    assert rec.index == 0


def test_invalid_simulator_falls_back_to_heuristic() -> None:
    for sim in (_FakeSim(None), _FakeSim([]), _FakeSim([float("nan"), 1.0])):
        rec = SearchPolicy(sim).recommend(_obs([_card(1), _card(2)]))
        assert rec is not None
        _assert_valid(rec, 2)
        assert "模拟" not in rec.reason


def test_simulator_exception_falls_back() -> None:
    class _Broken:
        def score_hand(self, obs: Observation) -> list[float]:
            raise RuntimeError("boom")

    rec = SearchPolicy(_Broken()).recommend(_obs([_card(1), _card(2)]))
    assert rec is not None
    _assert_valid(rec, 2)


def test_rank_sorted_and_bounded() -> None:
    obs = _obs(
        [_card(3, kind="attack"), _card(1, kind="attack"), _card(2, kind="buff")],
        {"ap": 4},
    )
    ranked = SearchPolicy().rank(obs)
    assert len(ranked) == 3
    scores = [score for _, score, _ in ranked]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= index < 3 for index, _, _ in ranked)


def test_rank_with_simulator() -> None:
    ranked = SearchPolicy(_FakeSim([1.0, 7.0])).rank(_obs([_card(1), _card(2)]))
    assert [item[0] for item in ranked] == [1, 0]


def test_deterministic() -> None:
    obs = _obs([_card(2, kind="attack"), _card(2, kind="attack")])
    policy = SearchPolicy()
    first = policy.recommend(obs)
    second = policy.recommend(obs)
    assert first == second
    assert first is not None
    assert first.index == 0
