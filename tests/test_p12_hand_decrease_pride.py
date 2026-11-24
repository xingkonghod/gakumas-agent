"""P1-2（2026-11-24）handDecrease 抽牌修正 + pride 自尊 回归测试。

覆盖五块：

1. ④ handDecrease：回合开始抽牌 max(hand_size − Σ, 0)（TurnManager.startTurn
   cardsToDraw）、timed 列表合算/倒计时/永久、只减回合开始抽牌（卡效果抽牌不受影响）；
2. ⑤ pride：resolveScore f 的 min(min(好印象,干劲)×0.02, 0.5) 加算（千分比
   min(min×20, 500)）、prideTurns 回合末 -1、回合末好印象同吃加成、score>0 门；
3. 来源：卡「我、绝不」（ExamLessonValueMultipleDependReviewOrAggressive turn=5，
   条件门 motivation>=9）+ P 道具「一笔入魂」（status_gain aggressive & 好印象>=6 &
   limit1）+ 塔 gimmick「手牌减少1（∞回合）」（exam_start）；
4. ExpectState 双镜：_card_award / end_turn_state / fire_p_items / apply_card /
   快照往返 / canonical / beam 下一手抽牌数 / 叶子快照对齐；
5. 解析层：sim_produce / play_choice 字段映射、评测牌组组成不变、p_items.json 标注。

证据（BSD-3 gakumas-tools + 主数据交叉，详见 RULES_REFERENCE §5.5）：
- ``engine/TurnManager.js::startTurn``：cardsToDraw = max(3 − getHandDecrease, 0)；
- ``engine/BuffManager.js``：setHandDecrease(amount, turns?) / getHandDecrease /
  decrementBuffTurns（handDecreases ∈ BUFF_LIST_FIELDS / DEBUFF_LIST_FIELDS）；
- ``Executor/resolvers.js::resolveScore`` f：prideTurns>0 →
  scoreBuff += min(min(goodImpressionTurns, motivation)×0.02, 0.5)；
- ``constants.js``：prideTurns ∈ EOT_DECREMENT_FIELDS / WHOLE_FIELDS；
- ``skill_cards.csv`` 632/633「私は、決して」prideTurns+=5 / if:motivation>=9
  ↔ 主数据「我、绝不」p_card-02-ido-3_140 turn=5 / trigger …aggressive_up-9；
- ``p_items.csv`` 354/355「一筆入魂」prideTurns+=2/3; motivation+=4/5 / limit:1
  ↔ 主数据「一笔入魂」pitem_02-2-117-0/1（pIdol 117/118 = 雨夜燕）；
- wiki ``data/knowledge/buffs.json``「手札減少」：合算、≥3 抽 0、只影响回合开始抽牌。
"""

from __future__ import annotations

import random
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.sim.expectimax import (
    ExpectState,
    apply_card,
    end_turn_state,
    fire_p_items,
    search_beam,
    sim_from_state,
    state_from_sim,
)
from gkagent.sim.expectimax import (
    _card_award as expect_card_award,
)
from gkagent.sim.leaf_data import RecordingLessonSim
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
from gkagent.sim.p_items import (
    EXAM_START,
    STATUS_GAIN,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    apply_passive,
    classify_effect_target,
    load_p_items,
)
from gkagent.sim.play_choice import (
    pride_min_motivation_from_trigger,
    spec_from_name,
)


def _config(**kwargs) -> LessonConfig:
    base = {
        "turns": 4,
        "stamina": 30,
        "target_clear": 1,
        "hand_size": 3,
        "plays_per_turn": 1,
    }
    base.update(kwargs)
    return LessonConfig(**base)


def _card(name: str = "牌", score: float = 10, cost: int = 0, **kwargs) -> CardSpec:
    return CardSpec(name=name, cost=cost, score=score, **kwargs)


def _deck(n: int, **kwargs) -> list[CardSpec]:
    return [_card(f"牌{i}", **kwargs) for i in range(n)]


