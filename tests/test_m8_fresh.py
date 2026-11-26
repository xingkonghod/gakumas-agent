"""M8 通用 fresh buff 保护：层轨迹回归 + 引擎 oracle 配对（engine-gap M8）。

引擎 oracle（rules=69 DLL，探针不提交）：
  * data/_m8_fresh_probe.py G1 卡渠道好印象重复获得（+6/回合 t1..t6）；
  * data/_m8_fresh_probe.py G2 好调单渠道（110 好调3回合 ×3 同回合）；
  * data/_m8_fresh_cond.py 好调跨回合叠加（030 好调3回合 t1/t2）；
  * data/_drinks_probe5_decay.py A 立即饮料好印象+3 / B 茶附魔 / C 混合。

通用 fresh 规则（探针实证）：当回合获得的层数/回合数（卡/立即饮料/P 道具/附魔
任何渠道）本回合末不扣，下一回合末才扣；叠加时只保护本回合新增部分（旧层照常 -1）。
好印象 = review_added_this_turn 计数；好调 = parameter_buff_passing_turn_start（同构）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.sim.drinks import DrinkEffect
from gkagent.sim.expectimax import (
    ExpectState,
    end_turn_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, DrinkSpec, LessonConfig, LessonSim

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "data" / "_m8_fresh_probe.jsonl"
COND = ROOT / "data" / "_m8_fresh_cond.json"
PROBE5 = ROOT / "data" / "_drinks_probe5_decay.json"


def _sim(deck, *, turns=9, stamina=60, drinks=()) -> LessonSim:
    return LessonSim(
        list(deck),
        LessonConfig(turns=turns, stamina=stamina, target_clear=10**9,
                     stamina_max=stamina, hand_size=3, drinks=drinks),
        rng_seed=0,
    )


def _drive(sim: LessonSim, plays: dict[int, int | None]) -> tuple[list[int], list[int]]:
    """按 {回合: 手牌下标/None} 驱动；返回 (每回合结算好印象分, 每回合开始好印象层)。

    回合开始层 = 上一回合结束后（_draw_hand 衰减后）的层数；第 1 回合开始恒 0。
    """
    settled: list[int] = []
    start_layers = [0]
    turn = 1
    while not sim.done and turn <= sim.config.turns:
        action = plays.get(turn, None)
        s0 = sim.score
        sim.step(action)
        settled.append(sim.score - s0)
        start_layers.append(sim.buffs.impression)
        turn += 1
    return settled, start_layers[1:]


# --------------------------------------------------------------- 卡渠道好印象
def test_card_impression_repeat_fresh_trajectory() -> None:
    """G1：卡渠道 +6/回合 t1..t6 → 结算 6,12,17,22,27,32,31,30,29（引擎逐位）。

    fresh 保护使本回合新增 6 层当回合末不扣：旧层每回合 -1、新层保留。
    M8 前 sim 结算 6,11,16,21,26,31,…（差一回合）。
    """
    imp = CardSpec("好印象", 0, 0, impression=6)
    sim = _sim([imp] * 12)
    settled, layers = _drive(sim, {t: 0 for t in range(1, 7)})
    assert settled == [6, 12, 17, 22, 27, 32, 31, 30, 29]
    # 回合开始层 t2..t9（最后一回合末 sim 不再抽牌故不扣，引擎扣——纯 cosmetic，
    # 结算分已在此之前发生，逐位一致；这里比对前 8 个回合开始层）。
    assert layers[:8] == [6, 11, 16, 21, 26, 31, 30, 29]


def test_card_impression_single_grant_fresh() -> None:
    """单渠道好印象 +6 t1：结算 6,6,5,4,…（fresh 多结算一回合，引擎 probe5 A 同构）。"""
    imp = CardSpec("好印象", 0, 0, impression=6)
    sim = _sim([imp] * 12)  # 全好印象牌堆，仅 t1 打一张（其余 SKIP）
    settled, layers = _drive(sim, {1: 0})
    assert settled[:4] == [6, 6, 5, 4]
    assert layers[:4] == [6, 5, 4, 3]


# --------------------------------------------------------------- 好调
def test_condition_single_grant_fresh_trajectory() -> None:
    """好调3回合 t1 获得：回合开始 3,3,2,1,0（当回合末不扣，引擎 G2 同构）。"""
    cond = CardSpec("好调", 0, 0, condition=3)
    sim = _sim([cond] * 12, turns=6)  # 全好调牌堆，仅 t1 打一张
    starts = [0]
    sim.step(0)  # t1 打好调（auto-end）
    starts.append(sim.buffs.condition_turns)
    for _ in range(5):
        if sim.done:
            break
        sim.step(None)
        starts.append(sim.buffs.condition_turns)
    assert starts[1:6] == [3, 2, 1, 0, 0]


def test_condition_stacking_fresh_trajectory() -> None:
    """_m8_fresh_cond.py：好调3回合 t1/t2 各一次 → 回合开始 3,5,4,3,2,1,0。

    叠加只保护本回合新增（t2 旧3→2 + 新3 = 5），非整体保护（否则 t3=6）。
    """
    cond = CardSpec("好调", 0, 0, condition=3)
    sim = _sim([cond] * 12, turns=8)
    starts = [0]
    sim.step(0)  # t1
    starts.append(sim.buffs.condition_turns)
    sim.step(0)  # t2
    starts.append(sim.buffs.condition_turns)
    for _ in range(6):
        if sim.done:
            break
        sim.step(None)
        starts.append(sim.buffs.condition_turns)
    assert starts[1:8] == [3, 5, 4, 3, 2, 1, 0]


# --------------------------------------------------------------- 饮料渠道
def test_drink_immediate_impression_fresh() -> None:
    """probe5 A：立即饮料好印象+3 → 回合开始 3,2,1（当回合末不扣）。"""
    drink = DrinkSpec("路易波士茶", 0, "multi", 0, effects=(
        DrinkEffect(kind="impression", value=3, effect_type="ExamReview"),))
    sim = _sim([CardSpec("占位", 0, 0)] * 12, turns=4, drinks=(drink,))
    sim.use_drink(0)
    assert sim.buffs.impression == 3 and sim.review_fresh == 3
    layers = []
    settled = []
    for _ in range(3):
        s0 = sim.score
        sim.step(None)
        settled.append(sim.score - s0)
        layers.append(sim.buffs.impression)
    assert layers == [3, 2, 1]
    assert settled == [3, 3, 2]


def test_drink_condition_fresh() -> None:
    """立即饮料好调3回合 → 回合开始 3,2,1（与卡渠道同口径）。"""
    drink = DrinkSpec("好调饮", 0, "condition", 3)
    sim = _sim([CardSpec("占位", 0, 0)] * 12, turns=4, drinks=(drink,))
    sim.use_drink(0)
    assert sim.buffs.condition_turns == 3 and sim.condition_fresh == 3
    layers = []
    for _ in range(3):
        sim.step(None)
        layers.append(sim.buffs.condition_turns)
    assert layers == [3, 2, 1]


# --------------------------------------------------------------- 双镜衰减
def test_end_turn_state_fresh_decay_mirror() -> None:
    """end_turn_state 的 fresh 衰减与 LessonSim 逐位一致（好印象+好调）。"""
    state = ExpectState(
        hand=(), deck=(), discard=(),
        impression=12, review_fresh=6,
        condition_turns=6, condition_fresh=3,
        turns_left=5, total_turns=5, stamina=30, stamina_max=30,
        clear=10**9, perfect=10**9,
    )
    after = end_turn_state(state)
    # 好印象：旧 6→5 + fresh 6 = 11；好调：旧 3→2 + fresh 3 = 5；fresh 清零。
    assert after.impression == 11 and after.review_fresh == 0
    assert after.condition_turns == 5 and after.condition_fresh == 0
    # 无 fresh 时退回旧行为（-1）。
    stale = ExpectState(
        hand=(), deck=(), discard=(),
        impression=12, review_fresh=0,
        condition_turns=6, condition_fresh=0,
        turns_left=5, total_turns=5, stamina=30, stamina_max=30,
        clear=10**9, perfect=10**9,
    )
    after2 = end_turn_state(stale)
    assert after2.impression == 11 and after2.condition_turns == 5


def test_state_from_sim_carries_fresh() -> None:
    """state_from_sim / sim_from_state 携带 review_fresh / condition_fresh（rollout 一致）。"""
    from gkagent.sim.expectimax import sim_from_state

    sim = _sim([CardSpec("占位", 0, 0)] * 12)
    # 当回合获得 fresh 的局面（直接置状态，测携带/往返而非驱动）。
    sim.buffs.impression = 10
    sim.review_fresh = 6
    sim.buffs.condition_turns = 4
    sim.condition_fresh = 3
    state = state_from_sim(sim, known_deck_order=True)
    assert state.review_fresh == 6 and state.condition_fresh == 3
    assert state.impression == 10 and state.condition_turns == 4
    rebuilt = sim_from_state(state)
    assert rebuilt.review_fresh == 6 and rebuilt.condition_fresh == 3
    # canonical 含 fresh 字段（不同 fresh → 不同记忆化键）。
    s2 = state_from_sim(sim, known_deck_order=True)
    object.__setattr__(s2, "review_fresh", 0)
    assert s2.canonical() != state.canonical()


# --------------------------------------------------------------- 引擎 oracle 配对
def _probe_rows(tag: str) -> list[dict]:
    if not PROBE.is_file():
        pytest.skip("缺少 data/_m8_fresh_probe.jsonl（探针不提交）")
    return [json.loads(line) for line in PROBE.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("tag") == tag]


def test_oracle_g1_card_impression_match() -> None:
    """G1 引擎卡渠道好印象轨迹 ↔ sim 逐回合配对（结算层 + 回合开始层）。"""
    rows = _probe_rows("G1_card_imp_repeat")
    steps = [r for r in rows if r["kind"] == "step"]
    engine_settled = [r["score_delta"] for r in steps]
    engine_layers = [r["after"]["review"] for r in steps]
    imp = CardSpec("好印象", 0, 0, impression=6)
    sim = _sim([imp] * 12)
    sim_settled, sim_layers = _drive(sim, {t: 0 for t in range(1, 7)})
    assert sim_settled == engine_settled
    # 最后一回合末 sim 不抽牌故不扣（cosmetic，结算分已发生）；比对前 8 回合开始层。
    assert sim_layers[:8] == engine_layers[:8]


def test_oracle_condition_stacking_match() -> None:
    """_m8_fresh_cond.py 引擎好调叠加轨迹 ↔ sim 逐回合配对。"""
    if not COND.is_file():
        pytest.skip("缺少 data/_m8_fresh_cond.json（探针不提交）")
    rows = json.loads(COND.read_text(encoding="utf-8"))
    steps = [r for r in rows if r["kind"] == "step"]
    engine_cond = [r["cond"] for r in steps]
    cond = CardSpec("好调", 0, 0, condition=3)
    sim = _sim([cond] * 12, turns=8)
    sim_cond = []
    sim.step(0); sim_cond.append(sim.buffs.condition_turns)
    sim.step(0); sim_cond.append(sim.buffs.condition_turns)
    for _ in range(6):
        if sim.done:
            break
        sim.step(None); sim_cond.append(sim.buffs.condition_turns)
    assert sim_cond == engine_cond


def test_oracle_probe5_drink_decay_match() -> None:
    """probe5 A/B/C 引擎好印象衰减轨迹 ↔ sim 逐位配对（立即/附魔/混合渠道）。"""
    if not PROBE5.is_file():
        pytest.skip("缺少 data/_drinks_probe5_decay.json（探针不提交）")
    data = json.loads(PROBE5.read_text(encoding="utf-8"))
    # A 立即饮料+3：回合开始 3,2,1
    a = {r["step"]: r for r in data["A_rooibos"]}
    assert [a[f"end{k}"]["impression"] for k in (1, 2, 3)] == [3, 2, 1]
    drink = DrinkSpec("路易波士茶", 0, "multi", 0, effects=(
        DrinkEffect(kind="impression", value=3, effect_type="ExamReview"),))
    sim = _sim([CardSpec("占位", 0, 0)] * 12, turns=4, drinks=(drink,))
    sim.use_drink(0)
    layers = []
    for _ in range(3):
        sim.step(None); layers.append(sim.buffs.impression)
    assert layers == [3, 2, 1]
    # C 混合（立即+3 + 附魔+1）：回合开始 4,4,4
    c = {r["step"]: r for r in data["C_rooibos_tea"]}
    assert [c[f"end{k}"]["impression"] for k in (1, 2, 3)] == [4, 4, 4]