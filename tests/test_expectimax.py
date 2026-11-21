"""回合内 expectimax 引擎的 L1 机制测试（架构评审 §5.1 逐条）。

这些测试只看机制，不依赖卡表/真机：用 ``CardSpec`` 直接构造局面，断言引擎的
动作、档位效用、机会节点和可行性。L2/L3（卡表、配对评测）在
``scripts/eval_expectimax.py``。
"""

from __future__ import annotations

import random

import pytest

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    ExpectState,
    apply_card,
    available_drinks,
    best_turn_sequence,
    end_turn_state,
    expected_tier_utility,
    expectimax,
    expectimax_with_stats,
    is_legal,
    run_sequence,
    sample_draws,
    search_beam,
    state_from_sim,
    use_drink_state,
)
from gkagent.sim.lesson import (
    Buffs,
    CardSpec,
    DrinkSpec,
    LessonConfig,
    LessonSim,
    PItemSpec,
)
from gkagent.vision.lesson import LessonState


def _state(**kwargs) -> ExpectState:
    base = {
        "turns_left": 1,
        "play_limit": 3,
        "clear": 1,
        "perfect": 1000,
    }
    base.update(kwargs)
    return ExpectState(**base)


# ---------------------------------------------------------------- §5.1 机制


def test_knapsack_chooses_high_value_not_cost_effective_pair() -> None:
    """背包：体力 4、[10/4费, 6/3费, 3/1费] → 必须选 10（性价比给 3+6=9）。"""
    state = _state(
        hand=(CardSpec("十", 4, 10), CardSpec("六", 3, 6), CardSpec("三", 1, 3)),
        stamina=4,
        clear=10,
        perfect=20,
    )
    result = expectimax_with_stats(state)
    assert result.card is not None and result.card.name == "十"
    # 3+6=9 够不到 CLEAR=10，10 可以；两者档位效用必须拉开
    by_name = dict(result.actions)
    assert result.utility == pytest.approx(1.0)
    assert by_name["三"] == pytest.approx(0.0)
    assert by_name["六"] == pytest.approx(0.0)


def test_vitality_pays_card_cost() -> None:
    """元气：体力 2、[元气+5/1费, 20/6费] → 必须先打元气牌再打 20。"""
    state = _state(
        hand=(CardSpec("元气", 1, 0, vitality=5), CardSpec("大", 6, 20)),
        stamina=2,
        play_limit=2,
        clear=20,
        perfect=40,
    )
    result = expectimax_with_stats(state)
    assert result.card is not None and result.card.name == "元气"
    assert result.utility == pytest.approx(1.0)
    # 直接打 20 不合法（体力 2 < 6），不能出现在动作列表里
    assert {name for name, _ in result.actions} == {"元气"}


def test_focus_must_go_before_scoring_cards() -> None:
    """顺序：[集中+1/1费(2分), 7/2费, 7/2费] → 集中必须在前（18 > 16）。"""
    focus = CardSpec("集中", 1, 2, focus=1)
    seven_a = CardSpec("七A", 2, 7)
    seven_b = CardSpec("七B", 2, 7)
    state = _state(
        hand=(focus, seven_a, seven_b),
        stamina=5,
        clear=18,
        perfect=40,
        play_limit=3,
    )
    result = expectimax_with_stats(state)
    assert result.card is not None and result.card.name == "集中"
    focus_first = run_sequence(state, (focus, seven_a, seven_b))
    score_first = run_sequence(state, (seven_a, seven_b, focus))
    assert focus_first.score == 18
    assert score_first.score == 16
    assert focus_first.score > score_first.score


def test_threshold_utility_prefers_safe_action() -> None:
    """阈值：最后 1 回合、score=125、C=120、P=200：

    A=+5 确定；B=30% +100 / 70% -20。B 的 E[分数] 更高（16 > 5），但档位
    期望效用更低，必须选 A。引擎没有随机卡牌效果，这条直接测叶子效用。
    """
    final = _state(score=125, turns_left=0, clear=120, perfect=200)
    utility_a = expected_tier_utility(final, {5: 1.0})
    utility_b = expected_tier_utility(final, {100: 0.3, -20: 0.7})
    mean_b = 0.3 * 100 + 0.7 * (-20)
    assert mean_b > 5
    assert utility_a == pytest.approx(1.0)
    assert utility_b == pytest.approx(0.6)
    assert utility_a > utility_b


