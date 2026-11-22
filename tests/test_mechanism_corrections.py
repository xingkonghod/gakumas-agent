"""2026-11-16 Gemini + wiki 机制核对的回归测试。

四条修正：
1. 喝饮料不占出牌次数（`use_drink` / `UseDrinkState` 都不动 plays_used）；
2. CLEAR/PERFECT 收益是连续进度，不是三档（score=50/clear=40/perfect=25 → 50）；
3. 好印象回合末加分、**下一回合开始**才 -1（最终回合不再扣）；
4. やる気（motivation）只放大元气获得量，和元气（vitality）分开存、都跨回合保留。
"""

from __future__ import annotations

import json

from gkagent.sim.expectimax import ExpectState, use_drink_state
from gkagent.sim.lesson import CardSpec, DrinkSpec, LessonConfig, LessonSim
from gkagent.sim.produce import ProduceConfig, ProduceSim
from gkagent.sim.stance import StanceState


def _config(**kwargs) -> LessonConfig:
    # 本文件是「一回合内连打多张」的机制核对：显式 3 次/回合（真机默认 1 张；
    # 旧口径 3 保留给机制叠加测试，B3 2026-11-22）。
    base = {"turns": 1, "stamina": 10, "target_clear": 1, "hand_size": 3, "plays_per_turn": 3}
    base.update(kwargs)
    return LessonConfig(**base)


def test_drinking_does_not_consume_play_slots() -> None:
    """饮料不占出牌次数：先喝 2 瓶，plays_used 仍 0，之后还能打满 3 张。"""
    drinks = (
        DrinkSpec("体力A", 0, "stamina", 2),
        DrinkSpec("体力B", 0, "stamina", 2),
    )
    deck = [CardSpec(f"牌{i}", 0, 5) for i in range(3)]
    sim = LessonSim(
        deck,
        _config(turns=1, stamina=10, hand_size=3, plays_per_turn=3, drinks=drinks),
        rng_seed=0,
    )
    sim.use_drink(0)
    sim.use_drink(1)  # 当前仓库口径 drinks_per_turn=None：不限瓶数
    assert sim.plays_this_turn == 0
    for _ in range(3):
        sim.step(0)
    assert sim.plays_this_turn == 3
    assert sim.score == 15

    state = ExpectState(
        hand=tuple(deck),
        stamina=10,
        play_limit=3,
        drinks=drinks,
        drink_uses=(1, 1),
        clear=10,
    )
    state = use_drink_state(state, 0)
    state = use_drink_state(state, 1)
    assert state.plays_used == 0
    assert state.plays_left == 3


def test_lesson_reward_gain_is_continuous() -> None:
    """score=50 / CLEAR=40 / PERFECT=25 → 40 + 10 = 50；未到 CLEAR 按已达成部分。"""
    deck = [CardSpec("占位", 0, 0)]
    sim = LessonSim(deck, _config(turns=1, target_clear=40, target_perfect=65))
    for score, expected in ((30, 30), (40, 40), (50, 50), (65, 65), (70, 65), (0, 0)):
        sim.score = score
        assert sim.reward_gain == expected
    # 档位判定保留（PERFECT 阈值 = CLEAR + PERFECT 值）
    sim.score = 65
    assert sim.reward_tier == 2
    sim.score = 40
    assert sim.reward_tier == 1


