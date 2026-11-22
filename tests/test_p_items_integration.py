"""P 道具接入 LessonSim / ExpectState 的回归测试（真数据 + 未实现 no-op）。"""

from __future__ import annotations

from gkagent.sim.expectimax import ExpectState, apply_card, expectimax_with_stats
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import EXAM_START, PItemSpec, load_p_items

ITEMS = load_p_items()


def _free(trigger: str) -> list[PItemSpec]:
    return [
        item
        for item in ITEMS
        if item.trigger == trigger
        and item.implemented
        and item.condition_known
        and not item.condition
        and not item.card_filter
        and not item.lesson_filter
        and not item.final_turn
        and item.turn is None
    ]


def _first(trigger: str, target: str | None = None) -> PItemSpec:
    for item in _free(trigger):
        if target is None or item.target == target:
            return item
    raise AssertionError(f"真数据里找不到 {trigger}/{target} 可触发的 P 道具")


def _config(**kwargs) -> LessonConfig:
    # 机制测试要在一回合里连打多张来触发 P 道具；真机默认 1 张（B3），这里显式放宽。
    base = {"turns": 1, "stamina": 20, "target_clear": 1, "hand_size": 1, "plays_per_turn": 10}
    base.update(kwargs)
    return LessonConfig(**base)


def test_turn_start_item_applies_at_lesson_start() -> None:
    item = _first("turn_start")
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=1, p_items=(item,)),
        rng_seed=0,
    )
    assert sim._p_items_by_trigger
    if item.target == "focus":
        assert sim.buffs.focus >= item.value
    elif item.target == "vitality":
        assert sim.vitality >= item.value
    else:
        assert sim.p_item_uses.get(item.item_id or item.name, 0) >= 1


def test_card_play_item_applies_before_card_effect() -> None:
    item = _first("card_play", "focus")
    sim = LessonSim(
        [CardSpec("打", 0, 0)],
        _config(turns=1, p_items=(item,)),
        rng_seed=0,
    )
    sim.hand = [CardSpec("打", 0, 0)]
    sim.step(0)
    assert sim.buffs.focus >= item.value


def test_card_played_item_applies_after_card_effect() -> None:
    item = _first("card_played", "score")
    sim = LessonSim(
        [CardSpec("打", 0, 0)],
        _config(turns=1, p_items=(item,)),
        rng_seed=0,
    )
    sim.hand = [CardSpec("打", 0, 0)]
    sim.step(0)
    assert sim.score >= item.value


def test_status_gain_item_triggers_on_impression() -> None:
    item = _first("status_gain", "impression")
    # 该道具的 status 字段必须是 impression；真数据里由 _first 保证
    assert item.status == "impression"
    sim = LessonSim(
        [CardSpec("好印象牌", 0, 0, impression=2)],
        _config(turns=1, p_items=(item,)),
        rng_seed=0,
    )
    sim.hand = [CardSpec("好印象牌", 0, 0, impression=2)]
    sim.step(0)
    assert sim.buffs.impression == 2 + item.value


def test_card_play_interval_item_fires_every_n_cards() -> None:
    item = _first("card_play_interval", "score")
    assert item.interval >= 2
    deck = [CardSpec(f"牌{i}", 0, 0) for i in range(item.interval)]
    sim = LessonSim(
        deck,
        _config(turns=1, stamina=20, hand_size=item.interval, p_items=(item,)),
        rng_seed=0,
    )
    for _ in range(item.interval):
        sim.step(0)
    assert sim.score == item.value  # 只触发一次（每 N 张）


def test_turn_end_item_applies_at_turn_end() -> None:
    candidates = [
        item
        for item in ITEMS
        if item.trigger == "turn_end"
        and item.implemented
        and item.target == "score"
        and item.remaining_turns is not None
    ]
    item = candidates[0]
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(
            turns=max(item.remaining_turns, 1),
            p_items=(item,),
        ),
        rng_seed=0,
    )
    sim.step(None)
    assert sim.score >= item.value


def test_max_uses_limits_repeated_triggers() -> None:
    item = PItemSpec(
        name="限次 P 道具",
        trigger="turn_start",
        effect_type="ExamLesson",
        value=5,
        max_uses=1,
    )
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=2, p_items=(item,)),
        rng_seed=0,
    )
    sim.step(None)
    assert sim.p_item_uses.get(item.item_id or item.name, 0) == 1
    assert sim.score == 5