def test_does_not_burn_stamina_on_worthless_buff() -> None:
    """空放：体力 2、[好调/2费/0分, 12/5, 9/5] → 不得打好调。"""
    state = _state(
        hand=(
            CardSpec("好调", 2, 0, condition=2),
            CardSpec("十二", 5, 12),
            CardSpec("九", 5, 9),
        ),
        stamina=2,
        turns_left=2,
        clear=1,
        perfect=100,
    )
    result = expectimax_with_stats(state)
    assert result.card is None  # SKIP
    assert result.utility == pytest.approx(result.skip_utility)


def test_same_state_twice_is_reproducible() -> None:
    """可复现：同状态两次决策逐位一致（引擎不调 RNG）。"""
    state = _state(
        hand=(CardSpec("a", 2, 9, focus=1), CardSpec("b", 3, 7), CardSpec("c", 1, 2)),
        stamina=6,
        turns_left=3,
        clear=15,
        perfect=30,
        deck=(CardSpec("d", 2, 5), CardSpec("e", 1, 0, focus=2)),
    )
    first = expectimax_with_stats(state)
    second = expectimax_with_stats(state)
    assert first.card == second.card
    assert first.utility == second.utility
    assert first.actions == second.actions
    assert first.skip_utility == second.skip_utility


def test_feasibility_never_negative_stamina_or_extra_plays() -> None:
    """可行性：任何决策都合法；打完后体力不为负、出牌数不超上限。"""
    states = [
        _state(
            hand=(CardSpec("大", 5, 12), CardSpec("小", 1, 2)),
            stamina=5,
            vitality=2,
            clear=10,
        ),
        _state(
            hand=(CardSpec("元气", 1, 0, vitality=3), CardSpec("大", 4, 15)),
            stamina=2,
            play_limit=2,
            clear=15,
            perfect=30,
        ),
        _state(
            hand=(CardSpec("加次数", 0, 0, extra_play=1), CardSpec("大", 5, 20)),
            stamina=5,
            play_limit=1,
            clear=20,
            perfect=40,
        ),
    ]
    for state in states:
        card = expectimax(state)
        assert card is None or card in state.hand
        if card is None:
            continue
        assert is_legal(state, card)
        outcomes = apply_card(state, card)
        assert outcomes
        assert sum(probability for probability, _ in outcomes) == pytest.approx(1.0)
        for probability, next_state in outcomes:
            assert probability > 0
            assert next_state.stamina >= 0
            assert next_state.vitality >= 0
            assert next_state.plays_used <= next_state.play_limit + next_state.extra_plays
            assert card not in next_state.hand or next_state.hand.count(card) < state.hand.count(card)


def test_extra_play_extends_turn_limit() -> None:
    """ExamPlayableValueAdd：0 费加次数牌让本回合能多打一张。"""
    extra = CardSpec("加次数", 0, 0, extra_play=1)
    big = CardSpec("大", 5, 20)
    state = _state(
        hand=(extra, big),
        stamina=5,
        play_limit=1,
        clear=20,
        perfect=40,
    )
    result = expectimax_with_stats(state)
    assert result.card is not None and result.card.name == "加次数"
    assert result.utility == pytest.approx(1.0)


def test_action_sensitivity_values_differ() -> None:
    """动作敏感：同一局面两个明显不同的动作，动作价值必须不同。"""
    state = _state(
        hand=(CardSpec("大", 4, 20), CardSpec("小", 1, 2)),
        stamina=4,
        clear=20,
        perfect=40,
    )
    result = expectimax_with_stats(state)
    utilities = dict(result.actions)
    assert utilities["大"] > utilities["小"]
    assert utilities["大"] == pytest.approx(1.0)
    assert utilities["小"] == pytest.approx(0.0)


