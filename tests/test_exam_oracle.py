"""考试牌序全知 ``ExamDrawOracle`` 的单元测试。

oracle 是「完全信息搜索」的数据源：seed + 牌堆 → 当前牌堆顺序，每回合给出真实手牌、
牌堆抽空时按真实 grave 顺序重洗。模型本体在 ``tests/test_exam_shuffle.py`` 验证。
"""

from __future__ import annotations

import pytest

from gkagent.sim.exam_oracle import ExamDrawOracle, initial_shuffled_deck
from gkagent.sim.exam_shuffle import (
    NativeRandom,
    k_before_shuffle,
    opening_deck_and_rng,
    replay_initial_deck,
    reshuffle_grave,
    support_upgrade,
)

SEED = 0x504C4509
TURNS = 5
NPC = 5
DECK = [(f"p_card-00-act-0_{index:03d}", index % 3) for index in range(12)]
SUPPORTS = [
    {"id": "s1", "filter": 1, "permil": 800},
    {"id": "s2", "filter": 0, "permil": 400},
    {"id": "s3", "filter": 2, "permil": 900},
]


def test_initial_shuffled_deck_is_opening_order() -> None:
    oracle = ExamDrawOracle(SEED, DECK, TURNS, npc_count=NPC)
    assert oracle.remaining == initial_shuffled_deck(SEED, DECK, TURNS, npc_count=NPC)
    assert oracle.turn == 0
    assert oracle.rng_state == opening_deck_and_rng(
        SEED, DECK, k_before_shuffle(TURNS, NPC)
    )[0].state


def test_peek_does_not_consume() -> None:
    oracle = ExamDrawOracle(SEED, DECK, TURNS, npc_count=NPC)
    before = oracle.remaining
    assert oracle.peek(3) == before[:3]
    assert oracle.remaining == before and oracle.turn == 0


def test_draw_next_turn_matches_replay_initial_deck() -> None:
    hands = replay_initial_deck(SEED, DECK, k_before_shuffle(TURNS, NPC))
    oracle = ExamDrawOracle(SEED, DECK, TURNS, npc_count=NPC)
    for turn, expected in enumerate(hands, start=1):
        assert oracle.draw_next_turn(1) == list(expected)
        assert oracle.turn == turn


def test_initial_cards_come_first_on_turn_one() -> None:
    deck = [("init", 1)] + [
        (f"p_card-00-act-0_{index:03d}", 0) for index in range(9)
    ]
    initial = frozenset({("init", 1)})
    hands = replay_initial_deck(
        SEED, deck, k_before_shuffle(TURNS, NPC), initial_keys=initial
    )
    oracle = ExamDrawOracle(SEED, deck, TURNS, npc_count=NPC, initial_keys=initial)
    assert oracle.draw_next_turn(3) == list(hands[0])
    assert oracle.draw_next_turn(3) == list(hands[1])


def test_support_upgrade_advances_rng_identically() -> None:
    hands = replay_initial_deck(SEED, DECK, k_before_shuffle(TURNS, NPC))
    oracle = ExamDrawOracle(SEED, DECK, TURNS, npc_count=NPC, supports=SUPPORTS)
    oracle.draw_next_turn(1)
    # 手动重放：抽牌不耗随机数，支援强化掷点耗 —— RNG 状态应完全一致
    rng, _ = opening_deck_and_rng(SEED, DECK, k_before_shuffle(TURNS, NPC))
    _planned, rolls = support_upgrade(rng, list(hands[0]), SUPPORTS, 1)
    assert rolls > 0
    assert oracle.rng_state == rng.state


def test_reshuffle_uses_given_grave_order() -> None:
    deck = [(f"c{index}", 0) for index in range(6)]
    oracle = ExamDrawOracle(SEED, deck, 4, npc_count=NPC)
    oracle.draw_next_turn(1)
    oracle.draw_next_turn(1)  # 6 张抽完，牌堆空
    grave = [("g1", 0), ("g2", 0), ("g3", 0), ("g4", 0)]
    expected_rng = NativeRandom(oracle.rng_state)
    expected = reshuffle_grave(expected_rng, grave)
    assert oracle.draw_next_turn(1, grave=grave) == expected[:3]


def test_empty_deck_without_grave_raises() -> None:
    deck = [(f"c{index}", 0) for index in range(3)]
    oracle = ExamDrawOracle(SEED, deck, 4, npc_count=NPC)
    oracle.draw_next_turn(1)
    with pytest.raises(ValueError, match="grave"):
        oracle.draw_next_turn(1)
