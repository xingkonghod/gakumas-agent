from __future__ import annotations

from gkagent.data.master import MasterData


def test_counts() -> None:
    data = MasterData()
    counts = data.counts()
    assert counts["produce_cards"] >= 1500
    assert counts["support_cards"] >= 200
    assert counts["events"] >= 5000


def test_lookup_and_search() -> None:
    data = MasterData()
    assert data.produce_cards
    card = data.produce_cards[0]
    assert data.get(card.id) is not None
    assert data.search("卡") is not None