def test_chance_node_seed_diversity() -> None:
    """种子多样：抽牌重状态 32 个不同牌序，≥28 个不同后继结果。

    expectimax 本身无 RNG；它把这 32 种未知牌序**精确积分**掉。这里验证机会
    节点的后继足够多（不确定性真实存在），且概率和为 1。
    """
    unique_cards = [CardSpec(f"c{i}", 1, i) for i in range(1, 13)]
    draw_two = CardSpec("抽二", 0, 0, draw=2)
    state = _state(hand=(draw_two,), deck=tuple(unique_cards), stamina=90, turns_left=3)
    outcomes = apply_card(state, draw_two)
    assert sum(probability for probability, _ in outcomes) == pytest.approx(1.0)
    hands = {
        tuple(sorted(card.name for card in next_state.hand)) for _, next_state in outcomes
    }
    assert len(hands) >= 28
    # 32 个不同 seed 的牌序 → 引擎只看组成，动作决策必须完全一致
    decisions = set()
    for seed in range(32):
        order = list(unique_cards)
        random.Random(seed).shuffle(order)
        shuffled = ExpectState(
            hand=(draw_two,),
            deck=tuple(order),
            stamina=90,
            turns_left=3,
            clear=10,
        )
        decisions.add(expectimax(shuffled))
    assert len(decisions) == 1


def test_chance_node_is_hypergeometric() -> None:
    """抽牌机会节点精确：4 张 A / 6 张 B 抽 1 张 → P(A)=0.4、P(B)=0.6。"""
    draw_one = CardSpec("抽一", 0, 0, draw=1)
    a = CardSpec("A", 1, 5)
    b = CardSpec("B", 1, 3)
    state = _state(
        hand=(draw_one,),
        deck=(a, a, a, a, b, b, b, b, b, b),
        stamina=5,
        turns_left=2,
        clear=10,
    )
    outcomes = apply_card(state, draw_one)
    by_drawn = {}
    for probability, next_state in outcomes:
        names = [card.name for card in next_state.hand if card.name != "抽一"]
        by_drawn[names[0]] = probability
    assert by_drawn["A"] == pytest.approx(0.4)
    assert by_drawn["B"] == pytest.approx(0.6)


def test_transition_matches_lesson_sim() -> None:
    """状态转换与 LessonSim 对齐：同序出牌后分数/体力/buff/指針一致。"""
    deck = [
        CardSpec("集中", 1, 2, focus=1),
        CardSpec("好调", 2, 0, condition=2),
        CardSpec("大", 4, 12),
        CardSpec("中", 3, 7),
        CardSpec("元气", 1, 0, vitality=3),
        CardSpec("印象", 2, 0, impression=3),
        CardSpec("恢复", 2, 0, stamina_recover=2),
    ]
    config = LessonConfig(turns=2, stamina=6, target_clear=10, target_perfect=20)
    sim = LessonSim(deck, config, rng_seed=1)
    sim.hand = [deck[0], deck[1], deck[2], deck[3]]
    sim.deck = [deck[4], deck[5], deck[6]]
    sim.score = 5
    sim.buffs = Buffs(condition_turns=1, focus=2, impression=2)
    sim.stamina = 6
    sim.turns_left = 2
    snapshot = state_from_sim(sim)
    sequence = [sim.hand[0], sim.hand[1], sim.hand[3]]
    ours = run_sequence(snapshot, sequence)
    for card in sequence:
        sim.step(sim.hand.index(card))
    assert ours.score == sim.score
    assert ours.stamina == sim.stamina
    assert ours.vitality == sim.vitality
    assert ours.focus == sim.buffs.focus
    assert ours.condition_turns == sim.buffs.condition_turns
    assert ours.impression == sim.buffs.impression
    assert ours.stance_state == sim.stance


