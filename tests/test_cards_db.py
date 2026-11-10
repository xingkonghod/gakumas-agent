from __future__ import annotations

from gkagent.data.cards_db import CardLibrary, score_text


def test_score_text() -> None:
    assert score_text("得分+9") > 0
    assert score_text("抽牌+2 得分+5") > score_text("抽牌+2")
    assert score_text("消耗") < 0


def test_library_lookup() -> None:
    lib = CardLibrary()
    assert len(lib) >= 500
    info = lib.find("快乐")
    if info is not None:
        assert info.value != 0 or info.name
    assert lib.score("快乐", "元气+7", cost=10) >= 0
