"""B3/T5 真机回合规则：每回合基础 1 张 + 追加次数 + 跳过回体力。

规则来源（2026-11-22 核实）：
- gakumas-tools（BSD-3）``TurnManager.startTurn``：``cardUsesRemaining = 1``；
- 同 ``CardManager.useCard`` 末尾：``cardUsesRemaining < 1 → endTurn``（打完最后一张
  **自动结束回合**）；
- 同 ``TurnManager.endTurn``：回合结束时 ``cardUsesRemaining > 0`` → 体力 +2（封顶
  最大体力）；
- 真机 4 场考试 39 回合逐回合日志（``tests/fixtures/t5_exam_turn_rules.json``，
  由 ``scripts/export_t5_turn_rules.py`` 从采集 traffic 导出）：32 回合正好 1 张、
  7 回合 2 张（其中 3 个首张牌带 ``ExamPlayableValueAdd``），每回合开始手牌都是 3 张。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    ExpectState,
    end_turn_state,
    search_beam,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.uiobs import DEFAULT_PLAY_LIMIT

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ------------------------------------------------------------------ 默认值对齐
def test_sim_default_plays_per_turn_is_one() -> None:
    """模拟器默认每回合 1 张（真机规则）；手牌数仍是 3。"""
    config = LessonConfig(turns=5, stamina=30, target_clear=100)
    assert config.plays_per_turn == 1
    assert config.hand_size == 3


def test_expect_state_default_play_limit_is_one() -> None:
    """搜索状态默认 play_limit=1：一回合只规划一张牌。"""
    state = ExpectState()
    assert state.play_limit == 1
    assert state.plays_left == 1


def test_uiobs_default_play_limit_is_one() -> None:
    """gkbench UIObs 上报的可出牌次数按真机 1 张算。"""
    assert DEFAULT_PLAY_LIMIT == 1


# -------------------------------------------------------------- 回合结束/回体力
def test_one_card_auto_ends_turn_without_stamina_recovery() -> None:
    """打掉本回合唯一一次出牌：回合立即结束，不回体力。"""
    sim = LessonSim(
        [CardSpec("打", 2, 9)],
        LessonConfig(turns=2, stamina=10, target_clear=9),
    )

    sim.step(0)

    assert sim.score == 9
    assert sim.turns_left == 1
    assert sim.stamina == 8  # 只付了牌费 2，没有 SKIP 的 +2
    assert sim.trace[-1]["skipped"] is False
    assert sim.trace[-1]["plays"] == 1


def test_skip_recovers_two_stamina_capped_at_max() -> None:
    """SKIP（次数没用完）回 2 体力、封顶 stamina_max。"""
    sim = LessonSim(
        [CardSpec("小", 1, 1)],
        LessonConfig(turns=2, stamina=3, stamina_max=4, target_clear=1),
    )
    assert sim.legal_actions() == [0, None]

    sim.step(None)

    assert sim.stamina == 4  # 3 + 2 封顶 4
    assert sim.turns_left == 1
    assert sim.trace[-1]["skipped"] is True


def test_skip_recovery_matches_expect_state_rule() -> None:
    """``end_turn_state`` 与 LessonSim 同口径：还有出牌次数才回 2 体力。"""
    base = ExpectState(stamina=3, stamina_max=4, turns_left=3, play_limit=1, clear=10)
    assert base.plays_left == 1
    skipped = end_turn_state(base)
    assert (skipped.stamina, skipped.turns_left) == (4, 2)

    exhausted = replace(base, plays_used=1)
    ended = end_turn_state(exhausted)
    assert ended.stamina == 3  # 出牌次数用尽 → 不回体力


def test_extra_play_keeps_turn_open_then_auto_ends() -> None:
    """卡效果 +1 次：打完追加的牌才自动结束回合（真机 7 个 2 张回合的机制）。"""
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        LessonConfig(turns=2, stamina=10, target_clear=1),
    )
    sim.hand = [
        CardSpec("次数+1", 0, 0, extra_play=1),
        CardSpec("打1", 0, 1),
        CardSpec("打2", 0, 1),
    ]
    sim.deck = []
    sim.discard = []

    sim.step(0)  # 基础 1 次用掉，追加 1 次还在
    assert sim.turns_left == 2
    assert sim.plays_this_turn == 1
    assert sim.extra_plays == 1

    sim.step(0)  # 追加次数用尽 → 自动结束回合
    assert sim.score == 1
    assert sim.turns_left == 1
    assert sim.plays_this_turn == 0
    assert sim.extra_plays == 0


def test_beam_plan_is_one_card_per_turn_without_extra_plays() -> None:
    """beam 默认局面（无额外出牌）每回合只排 1 张牌。"""
    state = ExpectState(
        hand=(CardSpec("大", 1, 10), CardSpec("中", 1, 6), CardSpec("小", 0, 3)),
        stamina=10,
        turns_left=3,
        play_limit=1,
        clear=30,
        perfect=60,
    )
    result = search_beam(state, AnalyticLeafValue(sigma=60.0))

    assert len(result.sequence) == 1
    assert result.sequence[0] in {card.name for card in state.hand}


# ------------------------------------------------------ 真机逐回合配对回归
def test_real_machine_exam_turns_follow_one_card_rule() -> None:
    """真机 4 场考试 39 回合：32 个 1 张 + 7 个 2 张，手牌每回合都是 3 张。

    素材见 ``tests/fixtures/t5_exam_turn_rules.json``（采集 traffic 导出，含溯源）。
    2 张回合里 3 个能被首张牌的 ``ExamPlayableValueAdd`` 直接解释；另外 4 个是
    P 道具追加（采集不含 P 道具数据，因此只能断言「不超过 2 张」）。
    """
    doc = json.loads((FIXTURES / "t5_exam_turn_rules.json").read_text(encoding="utf-8"))
    stats = doc["stats"]
    assert len(doc["exams"]) == 4
    assert stats["turns"] == 39
    assert stats["plays_1"] == 32
    assert stats["plays_2"] == 7

    turns = [turn for exam in doc["exams"] for turn in exam["turns"]]
    # 每回合开始手牌都是 3 张：1 张/回合不是「手牌只有 1 张」导致的
    assert {turn["hand_size"] for turn in turns} == {3}
    # 从没出现过 3 张：基础 1 次 + 卡效果/P 道具追加，最多到 2
    assert {turn["plays"] for turn in turns} <= {1, 2}
    two_play = [turn for turn in turns if turn["plays"] == 2]
    assert len(two_play) == 7
    assert sum(turn["first_card_extra_play"] for turn in two_play) == 3
    assert stats["two_play_by_card"] == 3