def test_anytime_deadline_returns_legal_action() -> None:
    """anytime：预算 0 时立即返回当前最优（可能退化为 SKIP），不抛异常。"""
    state = _state(
        hand=(CardSpec("a", 3, 15, focus=1), CardSpec("b", 2, 9), CardSpec("c", 1, 4)),
        stamina=8,
        turns_left=4,
        clear=30,
        perfect=60,
        deck=tuple(CardSpec(f"d{i}", 2, i) for i in range(8)),
    )
    result = expectimax_with_stats(state, time_budget_ms=0)
    assert result.complete is False
    assert result.card is None or is_legal(state, result.card)
    assert result.elapsed_ms >= 0


# 评审表里的"随机性 std 随 1/√K 下降"属于 PIMC；expectimax 是精确机会节点，
# 不适用。这里用"同局面 32 个牌序 → 决策不变 + 机会节点 ≥28 种后继"替代。


# ---------------------------------------------------------------- 再动卡
def test_extra_play_value_depends_on_stamina() -> None:
    """再动卡不能写死优先级：体力 6 → 先再动；体力 5 → 直接大牌。

    体力 6：再动(1) + 大牌(5) = 60；直接大牌(5) 后只剩 1 体力，虽然还能打再动，
    但 0 分且没有别的牌，收益相同；tie-break 选保留更多动作次数的再动。
    体力 5：再动后剩 4 < 5，大牌打不出 → 0 分；必须直接打大牌。
    """
    extra = CardSpec("再动", 1, 0, extra_play=1)
    big = CardSpec("大分", 5, 60)
    rich = _state(
        hand=(extra, big), stamina=6, play_limit=3, clear=60, perfect=120
    )
    poor = _state(
        hand=(extra, big), stamina=5, play_limit=3, clear=60, perfect=120
    )
    rich_result = expectimax_with_stats(rich)
    poor_result = expectimax_with_stats(poor)
    assert rich_result.card is not None and rich_result.card.name == "再动"
    assert poor_result.card is not None and poor_result.card.name == "大分"
    assert dict(rich_result.actions)["再动"] == pytest.approx(1.0)
    assert dict(poor_result.actions)["再动"] == pytest.approx(0.0)
    assert dict(poor_result.actions)["大分"] == pytest.approx(1.0)


def test_extra_play_does_not_truncate_stamina() -> None:
    """再动本身按实际费用扣体力，不吃体力上限截断；抽牌+再动也要能继续打。"""
    extra_draw = CardSpec("抽再", 1, 0, draw=1, extra_play=1)
    big = CardSpec("大", 0, 30)
    state = _state(
        hand=(extra_draw,),
        deck=(big,),
        stamina=2,
        play_limit=1,
        clear=30,
        perfect=60,
    )
    result = expectimax_with_stats(state)
    assert result.card is not None and result.card.name == "抽再"
    # 抽上来的大牌 cost0 可以在 +1 次出牌里打出 → 30 分
    assert result.utility == pytest.approx(1.0)
    outcomes = apply_card(state, extra_draw)
    assert len(outcomes) == 1
    next_state = outcomes[0][1]
    assert next_state.stamina == 1  # 只扣 1 费，没有被上限截断
    assert next_state.plays_left == 1
    assert [card.name for card in next_state.hand] == ["大"]


# ---------------------------------------------------------------- 除外/牌库
def test_once_card_goes_to_excluded_not_discard() -> None:
    """「レッスン中1回」：用掉后进除外区；弃牌洗回也不会再抽到。"""
    once = CardSpec("一次性", 1, 30, once=True)
    other = CardSpec("普通", 1, 5)
    sim = LessonSim(
        [once, other],
        LessonConfig(turns=2, stamina=10, target_clear=1, hand_size=1),
        rng_seed=0,
    )
    sim.hand = [once]
    sim.deck = []
    sim.discard = [other]
    sim.step(0)
    assert sim.excluded == [once]
    assert once not in sim.discard
    sim.step(None)  # 结束回合；弃牌只有普通牌
    assert sim.excluded == [once]
    assert all(card is not once for card in sim.hand)