def test_produce_training_gain_uses_continuous_progress(tmp_path) -> None:
    path = tmp_path / "official.json"
    path.write_text(
        json.dumps(
            {
                "schedule": [
                    {
                        "week": 1,
                        "action": "train",
                        "clear": 40,
                        "perfect": 25,
                        "train_clear": 40,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    sim = ProduceSim(
        [CardSpec("占位", 0, 0)],
        config=ProduceConfig(schedule_path=str(path), support_lesson_bonus=0.0),
        rng_seed=0,
    )
    assert sim._official_training_gain(30) == 30
    assert sim._official_training_gain(40) == 40
    assert sim._official_training_gain(50) == 50
    assert sim._official_training_gain(65) == 65
    assert sim._official_training_gain(80) == 65
    # 支援卡レッスンボーナス：base × (1+sum%)，向下取整
    buffed = ProduceSim(
        [CardSpec("占位", 0, 0)],
        config=ProduceConfig(
            schedule_path=str(path), support_lesson_bonus=0.5
        ),
        rng_seed=0,
    )
    assert buffed._official_training_gain(50) == 75
    assert buffed._official_training_gain(80) == 97


def test_impression_decrements_at_next_turn_start_not_final_turn() -> None:
    """好印象：回合末按当前层数加分；下一回合开始 -1；最后一回合不再扣。"""
    deck = [CardSpec("占位", 0, 0), CardSpec("占位2", 0, 0)]
    sim = LessonSim(
        deck,
        _config(turns=2, hand_size=2),
        rng_seed=0,
    )
    sim.buffs.impression = 3
    sim.step(None)  # 回合 1 结束 → 加 3 分，进入回合 2 时层数 -1
    assert sim.score == 3
    assert sim.buffs.impression == 2
    sim.step(None)  # 回合 2（最终）结束 → 加 2 分，不再扣
    assert sim.score == 5
    assert sim.buffs.impression == 2

    final = LessonSim(deck, _config(turns=1, hand_size=2), rng_seed=0)
    final.buffs.impression = 3
    final.step(None)
    assert final.score == 3
    assert final.buffs.impression == 3  # 没有下一回合，不扣


def test_motivation_and_vitality_are_separate_and_persist() -> None:
    """やる気只放大元气获得量：干劲牌不加元气，元气牌吃干劲，二者都跨回合保留。"""
    motivation = CardSpec("干劲", 0, 0, motivation=2)
    vitality = CardSpec("元气", 0, 0, vitality=3)
    sim = LessonSim(
        [motivation, vitality],
        _config(turns=2, hand_size=2),
        rng_seed=0,
    )
    sim.hand = [motivation, vitality]
    sim.step(0)
    assert (sim.motivation, sim.vitality) == (2, 0)
    sim.step(0)  # 手牌打空 → 自动进入下一回合
    assert (sim.motivation, sim.vitality) == (2, 5)
    assert sim.turns_left == 1


# ---------------------------------------------------------------- 2026-11-16 第二批 wiki 核实


def test_exam_rank_uses_exam_score_not_attributes() -> None:
    """考试名次只按局内最终得分与 NPC 分数档比；属性加权只配做最终评价点。"""
    config = ProduceConfig(
        weeks=1,
        exam_weeks=(1,),
        exam_turns_mid=1,
        audition_coefficient=1.0,
        exam_npc_scores=((100, 50, 8, 0), (100, 50, 8, 0)),
        reward_pick="none",
    )
    sim = ProduceSim([CardSpec("打", 0, 7)], config=config, rng_seed=0)
    sim.attrs = [900, 900, 900]  # 属性很高，但局内只打 7 分
    score_exam = sim.exam(0)
    assert score_exam["score"] == 7
    assert score_exam["rank"] == 4  # 100/50/8 三个 NPC > 7
    assert score_exam["passed"] is False
    assert score_exam["rank_mode"] == "score"
    # ablation：旧属性口径会判第 1；新口径不再用属性
    old = ProduceSim(
        [CardSpec("打", 0, 7)],
        config=ProduceConfig(
            weeks=1,
            exam_weeks=(1,),
            exam_turns_mid=1,
            audition_coefficient=1.0,
            exam_npc_scores=((100, 50, 8, 0), (100, 50, 8, 0)),
            exam_rank_mode="attribute",
            reward_pick="none",
        ),
        rng_seed=0,
    )
    old.attrs = [900, 900, 900]
    assert old.exam(0)["rank"] == 1


def test_exam_turn_counts_mid_and_final_by_plan() -> None:
    """期中 9 回合；期末 Sense/Anomaly 12、Logic 11 回合。"""
    base = {
        "weeks": 16,
        "exam_weeks": (7, 16),
        "exam_turns_mid": 9,
        "exam_turns_final": 12,
        "exam_turns_final_logic": 11,
        "audition_coefficient": 1.0,
        "reward_pick": "none",
    }
    sense = ProduceSim([CardSpec("打", 0, 1)], config=ProduceConfig(**base), rng_seed=0)
    assert sense.exam(0)["turns"] == 9
    sense.week = 16
    assert sense.exam(1)["turns"] == 12
    logic = ProduceSim(
        [CardSpec("打", 0, 1)],
        config=ProduceConfig(**base, plan="logic"),
        rng_seed=0,
    )
    logic.week = 16
    assert logic.exam(1)["turns"] == 11


def test_training_has_no_entry_stamina_cost() -> None:
    """训练没有固定入场耗体：只按局内打出的牌结算；0 费牌不扣体力。"""
    free = ProduceSim(
        [CardSpec("免费", 0, 100)],
        config=ProduceConfig(
            weeks=1,
            exam_weeks=(),
            schedule_source="constants",
            training_targets=(100,),
            training_gain_ratio=0.5,
            support_lesson_bonus=0.0,
            start_stamina=10,
        ),
        rng_seed=0,
    )
    assert free.config.training_cost == 0
    assert free.training() is True
    assert free.stamina == 10  # 0 费牌不扣体力，且没有 10 点入场费
    costly = ProduceSim(
        [CardSpec("贵", 3, 5)],
        config=ProduceConfig(
            weeks=1,
            exam_weeks=(),
            schedule_source="constants",
            training_targets=(100,),
            training_gain_ratio=0.5,
            support_lesson_bonus=0.0,
            start_stamina=10,
        ),
        rng_seed=0,
    )
    costly.training()
    assert 0 <= costly.stamina < 10  # 只扣局内牌费


def test_rest_recovers_70_percent_and_is_unavailable_at_full() -> None:
    sim = ProduceSim(
        [CardSpec("打", 0, 1)],
        config=ProduceConfig(stamina_max=35, start_stamina=0),
        rng_seed=0,
    )
    sim.stamina = 0
    assert sim.rest() is True
    assert sim.stamina == 24  # floor(35×0.7)
    sim.stamina = 35
    assert sim.rest() is False
    assert sim.stamina == 35


def test_stance_cost_modifiers_and_strong_pierce() -> None:
    card = CardSpec("四费", 4, 0)
    cases = [
        (StanceState(stance="normal"), 10, 0, 6),
        (StanceState(stance="save", save_level=1), 10, 0, 8),
        (StanceState(stance="save", save_level=2), 10, 0, 9),
        (StanceState(stance="strong1"), 10, 0, 2),
        (StanceState(stance="strong2"), 10, 5, 7),  # 穿透 1 点：体力 -1，元气 -5，体力再 -2
    ]
    for stance, stamina, vitality, expected in cases:
        # plays_per_turn=1：出 1 张就用尽次数，回合自动结束且不回体力（B3 真机规则）
        sim = LessonSim(
            [card], _config(turns=1, stamina=stamina, plays_per_turn=1), rng_seed=0
        )
        sim.hand = [card]
        sim.stamina = stamina
        sim.vitality = vitality
        sim.stance = stance
        sim.step(0)
        assert sim.stamina == expected, (stance, sim.stamina, expected)
        assert sim.vitality == 0


def test_save_release_gives_enthusiasm_not_condition_turns() -> None:
    """解除温存（T5②）：熱意 +5 / 額外出牌次数 +1，不再近似成好调回合。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    filler = CardSpec("占位", 0, 0)
    sim = LessonSim(
        [save, strong, filler],
        _config(turns=2, stamina=10, hand_size=3),
        rng_seed=0,
    )
    sim.hand = [save, strong, filler]
    sim.step(0)  # 切到温存 1 段階：还没有熱意
    assert sim.enthusiasm == 0
    sim.step(0)  # 温存→強気 解除：熱意 +5、本回合多 1 次出牌
    assert sim.stance.stance != "save"
    assert sim.enthusiasm == 5
    assert sim.extra_plays == 1
    assert sim.buffs.condition_turns == 0
