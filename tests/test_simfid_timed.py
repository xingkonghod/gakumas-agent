"""sim-fid ① timed 倍率层差一回合对齐回归（M8 G3 引擎 oracle 配对，纯 sim 无引擎跑）。

引擎锚点（data/_m8_fresh_probe.py G3 / out/_drinks_test_W9.json，均不提交）：
  * 层列表 until_turn = 获得回合 + N，获得当回合起生效 N+1 回合、until_turn 回合末移除
    （G3 好印象强化 171 +50% 5回合：t1→until6 / t3→until8 / t6→until11）。
  * 标量 stamina_consumption_down_until_turn 同口径且再施加 until += N
    （G3 005 N=2：t2→4 / t4→6 / t5→8；W9 汉方 N=3：14→17）。
  * W9 重放门（1,426,865）是纯引擎 DLL 重放（scripts/replay_rinami.py），不含 sim
    倒计时锚点 → 本对齐不动 W9 门；tests/test_drinks_m6.py 的 ((100,5))→((100,4))
    等表示断言在「0=最后生效回合」口径下逐位保持。

sim 口径：add_timed 仍存卡面 N；tick_timed 到 0 保留（0=最后生效回合）、再 tick 移除；
half_cost_turns -1=未生效 / >=0 生效；review_multiple 标量 turns==0 且值>0 时末回合清零。
"""

from __future__ import annotations

from gkagent.sim.expectimax import (
    ExpectState,
    _drink_draw_state,
    end_turn_state,
    start_turn_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    PItemDelta,
    add_timed,
    tick_timed,
    total_timed,
)


def _sim(turns: int = 12, **kw) -> LessonSim:
    deck = [CardSpec("占位", 0, 0)] * 30
    cfg = LessonConfig(turns=turns, stamina=60, target_clear=10**9, hand_size=1, **kw)
    return LessonSim(deck, cfg, rng_seed=0)


def test_tick_timed_active_span_is_n_plus_1() -> None:
    """纯函数性质：卡面 N 回合 → 生效 N+1 个回合（含获得回合），到 0 保留一回合。"""
    for n in range(1, 6):
        entries = add_timed((), 100, n)
        assert entries == ((100, n),)  # add 口径不变（drinks_m6 表示断言依赖）
        active = 0
        while total_timed(entries) > 0:
            active += 1
            entries = tick_timed(entries)
        assert active == n + 1, n


def test_g3_revmult_until_turn_trajectory() -> None:
    """G3 171 轨迹配对：t1/t3/t6 各 +50% 5回合 → 引擎 until 6/8/11，生效包络 t1..t11。

    sim 标量 max 近似只配对「生效回合边界」（叠加值 max≠引擎层加算是另一遗留缺口，
    不在本批 scope）；turns 倒计时 = until_turn − 当前回合逐位吻合。
    """
    sim = _sim(turns=12)
    card = CardSpec("好印象强化", 0, 0, review_multiple=500, review_multiple_turns=5)
    engine_until = {1: 6, 3: 8, 6: 11}  # G3 实测层 [0.5, 6, 1] / [0.5, 8, 3] / [0.5, 11, 6]
    active_turns: list[int] = []
    prev_score = 0
    for t in range(1, 13):
        # 每回合置好印象 10 层：回合末结算分 15（×1.5 生效）/ 10（未生效）探针。
        sim.buffs.impression = 10
        if t in engine_until:
            sim.hand = [card]
            sim.step(0)
            # step 含回合末 tick：倒计时 = until − 当前回合 − 1
            assert sim.buffs.review_multiple_turns == engine_until[t] - t - 1
        else:
            sim.step(None)
        delta = sim.score - prev_score
        prev_score = sim.score
        assert delta in (10, 15), (t, delta)
        if delta == 15:
            active_turns.append(t)
    assert active_turns == list(range(1, 12))  # t12 已失效（until11 末移除）
    assert sim.buffs.review_multiple == 0


def test_g3_halfcost_until_additive_trajectory() -> None:
    """G3 005 + W9 汉方配对：N=2 于 t2/t4/t5 施加 → until 4/6/8（until += N）。"""
    sim = _sim(turns=10)
    cost4 = CardSpec("费4", 4, 0)
    applies = {2, 4, 5}
    engine_until = {2: 4, 4: 6, 5: 8}
    halved_turns: list[int] = []
    for t in range(1, 11):
        if t in applies:
            sim._apply_p_delta(PItemDelta(half_cost_turns=2))
            assert sim.half_cost_turns == engine_until[t] - t
        if sim._effective_cost(cost4) == 2:
            halved_turns.append(t)
        sim.step(None)
    assert halved_turns == list(range(2, 9))  # t2..t8 减半（until8），t9 恢复
    assert sim.half_cost_turns == -1


def test_half_cost_inactive_sentinel_and_reapply() -> None:
    """-1=未生效（初始不减半）；过期后再施加从 0 起算（引擎过期再施加口径未探针）。"""
    sim = _sim(turns=6)
    cost4 = CardSpec("费4", 4, 0)
    assert sim.half_cost_turns == -1
    assert sim._effective_cost(cost4) == 4
    sim._apply_p_delta(PItemDelta(half_cost_turns=1))  # t1 → until 2
    assert sim.half_cost_turns == 1
    sim.step(None)  # t2：0 = 最后生效回合
    assert sim.half_cost_turns == 0
    assert sim._effective_cost(cost4) == 2
    sim.step(None)  # t3：-1 失效
    assert sim.half_cost_turns == -1
    assert sim._effective_cost(cost4) == 4
    sim._apply_p_delta(PItemDelta(half_cost_turns=2))  # 过期再施加 → 2（非 1）
    assert sim.half_cost_turns == 2


def test_timed_double_mirror_boundary() -> None:
    """LessonSim ↔ ExpectState 双镜：score_buffs/half_cost 含 0 边界逐位一致。"""
    from gkagent.sim.p_items import PItemSpec, EXAM_START

    specs = (
        PItemSpec(name="倍率", trigger=EXAM_START, effect_type="ExamLessonValueMultiple",
                  value=500, target_kind="score_buff", duration=2, item_id="倍率"),
        PItemSpec(name="减半", trigger=EXAM_START, effect_type="ExamStaminaConsumptionDown",
                  value=2, target_kind="half_cost_turns", duration=2, item_id="减半"),
    )
    sim = _sim(turns=6, p_items=specs)
    state = state_from_sim(sim, known_deck_order=True)
    for _ in range(5):
        assert tuple(sim.score_buffs) == tuple(state.score_buffs)
        assert sim.half_cost_turns == state.half_cost_turns
        sim.step(None)
        state = start_turn_state(_drink_draw_state(end_turn_state(state), state.hand_size))
    assert tuple(sim.score_buffs) == tuple(state.score_buffs) == ()
    assert sim.half_cost_turns == state.half_cost_turns == -1


def test_permanent_and_zero_turns_unchanged() -> None:
    """永久（-1）与 turns<=0 归一永久口径不变（回归守卫）。"""
    entries = add_timed((), 250, 0)
    assert entries == ((250, -1),)
    for _ in range(5):
        entries = tick_timed(entries)
    assert entries == ((250, -1),)
    state = ExpectState(stamina=10, stamina_max=10, turns_left=3, total_turns=3)
    assert state.half_cost_turns == -1  # 默认未生效（旧 0 语义平移，行为逐位不变）
    after = end_turn_state(state)
    assert after.half_cost_turns == -1