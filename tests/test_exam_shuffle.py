"""考试洗牌模型的回归测试：用四场实机采集的真值逐张核对。

数据来源：``traffic.jsonl``（2026-11-20 两场 + 2026-11-21 PRO/hkne 局两场），牌堆、逐回合手牌、
回合属性见 ``docs/MASTER_DATA.md`` 附录「洗牌重放」。模型见 ``src/gkagent/sim/exam_shuffle.py``。

要点：
* 期末牌堆里可能有 isInitial 卡，第 1 回合会先被抽入手牌，不能按「牌堆顶 3 张」拼接；
* 洗牌前 RNG 消耗 K = (turns-3) + npc_count*turns（四场都是 5 个 NPC → 6*turns-3）；
* ``turns`` 是**配置回合数**：中间考试到 forceEndScore 会提前结束，K 仍按配置回合算
  （2026-11-21 那场配置 9 回合、实战只打 7 回合 → K=51 而不是 39）；
* 牌堆抽空前每回合的「支援强化掷点」也在这条 RNG 流上（入手顺序 × 支援卡顺序，各掷
  integer(0,1000)，命中后该支援本回合不再参与）——三组重洗样本的掷点总数分别是
  45 / 29 / 46 次，之后洗弃牌堆的手牌顺序逐张对上（``docs/MASTER_DATA.md`` 附录「洗后重洗」）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gkagent.sim.exam_shuffle import (
    NativeRandom,
    generate_turn_types,
    infer_turn_type_pool,
    k_before_shuffle,
    opening_deck_and_rng,
    replay_initial_deck,
    reshuffle_grave,
    support_upgrade,
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

# ===== 弃牌堆重洗（2026-11-21 深夜破解） =====
# 牌堆抽空前每回合抽牌都会掷支援强化（入手顺序 × 支援卡顺序，integer(0,1000)）；
# 牌堆抽空时用同一条 RNG 流洗弃牌堆（进弃牌堆的先后顺序见 build_grave 规则）。
# 下面三组 = 11-20 期中 T7(45 次) / 11-21 期中 T6(29 次) / 11-21 期末 T10(46 次) 重洗样本。

# 支援卡：(supportCardId, filter 属性 1 Vo/2 Da/3 Vi/0 不限, 服务器下发的强化概率‰)，按编成槽位号升序
MIDTERM_SUPPORTS = [
    ("s_card-3-0007", 3, 62),
    ("s_card-3-0099", 3, 62),
    ("s_card-2-0007", 2, 51),
    ("s_card-3-0114", 1, 78),
    ("s_card-2-0001", 1, 57),
    ("s_card-3-0001", 1, 91),
]

# 11-20 期中重洗前弃牌堆（12 张，按进弃牌堆先后）：T1-T6 出牌 + 回合末剩余手牌，Lost 卡不在其中
MIDTERM_GRAVE = [
    ("p_card-02-men-0_011", 0),
    ("p_card-02-act-1_003", 0),
    ("p_card-02-men-2_050", 0),
    ("p_card-02-ido-3_221", 0),
    ("p_card-02-men-2_055", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-00-act-0_001", 0),
    ("p_card-02-men-0_011", 0),
    ("p_card-00-act-0_001", 1),
    ("p_card-02-act-1_004", 0),
    ("p_card-02-act-1_027", 0),
    ("p_card-00-act-0_002", 0),
]

# 实战重洗后的手牌（含随后掷支援强化带来的临时强化，所以强化数可能大于牌堆里的）
MIDTERM_RESHUFFLE = [
    [("p_card-02-act-1_027", 1), ("p_card-02-act-1_004", 0), ("p_card-02-men-0_011", 0)],
    [("p_card-00-act-0_002", 1), ("p_card-00-act-0_001", 0), ("p_card-00-act-0_001", 1)],
    [("p_card-02-men-2_050", 0), ("p_card-02-act-1_003", 0), ("p_card-02-men-2_055", 1)],
]

MID2_SUPPORTS = [
    ("s_card-3-0007", 3, 81),
    ("s_card-3-0099", 3, 81),
    ("s_card-2-0007", 2, 56),
    ("s_card-3-0115", 1, 89),  # 主数据 d31baf6 里没有这张（11-21 新卡），filter 由掷点反推 = Vocal
    ("s_card-2-0001", 1, 61),
    ("s_card-3-0069", 2, 82),
]
MID2_TURN_PARAMS = [3, 3, 3, 1, 2]  # T1-T5（T6 起已重洗，不在掷点段里）
MID2_GRAVE = [
    ("p_card-01-men-1_024", 0),
    ("p_card-00-act-0_001", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-00-act-0_002", 0),
    ("p_card-01-act-3_031", 0),
    ("p_card-01-men-0_008", 0),
    ("p_card-01-act-1_022", 0),
    ("p_card-01-men-0_008", 1),
    ("p_card-00-act-0_001", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-01-men-2_043", 0),
]
MID2_RESHUFFLE = [
    [("p_card-00-act-0_001", 0), ("p_card-00-men-0_003", 0), ("p_card-01-men-2_043", 1)],
    [("p_card-01-act-1_022", 0), ("p_card-01-men-0_008", 0), ("p_card-00-act-0_001", 0)],
]

FINAL2_SUPPORTS = [
    ("s_card-3-0007", 3, 98),
    ("s_card-3-0099", 3, 98),
    ("s_card-2-0007", 2, 73),
    ("s_card-3-0115", 1, 111),
    ("s_card-2-0001", 1, 78),
    ("s_card-3-0069", 2, 104),
]
FINAL2_TURN_PARAMS = [3, 3, 3, 1, 3, 3, 2, 1, 2]  # T1-T9
FINAL2_GRAVE = [
    ("p_card-01-men-2_035", 0),
    ("p_card-01-men-2_035", 1),
    ("p_card-01-act-1_022", 0),
    ("p_card-01-men-0_008", 1),
    ("p_card-01-act-2_002", 0),
    ("p_card-01-men-1_024", 0),
    ("p_card-00-men-3_012", 0),
    ("p_card-01-act-0_006", 0),
    ("p_card-01-act-3_031", 1),
    ("p_card-01-men-1_008", 0),
    ("p_card-01-act-1_021", 0),
    ("p_card-01-men-0_008", 0),
    ("p_card-01-men-1_024", 0),
    ("p_card-00-men-0_003", 0),
    ("p_card-00-act-0_002", 0),
    ("p_card-01-men-2_039", 1),
    ("p_card-01-men-2_039", 0),
    ("p_card-00-act-0_001", 0),
    ("p_card-01-men-2_043", 0),
    ("p_card-01-men-1_024", 0),
]
FINAL2_RESHUFFLE = [
    [("p_card-01-act-3_031", 2), ("p_card-00-act-0_001", 0), ("p_card-01-men-1_024", 0)],
    [("p_card-01-act-0_006", 0), ("p_card-01-act-1_021", 0), ("p_card-01-act-2_002", 0)],
    [("p_card-01-men-2_039", 1), ("p_card-01-act-1_022", 0), ("p_card-01-men-2_039", 0)],
]


def _supports(rows: list[tuple[str, int, int]]) -> list[dict]:
    return [{"id": sid, "filter": filt, "permil": permil} for sid, filt, permil in rows]


def _roll_support_until_deck_empty(seed, deck, k, initial_keys, hands, turn_params, supports):
    """从开局洗牌后的 RNG 状态出发，按实战手牌顺序补掷支援强化，返回（重洗前 RNG, 掷点数, 逐回合成功数）。"""
    rng, _ = opening_deck_and_rng(seed, deck, k)
    rolls = 0
    per_turn_successes = []
    for hand, param in zip(hands, turn_params):
        used: list[str] = []
        planned, turn_rolls = support_upgrade(rng, hand, supports, param, used=used)
        rolls += turn_rolls
        per_turn_successes.append(len(planned))
    return rng, rolls, per_turn_successes


def _assert_reshuffled_hands(predicted, observed_turns) -> None:
    """重洗手牌逐张对照：id 必须相同，实战强化数 ≥ 预测（预测是牌堆里的强化，实战手牌还带临时强化）。"""
    predicted_flat = [c for c in predicted]
    observed_flat = [c for hand in observed_turns for c in hand]
    assert [p[0] for p in predicted_flat[: len(observed_flat)]] == [o[0] for o in observed_flat]
    assert all(p[1] <= o[1] for p, o in zip(predicted_flat, observed_flat))


def test_support_upgrade_roll_order_filters_and_turn_used():
    """掷点顺序：入手顺序（外）× 支援卡顺序（内）；命中后本回合不再参与；属性不符不掷。"""
    rng = NativeRandom(12345)
    supports = _supports([("a", 0, 0), ("b", 0, 1000), ("c", 2, 1000)])
    planned, rolls = support_upgrade(rng, [("x", 0), ("y", 0)], supports, 1)
    # card x：a 掷（失败）→ b 掷（成功，b 本回合不再参与）→ c 属性 2≠1 跳过
    # card y：a 掷（失败）→ b 已用跳过 → c 跳过
    assert rolls == 3
    assert planned == [(("x", 0), "b")]


def test_support_upgrade_skips_cards_without_next_variant():
    rng = NativeRandom(1)
    planned, rolls = support_upgrade(
        rng, [("x", 3)], _supports([("a", 0, 0)]), 1, upgradeable=lambda card: False
    )
    assert rolls == 0 and planned == []


def test_reshuffle_grave_is_fisher_yates_without_mutating_input():
    rng = NativeRandom(1)
    grave = [(f"c{i}", 0) for i in range(6)]
    snapshot = list(grave)
    out = reshuffle_grave(rng, grave)
    assert grave == snapshot  # 不改输入
    reference = NativeRandom(1)
    expected = list(grave)
    for n in range(len(expected), 1, -1):
        j = reference.integer(0, n)
        expected[j], expected[n - 1] = expected[n - 1], expected[j]
    assert out == expected


def test_midterm_reshuffle_45_rolls_matches_live_hands():
    """11-20 期中：T1-T6 掷点 45 次（一次没成功）后洗 12 张弃牌堆 → T7-T9 手牌 9/9 逐张对上。"""
    hands = replay_initial_deck(MIDTERM_SEED, MIDTERM_DECK, k_before_shuffle(9))
    assert [len(h) for h in hands] == [3] * 6
    rng, rolls, successes = _roll_support_until_deck_empty(
        MIDTERM_SEED, MIDTERM_DECK, k_before_shuffle(9), frozenset(),
        hands, MIDTERM_TURN_TYPES[:6], _supports(MIDTERM_SUPPORTS),
    )
    assert rolls == 45
    assert successes == [0] * 6  # 前 6 回合一次支援强化都没成功（所以消耗正好是掷点上限）
    predicted = reshuffle_grave(rng, MIDTERM_GRAVE)
    assert len(predicted) == 12
    _assert_reshuffled_hands(predicted[:9], MIDTERM_RESHUFFLE)


def test_mid2_reshuffle_29_rolls_matches_live_hands():
    """11-21 期中：T1-T5 掷点 29 次（1 次成功）后洗 11 张 → T6-T7 手牌 6/6 逐张对上。"""
    hands = replay_initial_deck(
        MID2_SEED, MID2_DECK, k_before_shuffle(9), initial_keys=MID2_INITIAL_KEYS
    )
    assert [len(h) for h in hands] == [3] * 5
    rng, rolls, successes = _roll_support_until_deck_empty(
        MID2_SEED, MID2_DECK, k_before_shuffle(9), MID2_INITIAL_KEYS,
        hands, MID2_TURN_PARAMS, _supports(MID2_SUPPORTS),
    )
    assert rolls == 29
    assert successes == [1, 0, 0, 0, 0]
    predicted = reshuffle_grave(rng, MID2_GRAVE)
    assert len(predicted) == 11
    _assert_reshuffled_hands(predicted[:6], MID2_RESHUFFLE)


def test_final2_reshuffle_46_rolls_matches_live_hands():
    """11-21 期末：T1-T9 掷点 46 次（6 次成功）后洗 20 张 → T10-T12 手牌 9/9 逐张对上。"""
    hands = replay_initial_deck(
        FINAL2_SEED, FINAL2_DECK, k_before_shuffle(12), initial_keys=FINAL2_INITIAL_KEYS
    )
    assert [len(h) for h in hands] == [3] * 9
    rng, rolls, successes = _roll_support_until_deck_empty(
        FINAL2_SEED, FINAL2_DECK, k_before_shuffle(12), FINAL2_INITIAL_KEYS,
        hands, FINAL2_TURN_PARAMS, _supports(FINAL2_SUPPORTS),
    )
    assert rolls == 46
    assert successes == [0, 1, 1, 0, 0, 1, 1, 1, 1]
    predicted = reshuffle_grave(rng, FINAL2_GRAVE)
    assert len(predicted) == 20
    _assert_reshuffled_hands(predicted[:9], FINAL2_RESHUFFLE)
