"""考试洗牌模型的回归测试：用四场实机采集的真值逐张核对。

数据来源：``traffic.jsonl``（2026-11-20 两场 + 2026-11-21 PRO/hkne 局两场），牌堆、逐回合手牌、
回合属性见 ``docs/MASTER_DATA.md`` 附录「洗牌重放」。模型见 ``src/gkagent/sim/exam_shuffle.py``。

要点：
* 期末牌堆里可能有 isInitial 卡，第 1 回合会先被抽入手牌，不能按「牌堆顶 3 张」拼接；
* 洗牌前 RNG 消耗 K = (turns-3) + npc_count*turns（四场都是 5 个 NPC → 6*turns-3）；
* ``turns`` 是**配置回合数**：中间考试到 forceEndScore 会提前结束，K 仍按配置回合算
  （2026-11-21 那场配置 9 回合、实战只打 7 回合 → K=51 而不是 39）。
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


# ===== 2026-11-21 采集：PRO（produce-002）hkne 局，验证「配置回合 vs 实战提前结束」 =====
# 期中配置 9 回合，实战打到 forceEndScore(1700) 只打了 7 回合 → K 按 9 回合算 = 51。

MID2_SEED = 0x47E1B2A5
MID2_DECK = [
    ("p_card-01-ido-3_292", 1),
    ("p_card-00-act-0_001", 0),
    ("p_card-00-act-0_001", 0),
    ("p_card-00-act-0_002", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-01-men-0_008", 0),
    ("p_card-01-men-0_008", 1),
    ("p_card-01-act-0_006", 0),
    ("p_card-01-men-2_035", 0),
    ("p_card-01-men-1_024", 0),
    ("p_card-01-act-1_022", 0),
    ("p_card-01-men-2_043", 0),
    ("p_card-01-men-2_039", 1),
    ("p_card-01-act-3_031", 0),
]

# 实战前 5 回合手牌（15 张牌堆抽完；T6/T7 已进入弃牌堆重洗，不在本模型范围）
MID2_DRAW = [
    ("p_card-01-men-2_035", 0),
    ("p_card-01-men-1_024", 1),
    ("p_card-00-act-0_001", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-01-men-2_039", 1),
    ("p_card-00-act-0_002", 0),
    ("p_card-01-men-0_008", 0),
    ("p_card-01-act-3_031", 0),
    ("p_card-01-act-1_022", 0),
    ("p_card-00-act-0_001", 0),
    ("p_card-01-men-0_008", 1),
    ("p_card-01-ido-3_292", 1),
    ("p_card-00-men-0_003", 0),
    ("p_card-01-men-2_043", 0),
    ("p_card-01-act-0_006", 0),
]
MID2_INITIAL_KEYS = frozenset({("p_card-01-men-2_035", 0)})

FINAL2_SEED = 0x1E1A740D
FINAL2_DECK = [
    ("p_card-01-ido-3_292", 1),
    ("p_card-00-act-0_001", 0),
    ("p_card-00-act-0_002", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-01-men-0_008", 0),
    ("p_card-01-men-0_008", 1),
    ("p_card-01-act-0_006", 0),
    ("p_card-01-men-2_035", 0),
    ("p_card-01-men-1_024", 0),
    ("p_card-01-act-1_022", 0),
    ("p_card-01-men-2_043", 0),
    ("p_card-01-men-2_039", 1),
    ("p_card-01-act-3_031", 1),
    ("p_card-01-act-3_030", 1),
    ("p_card-01-men-1_024", 0),
    ("p_card-01-men-2_039", 1),
    ("p_card-01-men-1_024", 0),
    ("p_card-01-men-2_043", 0),
    ("p_card-00-men-3_012", 0),
    ("p_card-01-men-2_035", 1),
    ("p_card-01-men-2_039", 0),
    ("p_card-01-men-2_038", 0),
    ("p_card-01-act-2_002", 0),
    ("p_card-01-act-1_020", 1),
    ("p_card-01-act-1_021", 0),
    ("p_card-01-men-1_008", 0),
    ("p_card-01-men-2_035", 1),
]

# 12 回合里前 9 回合共 27 张（牌堆抽完）；T10-T12 已进入弃牌堆重洗
FINAL2_DRAW = [
    ("p_card-01-men-2_035", 0),
    ("p_card-01-men-2_035", 1),
    ("p_card-01-men-2_035", 1),
    ("p_card-01-act-3_030", 2),
    ("p_card-01-act-1_022", 0),
    ("p_card-01-men-0_008", 1),
    ("p_card-01-act-1_020", 2),
    ("p_card-01-act-2_002", 0),
    ("p_card-01-men-1_024", 0),
    ("p_card-00-men-3_012", 0),
    ("p_card-01-act-0_006", 0),
    ("p_card-01-men-2_038", 0),
    ("p_card-01-men-1_008", 0),
    ("p_card-01-act-3_031", 1),
    ("p_card-01-act-1_021", 0),
    ("p_card-01-men-0_008", 1),
    ("p_card-01-ido-3_292", 1),
    ("p_card-01-men-2_039", 1),
    ("p_card-01-men-1_024", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-01-men-2_043", 1),
    ("p_card-00-act-0_002", 0),
    ("p_card-01-men-2_039", 2),
    ("p_card-01-men-2_039", 0),
    ("p_card-00-act-0_001", 0),
    ("p_card-01-men-2_043", 1),
    ("p_card-01-men-1_024", 0),
]
FINAL2_INITIAL_KEYS = frozenset({("p_card-01-men-2_035", 0), ("p_card-01-men-2_035", 1)})


def test_k_uses_config_turns_when_exam_ends_early():
    """实战只打 7 回合，但配置是 9 回合 → K 必须按配置回合算（39 是错的，51 才对）。"""
    hands = replay_initial_deck(
        MID2_SEED,
        MID2_DECK,
        k_before_shuffle(9),
        initial_keys=MID2_INITIAL_KEYS,
    )
    flat = _flat(hands)
    assert [len(h) for h in hands] == [3] * 5  # 15 张正好 5 回合抽完
    assert [card[0] for card in flat] == [card[0] for card in MID2_DRAW]
    assert all(obs[1] >= pred[1] for pred, obs in zip(flat, MID2_DRAW))

    # 回归防线：按实战回合数(7)算 K=39 会错位——别再犯
    wrong = replay_initial_deck(
        MID2_SEED,
        MID2_DECK,
        k_before_shuffle(7),
        initial_keys=MID2_INITIAL_KEYS,
    )
    assert [card[0] for card in _flat(wrong)] != [card[0] for card in MID2_DRAW]


def test_final2_replay_exact_with_three_initial_cards():
    """期末有 3 张 isInitial（同一 id 的 +0/+1 变体），首回合全部先入手。"""
    hands = replay_initial_deck(
        FINAL2_SEED,
        FINAL2_DECK,
        k_before_shuffle(12),
        initial_keys=FINAL2_INITIAL_KEYS,
    )
    flat = _flat(hands)
    assert [len(h) for h in hands] == [3] * 9  # 27 张正好 9 回合抽完
    assert [card[0] for card in flat] == [card[0] for card in FINAL2_DRAW]
    assert all(obs[1] >= pred[1] for pred, obs in zip(flat, FINAL2_DRAW))
    # 三张 isInitial 的首回合顺序（按洗后牌堆底→顶扫描）也要对
    assert [card[1] for card in flat[:3]] == [card[1] for card in FINAL2_DRAW[:3]]