def _hand_decrease_spec(amount: int = 1, turns: int = 0, name: str = "手牌减少") -> PItemSpec:
    """塔 gimmick「手牌减少N（∞回合）」（exam_start；turns=0 → 永久 -1）。"""
    return PItemSpec(
        name=name,
        trigger=EXAM_START,
        effect_type="ExamGimmickStartTurnCardDrawDown",
        value=amount,
        target_kind="hand_decrease",
        duration=turns,
        item_id=name,
    )


def _pride_specs() -> list[PItemSpec]:
    """主数据「一笔入魂」/「一笔入魂+」的自尊段 spec（target=pride_turns）。"""
    return [
        spec
        for spec in load_p_items()
        if spec.item_id in ("pitem_02-2-117-0", "pitem_02-2-117-1")
        and spec.target == "pride_turns"
    ]


def _pride_item_specs(item_id: str) -> tuple[PItemSpec, ...]:
    """整件道具的全部 spec（自尊段 + 干劲段；LessonSim 按整件道具接入）。"""
    return tuple(spec for spec in load_p_items() if spec.item_id == item_id)


# ---------------------------------------------------------------- ④ handDecrease


def test_hand_decrease_reduces_turn_start_draw() -> None:
    """cardsToDraw = max(3 − handDecrease, 0)：减少 1 → 每回合手牌 2 张。"""
    sim = LessonSim(_deck(12), _config(p_items=(_hand_decrease_spec(1),)), rng_seed=0)
    assert len(sim.hand) == 2
    assert sim.hand_decreases == ((1, -1),)
    sim.step(None)  # SKIP → 下一回合
    assert len(sim.hand) == 2
    sim.step(None)
    assert len(sim.hand) == 2


def test_hand_decrease_three_or_more_draws_zero() -> None:
    """合算 ≥3 → 抽 0 张（max(...,0)；wiki「手札減少3以上…何も引かない」）。"""
    for amount in (3, 5):
        sim = LessonSim(_deck(12), _config(p_items=(_hand_decrease_spec(amount),)), rng_seed=0)
        assert sim.hand == []
        sim.step(None)
        assert sim.hand == []


def test_hand_decrease_stacks_by_amount() -> None:
    """多次付与合算（参考 setBuff 按 turns 分组、amount 加算）：1+1 → 抽 1 张。"""
    specs = (_hand_decrease_spec(1, name="a"), _hand_decrease_spec(1, name="b"))
    sim = LessonSim(_deck(12), _config(p_items=specs), rng_seed=0)
    assert sim.hand_decreases == ((2, -1),)
    assert len(sim.hand) == 1


def test_hand_decrease_timed_expires() -> None:
    """持续 2 回合的手牌减少：前 2 回合抽 2 张，第 3 回合恢复 3 张（回合末倒计时）。"""
    sim = LessonSim(_deck(20), _config(p_items=(_hand_decrease_spec(1, turns=2),)), rng_seed=0)
    assert len(sim.hand) == 2
    sim.step(None)
    assert sim.hand_decreases == ((1, 1),)
    assert len(sim.hand) == 2
    sim.step(None)
    assert sim.hand_decreases == ()
    assert len(sim.hand) == 3


def test_hand_decrease_does_not_affect_card_draw() -> None:
    """只减回合开始抽牌：卡效果抽牌（ExamCardDraw）不受影响（wiki 口径）。"""
    draw_card = _card("抽牌卡", score=0, draw=2)
    sim = LessonSim(_deck(12), _config(p_items=(_hand_decrease_spec(1),)), rng_seed=0)
    sim.hand = [draw_card]
    sim.step(0)  # 打出抽牌卡：效果抽 2 张（不是 2−1）
    assert len(sim.hand) == 2


def test_hand_decrease_default_zero_behavior() -> None:
    """无来源 → 每回合 3 张（默认逐位不变）。"""
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    assert sim.hand_decreases == ()
    assert len(sim.hand) == 3
    sim.step(None)
    assert len(sim.hand) == 3