def test_expect_state_excludes_once_card_from_redraw() -> None:
    once = CardSpec("一次性", 1, 30, once=True)
    filler = CardSpec("填充", 1, 1)
    state = _state(
        hand=(once,),
        deck=(filler,),
        stamina=5,
        turns_left=2,
        clear=30,
        perfect=60,
    )
    outcomes = apply_card(state, once)
    assert len(outcomes) == 1
    successor = outcomes[0][1]
    assert successor.excluded == (once,)
    assert once not in successor.discard
    assert successor.deck == (filler,)
    # 之后抽牌只会摸到填充牌（一次性卡已经除外）
    drawn = sample_draws(successor, 2, random.Random(0))
    assert all(card.name != "一次性" for card in drawn.hand)


def test_sample_draws_without_replacement_and_reshuffle() -> None:
    cards = [CardSpec(f"c{i}", 1, i) for i in range(4)]
    state = _state(hand=(), deck=tuple(cards), discard=(), turns_left=2)
    drawn = sample_draws(state, 3, random.Random(1))
    assert len(drawn.hand) == 3
    assert sorted(card.name for card in drawn.deck) == sorted(
        card.name for card in cards if card not in drawn.hand
    )
    # 牌库空 + 弃牌堆 3 张：抽 2 张应触发洗回，弃牌堆减少 2 张
    empty_deck = _state(hand=(), deck=(), discard=tuple(cards[:3]), turns_left=2)
    after = sample_draws(empty_deck, 2, random.Random(2))
    assert len(after.hand) == 2
    assert len(after.deck) + len(after.discard) == 1


# ---------------------------------------------------------------- 跨回合 beam
def test_beam_planning_values_buff_investment() -> None:
    """beam 用 V_leaf 评分，不能把"先铺集中"的投资线按当前分数剪掉。"""
    focus = CardSpec("集中", 1, 0, focus=2)
    small = CardSpec("小分", 1, 5)
    big = CardSpec("大分", 2, 15)
    state = _state(
        hand=(focus, small),
        deck=(big, big, big, big),
        discard=(),
        stamina=12,
        turns_left=2,
        clear=20,
        perfect=40,
        play_limit=2,
    )
    result = search_beam(
        state, width=8, depth=2, deadline_ms=2000, rng=random.Random(0)
    )
    assert result.card is not None and result.card.name == "集中"
    assert result.sequence[0] == "集中"
    assert result.utility > 0


def test_beam_respects_deadline_and_is_reproducible() -> None:
    focus = CardSpec("集中", 1, 0, focus=2)
    small = CardSpec("小分", 1, 5)
    big = CardSpec("大分", 2, 15)
    state = _state(
        hand=(focus, small),
        deck=(big, big, big),
        stamina=10,
        turns_left=3,
        clear=20,
        perfect=40,
        play_limit=2,
    )
    first = search_beam(
        state, width=8, depth=3, deadline_ms=3000, rng=random.Random(7)
    )
    second = search_beam(
        state, width=8, depth=3, deadline_ms=3000, rng=random.Random(7)
    )
    assert first.card == second.card
    assert first.utility == second.utility
    expired = search_beam(
        state, width=8, depth=3, deadline_ms=0, rng=random.Random(7)
    )
    assert expired.complete is False
    assert expired.card is None or is_legal(state, expired.card)


def test_best_turn_sequence_returns_ordered_cards() -> None:
    focus = CardSpec("集中", 1, 2, focus=1)
    seven_a = CardSpec("七A", 2, 7)
    seven_b = CardSpec("七B", 2, 7)
    state = _state(
        hand=(seven_a, focus, seven_b),
        stamina=5,
        clear=18,
        perfect=40,
        play_limit=3,
    )
    cards, end, complete = best_turn_sequence(state)
    assert complete
    assert [card.name for card in cards] == ["集中", "七A", "七B"]
    assert end.score == 18
    assert end_turn_state(state).turns_left == 0


