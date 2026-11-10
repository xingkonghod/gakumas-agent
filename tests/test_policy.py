from __future__ import annotations

from gkagent.contract.models import Card, Observation
from gkagent.policy.router import RuleCardPolicy


def _obs(cards: list[Card], scores: list[float] | None = None) -> Observation:
    return Observation(
        frame_id=0,
        ts_ms=0,
        hand=cards,
        raw={"scores": scores or []},
    )


def test_prefers_suggestions() -> None:
    obs = _obs(
        [Card(card_id="a", kind="cards"), Card(card_id="b", kind="suggestions")],
        [0.9, 0.2],
    )
    rec = RuleCardPolicy().recommend(obs)
    assert rec is not None
    assert rec.index == 1
    assert rec.reason == "系统推荐"


def test_falls_back_to_highest_score() -> None:
    obs = _obs(
        [Card(card_id="a", kind="cards"), Card(card_id="b", kind="cards")],
        [0.3, 0.8],
    )
    rec = RuleCardPolicy().recommend(obs)
    assert rec is not None
    assert rec.index == 1
    assert rec.confidence == 0.5


def test_no_playable_returns_none() -> None:
    obs = _obs([Card(card_id="a", kind="useless", playable=False)])
    assert RuleCardPolicy().recommend(obs) is None