def test_expect_state_turn_draw_count_and_tick() -> None:
    """ExpectState.turn_draw_count / end_turn_state 倒计时（与 LessonSim 双镜）。"""
    state = ExpectState(hand_size=3, hand_decreases=((1, 2),), turns_left=3)
    assert state.turn_draw_count == 2
    state = end_turn_state(state)
    assert state.hand_decreases == ((1, 1),)
    assert state.turn_draw_count == 2
    state = end_turn_state(state)
    assert state.hand_decreases == ()
    assert state.turn_draw_count == 3
    # 永久保持、合算 ≥3 → 0
    perm = ExpectState(hand_size=3, hand_decreases=((2, -1), (2, -1)))
    assert perm.turn_draw_count == 0
    assert end_turn_state(perm).hand_decreases == ((2, -1), (2, -1))


def test_expect_state_fire_p_items_hand_decrease() -> None:
    """fire_p_items exam_start → hand_decreases 落状态（setHandDecrease 同口径）。"""
    spec = _hand_decrease_spec(1)
    state = ExpectState(p_items=(spec,), turns_left=3)
    state = fire_p_items(state, EXAM_START)
    assert state.hand_decreases == ((1, -1),)
    assert state.turn_draw_count == 2


def test_state_sim_roundtrip_new_fields() -> None:
    """state_from_sim / sim_from_state 双镜带上 hand_decreases / pride_turns。"""
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.hand_decreases = ((1, 2),)
    sim.pride_turns = 3
    state = state_from_sim(sim)
    assert state.hand_decreases == ((1, 2),)
    assert state.pride_turns == 3
    rebuilt = sim_from_state(state, rng=random.Random(1))
    assert rebuilt.hand_decreases == ((1, 2),)
    assert rebuilt.pride_turns == 3
    assert len(rebuilt.hand) == 3  # 已有手牌原样保留
    # 叶子形态（手牌已空）补手牌按 cardsToDraw 口径（3−1=2 张）
    leaf = replace(state, hand=())
    rebuilt_leaf = sim_from_state(leaf, rng=random.Random(1))
    assert len(rebuilt_leaf.hand) == 2


def test_beam_next_turn_draw_uses_reduced_count() -> None:
    """beam 跨回合抽下一手按 turn_draw_count（handDecrease 1 → 每层少抽 1 张）。"""
    deck = tuple(_deck(8, score=10, cost=1))
    base = ExpectState(
        hand=(_card("手牌", score=10, cost=1),),
        deck=deck,
        stamina=30,
        stamina_max=30,
        turns_left=2,
        total_turns=2,
        play_limit=1,
        clear=1,
    )
    decreased = replace(base, hand_decreases=((1, -1),))
    rng = random.Random(0)
    res_plain = search_beam(base, width=2, deadline_ms=2000, rng=rng)
    res_decreased = search_beam(decreased, width=2, deadline_ms=2000, rng=random.Random(0))
    assert res_plain.complete and res_decreased.complete
    # 第 2 回合抽牌：普通 3 张（deck 8→5），减少 1 → 2 张（deck 8→6）
    assert len(res_plain.end_state.deck) == 5
    assert len(res_decreased.end_state.deck) == 6


# ---------------------------------------------------------------- ⑤ pride 计分


def test_pride_score_formula_min_and_cap() -> None:
    """resolveScore f：min(好印象,干劲)×0.02，上限 +0.5（千分比 min×20 / 500）。"""
    sim = LessonSim(_deck(6), _config(), rng_seed=0)
    sim.buffs.impression = 10
    sim.motivation = 8
    sim.pride_turns = 5
    card = _card("白值", score=100)
    # min(10,8)=8 → +160‰ → 100×1.16 = 116
    assert sim._card_award(card) == 116
    sim.buffs.impression = 30
    sim.motivation = 30
    # min(30,30)=30 → 600‰ 封顶 500‰ → 100×1.5 = 150
    assert sim._card_award(card) == 150
    sim.buffs.impression = 0
    sim.motivation = 30
    # min(0,30)=0 → 无加成
    assert sim._card_award(card) == 100