# ---------------------------------------------------------------- buff/盾/再动 同台比较
def test_search_compares_buff_against_extra_play() -> None:
    """buff 与再动不写死优先级：同一搜索里按体力/手牌/阈值比较。

    状态 A（clear=42）：buff+大牌 = 42 过线；再动+大牌 = 40 不够 → buff 动作价值更高。
    状态 B（clear=9）：再动+两张 5 分 = 10 过线；buff 太贵只剩 0 分 → 再动动作价值更高。
    """
    buff = CardSpec("buff", 1, 0, focus=2)
    expensive_buff = CardSpec("buff", 3, 0, focus=2)
    extra = CardSpec("再动", 1, 0, extra_play=1)
    big = CardSpec("大牌", 5, 40)
    small_a = CardSpec("小A", 1, 5)
    small_b = CardSpec("小B", 1, 5)
    buff_wins = _state(
        hand=(buff, extra, big),
        stamina=6,
        play_limit=3,
        clear=42,
        perfect=100,
    )
    extra_wins = _state(
        hand=(expensive_buff, extra, small_a, small_b),
        stamina=3,
        play_limit=3,
        clear=9,
        perfect=100,
    )
    first = dict(expectimax_with_stats(buff_wins).actions)
    second = dict(expectimax_with_stats(extra_wins).actions)
    assert first["buff"] > first["再动"]
    assert second["再动"] > second["buff"]


def test_search_compares_shield_against_big_card() -> None:
    """盾牌价值 = 它解锁的高费牌：体力不够解锁时打盾就是白费。"""
    shield = CardSpec("盾", 1, 0, vitality=5)
    big = CardSpec("大牌", 6, 30)
    unlocked = _state(
        hand=(shield, big), stamina=2, play_limit=2, clear=30, perfect=60
    )
    locked = _state(
        hand=(shield, CardSpec("更大的牌", 7, 30)),
        stamina=2,
        play_limit=2,
        clear=30,
        perfect=60,
    )
    chosen = expectimax(unlocked)
    assert chosen is not None and chosen.name == "盾"
    assert expectimax(locked) is None


def test_search_skips_zero_value_cards_when_stamina_short() -> None:
    """体力/收益不足时三类功能牌都不该硬打：搜索返回 SKIP。"""
    state = _state(
        hand=(
            CardSpec("buff", 1, 0, focus=2),
            CardSpec("再动", 1, 0, extra_play=1),
            CardSpec("盾", 1, 0, vitality=5),
        ),
        stamina=0,
        turns_left=1,
        clear=10,
        perfect=20,
    )
    assert expectimax(state) is None
    # 有 1 点体力也只够打一张 0 分牌，仍然 SKIP（没有后续得分牌）
    one_stamina = _state(
        hand=(CardSpec("buff", 1, 0, focus=2),),
        stamina=1,
        turns_left=1,
        clear=10,
        perfect=20,
    )
    assert expectimax(one_stamina) is None


# ---------------------------------------------------------------- 状态完备性
def test_state_carries_buff_durations_total_turns_and_drinks() -> None:
    """buff 剩余回合 / 总回合数 / 当前回合 / 三框饮料都要进状态。"""
    drinks = (
        DrinkSpec("体力饮料", 0, "stamina", 5),
        DrinkSpec("集中饮料", 0, "focus", 2),
    )
    config = LessonConfig(
        turns=6, stamina=10, target_clear=100, hand_size=3, drinks=drinks
    )
    sim = LessonSim([CardSpec("占位", 1, 5)], config, rng_seed=0)
    sim.turns_left = 4
    sim.stamina = 7
    sim.buffs = Buffs(condition_turns=2, focus=3, impression=4)
    sim.vitality = 5
    state = state_from_sim(sim)
    assert state.total_turns == 6
    assert state.current_turn == 3
    assert (state.condition_turns, state.focus, state.impression) == (2, 3, 4)
    assert state.vitality == 5
    assert state.drinks == drinks
    assert state.drink_uses == (1, 1)
    assert LessonState(turns_left=4, total_turns=6).current_turn == 3


