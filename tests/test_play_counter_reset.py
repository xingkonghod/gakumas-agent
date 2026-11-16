"""出牌计数在「读不到回合数」时也必须能重置（防满体力一直 SKIP）。"""

from __future__ import annotations


def _policy():
    from gkagent.policy.lesson import LessonPolicy

    return LessonPolicy(engine="rules")


def _state(score: int = 100, cards: int = 1):
    from gkagent.vision.lesson import LessonCard, LessonState

    hand = [
        LessonCard(index=i, box=(0, 0, 0, 0), point=(0, 0), name="试行错误+", score=84, cost=5, buff=False, text="")
        for i in range(cards)
    ]
    return LessonState(kind="lesson", cards=hand, stamina=34, turns_left=None, score=score, total_turns=5)


def test_skip_resets_play_counter_when_turns_unknown() -> None:
    """turns_left 读不到（真机常态）时，SKIP 之后必须重置出牌计数，否则会一直 SKIP。"""
    policy = _policy()
    state = _state()
    for _ in range(3):
        action = policy.decide(state)
        policy.note_play(action.card if action.kind == "card" else None)
    assert policy._plays_this_turn == 3

    skip_state = _state(cards=0)
    action = policy.decide(skip_state)
    policy.note_play(None)
    assert policy._await_turn_reset is True

    action = policy.decide(state)
    assert policy._plays_this_turn == 0
    assert action.kind == "card"


def test_skip_does_not_count_as_play() -> None:
    """SKIP 本身不增加出牌计数。"""
    policy = _policy()
    policy.note_play(None)
    assert policy._plays_this_turn == 0