def test_pride_zero_turns_no_effect() -> None:
    """prideTurns=0 → 不吃加成（默认逐位不变）。"""
    sim = LessonSim(_deck(6), _config(), rng_seed=0)
    sim.buffs.impression = 10
    sim.motivation = 8
    assert sim.pride_turns == 0
    assert sim._card_award(_card("白值", score=100)) == 100


def test_pride_only_positive_score() -> None:
    """score>0 门：纯 buff 牌（白值 0）不吃自尊加成（参考 resolveScore 外层 if）。"""
    sim = LessonSim(_deck(6), _config(), rng_seed=0)
    sim.buffs.impression = 10
    sim.motivation = 8
    sim.pride_turns = 5
    assert sim._card_award(_card("buff", score=0)) == 0


def test_pride_applies_to_end_turn_impression() -> None:
    """回合末好印象也走 resolveScore f：10 层 ×1.16 → ceil(11.6)=12。"""
    sim = LessonSim(_deck(6), _config(), rng_seed=0)
    sim.hand = []
    sim.buffs.impression = 10
    sim.motivation = 8
    sim.pride_turns = 5
    sim.step(None)
    assert sim.score == 12


def test_pride_turns_decrement_at_end_turn() -> None:
    """prideTurns ∈ EOT_DECREMENT_FIELDS：回合末 -1，到 0 后不再加成。"""
    sim = LessonSim(_deck(12), _config(), rng_seed=0)
    sim.pride_turns = 2
    sim.step(None)
    assert sim.pride_turns == 1
    sim.step(None)
    assert sim.pride_turns == 0
    sim.buffs.impression = 10
    sim.motivation = 8
    assert sim._card_award(_card("白值", score=100)) == 100


def test_pride_stacks_with_score_buffs() -> None:
    """自尊与 P 道具分数倍率同在 f 段加算（参考 scoreBuff 累加后一次乘）。"""
    sim = LessonSim(_deck(6), _config(), rng_seed=0)
    sim.buffs.impression = 10
    sim.motivation = 10
    sim.pride_turns = 5
    sim.score_buffs = ((500, -1),)  # +500‰
    # pride +200‰ 与 score_buff +500‰ 加算 → ×1.7
    assert sim._card_award(_card("白值", score=100)) == 170


# ---------------------------------------------------------------- ⑤ pride 来源


def test_pride_card_source_gate() -> None:
    """卡「我、绝不」：prideTurns+=5，条件门出牌前干劲 >=9（参考 if:motivation>=9）。"""
    pride_card = _card("我、绝不", score=0, pride_turns=5, pride_min_motivation=9)
    # plays_per_turn=3：两次出牌都不自动结束回合，避免回合末 prideTurns -1 干扰
    sim = LessonSim(_deck(6), _config(plays_per_turn=3), rng_seed=0)
    sim.hand = [pride_card, _card("填充")]
    sim.motivation = 8
    sim.step(0)
    assert sim.pride_turns == 0  # 8 < 9 → 不给
    sim.hand = [pride_card, _card("填充")]
    sim.motivation = 9
    sim.step(0)
    assert sim.pride_turns == 5


def test_pride_card_gate_uses_pre_card_motivation() -> None:
    """门槛用出牌前的干劲：本牌自己的干劲加成不算进门槛（参考条件先于动作求值）。"""
    pride_card = _card(
        "我、绝不", score=0, pride_turns=5, pride_min_motivation=9, motivation=1
    )
    sim = LessonSim(_deck(6), _config(plays_per_turn=2), rng_seed=0)
    sim.hand = [pride_card, _card("填充")]
    sim.motivation = 8
    sim.step(0)
    assert sim.motivation == 9  # 本牌给了 1 干劲
    assert sim.pride_turns == 0  # 但出牌前 8 < 9 → 不给自尊