def test_drinks_are_usable_from_expect_state() -> None:
    """三框饮料在 ExpectState 里可用：按效果结算、瓶数上限可配、回合末重置。

    当前仓库口径（e24b3fd）：``drinks_per_turn=None`` 不限；显式给 1 才限 1 瓶。
    """
    drinks = (
        DrinkSpec("体力饮料", 0, "stamina", 5),
        DrinkSpec("集中饮料", 0, "focus", 2),
        DrinkSpec("分数饮料", 0, "score", 7),
    )
    state = _state(
        hand=(),
        stamina=2,
        stamina_max=10,
        drinks=drinks,
        drink_uses=(1, 1, 1),
        drinks_per_turn=1,
        turns_left=2,
        clear=10,
    )
    assert available_drinks(state) == [0, 1, 2]
    after = use_drink_state(state, 0)
    assert (after.stamina, after.drink_uses) == (7, (0, 1, 1))
    assert after.drinks_used_this_turn == 1
    assert available_drinks(after) == []  # 显式 drinks_per_turn=1
    with pytest.raises(ValueError):
        use_drink_state(after, 1)
    next_turn = end_turn_state(after)
    assert next_turn.drinks_used_this_turn == 0
    assert available_drinks(next_turn) == [1, 2]
    assert use_drink_state(state, 1).focus == 2
    assert use_drink_state(state, 2).score == 7
    # 默认 None = 不限：喝完一瓶还能继续喝别的槽
    unlimited = _state(
        hand=(), stamina=2, stamina_max=10, drinks=drinks, drink_uses=(1, 1, 1)
    )
    assert available_drinks(use_drink_state(unlimited, 0)) == [1, 2]


def test_p_item_interface_is_present_but_not_fabricated() -> None:
    """P 道具接口就位、默认为空；没有数据时不结算、不编造数值。"""
    default = LessonConfig(turns=3, stamina=10, target_clear=10)
    assert default.p_items == ()
    item = PItemSpec(
        name="测试 P 道具",
        trigger="turn_start",
        effect_type="ExamLesson",
        value=5,
        text="每回合开始 +5 分（未接入课程结算）",
    )
    config = LessonConfig(turns=3, stamina=10, target_clear=10, p_items=(item,))
    sim = LessonSim([CardSpec("占位", 1, 5)], config, rng_seed=0)
    assert sim.p_items == (item,)
    plain = LessonSim(
        [CardSpec("占位", 1, 5)],
        LessonConfig(turns=3, stamina=10, target_clear=10),
        rng_seed=0,
    )
    assert plain.p_items == ()


# ---------------------------------------------------------------- 档位效用封顶的 tie-break
def test_score_tiebreak_default_off_keeps_tier_utility() -> None:
    """默认 score_tiebreak=0：档位效用与历史口径逐位一致（生产行为不变）。"""
    model = AnalyticLeafValue(sigma=0.0)
    assert model.score_tiebreak == 0.0
    below = _state(score=90, clear=100, perfect=200)
    clear_only = _state(score=150, clear=100, perfect=200)
    assert model.utility(below) == pytest.approx(0.0)
    assert model.utility(clear_only) == pytest.approx(1.0)


def test_score_tiebreak_breaks_saturated_ties_by_projected_score() -> None:
    """效用封顶后大量「稳 CLEAR」局面打平；tie-break>0 时按预测总分排开。"""
    low = _state(score=150, clear=100, perfect=200)
    high = _state(score=180, clear=100, perfect=200)
    model = AnalyticLeafValue(sigma=0.0, score_tiebreak=1e-3)
    assert model.utility(high) > model.utility(low) > 1.0
    assert model.utility(low) == pytest.approx(1.0 + 1e-3 * 150 / 200)
    assert model.utility(high) == pytest.approx(1.0 + 1e-3 * 180 / 200)
    # 主项仍主导：毫秒级 tie-break 不会把「没过 CLEAR」抬到「稳过」之上
    below = _state(score=50, clear=100, perfect=200)
    assert model.utility(low) > model.utility(below)


