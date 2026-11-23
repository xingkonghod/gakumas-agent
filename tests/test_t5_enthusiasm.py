"""T5②（2026-11-22）熱意（enthusiasm）+ 温存解除 机制回归。

口径来源（证据见 `src/gkagent/sim/enthusiasm.py` 模块 docstring）：

- 参考引擎 gakumas-tools（BSD-3）`constants.js STANCE_CHANGED_EFFECTS`：
  温存 1 段階解除 → 熱意 +5、出牌次数 +1；2 段階解除 → 熱意 +8、固定元気 +5、
  出牌次数 +1；同回合重复解除可重复获得；
- `Executor/resolvers.js`：`score += 熱意`（集中之后、好调/指針之前），
  `resolveEnthusiasm` = `(熱意追加 + 基础) × (1 + 熱意増加‰)`，回合末熱意清零；
  `TurnManager.endTurn`：有熱意延長时回合末不清零，改为消耗 1 层延長；
- 官方 wiki 温存条（`data/cache/_buffs_before.json`）：「熱意+5・使用数追加+1」
  「熱意+8・固定元気+5・使用数追加+1」「ターン終了時、熱意を0にする」。
"""

from __future__ import annotations

from dataclasses import replace

from gkagent.sim.enthusiasm import (
    enthusiasm_gain,
    release_on_stance_change,
    turn_end_enthusiasm,
)
from gkagent.sim.expectimax import (
    apply_card,
    end_turn_state,
    sim_from_state,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.stance import StanceState


def _config(**kwargs) -> LessonConfig:
    base = {
        "turns": 2,
        "stamina": 20,
        "target_clear": 1,
        "hand_size": 3,
        "plays_per_turn": 3,
    }
    base.update(kwargs)
    return LessonConfig(**base)


def _sim(deck: list[CardSpec], hand: list[CardSpec], **config) -> LessonSim:
    sim = LessonSim(deck, _config(**config), rng_seed=0)
    sim.hand = list(hand)
    sim.deck = []
    sim.discard = []
    return sim


# ---------------------------------------------------------------- 纯规则


def test_release_rules_match_reference_constants() -> None:
    """温存 1/2 段階解除的基础值、固定元気、+1 出牌次数（参考引擎常量）。

    P1-1（2026-11-24）：返回值扩成 4 元组，末位是全体卡打分成长
    （のんびり→全力 才有，温存解除恒 0）。
    """
    normal = StanceState()
    save1 = StanceState(stance="save", save_level=1)
    save2 = StanceState(stance="save", save_level=2)
    strong = StanceState(stance="strong1")
    full = StanceState(stance="full")

    assert release_on_stance_change(save1, strong) == (5, 0, 1, 0)
    assert release_on_stance_change(save2, strong) == (8, 5, 1, 0)
    assert release_on_stance_change(save1, full) == (5, 0, 1, 0)  # 解除到全力也触发
    # 进入温存 / 温存段階升级 / 离开的不是温存 → 不触发
    assert release_on_stance_change(normal, save1) == (0, 0, 0, 0)
    assert release_on_stance_change(save1, save2) == (0, 0, 0, 0)
    assert release_on_stance_change(strong, normal) == (0, 0, 0, 0)


def test_enthusiasm_gain_formula_and_rounding() -> None:
    """``(熱意追加 + N) × (1 + 増加‰)``，获得时向上取整（WHOLE_FIELDS）。"""
    assert enthusiasm_gain(5) == 5
    assert enthusiasm_gain(5, bonus=5) == 10
    assert enthusiasm_gain(5, multiple_permil=1000) == 10
    assert enthusiasm_gain(5, bonus=5, multiple_permil=1000) == 20
    # 5 × 1.1 = 5.5 → 参考引擎 WHOLE_FIELDS ceil → 6（wiki 同口径）
    assert enthusiasm_gain(5, multiple_permil=100) == 6
    assert enthusiasm_gain(8, multiple_permil=300) == 11  # 10.4 → 11


def test_turn_end_enthusiasm_reset_or_extension() -> None:
    """回合末：没延長归 0；有延長保留并 -1；延長可叠多层。"""
    assert turn_end_enthusiasm(7.0, 0) == (0.0, 0)
    assert turn_end_enthusiasm(7.0, 2) == (7.0, 1)
    assert turn_end_enthusiasm(0.0, 0) == (0.0, 0)


# ---------------------------------------------------------------- LessonSim


def test_save_release_grants_enthusiasm_and_extra_play() -> None:
    """温存→強気：熱意 +5、出牌次数 +1（本回合还能再打一张）。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    filler = CardSpec("占位", 1, 0)
    sim = _sim([save, strong, filler], [save, strong, filler])
    sim.step(0)  # 温存 1 段階
    assert sim.enthusiasm == 0
    sim.step(0)  # 温存 → 強気（解除）
    assert sim.stance.stance != "save"
    assert sim.enthusiasm == 5
    assert sim.extra_plays == 1
    assert sim.plays_per_turn + sim.extra_plays - sim.plays_this_turn == 2


def test_save_level2_release_grants_fixed_genki_without_motivation() -> None:
    """温存 2 段階解除：熱意 +8、固定元気 +5（不吃「やる気」）、+1 出牌。"""
    save2 = CardSpec("温存2", 0, 0, preservation=2)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    filler = CardSpec("占位", 1, 0)
    sim = _sim([save2, strong, filler], [save2, strong, filler])
    sim.motivation = 3  # 固定元気不吃やる気：若吃了会变 +8
    sim.vitality = 1
    sim.step(0)
    assert sim.stance.save_level == 2
    sim.step(0)
    assert sim.enthusiasm == 8
    assert sim.vitality == 1 + 5
    assert sim.extra_plays == 1


def test_repeated_save_release_stacks_in_same_turn() -> None:
    """同一回合反复「温存→強気」：每次都给熱意 +5 / 出牌次数 +1。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    filler = CardSpec("占位", 1, 0)
    hand = [save, strong, save, strong, filler]
    sim = _sim([save, strong, filler], hand, plays_per_turn=4)
    for _ in range(4):
        sim.step(0)
    assert sim.enthusiasm == 10
    assert sim.extra_plays == 2
    assert sim.plays_this_turn == 4


def test_enthusiasm_adds_to_scoring_card_after_release() -> None:
    """熱意参与本牌算分：(10 + 熱意 5) × 強気1 ×2 = 30（集中加算之后加）。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    hit = CardSpec("打分", 1, 10)
    sim = _sim([save, strong, hit], [save, strong, hit])
    sim.step(0)  # 温存
    sim.step(0)  # 解除：熱意 5，切到強気 1 段階
    sim.step(0)  # 打分：raw = (10 + 5) × 2 = 30
    assert sim.score == 30


def test_enthusiasm_multiplier_card_doubles_contribution() -> None:
    """ExamMultipleEnthusiasticLesson（本牌熱意適用倍数 ×2）：20 分而非 15 分。"""
    normal = CardSpec("普通", 1, 10)
    boosted = CardSpec("熱意倍化", 1, 10, enthusiasm_multiplier=2000)
    for card, expected in ((normal, 15), (boosted, 20)):
        sim = _sim([card], [card])
        sim.enthusiasm = 5
        sim.step(0)
        assert sim.score == expected


def test_enthusiasm_is_not_added_to_zero_score_buff_card() -> None:
    """纯 buff 牌（score=0）不吃熱意加算（参考引擎 ``if score>0`` 才加）。"""
    buff = CardSpec("纯buff", 0, 0, condition=1)
    filler = CardSpec("占位", 1, 0)
    sim = _sim([buff, filler], [buff, filler])
    sim.enthusiasm = 5
    sim.step(0)
    assert sim.score == 0
    assert sim.buffs.condition_turns == 1


def test_turn_end_good_impression_adds_enthusiasm() -> None:
    """回合末好印象结算也加熱意（参考引擎好印象走同一个 resolveScore）。"""
    imp = CardSpec("好印象", 0, 0, impression=3)
    sim = _sim([imp], [imp])
    sim.enthusiasm = 4
    sim.step(0)  # 打完后手牌空 → 自动结束回合，好印象 3 + 熱意 4
    assert sim.score == 7
    assert sim.enthusiasm == 0  # 回合末清零


def test_enthusiasm_bonus_buff_feeds_release_gain() -> None:
    """熱意追加 buff（ExamEnthusiasticAdditive）：解除温存的基础 5 → (5+5)=10。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    bonus = CardSpec("熱意追加", 0, 0, enthusiasm_bonus=5)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    filler = CardSpec("占位", 1, 0)
    hand = [save, bonus, strong, filler]
    sim = _sim([save, bonus, strong, filler], hand)
    sim.step(0)  # 温存
    sim.step(0)  # 熱意追加 buff
    assert sim.buffs.enthusiasm_bonus == 5
    sim.step(0)  # 解除温存
    assert sim.enthusiasm == 10
    # buff 默认只持续到本回合末（turns 缺省 0 → 1 回合）
    sim.step(None)  # SKIP 结束回合
    assert sim.buffs.enthusiasm_bonus == 0


def test_enthusiasm_multiple_buff_feeds_release_gain() -> None:
    """熱意増加 buff（ExamEnthusiasticMultiple，千分比）：基础 5 × (1+1000‰) = 10。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    multiple = CardSpec("熱意増加", 0, 0, enthusiasm_multiple=1000)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    filler = CardSpec("占位", 1, 0)
    hand = [save, multiple, strong, filler]
    sim = _sim([save, multiple, strong, filler], hand)
    sim.step(0)
    sim.step(0)
    assert sim.buffs.enthusiasm_multiple == 1000
    sim.step(0)
    assert sim.enthusiasm == 10


def test_enthusiasm_extension_keeps_enthusiasm_across_turn_end() -> None:
    """熱意延長：回合末保留熱意并消耗 1 层延長；下一回合末才清零。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    ext = CardSpec("熱意延長", 0, 0, enthusiasm_extension=1)
    filler = CardSpec("占位", 1, 0)
    hand = [save, strong, ext, filler]
    sim = _sim([save, strong, ext, filler], hand)
    sim.step(0)  # 温存
    sim.step(0)  # 解除 → 熱意 5
    sim.step(0)  # 熱意延長 1
    assert sim.enthusiasm_extension_turns == 1
    sim.step(None)  # 回合末：保留熱意 5、延長 1 → 0
    assert sim.enthusiasm == 5
    assert sim.enthusiasm_extension_turns == 0
    assert sim.turns_left == 1
    sim.step(None)  # 下一回合末：没有延長 → 熱意归 0
    assert sim.enthusiasm == 0
    assert sim.turns_left == 0


def test_save_release_at_turn_boundary_grants_next_turn_extra_play() -> None:
    """温存→全力 的回合边界切换也触发解除收益（参考引擎 startTurn 的 setStance）。

    P1-1（2026-11-24）：全力回合本身再 +1 出牌次数（FULL_POWER_CHANGED_EFFECTS，
    与温存解除的 +1 是两条独立效果）→ 边界后新回合 extra_plays = 1 + 1 = 2。
    """
    save = CardSpec("温存攒点", 0, 0, preservation=1, full_power_point=10)
    filler = CardSpec("占位", 1, 0)
    sim = _sim([save, filler], [save, filler], plays_per_turn=2)
    sim.step(0)  # 温存 + 全力值 10
    assert sim.stance.stance == "save"
    sim.step(0)  # 占位牌打完自动结束回合 → 全力值满 → 下一回合全力
    assert sim.stance.stance == "full"
    assert sim.turns_left == 1
    assert sim.enthusiasm == 5
    assert sim.extra_plays == 2


# ---------------------------------------------------------------- ExpectState 镜像


def test_expect_state_matches_lesson_sim_for_save_release() -> None:
    """同一序出牌后，ExpectState 的熱意 / 出牌次数 / 分数与 LessonSim 一致。"""
    save = CardSpec("温存", 0, 0, preservation=1)
    strong = CardSpec("强气", 0, 0, strong_level=1)
    hit = CardSpec("打分", 1, 10)
    sim = _sim([save, strong, hit], [save, strong, hit])
    sim.step(0)
    sim.step(0)
    assert (sim.enthusiasm, sim.extra_plays) == (5, 1)

    state = state_from_sim(sim, known_deck_order=True)
    assert state.enthusiasm == 5
    assert state.extra_plays == 1
    outcomes = apply_card(state, hit)
    assert outcomes and max(outcomes, key=lambda item: item[0])[1].score == 30

    back = sim_from_state(state)
    assert back.enthusiasm == 5
    assert back.extra_plays == 1
    assert back.plays_per_turn == sim.plays_per_turn
    assert back.buffs.enthusiasm_bonus == sim.buffs.enthusiasm_bonus


def test_expect_state_turn_end_resets_or_extends_enthusiasm() -> None:
    """ExpectState 回合末与 LessonSim 同口径：无延長清零、有延長保留并 -1。"""
    base = state_from_sim(_sim([CardSpec("占位", 1, 0)], [CardSpec("占位", 1, 0)]))
    assert end_turn_state(base).enthusiasm == 0  # 没熱意时行为不变

    # 手工状态：熱意 7 + 延長 2 → 回合末保留 7、延長 1
    extended = replace(base, enthusiasm=7, enthusiasm_extension_turns=2)
    after = end_turn_state(extended)
    assert after.enthusiasm == 7
    assert after.enthusiasm_extension_turns == 1
    cleared = end_turn_state(replace(extended, enthusiasm_extension_turns=0))
    assert cleared.enthusiasm == 0