def test_pride_card_no_gate_and_encore() -> None:
    """无门槛（0）直接给；再演（encore）直接效果翻倍 → prideTurns×2。"""
    sim = LessonSim(_deck(6), _config(plays_per_turn=3), rng_seed=0)
    sim.hand = [_card("自尊", score=0, pride_turns=5), _card("填充")]
    sim.step(0)
    assert sim.pride_turns == 5
    sim.hand = [_card("自尊再演", score=0, pride_turns=5, encore=True), _card("填充")]
    sim.step(0)
    assert sim.pride_turns == 15


def test_pride_p_item_source_real_data() -> None:
    """P 道具「一笔入魂」：直接效果干劲增加后好印象>=6 → prideTurns+=2、干劲+4，limit1。"""
    specs = _pride_specs()
    assert len(specs) == 2
    item = _pride_item_specs("pitem_02-2-117-0")  # 一笔入魂（自尊2回合 + 干劲+4）
    assert any(s.target == "pride_turns" and s.value == 2 and s.max_uses == 1 for s in item)
    sim = LessonSim(_deck(12), _config(plays_per_turn=3, p_items=item), rng_seed=0)
    sim.buffs.impression = 6
    sim.hand = [_card("干劲卡", score=0, motivation=4), _card("填充")]
    sim.step(0)
    assert sim.pride_turns == 2
    assert sim.motivation == 8  # 卡 4 + 道具 4
    # limit:1：第二次干劲增加不再触发
    sim.hand = [_card("干劲卡2", score=0, motivation=4), _card("填充")]
    sim.step(0)
    assert sim.pride_turns == 2
    assert sim.motivation == 12


def test_pride_p_item_condition_blocks() -> None:
    """好印象 <6 → 不触发（条件求值）；好印象在干劲增加之后仍按当时层数判。"""
    item = _pride_item_specs("pitem_02-2-117-0")
    sim = LessonSim(_deck(12), _config(p_items=item), rng_seed=0)
    sim.buffs.impression = 5
    sim.hand = [_card("干劲卡", score=0, motivation=4)]
    sim.step(0)
    assert sim.pride_turns == 0
    assert sim.motivation == 4


def test_pride_p_item_requires_direct_effect() -> None:
    """isDirectEffect：P 道具自己给的干劲不算直接效果，不触发「一笔入魂」。"""
    give_motivation = PItemSpec(
        name="给干劲",
        trigger="card_play",
        effect_type="ExamCardPlayAggressive",
        value=4,
        item_id="give_motivation",
    )
    pride = _pride_item_specs("pitem_02-2-117-0")
    sim = LessonSim(_deck(12), _config(p_items=(give_motivation, *pride)), rng_seed=0)
    sim.buffs.impression = 6
    sim.hand = [_card("白板", score=1)]
    sim.step(0)
    assert sim.motivation == 4  # 道具给了干劲
    assert sim.pride_turns == 0  # 但不是直接效果 → 不触发自尊


def test_pride_p_item_plus_variant() -> None:
    """「一笔入魂+」：prideTurns+=3、干劲+5（p_items.csv 355 交叉）。"""
    spec = _pride_specs()[1]
    assert spec.value == 3
    item = _pride_item_specs("pitem_02-2-117-1")  # 一笔入魂+（自尊3回合 + 干劲+5）
    sim = LessonSim(_deck(12), _config(plays_per_turn=2, p_items=item), rng_seed=0)
    sim.buffs.impression = 6
    sim.hand = [_card("干劲卡", score=0, motivation=4), _card("填充")]
    sim.step(0)
    assert sim.pride_turns == 3
    assert sim.motivation == 9


# ---------------------------------------------------------------- ExpectState 双镜


def test_expect_pride_award_matches_sim() -> None:
    """ExpectState._card_award 与 LessonSim 同口径（min/封顶/好印象/干劲）。"""
    state = ExpectState(pride_turns=5, impression=10, motivation=8)
    award, _ = expect_card_award(state, _card("白值", score=100))
    assert award == 116
    capped = replace(state, impression=30, motivation=30)
    award, _ = expect_card_award(capped, _card("白值", score=100))
    assert award == 150
    zero = replace(state, pride_turns=0)
    award, _ = expect_card_award(zero, _card("白值", score=100))
    assert award == 100