def test_unimplemented_p_item_type_is_noop_and_does_not_raise() -> None:
    item = PItemSpec(
        name="未实现 P 道具",
        trigger="turn_start",
        effect_type="ExamUnknownEffect",
        value=999,
    )
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=1, p_items=(item,)),
        rng_seed=0,
    )
    sim.step(None)
    assert sim.score == 0


def test_expectimax_state_also_triggers_p_items() -> None:
    item = _first("card_played", "score")
    state = ExpectState(
        hand=(CardSpec("打", 0, 0),),
        stamina=10,
        turns_left=1,
        clear=1,
        perfect=1000,
        p_items=(item,),
    )
    outcomes = apply_card(state, state.hand[0])
    assert outcomes
    successor = outcomes[0][1]
    assert successor.score >= item.value
    assert successor.p_item_uses  # 记录了触发次数
    assert expectimax_with_stats(state).card is not None


# ---- test/考试开始（EXAM_START，T5③ 2026-11-22 P 道具数据接入）-------------


def test_exam_start_items_apply_at_sim_construction() -> None:
    """考试开始类 P 道具在 LessonSim 构造时结算一次：分数/元气/额外出牌。"""
    items = (
        PItemSpec(name="开局加分开局", trigger=EXAM_START, effect_type="ExamLesson", value=7),
        PItemSpec(name="开局元气", trigger=EXAM_START, effect_type="ExamBlock", value=3),
        PItemSpec(
            name="开局再动",
            trigger=EXAM_START,
            effect_type="ExamPlayableValueAdd",
            value=1,
        ),
    )
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=1, p_items=items),
        rng_seed=0,
    )
    assert sim.score == 7
    assert sim.vitality == 3
    assert sim.extra_plays == 1
    assert sim.p_item_uses == {"开局加分开局": 1, "开局元气": 1, "开局再动": 1}


def test_exam_start_runs_before_turn_start() -> None:
    """顺序是「考试开始 → 回合开始」：turn_start 的条件能看到 exam_start 给的层数。"""
    exam = PItemSpec(name="开局元气", trigger=EXAM_START, effect_type="ExamBlock", value=5)
    turn = PItemSpec(
        name="回合开始打分",
        trigger="turn_start",
        effect_type="ExamLesson",
        value=9,
        condition="元气在5以上的时候",
    )
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=1, p_items=(exam, turn)),
        rng_seed=0,
    )
    assert sim.vitality == 5
    assert sim.score == 9  # 条件成立 → turn_start 道具触发


def test_exam_start_extra_play_keeps_first_turn_open() -> None:
    """exam_start 给的额外出牌次数属于第 1 回合：第 1 张打完不自动结束回合。"""
    extra = PItemSpec(
        name="开局再动",
        trigger=EXAM_START,
        effect_type="ExamPlayableValueAdd",
        value=1,
    )
    deck = [CardSpec(f"牌{i}", 0, 0) for i in range(3)]
    config = _config(turns=1, hand_size=2, plays_per_turn=1, p_items=(extra,))
    sim = LessonSim(list(deck), config, rng_seed=0)
    assert sim.extra_plays == 1
    sim.step(0)
    assert sim.plays_this_turn == 1
    assert sim.turns_left == 1  # 没自动结束：还有 1 个额外次数 + 手牌还有 1 张
    sim.step(0)
    assert sim.turns_left == 0  # 第 2 张打完才结束

    # 对照：没有 exam_start 再动道具时，打完第 1 张就自动结束回合。
    control = LessonSim(
        list(deck), _config(turns=1, hand_size=2, plays_per_turn=1), rng_seed=0
    )
    control.step(0)
    assert control.turns_left == 0


def test_real_exam_start_item_fires_once() -> None:
    """真数据里至少有一条可结算的 exam_start 道具，触发一次并记录次数。"""
    candidates = [
        item
        for item in ITEMS
        if item.trigger == EXAM_START
        and item.implemented
        and item.condition_known
        and not item.condition
        and not item.lesson_filter
        and item.target != "stamina"
    ]
    assert candidates, "p_items.json 里应有可结算的训练/考试开始道具"
    item = candidates[0]
    sim = LessonSim(
        [CardSpec("占位", 0, 0)],
        _config(turns=1, p_items=(item,)),
        rng_seed=0,
    )
    assert sim.p_item_uses.get(item.item_id, 0) == 1
    # 第 1 回合开始时它**不会**再触发一次（exam_start 与 turn_start 是独立事件）。
    sim.step(None)
    assert sim.p_item_uses.get(item.item_id, 0) == 1
