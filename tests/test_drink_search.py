"""饮料作为 expectimax 动作：搜索选择、不占出牌次数、库存/每回合限制。"""

from __future__ import annotations

import time

import pytest

from gkagent.sim.expectimax import (
    ExpectState,
    available_drinks,
    expectimax_action,
    expectimax_with_stats,
    use_drink_state,
)
from gkagent.sim.lesson import CardSpec, DrinkSpec


def _drinks():
    return (
        DrinkSpec("体力饮料", 0, "stamina", 5),
        DrinkSpec("集中饮料", 0, "focus", 2),
        DrinkSpec("分数饮料", 0, "score", 7),
    )


def test_search_chooses_drink_when_it_unlocks_big_card() -> None:
    state = ExpectState(
        hand=(CardSpec("大牌", 6, 50),),
        stamina=4,
        stamina_max=20,
        turns_left=1,
        clear=50,
        perfect=100,
        play_limit=1,
        drinks=_drinks(),
        drink_uses=(1, 1, 1),
    )
    result = expectimax_with_stats(state)
    assert result.drink == 0
    assert result.card is None
    # 喝完后仍能打大牌
    after = use_drink_state(state, result.drink)
    assert after.plays_used == 0
    card, drink = expectimax_action(after)
    assert card is not None and card.name == "大牌"
    assert drink is None


def test_search_does_not_drink_when_stamina_already_enough() -> None:
    state = ExpectState(
        hand=(CardSpec("大牌", 6, 50),),
        stamina=6,
        stamina_max=20,
        turns_left=1,
        clear=50,
        perfect=100,
        play_limit=1,
        drinks=_drinks(),
        drink_uses=(1, 1, 1),
    )
    result = expectimax_with_stats(state)
    assert result.card is not None and result.card.name == "大牌"
    assert result.drink is None  # 体力够大牌时，stamina 饮料被剪枝；不写死喝/不喝


def test_drinks_per_turn_one_blocks_second_drink() -> None:
    state = ExpectState(
        hand=(CardSpec("大牌", 6, 50),),
        stamina=4,
        stamina_max=20,
        turns_left=1,
        clear=50,
        perfect=100,
        play_limit=1,
        drinks=_drinks(),
        drink_uses=(1, 1, 1),
        drinks_per_turn=1,
    )
    after = use_drink_state(state, 0)
    assert after.drinks_used_this_turn == 1
    assert available_drinks(after) == []
    with pytest.raises(ValueError):
        use_drink_state(after, 1)


def test_exhausted_stock_cannot_be_drunk() -> None:
    state = ExpectState(
        hand=(CardSpec("大牌", 6, 50),),
        stamina=4,
        stamina_max=20,
        turns_left=1,
        clear=50,
        perfect=100,
        play_limit=1,
        drinks=_drinks(),
        drink_uses=(0, 0, 0),
    )
    assert available_drinks(state) == []
    result = expectimax_with_stats(state)
    assert result.drink is None
    assert result.card is None  # 没饮料、4 体力打不起 6 费牌 → SKIP


def test_drink_does_not_consume_play_slot_and_then_play_continues() -> None:
    state = ExpectState(
        hand=(CardSpec("大牌", 6, 50),),
        stamina=4,
        stamina_max=20,
        turns_left=1,
        clear=50,
        perfect=100,
        play_limit=1,
        drinks=_drinks(),
        drink_uses=(1, 1, 1),
    )
    first = expectimax_with_stats(state)
    assert first.drink == 0
    after = use_drink_state(state, first.drink)
    assert after.plays_used == 0
    assert after.plays_left == 1  # 喝饮料不占次数（和喝之前一样）
    card, _ = expectimax_action(after)
    assert card is not None and card.name == "大牌"


def test_drink_search_latency_stays_bounded() -> None:
    state = ExpectState(
        hand=(
            CardSpec("大牌", 4, 50),
            CardSpec("中牌", 3, 20),
            CardSpec("buff", 1, 0, focus=2),
        ),
        stamina=8,
        turns_left=2,
        clear=50,
        perfect=100,
        play_limit=3,
        drinks=_drinks(),
        drink_uses=(3, 3, 3),
        drinks_per_turn=1,
    )
    started = time.perf_counter()
    for _ in range(100):
        expectimax_with_stats(state)
    mean_ms = (time.perf_counter() - started) * 1000 / 100
    assert mean_ms < 10.0, f"饮料搜索单次 {mean_ms:.2f}ms > 10ms"