def test_expect_end_turn_pride_and_decrement() -> None:
    """end_turn_state：好印象吃自尊加成、prideTurns -1（与 LessonSim 同口径）。"""
    state = ExpectState(
        pride_turns=2, impression=10, motivation=8, turns_left=3, total_turns=3
    )
    after = end_turn_state(state)
    assert after.score == 12  # ceil(10×1.16)
    assert after.pride_turns == 1
    assert after.impression == 9
    after2 = end_turn_state(after)
    assert after2.pride_turns == 0


def test_expect_fire_p_items_pride() -> None:
    """fire_p_items status_gain → pride_turns / motivation 落状态（双镜）。"""
    item = _pride_item_specs("pitem_02-2-117-0")
    state = ExpectState(p_items=item, impression=6, turns_left=3)
    state = fire_p_items(state, STATUS_GAIN, status="aggressive", amount=4)
    assert state.pride_turns == 2
    assert state.motivation == 4
    # limit:1（按道具计，B10 口径）：整件道具不再触发 → 自尊/干劲都不再加
    state = fire_p_items(state, STATUS_GAIN, status="aggressive", amount=4)
    assert state.pride_turns == 2
    assert state.motivation == 4


def test_expect_card_pride_gate_mirror() -> None:
    """apply_card 的自尊条件门与 LessonSim 一致（出牌前干劲 >= 门槛）。"""
    pride_card = _card("我、绝不", score=0, pride_turns=5, pride_min_motivation=9)
    for motivation, expected in ((8, 0), (9, 5)):
        state = ExpectState(
            hand=(pride_card,),
            deck=tuple(_deck(6)),
            motivation=motivation,
            stamina=30,
            turns_left=3,
        )
        outcomes = apply_card(state, pride_card)
        assert len(outcomes) == 1
        assert outcomes[0][1].pride_turns == expected


def test_canonical_includes_new_fields() -> None:
    """canonical 记忆化键带上 hand_decreases / pride_turns（影响后续价值）。"""
    base = ExpectState(turns_left=3)
    assert base.canonical() != replace(base, pride_turns=1).canonical()
    assert base.canonical() != replace(base, hand_decreases=((1, -1),)).canonical()


def test_leaf_snapshot_aligns_with_end_turn_state() -> None:
    """叶子快照（RecordingLessonSim）与 end_turn_state 逐字段相等（新字段对齐）。"""
    sim = RecordingLessonSim(_deck(12), _config(), rng_seed=0)
    sim.pride_turns = 3
    sim.hand_decreases = ((1, 2),)
    sim.buffs.impression = 5
    sim.motivation = 4
    before = state_from_sim(sim)
    sim.step(None)
    assert sim.leaf_states, "应记录一个叶子快照"
    leaf = sim.leaf_states[-1]
    expected = end_turn_state(before)
    assert leaf == expected
    assert leaf.pride_turns == 2
    assert leaf.hand_decreases == ((1, 1),)


# ---------------------------------------------------------------- 解析层 / 数据


def test_pride_trigger_gate_parser() -> None:
    """主数据 trigger → 门槛：…aggressive_up-9 → 9；空 → 0；未知 → None（保守）。"""
    assert pride_min_motivation_from_trigger("e_trigger-none-card_play_aggressive_up-9") == 9
    assert pride_min_motivation_from_trigger("") == 0
    assert pride_min_motivation_from_trigger("e_trigger-none-review_up-10") is None


