"""非凡指針状态机的单测：倍率表 / 全力值结算 / 温存段階 / 卡效果翻译。"""

from __future__ import annotations

import pytest

from gkagent.sim.stance import (
    FULL_POWER_POINT_COST,
    MULTIPLIER,
    Stance,
    StanceState,
    apply_full_power_point,
    card_stance_effect,
    end_turn,
    score_multiplier,
)


def test_multiplier_table_matches_official_values() -> None:
    """倍率表必须与官方攻略表一致，且全力门槛是 10。"""
    assert MULTIPLIER == {
        "save1": 0.5,
        "save2": 0.25,
        "normal": 1.0,
        "strong1": 2.0,
        "strong2": 2.5,
        "full": 3.0,
    }
    assert FULL_POWER_POINT_COST == 10


def test_score_multiplier_for_each_stance() -> None:
    """温存 / 強気 / 全力 / 无指針四种指針的倍率；未知指針按无指針保守处理。"""
    assert score_multiplier(StanceState()) == 1.0
    assert score_multiplier(StanceState(stance=Stance.SAVE, save_level=1)) == 0.5
    assert score_multiplier(StanceState(stance=Stance.SAVE, save_level=2)) == 0.25
    assert score_multiplier(StanceState(stance=Stance.STRONG1)) == 2.0
    assert score_multiplier(StanceState(stance=Stance.STRONG2)) == 2.5
    assert score_multiplier(StanceState(stance=Stance.FULL)) == 3.0
    assert score_multiplier(StanceState(stance="no-such-stance")) == 1.0


def test_strong_level_alias_and_save_level_are_clamped() -> None:
    """兼容 strong + level 写法；段階 0/越界都夹到 1/2 段階，不抛异常。"""
    assert score_multiplier(StanceState(stance="strong", strong_level=1)) == 2.0
    assert score_multiplier(StanceState(stance="strong", strong_level=2)) == 2.5
    assert score_multiplier(StanceState(stance=Stance.SAVE, save_level=0)) == 0.5
    assert score_multiplier(StanceState(stance=Stance.SAVE, save_level=99)) == 0.25


def test_apply_full_power_point_accumulates_without_mutating() -> None:
    """加全力值是可叠加的纯函数；负增量按 0 处理。"""
    before = StanceState(stance=Stance.SAVE, save_level=1, full_power_point=8)
    after = apply_full_power_point(before, 3)

    assert after.full_power_point == 11
    assert after.stance == Stance.SAVE
    assert before.full_power_point == 8  # 纯函数：原状态不变
    assert apply_full_power_point(before, -5).full_power_point == 8


def test_apply_full_power_point_rejects_bool() -> None:
    """bool 是 int 的子类，但这里必须当错误参数拒绝。"""
    with pytest.raises(TypeError, match="delta"):
        apply_full_power_point(StanceState(), True)  # type: ignore[arg-type]


def test_end_turn_switches_to_full_when_threshold_reached() -> None:
    """全力值 10 → 回合结束消耗 10 并切到全力。"""
    state = StanceState(stance=Stance.SAVE, save_level=1, full_power_point=10)
    after = end_turn(state)

    assert after.stance == Stance.FULL
    assert after.full_power_point == 0
    assert after.save_level == 1  # 只切指針，不清段階
    assert state.stance == Stance.SAVE  # 原状态不变


def test_end_turn_only_consumes_ten_points() -> None:
    """超过 10 的部分保留给下一次全力。"""
    after = end_turn(StanceState(full_power_point=12))

    assert (after.stance, after.full_power_point) == (Stance.FULL, 2)


def test_end_turn_below_threshold_keeps_state() -> None:
    """全力值 <10：不扣点、不切指針，但返回新副本。"""
    state = StanceState(stance=Stance.STRONG2, full_power_point=9)
    after = end_turn(state)

    assert after == state
    assert after is not state


def test_full_lasts_one_turn_then_returns_to_normal() -> None:
    """全力回合结束回到无指針；若又攒满 10 点则继续全力。"""
    expired = end_turn(StanceState(stance=Stance.FULL, full_power_point=0))
    assert expired.stance == Stance.NORMAL
    assert expired.full_power_point == 0

    again = end_turn(StanceState(stance=Stance.FULL, full_power_point=10))
    assert (again.stance, again.full_power_point) == (Stance.FULL, 0)


def test_card_stance_effect_preservation_sets_save_stage() -> None:
    """ExamPreservation 的 values[0] 是温存段階（1/2），不是全力值。"""
    level1 = card_stance_effect("ExamPreservation", [1])
    assert level1 == {
        "stance": Stance.SAVE,
        "save_level": 1,
        "full_power_point": 0,
    }
    assert score_multiplier(StanceState(stance=Stance.SAVE, save_level=1)) == 0.5

    level2 = card_stance_effect("ExamPreservation", [2])
    assert level2 == {
        "stance": Stance.SAVE,
        "save_level": 2,
        "full_power_point": 0,
    }
    assert score_multiplier(StanceState(stance=Stance.SAVE, save_level=2)) == 0.25


def test_card_stance_effect_full_power_point_is_additive() -> None:
    """ExamFullPowerPoint 的 values[0] 是全力值增量，不改变指針。"""
    delta = card_stance_effect("ExamFullPowerPoint", [3])

    assert delta == {"stance": None, "save_level": 0, "full_power_point": 3}
    after = apply_full_power_point(StanceState(full_power_point=8), delta["full_power_point"])
    assert after.full_power_point == 11


def test_card_stance_effect_unknown_types_are_noops() -> None:
    """ExamStatusEnchant / 未知类型 / 坏 values：保守 no-op，不崩。"""
    noop = {"stance": None, "save_level": 0, "full_power_point": 0}

    assert card_stance_effect("ExamStatusEnchant", []) == noop
    assert card_stance_effect("NotARealEffect", [9]) == noop
    assert card_stance_effect("ExamPreservation", []) == noop
    assert card_stance_effect("ExamPreservation", [3]) == noop
    assert card_stance_effect("ExamFullPowerPoint", []) == noop
    assert card_stance_effect("ExamFullPowerPoint", [-4]) == noop


def test_full_power_cycle_end_to_end() -> None:
    """攒 5+5 → 回合结束全力 3.0x → 全力回合结束回无指針 1.0x。"""
    state = apply_full_power_point(StanceState(), 5)
    state = apply_full_power_point(state, 5)
    assert state.full_power_point == 10

    state = end_turn(state)
    assert state.stance == Stance.FULL
    assert state.full_power_point == 0
    assert score_multiplier(state) == 3.0

    state = end_turn(state)
    assert state.stance == Stance.NORMAL
    assert score_multiplier(state) == 1.0
