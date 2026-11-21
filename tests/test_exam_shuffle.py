"""考试洗牌模型的回归测试：用两场实机采集的真值逐张核对。

数据来源：2026-11-20 采集（traffic.jsonl），牌堆、逐回合手牌、回合属性见
``docs/MASTER_DATA.md`` 附录「洗牌重放」。模型见 ``src/gkagent/sim/exam_shuffle.py``。

要点：期末牌堆里有一张 isInitial 卡，第 1 回合会先被抽入手牌，不能按「牌堆顶 3 张」拼接；
洗牌前 RNG 消耗 K = (turns-3) + npc_count*turns（两场都是 5 个 NPC → 6*turns-3）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gkagent.sim.exam_shuffle import (
    generate_turn_types,
    infer_turn_type_pool,
    k_before_shuffle,
    replay_initial_deck,
)

MIDTERM_SEED = 0x504C4509
FINAL_SEED = 0x7ECD7553

MIDTERM_DECK = [
    ("p_card-02-ido-3_208", 1),
    ("p_card-02-ido-3_221", 0),
    ("p_card-00-act-0_001", 1),
    ("p_card-00-act-0_001", 0),
    ("p_card-00-act-0_002", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-02-men-0_011", 0),
    ("p_card-02-men-0_011", 0),
    ("p_card-02-act-0_009", 0),
    ("p_card-02-act-1_004", 0),
    ("p_card-02-act-1_003", 0),
    ("p_card-02-men-2_055", 0),
    ("p_card-02-act-1_027", 0),
    ("p_card-02-men-2_058", 0),
    ("p_card-02-men-2_052", 0),
    ("p_card-02-men-2_050", 0),
    ("p_card-02-act-1_003", 1),
]

MIDTERM_DRAW = [
    ("p_card-02-men-0_011", 0),
    ("p_card-02-act-0_009", 0),
    ("p_card-02-men-2_058", 0),
    ("p_card-02-act-1_003", 0),
    ("p_card-02-men-2_050", 0),
    ("p_card-02-ido-3_208", 1),
    ("p_card-02-men-2_055", 0),
    ("p_card-02-ido-3_221", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-00-act-0_001", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-02-men-0_011", 0),
    ("p_card-02-act-1_003", 1),
    ("p_card-00-act-0_001", 1),
    ("p_card-02-act-1_004", 0),
    ("p_card-02-act-1_027", 0),
    ("p_card-00-act-0_002", 0),
    ("p_card-02-men-2_052", 0),
]

MIDTERM_TURN_TYPES = [1, 3, 1, 2, 1, 1, 2, 3, 1]

FINAL_DECK = [
    ("p_card-02-ido-3_208", 1),
    ("p_card-02-ido-3_221", 1),
    ("p_card-00-act-0_001", 1),
    ("p_card-00-act-0_002", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-02-men-0_011", 0),
    ("p_card-02-men-0_011", 0),
    ("p_card-02-act-0_009", 0),
    ("p_card-02-act-1_004", 0),
    ("p_card-02-act-1_003", 0),
    ("p_card-02-men-2_055", 0),
    ("p_card-02-act-1_027", 1),
    ("p_card-02-men-2_058", 0),
    ("p_card-02-men-2_052", 0),
    ("p_card-02-men-2_050", 0),
    ("p_card-02-act-1_003", 1),
    ("p_card-02-men-1_031", 0),
    ("p_card-02-act-1_028", 0),
    ("p_card-02-men-2_054", 0),
    ("p_card-02-men-2_053", 0),
    ("p_card-00-acc-0_002", 0),
    ("p_card-02-men-2_050", 0),
    ("p_card-00-men-3_012", 0),
    ("p_card-02-act-2_046", 0),
    ("p_card-02-act-3_001", 0),
]

# 实战手牌（含考试内支援临时强化，所以 +1/+2 可能大于牌堆里的强化数）
FINAL_DRAW = [
    ("p_card-02-men-2_054", 0),
    ("p_card-02-act-1_003", 1),
    ("p_card-02-men-2_050", 0),
    ("p_card-00-act-0_001", 1),
    ("p_card-00-act-0_002", 0),
    ("p_card-02-act-1_003", 0),
    ("p_card-00-men-3_012", 0),
    ("p_card-02-men-0_011", 1),
    ("p_card-02-men-1_031", 1),
    ("p_card-02-men-2_058", 1),
    ("p_card-02-act-1_028", 0),
    ("p_card-02-ido-3_221", 1),
    ("p_card-02-act-1_004", 0),
    ("p_card-02-act-3_001", 2),
    ("p_card-02-men-2_050", 0),
    ("p_card-00-acc-0_002", 0),
    ("p_card-02-men-0_011", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-02-men-2_053", 0),
    ("p_card-02-ido-3_208", 1),
    ("p_card-02-act-2_046", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-02-act-1_027", 2),
    ("p_card-02-men-2_055", 0),
    ("p_card-02-men-2_052", 1),
    ("p_card-02-act-0_009", 1),
]

FINAL_TURN_TYPES = [1, 2, 1, 2, 1, 3, 1, 3, 2, 3, 1]
FINAL_INITIAL_KEYS = frozenset({("p_card-02-men-2_054", 0)})


def _flat(hands: list[list[tuple[str, int]]]) -> list[tuple[str, int]]:
    return [card for hand in hands for card in hand]


def test_k_before_shuffle():
    assert k_before_shuffle(9) == 51
    assert k_before_shuffle(11) == 63
    assert k_before_shuffle(9, npc_count=3) == 33
    assert k_before_shuffle(3) == 15


def test_midterm_replay_exact():
    hands = replay_initial_deck(MIDTERM_SEED, MIDTERM_DECK, k_before_shuffle(9))
    assert [len(h) for h in hands] == [3] * 6  # 18 张正好 6 回合抽完
    assert _flat(hands) == MIDTERM_DRAW


def test_final_replay_exact_with_initial_card():
    hands = replay_initial_deck(
        FINAL_SEED,
        FINAL_DECK,
        k_before_shuffle(11),
        initial_keys=FINAL_INITIAL_KEYS,
    )
    flat = _flat(hands)
    assert len(flat) == 26  # 26 张牌在第 9 回合抽到第 2 张后耗尽
    assert [len(h) for h in hands] == [3] * 8 + [2]
    assert [card[0] for card in flat] == [card[0] for card in FINAL_DRAW]
    # 实战手牌带临时强化，只要求「不低于牌堆里的强化数」
    assert all(obs[1] >= pred[1] for pred, obs in zip(flat, FINAL_DRAW))
    # 首回合第一张必然是 isInitial 卡
    assert flat[0] == ("p_card-02-men-2_054", 0)


def test_initial_card_changes_deal_order():
    """把 isInitial 当普通牌会让期末整段错位——回归防线。"""
    hands = replay_initial_deck(FINAL_SEED, FINAL_DECK, k_before_shuffle(11))
    assert [card[0] for card in _flat(hands)] != [card[0] for card in FINAL_DRAW]


def test_turn_types_reproduce_from_rng_offset_zero():
    for seed, types in ((MIDTERM_SEED, MIDTERM_TURN_TYPES), (FINAL_SEED, FINAL_TURN_TYPES)):
        pool = infer_turn_type_pool(types)
        assert pool is not None
        assert generate_turn_types(seed, pool) == types[:-3]