def test_sim_produce_pride_card_parse() -> None:
    """sim_produce：真实卡表「我、绝不」四变体 → pride_turns=5 / 门槛 9
   （P1-3 起 41 元组，索引 33/34 仍是自尊两位）。"""
    import json

    import sim_produce as sp

    table = json.loads((ROOT / "data" / "knowledge" / "card_table.json").read_text(encoding="utf-8"))["cards"]
    for name in ("我、绝不", "我、绝不+", "我、绝不++", "我、绝不+++"):
        fields = sp._effect_fields(table[name])
        assert len(fields) == 41
        assert fields[33] == 5, name
        assert fields[34] == 9, name
        spec = sp._spec_from_row(sp._rich_row(name, int(table[name]["cost"]), fields))
        assert spec.pride_turns == 5 and spec.pride_min_motivation == 9
    # 未知 trigger 保守不给自尊
    row = {
        "id": "p_card-02-ido-3_140",
        "trigger": "e_trigger-none-unknown_condition",
        "effects": [{"type": "ExamLessonValueMultipleDependReviewOrAggressive", "turn": 5, "values": []}],
    }
    fields = sp._effect_fields(row)
    assert fields[33] == 0


def test_play_choice_pride_card_parse() -> None:
    """play_choice.spec_from_name：生产卡表同口径（pride_turns=5 / 门槛 9）。"""
    spec = spec_from_name("我、绝不")
    assert spec is not None
    assert spec.pride_turns == 5
    assert spec.pride_min_motivation == 9
    # 好印象/抽牌有 values → 映射；ExamPlayableValueAdd 的 count 列是 sim_produce
    # 口径（play_choice 旧口径只认 values，保持既有行为不动）。
    assert spec.impression == 8 and spec.draw == 1


def test_pride_card_not_in_eval_pool() -> None:
    """评测牌组组成不变：自尊卡 score=0 且 SSR，本就不进 build_pool/build_deck。"""
    import sim_produce as sp

    pool_names = {row.name for row in sp.build_pool(rich=True)}
    deck_names = {row.name for row in sp.build_deck(rich=True)}
    for name in ("我、绝不", "我、绝不+", "我、绝不++", "我、绝不+++"):
        assert name not in pool_names
        assert name not in deck_names


def test_p_items_data_annotations() -> None:
    """p_items.json 标注：12 段 hand_decrease + 2 段 pride_turns 全部 implemented。"""
    assert classify_effect_target("ExamGimmickStartTurnCardDrawDown") == "hand_decrease"
    assert (
        classify_effect_target("ExamLessonValueMultipleDependReviewOrAggressive")
        == "pride_turns"
    )
    specs = load_p_items()
    hd = [s for s in specs if s.target == "hand_decrease"]
    pr = [s for s in specs if s.target == "pride_turns"]
    assert len(hd) == 12 and all(s.implemented for s in hd)
    assert all(s.value == 1 and s.duration == 0 for s in hd)  # 减少1 ∞永久
    assert len(pr) == 2 and all(s.implemented for s in pr)
    assert {s.value for s in pr} == {2, 3}


def test_apply_passive_hand_decrease_delta() -> None:
    """apply_passive exam_start → delta.hand_decreases（永久 -1）。"""
    spec = _hand_decrease_spec(1)
    delta = apply_passive(
        (spec,), PassiveEvent(kind=EXAM_START), PassiveState(turn=1, turns_left=4)
    )
    assert delta.hand_decreases == [(1, -1)]
    assert delta.as_dict()["hand_decreases"] == [(1, -1)]
    assert not delta.is_zero()


def test_apply_passive_pride_delta() -> None:
    """apply_passive status_gain → delta.pride_turns（整数资源，不是 timed 列表）。"""
    item = _pride_item_specs("pitem_02-2-117-0")
    state = PassiveState(turn=1, turns_left=4, stacks={"impression": 6, "aggressive": 4})
    delta = apply_passive(
        item, PassiveEvent(kind=STATUS_GAIN, status="aggressive", amount=4), state
    )
    assert delta.pride_turns == 2
    assert delta.stacks.get("aggressive") == 4
    assert delta.as_dict()["pride_turns"] == 2
    # 好印象不足 → 不触发
    low = PassiveState(turn=1, turns_left=4, stacks={"impression": 5})
    delta = apply_passive(
        item, PassiveEvent(kind=STATUS_GAIN, status="aggressive", amount=4), low
    )
    assert delta.pride_turns == 0 and delta.is_zero()
