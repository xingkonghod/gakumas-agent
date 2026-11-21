"""训练目标按 PERFECT（CLEAR + PERFECT 满档）的三档结算单测。"""

from __future__ import annotations

import json
from pathlib import Path

from gkagent.policy.lesson import LessonPolicy
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.produce import ProduceConfig, ProduceSim
from gkagent.vision.lesson import LessonCard, LessonState


def _policy(tmp_path: Path, **kwargs) -> LessonPolicy:
    return LessonPolicy(params_path=tmp_path / "missing.json", **kwargs)


def _card(index: int, name: str, score: int, cost: int) -> LessonCard:
    return LessonCard(
        index=index,
        box=(index * 200, 900, 190, 232),
        point=(index * 200 + 95, 1000),
        name=name,
        score=score,
        cost=cost,
        text=f"打分+{score}",
    )


# --------------------------------------------------------------------- LessonSim
def test_lesson_sim_reward_tiers_failed_clear_perfect() -> None:
    deck = [CardSpec("打", 0, 10)]

    failed = LessonSim(deck, LessonConfig(turns=1, stamina=5, target_clear=100))
    failed.step(0)
    assert (failed.result, failed.reward_tier) == ("FAILED", 0)

    clear = LessonSim(deck, LessonConfig(turns=1, stamina=5, target_clear=10))
    clear.step(0)
    assert (clear.result, clear.reward_tier) == ("CLEAR", 1)

    perfect = LessonSim(deck, LessonConfig(turns=1, stamina=5, target_clear=10, target_perfect=10))
    perfect.step(0)
    assert (perfect.result, perfect.reward_tier) == ("PERFECT", 2)


def test_lesson_sim_default_perfect_is_double_clear() -> None:
    deck = [CardSpec("打", 0, 10)]
    sim = LessonSim(deck, LessonConfig(turns=1, stamina=5, target_clear=10))
    assert sim.target_clear == 10
    assert sim.target_perfect == 20  # 缺省 = 2×CLEAR
    sim.step(0)
    assert sim.result == "CLEAR"  # 10 只到 CLEAR，不是 PERFECT

    perfect_deck = [CardSpec("大", 0, 20)]
    perfect = LessonSim(perfect_deck, LessonConfig(turns=1, stamina=5, target_clear=10))
    perfect.step(0)
    assert perfect.result == "PERFECT"


# --------------------------------------------------------------------- LessonPolicy
def test_lesson_policy_targets_perfect_not_clear(tmp_path: Path) -> None:
    """CLEAR 线 50（PERFECT 100）、当前 95：应打 9 分补刀而不是性价比更高的 4 分。"""
    cards = [_card(0, "效率牌", 4, 1), _card(1, "补刀牌", 9, 3)]
    state = LessonState(
        cards=tuple(cards),
        turns_left=2,
        stamina=10,
        score=95,
        gauge=50,
    )
    action = _policy(tmp_path).decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "补刀牌"

    # 没有 CLEAR 基准（gauge）时退回性价比：4/1 效率更高
    no_gauge = LessonState(cards=tuple(cards), turns_left=2, stamina=10, score=95)
    action = _policy(tmp_path).decide(no_gauge)
    assert action.card is not None and action.card.name == "效率牌"


def test_lesson_policy_does_not_skip_below_perfect(tmp_path: Path) -> None:
    """还没到 PERFECT 线时，低于 min_gain 的牌也要继续推进，不能 SKIP 收手。"""
    state = LessonState(
        cards=(_card(0, "小分", 3, 1),),
        turns_left=3,
        stamina=20,
        score=0,
        gauge=50,
    )
    policy = _policy(tmp_path, params={"min_gain": 5.0})
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "小分"

    no_gauge = LessonState(cards=(_card(0, "小分", 3, 1),), turns_left=3, stamina=20, score=0)
    # 2026-11-21 用户规则：没有 PERFECT 线也不许跳过——分数低不是跳过理由
    assert _policy(tmp_path, params={"min_gain": 5.0}).decide(no_gauge).kind == "card"


# --------------------------------------------------------------------- ProduceSim
def _official_path(tmp_path: Path) -> Path:
    path = tmp_path / "official.json"
    path.write_text(
        json.dumps(
            {
                "schedule": [
                    {
                        "week": 1,
                        "action": "lesson",
                        "clear": 40,
                        "perfect": 25,
                        "train_clear": 40,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _train(score: int, tmp_path: Path) -> dict:
    sim = ProduceSim(
        [CardSpec("打", 0, score)],
        config=ProduceConfig(
            weeks=1,
            exam_weeks=(),
            schedule_path=str(_official_path(tmp_path)),
            reward_pick="none",
            support_lesson_bonus=0.0,
        ),
        rng_seed=1,
    )
    sim.training()
    assert sim.last_training is not None
    return sim.last_training


def test_training_gain_uses_continuous_progress(tmp_path: Path) -> None:
    """CLEAR/PERFECT 是连续进度：gain = min(score,40) + min(max(score-40,0),25)。

    score=25 → 25（未到 CLEAR 也按已达成进度）；score=50 → 40+10=50；
    score=100 → 40+25=65（封顶）。档位判定仍是 FAILED/CLEAR/PERFECT 三档（UI 用）。
    """
    failed = _train(5, tmp_path)   # 5 回合 × 5 = 25 < CLEAR 40
    clear = _train(10, tmp_path)   # 10 × 5 = 50（40 ≤ 50 < 65）
    perfect = _train(20, tmp_path)  # 20 × 5 = 100 ≥ 65
    assert (failed["grade"], failed["attr_gain"]) == ("FAILED", 25)
    assert (clear["grade"], clear["attr_gain"]) == ("CLEAR", 50)
    assert (perfect["grade"], perfect["attr_gain"]) == ("PERFECT", 65)


def test_training_targets_read_official_clear_perfect_pair(tmp_path: Path) -> None:
    row = _train(20, tmp_path)
    assert (row["target_clear"], row["target_perfect"]) == (40, 65)
    assert row["reward_tier"] == 2


def test_training_targets_fall_back_when_official_missing(tmp_path: Path) -> None:
    sim = ProduceSim(
        [CardSpec("打", 0, 5)],
        config=ProduceConfig(
            weeks=16,
            schedule_source="constants",
            schedule_path=str(tmp_path / "missing.json"),
        ),
    )
    assert sim.training_target_pair() == (100, 200)  # 旧单值 + 默认 perfect=2×clear
