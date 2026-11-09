from __future__ import annotations

from gkagent.contract.models import Action, ActionKind, Observation
from gkagent.integration.maa import MaaCardHit, action_to_point, box_center, observation_from_maa


def test_box_center() -> None:
    assert box_center((10, 20, 100, 50)) == (60, 45)


def test_observation_from_maa() -> None:
    hits = [
        MaaCardHit(label="suggestions", box=(100, 900, 80, 120), score=0.95),
        MaaCardHit(label="cards", box=(200, 900, 80, 120), score=0.90),
        MaaCardHit(label="useless", box=(300, 900, 80, 120), score=0.80),
    ]
    obs = observation_from_maa(hits, frame_id=1, ts_ms=1000)
    assert len(obs.hand) == 3
    assert obs.hand[0].kind == "suggestions"
    assert obs.hand[2].playable is False
    assert obs.confidence == 0.95
    assert obs.raw["boxes"][1] == [200, 900, 80, 120]


def test_action_to_point() -> None:
    obs = Observation(
        frame_id=0,
        ts_ms=0,
        raw={"boxes": [[100, 900, 80, 120]]},
    )
    action = Action(kind=ActionKind.PLAY_CARD, index=0)
    assert action_to_point(action, obs) == (140, 960)
    assert action_to_point(Action(kind=ActionKind.PLAY_CARD, index=5), obs) is None
    assert action_to_point(Action(kind=ActionKind.END_TURN), obs) is None
