"""回合内 expectimax + 跨回合 beam 出牌引擎（架构评审 §2.3 / §2.4）。

在线决策分两层：

1. ``expectimax``：**本回合**精确搜索。枚举本回合所有合法**有序出牌序列**，
   抽牌走精确超几何机会节点（剩余牌少时枚举组合，多时逐张按 count/remain
   分支），回合末交给解析式 ``V_leaf`` 估未来得分；
2. ``search_beam``：**跨回合** beam。每层一个回合，节点是回合结束后的状态；
   回合内用 ``expectimax`` 产出该回合的最佳序列，按 ``V_leaf`` 保留 top-width。
   抽牌用真实剩余多重集**无放回抽样**，不是固定牌库。

目标不是 E[分数]，而是 CLEAR/PERFECT 两档的期望效用::

    E[u] = a · P(最终分 ≥ CLEAR) + b · P(最终分 ≥ PERFECT)

这样在阈值附近会自动"够不到就冒险、过线就保守"。

牌库建模（与真机 wiki 口径一致）：

- 山札：每回合抽 ``hand_size`` 张；抽空时把捨札洗回山札；
- 捨札：没用掉的手牌 + 用掉的可重复卡；
- 除外：``CardSpec.once``（卡面「訓練中1回」）用掉后本场消失，推进牌库压缩；
- ``ExpectState.deck`` / ``discard`` 都是已知多重集，顺序未知；抽牌只依赖组成。

可行性与结算（与 ``sim/lesson.py`` 对齐，纯函数、无 RNG）：

- 合法 = ``stamina + vitality >= cost`` 且 ``plays_used < play_limit + extra_plays``；
- 出牌先按**当前** buff 算分，再付牌费（元气先扣）、结算本牌 buff/指針、抽牌；
- 再动卡（``ExamPlayableValueAdd``）只加 ``extra_plays``，不写死优先级：搜索会
  自己比较"多打一张"和"把体力留给大牌"的期望档位效用；
- 同名牌/同数值牌去重；状态键做规范化缓存；带 anytime deadline。

V_leaf 先上线**解析式**（不训练）::

    μ = n·集中 + 好印象年金(n, 层数) + 均值牌面 × 可打张数(体力模型)
    E[u] = a·Φ((μ-(C-s))/σ) + b·Φ((μ-(P-s))/σ)

``Φ`` 用 ``math.erf``。只依赖当前局面，可解释、可单测；换学习模型只需实现同样的
``predict()/utility()`` 接口。
"""

from __future__ import annotations

import math
import random
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from typing import Any

from gkagent.sim.lesson import Buffs, CardSpec, DrinkSpec
from gkagent.sim.p_items import (
    CARD_PLAY,
    STATUS_GAIN,
    TURN_END,
    TURN_START,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    apply_passive,
)
from gkagent.sim.stance import (
    StanceState,
    apply_full_power_point,
    card_stance_effect,
    end_turn,
    score_multiplier,
    stamina_cost_multiplier,
    stamina_pierce,
)

__all__ = [
    "AnalyticLeafValue",
    "BeamResult",
    "ExpectState",
    "ExpectimaxConfig",
    "ExpectimaxResult",
    "apply_card",
    "available_drinks",
    "best_turn_sequence",
    "effective_cost",
    "end_turn_state",
    "expected_tier_utility",
    "expectimax",
    "expectimax_value",
    "expectimax_with_stats",
    "fire_p_items",
    "is_legal",
    "legal_cards",
    "run_sequence",
    "sample_apply_card",
    "sample_draws",
    "search_beam",
    "start_turn_state",
    "state_from_sim",
    "use_drink_state",
]

# 默认保守 σ：μ 的点估计误差按回合末剩余分数的大致波动取常数；越大越保守。
DEFAULT_SIGMA = 80.0
# 抽牌剩余牌 ≤ 这个数时直接枚举组合；更大时按 count/remain 逐张分支。
DEFAULT_DRAW_ENUM_LIMIT = 8
# 搜索节点默认上限，防止病态局面把在线决策拖死。
DEFAULT_MAX_NODES = 200_000
# 默认在线预算：真机决策 ≤1-2s，留 UI/OCR 余量。
DEFAULT_TIME_BUDGET_MS = 800.0
# beam 默认预算：用户要求单次决策 ≤200ms、deadline 500ms。
DEFAULT_BEAM_DEADLINE_MS = 500.0
# 好印象/好调等持续 buff 的"永久"哨兵（卡表 turn=-1）。
_PERMANENT = -1


class _Deadline(Exception):
    """内部 anytime 超时信号；只用于跳出递归，不对外抛出。"""


def _phi(value: float) -> float:
    """标准正态 CDF，用 math.erf 实现。"""
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


@lru_cache(maxsize=4096)
def _card_key(card: CardSpec) -> tuple[Any, ...]:
    """同名牌/同数值牌的稳定排序键（CardSpec 可哈希，缓存一次）。"""
    return tuple(getattr(card, field.name) for field in fields(CardSpec))


def _counts_key(cards: Iterable[CardSpec]) -> tuple[tuple[CardSpec, int], ...]:
    """多重集的规范化键：只保留"哪张牌几张"，与手牌顺序无关。"""
    counter = Counter(cards)
    return tuple(sorted(counter.items(), key=lambda item: _card_key(item[0])))


def _counts_tuple(counter: Counter[CardSpec]) -> tuple[CardSpec, ...]:
    """多重集 → 展平的 tuple（顺序按稳定键；机械上不依赖手牌顺序）。"""
    return tuple(
        card
        for card, count in sorted(counter.items(), key=lambda item: _card_key(item[0]))
        for _ in range(count)
    )


@dataclass(frozen=True)
class ExpectState:
    """一回合内的纯状态（无 RNG、无 LessonSim 对象引用）。

    ``deck`` / ``discard`` 都是**已知多重集**（顺序未知，抽牌只依赖组成）；
    ``excluded`` 是「レッスン中1回」用掉后的除外区，不参与任何抽取。
    ``plays_used`` 是本回合已出牌数，``play_limit`` 是基础出牌上限，
    ``extra_plays`` 是本回合额外次数（``ExamPlayableValueAdd``）。
    """

    hand: tuple[CardSpec, ...] = ()
    deck: tuple[CardSpec, ...] = ()
    discard: tuple[CardSpec, ...] = ()
    excluded: tuple[CardSpec, ...] = ()
    stamina: int = 0
    stamina_max: int = 0
    vitality: int = 0
    score: int = 0
    turns_left: int = 1
    # 本课程总回合数（5/6/7/8 回合课的策略不同）；0 = 未知
    total_turns: int = 0
    plays_used: int = 0
    play_limit: int = 3
    extra_plays: int = 0
    clear: int = 0
    perfect: int = 0
    condition_turns: int = 0
    focus: int = 0
    impression: int = 0
    motivation: int = 0
    condition_additive: int = 0
    condition_additive_turns: int = 0
    review_multiple: int = 0
    review_multiple_turns: int = 0
    full_power_lesson_multiple: int = 0
    full_power_lesson_multiple_turns: int = 0
    parameter_buff: int = 0
    # StanceState 的冻结快照：(stance, strong_level, save_level, full_power_point)
    stance: tuple[str, int, int, int] = ("normal", 0, 0, 0)
    # 温存期间已打出牌数：解除温存时按「使用数 + 1」给热意
    save_cards_used: int = 0
    attribute_coefficient: float = 1.0
    hand_size: int = 3
    min_cost: int = 0
    # P 道具（被动）：状态里带着，出牌/回合事件会触发；数据来自 sim/p_items.py
    p_items: tuple[PItemSpec, ...] = ()
    p_item_uses: tuple[tuple[str, int], ...] = ()
    cards_played_total: int = 0
    # 三框饮料：只在状态里携带，决策层仍走调用方现有 use_drink 流程
    # （架构评审的动作定义是 play(card)/SKIP；饮品不占出牌次数、每回合限 1 瓶）
    drinks: tuple[DrinkSpec, ...] = ()
    drink_uses: tuple[int, ...] = ()
    drinks_used_this_turn: int = 0
    # None = 不限每回合瓶数（与 LessonConfig.drinks_per_turn 同口径）
    drinks_per_turn: int | None = None
    # ExamAddGrowEffect 的按牌名计数（真卡表当前 grow_score 恒 0，留接口）
    card_uses: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if self.perfect <= 0 and self.clear > 0:
            object.__setattr__(self, "perfect", self.clear * 2)
        if self.stamina_max <= 0:
            object.__setattr__(self, "stamina_max", self.stamina)

    @property
    def stance_state(self) -> StanceState:
        stance, strong_level, save_level, full_power_point = self.stance
        return StanceState(
            stance=stance,
            strong_level=strong_level,
            save_level=save_level,
            full_power_point=full_power_point,
        )

    @property
    def plays_left(self) -> int:
        return max(self.play_limit + self.extra_plays - self.plays_used, 0)

    @property
    def current_turn(self) -> int:
        """当前是第几回合（1 起）；``total_turns`` 未知时返回 0。"""
        if self.total_turns <= 0 or self.turns_left <= 0:
            return 0
        return max(self.total_turns - self.turns_left + 1, 1)

    @property
    def total_cost_available(self) -> int:
        return self.stamina + self.vitality

    def with_stance(self, stance: StanceState) -> ExpectState:
        return replace(
            self,
            stance=(
                stance.stance,
                stance.strong_level,
                stance.save_level,
                stance.full_power_point,
            ),
        )

    def uses_of(self, name: str) -> int:
        for card_name, count in self.card_uses:
            if card_name == name:
                return count
        return 0

    def canonical(self) -> tuple[Any, ...]:
        """记忆化键：所有影响价值/合法动作的字段 + 多重集组成。"""
        return (
            _counts_key(self.hand),
            _counts_key(self.deck),
            _counts_key(self.discard),
            _counts_key(self.excluded),
            self.stamina,
            self.stamina_max,
            self.vitality,
            self.score,
            self.turns_left,
            self.total_turns,
            self.plays_used,
            self.play_limit,
            self.extra_plays,
            self.clear,
            self.perfect,
            self.condition_turns,
            self.focus,
            self.impression,
            self.motivation,
            self.condition_additive,
            self.condition_additive_turns,
            self.review_multiple,
            self.review_multiple_turns,
            self.full_power_lesson_multiple,
            self.full_power_lesson_multiple_turns,
            self.parameter_buff,
            self.stance,
            self.save_cards_used,
            float(self.attribute_coefficient),
            self.hand_size,
            self.min_cost,
            self.p_item_uses,
            self.cards_played_total,
            self.drinks,
            self.drink_uses,
            self.drinks_used_this_turn,
            self.drinks_per_turn,
            self.card_uses,
        )


@dataclass(frozen=True)
class ExpectimaxConfig:
    """搜索/叶子估值参数（权重与 σ 都可从 policy 覆盖）。"""

    a_clear: float = 1.0
    a_perfect: float = 1.0
    sigma: float = DEFAULT_SIGMA
    draw_enum_limit: int = DEFAULT_DRAW_ENUM_LIMIT
    max_nodes: int = DEFAULT_MAX_NODES
    time_budget_ms: float | None = DEFAULT_TIME_BUDGET_MS


@dataclass(frozen=True)
class ExpectimaxResult:
    """一次回合内决策的完整结果（日志/测试用）。"""

    card: CardSpec | None
    utility: float
    skip_utility: float
    actions: tuple[tuple[str, float], ...]
    nodes: int
    elapsed_ms: float
    complete: bool


# ---------------------------------------------------------------- 叶子价值 V
@dataclass(frozen=True)
class AnalyticLeafValue:
    """解析式 V_leaf + 档位效用（评审 §2.4，不训练）。

    ``predict`` 只返回**未来得分**的均值/标准差（不含当前 ``score``），
    ``utility`` 再把当前分数和阈值一起算成 CLEAR/PERFECT 的期望效用。
    """

    sigma: float = DEFAULT_SIGMA
    a_clear: float = 1.0
    a_perfect: float = 1.0
    condition_multiplier: float = 1.5

    # ------------------------------------------------------------- 特征
    def mean_card_score(self, state: ExpectState) -> float:
        """剩余牌（手牌 + 牌库 + 弃牌）里正分牌的均值牌面。"""
        cards = (*state.hand, *state.deck, *state.discard)
        scores = [float(card.score) for card in cards if card.score > 0]
        return sum(scores) / len(scores) if scores else 0.0

    def mean_card_cost(self, state: ExpectState) -> float:
        """正分牌的均值费用（体力模型的分母）。"""
        cards = (*state.hand, *state.deck, *state.discard)
        costs = [max(int(card.cost), 0) for card in cards if card.score > 0]
        return sum(costs) / len(costs) if costs else 1.0

    def playable_count(self, state: ExpectState) -> int:
        """可打张数 n：剩余出牌位与体力能负担张数的较小值。

        剩余出牌位 = 本回合剩余 + 之后每回合 ``play_limit`` 张；
        体力封顶 = ``(stamina + vitality) / 均值费用``（回合间不回复体力）。
        """
        if state.turns_left <= 0:
            return 0
        slots = state.plays_left + max(state.turns_left - 1, 0) * state.play_limit
        cards = (*state.hand, *state.deck, *state.discard)
        if not cards:
            return 0
        mean_cost = self.mean_card_cost(state)
        affordable = int(state.total_cost_available / max(mean_cost, 1.0))
        return max(min(slots, affordable), 0)

    def impression_annuity(self, state: ExpectState) -> float:
        """好印象年金：i + (i-1) + … 直到回合用完（含 review_multiple 放大）。"""
        total = 0.0
        level = state.impression
        for _ in range(max(state.turns_left, 0)):
            if level <= 0:
                break
            value = float(level)
            if state.review_multiple > 0:
                value = int(level * (1000 + state.review_multiple) / 1000)
            total += value
            level -= 1
        return total

    # ------------------------------------------------------------- 预测
    def predict(self, state: ExpectState) -> tuple[float, float]:
        """返回未来得分的 ``(μ, σ)``；回合已用完时 σ=0（硬档位）。"""
        if state.turns_left <= 0:
            return 0.0, 0.0
        n = self.playable_count(state)
        mean = self.mean_card_score(state)
        mu = float(n * state.focus) + mean * n
        # 好调覆盖未来若干张牌：只给条件仍生效的那部分牌加 50% 均值
        if state.condition_turns > 0 and self.condition_multiplier > 1.0:
            conditioned = min(n, state.play_limit * state.condition_turns)
            mu += mean * (self.condition_multiplier - 1.0) * conditioned
        mu += self.impression_annuity(state)
        if not math.isfinite(mu):
            mu = 0.0
        return max(mu, 0.0), max(float(self.sigma), 0.0)

    # ------------------------------------------------------------- 效用
    def utility(self, state: ExpectState) -> float:
        """E[档位效用] = a·P(score ≥ CLEAR) + b·P(score ≥ PERFECT)。"""
        if state.clear <= 0:
            return 0.0
        mu, sigma = self.predict(state)
        projected = state.score + mu
        if sigma <= 0:
            return (
                self.a_clear * (1.0 if projected >= state.clear else 0.0)
                + self.a_perfect * (1.0 if projected >= state.perfect else 0.0)
            )
        clear_gap = state.clear - state.score
        perfect_gap = state.perfect - state.score
        return self.a_clear * _phi((mu - clear_gap) / sigma) + self.a_perfect * _phi(
            (mu - perfect_gap) / sigma
        )


def expected_tier_utility(
    state: ExpectState,
    outcomes: Mapping[int, float],
    *,
    value: AnalyticLeafValue | None = None,
) -> float:
    """给定「分数增量 → 概率」的档位期望效用（阈值风险态度用）。"""
    model = value or AnalyticLeafValue()
    total = 0.0
    for delta, probability in outcomes.items():
        total += float(probability) * model.utility(
            replace(state, score=state.score + int(delta))
        )
    return total


# ---------------------------------------------------------------- 状态转换
def is_legal(state: ExpectState, card: CardSpec) -> bool:
    """本牌此刻是否合法：体力+元气够付**指針修正后的实际牌费**且还有出牌次数。"""
    return state.plays_left > 0 and effective_cost(state, card) <= state.total_cost_available


def effective_cost(state: ExpectState, card: CardSpec) -> int:
    """指針修正后的实际牌费（与 LessonSim._effective_cost 同式，向上取整）。"""
    multiplier = stamina_cost_multiplier(state.stance_state)
    if multiplier == 1.0:
        return int(card.cost)
    return math.ceil(card.cost * multiplier)


def legal_cards(state: ExpectState) -> list[CardSpec]:
    """可打出的**去重**牌（同值副本只列一次），顺序稳定。"""
    unique: dict[CardSpec, CardSpec] = {}
    for card in state.hand:
        if is_legal(state, card):
            unique.setdefault(card, card)
    return [unique[key] for key in sorted(unique, key=_card_key)]


def available_drinks(state: ExpectState) -> list[int]:
    """当前能喝的饮料下标（未用完、体力够付、本回合瓶数未超上限）。"""
    if (
        state.drinks_per_turn is not None
        and state.drinks_used_this_turn >= state.drinks_per_turn
    ):
        return []
    return [
        index
        for index, (drink, uses) in enumerate(zip(state.drinks, state.drink_uses))
        if uses > 0 and drink.cost <= state.stamina
    ]


def use_drink_state(state: ExpectState, index: int) -> ExpectState:
    """喝一瓶饮料，返回新状态（与 ``LessonSim.use_drink`` 同语义）。

    饮料不占本回合出牌次数；饮品槽/次数进 ``ExpectState``。当前 expectimax 的
    动作仍是 play/SKIP，饮料由调用方在出牌前/后决定。
    """
    if isinstance(index, bool) or not isinstance(index, int):
        raise TypeError(f"饮料下标必须是 int：{index!r}")
    if not 0 <= index < len(state.drinks):
        raise ValueError(f"饮料下标越界：{index}")
    if (
        state.drinks_per_turn is not None
        and state.drinks_used_this_turn >= state.drinks_per_turn
    ):
        raise ValueError(
            f"本回合已经喝够饮料（每回合最多 {state.drinks_per_turn} 瓶）"
        )
    drink = state.drinks[index]
    if state.drink_uses[index] <= 0:
        raise ValueError(f"饮料已经用完：{drink.name}")
    if drink.cost > state.stamina:
        raise ValueError(
            f"体力不足：喝「{drink.name}」需要 {drink.cost}，当前 {state.stamina}"
        )
    stamina = state.stamina - drink.cost
    focus = state.focus
    condition_turns = state.condition_turns
    score = state.score
    if drink.effect_type == "stamina":
        stamina = min(state.stamina_max, stamina + drink.value)
    elif drink.effect_type == "focus":
        focus += drink.value
    elif drink.effect_type == "condition":
        condition_turns += drink.value
    else:  # score
        score += drink.value
    uses = list(state.drink_uses)
    uses[index] -= 1
    return replace(
        state,
        stamina=stamina,
        focus=focus,
        condition_turns=condition_turns,
        score=score,
        drink_uses=tuple(uses),
        drinks_used_this_turn=state.drinks_used_this_turn + 1,
    )


def _encore_card(card: CardSpec) -> CardSpec:
    """再演（ExamStatusEnchantEncore）：直接效果执行两次，倍率类字段不翻倍。"""
    return replace(
        card,
        score=card.score * 2,
        vitality=card.vitality * 2,
        condition=card.condition * 2,
        focus=card.focus * 2,
        motivation=card.motivation * 2,
        impression=card.impression * 2,
        draw=card.draw * 2,
        full_power_point=card.full_power_point * 2,
        extra_play=card.extra_play * 2,
        stamina_recover=card.stamina_recover * 2,
    )


def _tick_turns(turns: int) -> int:
    return turns - 1 if turns > 0 else turns


def _merge_turns(current: int, new: int) -> int:
    if current == _PERMANENT or new == _PERMANENT:
        return _PERMANENT
    return max(current, new)


def _card_award(
    state: ExpectState, card: CardSpec, *, uses: int = 0
) -> tuple[int, int]:
    """本牌得分 + 更新后的本回合审查基准加成（与 LessonSim._card_award 对齐）。"""
    award = 0
    base_score = card.score
    if base_score > 0 and card.grow_score > 0 and uses > 0:
        base_score = base_score * (100 + uses * card.grow_score) / 100
    if base_score > 0:
        multiplier = 1.5 if state.condition_turns > 0 else 1.0
        raw = (
            (base_score + state.focus)
            * multiplier
            * score_multiplier(state.stance_state)
        )
        if state.attribute_coefficient == 1.0:
            award = math.floor(raw)
        else:
            award = math.floor(raw * state.attribute_coefficient + 0.5)
    if card.impression_scale > 0 and state.impression > 0:
        award += int(state.impression * card.impression_scale / 100)
    if card.block_scale > 0 and state.vitality > 0:
        award += int(state.vitality * card.block_scale / 100)
    if card.full_power_scale > 0 and state.stance_state.full_power_point > 0:
        power = int(
            state.stance_state.full_power_point * card.full_power_scale / 1000
        )
        multiple = max(card.full_power_lesson_multiple, state.full_power_lesson_multiple)
        if multiple > 0:
            power = int(power * (1000 + multiple) / 1000)
        award += power
    parameter_buff = max(card.parameter_buff, state.parameter_buff)
    if parameter_buff > 0 and award > 0:
        award = int(award * parameter_buff / 1000)
    next_parameter_buff = state.parameter_buff
    if card.parameter_buff > 0 and card.parameter_buff_turns > 1:
        next_parameter_buff = max(state.parameter_buff, card.parameter_buff)
    return award, next_parameter_buff


def _apply_card_effects(state: ExpectState, played: CardSpec) -> tuple[ExpectState, int]:
    """算分、付牌费、结算 buff/指針/体力回复；返回 ``(新状态, 抽牌数)``。"""
    effect_card = _encore_card(played) if played.encore else played
    uses = state.uses_of(played.name)
    award, next_parameter_buff = _card_award(state, effect_card, uses=uses)
    state = replace(state, score=state.score + award, parameter_buff=next_parameter_buff)
    # 付牌费：先按指針修正实际费用，強気 2 段階穿透 1 点元气（直接扣体力）
    previous_stance = state.stance_state.stance
    cost = effective_cost(state, played)
    pierce = min(cost, stamina_pierce(state.stance_state))
    if pierce:
        state = replace(state, stamina=state.stamina - pierce)
    remaining = cost - pierce
    absorbed = min(state.vitality, remaining)
    state = replace(
        state,
        vitality=state.vitality - absorbed,
        stamina=state.stamina - (remaining - absorbed),
    )
    if effect_card.stamina_recover > 0:
        state = replace(
            state,
            stamina=min(state.stamina_max, state.stamina + effect_card.stamina_recover),
        )
    if effect_card.condition_additive > 0:
        state = replace(
            state,
            condition_additive=max(
                state.condition_additive, effect_card.condition_additive
            ),
            condition_additive_turns=_merge_turns(
                state.condition_additive_turns,
                effect_card.condition_additive_turns
                if effect_card.condition_additive_turns
                else 1,
            ),
        )
    if effect_card.review_multiple > 0:
        state = replace(
            state,
            review_multiple=max(state.review_multiple, effect_card.review_multiple),
            review_multiple_turns=_merge_turns(
                state.review_multiple_turns,
                effect_card.review_multiple_turns
                if effect_card.review_multiple_turns
                else 1,
            ),
        )
    if effect_card.full_power_lesson_multiple > 0:
        state = replace(
            state,
            full_power_lesson_multiple=max(
                state.full_power_lesson_multiple,
                effect_card.full_power_lesson_multiple,
            ),
            full_power_lesson_multiple_turns=_merge_turns(
                state.full_power_lesson_multiple_turns,
                effect_card.full_power_lesson_multiple_turns
                if effect_card.full_power_lesson_multiple_turns
                else 1,
            ),
        )
    condition_gain = effect_card.condition
    if condition_gain > 0 and state.condition_additive > 0:
        condition_gain += state.condition_additive
    vitality_gain = effect_card.vitality + state.motivation
    state = replace(
        state,
        condition_turns=state.condition_turns + condition_gain,
        focus=state.focus + effect_card.focus,
        impression=state.impression + effect_card.impression,
        vitality=state.vitality + vitality_gain,
        motivation=state.motivation + effect_card.motivation,
        extra_plays=state.extra_plays + effect_card.extra_play,
        plays_used=state.plays_used + 1,
    )
    stance = state.stance_state
    if effect_card.full_power_point > 0:
        stance = apply_full_power_point(stance, effect_card.full_power_point)
    if effect_card.strong_level > 0:
        delta = card_stance_effect("ExamConcentration", [effect_card.strong_level])
        if delta["stance"] is not None:
            stance = replace(
                stance,
                stance=delta["stance"],
                strong_level=effect_card.strong_level,
                save_level=0,
            )
    if effect_card.preservation > 0:
        delta = card_stance_effect("ExamPreservation", [effect_card.preservation])
        if delta["stance"] is not None:
            stance = replace(
                stance,
                stance=delta["stance"],
                strong_level=0,
                save_level=max(stance.save_level, int(delta["save_level"])),
            )
    state = state.with_stance(stance)
    # P 道具：获得层数时（status_gain）
    if condition_gain > 0:
        state = fire_p_items(
            state, STATUS_GAIN, status="parameter_buff", amount=condition_gain
        )
    if effect_card.focus > 0:
        state = fire_p_items(
            state, STATUS_GAIN, status="focus", amount=effect_card.focus
        )
    if effect_card.impression > 0:
        state = fire_p_items(
            state,
            STATUS_GAIN,
            status="impression",
            amount=effect_card.impression,
        )
    if effect_card.vitality > 0:
        state = fire_p_items(
            state, STATUS_GAIN, status="vitality", amount=vitality_gain
        )
    if effect_card.motivation > 0:
        state = fire_p_items(
            state,
            STATUS_GAIN,
            status="aggressive",
            amount=effect_card.motivation,
        )
    if effect_card.full_power_point > 0:
        state = fire_p_items(
            state,
            STATUS_GAIN,
            status="full_power_point",
            amount=effect_card.full_power_point,
        )
    if stance.stance == "save":
        state = replace(state, save_cards_used=state.save_cards_used + 1)
    elif previous_stance == "save":
        state = replace(
            state,
            condition_turns=state.condition_turns + state.save_cards_used + 1,
            save_cards_used=0,
        )
    if effect_card.grow_score > 0:
        uses_map = dict(state.card_uses)
        uses_map[played.name] = uses_map.get(played.name, 0) + 1
        state = replace(state, card_uses=tuple(sorted(uses_map.items())))
    return state, max(int(effect_card.draw), 0)


# ---------------------------------------------------------------- 抽牌机会节点
def _draw_combinations(
    deck: Counter[CardSpec], count: int
) -> list[tuple[float, Counter[CardSpec]]]:
    """从已知多重集抽 ``count`` 张（不放回）的组合分布，超几何精确枚举。"""
    items = sorted(deck.items(), key=lambda item: _card_key(item[0]))
    total = sum(deck.values())
    draw = min(max(count, 0), total)
    if draw <= 0:
        return [(1.0, Counter())]
    denominator = math.comb(total, draw)
    results: list[tuple[float, Counter[CardSpec]]] = []

    def recurse(
        index: int, left: int, numerator: int, chosen: Counter[CardSpec]
    ) -> None:
        if index == len(items):
            if left == 0:
                results.append((numerator / denominator, Counter(chosen)))
            return
        card, available = items[index]
        for take in range(min(available, left) + 1):
            if take:
                chosen[card] = take
            recurse(
                index + 1, left - take, numerator * math.comb(available, take), chosen
            )
            chosen.pop(card, None)

    recurse(0, draw, 1, Counter())
    return results


def _draw_sequential(
    deck: Counter[CardSpec], discard: Counter[CardSpec], count: int
) -> list[tuple[float, Counter[CardSpec], Counter[CardSpec], Counter[CardSpec]]]:
    """逐张按 count/remain 分支；处理抽到一半牌库空、弃牌洗回的情况。"""
    results: dict[tuple[Any, ...], list[Any]] = {}

    def record(
        probability: float,
        drawn: Counter[CardSpec],
        left_deck: Counter[CardSpec],
        left_discard: Counter[CardSpec],
    ) -> None:
        key = (_counts_key(drawn), _counts_key(left_deck), _counts_key(left_discard))
        entry = results.get(key)
        if entry is None:
            results[key] = [probability, Counter(drawn), Counter(left_deck), Counter(left_discard)]
        else:
            entry[0] += probability

    def recurse(
        current_deck: Counter[CardSpec],
        current_discard: Counter[CardSpec],
        left: int,
        probability: float,
        drawn: Counter[CardSpec],
    ) -> None:
        if left <= 0:
            record(probability, drawn, current_deck, current_discard)
            return
        if not current_deck:
            if not current_discard:
                record(probability, drawn, current_deck, current_discard)
                return
            recurse(Counter(current_discard), Counter(), left, probability, drawn)
            return
        total = sum(current_deck.values())
        for card, available in list(current_deck.items()):
            share = probability * available / total
            next_deck = Counter(current_deck)
            next_deck[card] -= 1
            if next_deck[card] <= 0:
                del next_deck[card]
            next_drawn = Counter(drawn)
            next_drawn[card] += 1
            recurse(next_deck, current_discard, left - 1, share, next_drawn)

    recurse(Counter(deck), Counter(discard), max(count, 0), 1.0, Counter())
    return [
        (float(entry[0]), Counter(entry[1]), Counter(entry[2]), Counter(entry[3]))
        for entry in results.values()
    ]


def _draw_distribution(
    state: ExpectState,
    count: int,
    *,
    enum_limit: int = DEFAULT_DRAW_ENUM_LIMIT,
) -> list[tuple[float, ExpectState]]:
    """抽 ``count`` 张牌的精确机会节点 ``[(概率, 后继状态)]``。"""
    if count <= 0:
        return [(1.0, state)]
    deck = Counter(state.deck)
    discard = Counter(state.discard)
    if not deck and discard:
        deck, discard = discard, Counter()
    if not deck:
        return [(1.0, state)]

    total = sum(deck.values())
    mid_draw_reshuffle = total < count and bool(discard)
    if total <= enum_limit and not mid_draw_reshuffle:
        outcomes: list[tuple[float, ExpectState]] = []
        for probability, drawn in _draw_combinations(deck, count):
            remaining = Counter(deck)
            remaining.subtract(drawn)
            remaining = Counter(
                {card: number for card, number in remaining.items() if number > 0}
            )
            outcomes.append(
                (
                    probability,
                    replace(
                        state,
                        hand=state.hand + _counts_tuple(drawn),
                        deck=_counts_tuple(remaining),
                        discard=_counts_tuple(discard),
                    ),
                )
            )
        return outcomes

    outcomes = []
    for probability, drawn, left_deck, left_discard in _draw_sequential(
        deck, discard, count
    ):
        outcomes.append(
            (
                probability,
                replace(
                    state,
                    hand=state.hand + _counts_tuple(drawn),
                    deck=_counts_tuple(left_deck),
                    discard=_counts_tuple(left_discard),
                ),
            )
        )
    return outcomes


def apply_card(state: ExpectState, card: CardSpec) -> list[tuple[float, ExpectState]]:
    """打出一张牌，返回抽牌机会节点的后继分布 ``[(p, state)]``。

    打出的牌在抽牌结算**之后**才进弃牌堆/除外区（与 LessonSim.step 一致）。
    """
    if card not in state.hand:
        raise ValueError(f"牌不在手牌里：{card.name}")
    if not is_legal(state, card):
        raise ValueError(
            f"牌不合法：{card.name} 需要 {effective_cost(state, card)}，当前体力+元气 "
            f"{state.total_cost_available}，出牌次数 "
            f"{state.plays_used}/{state.play_limit + state.extra_plays}"
        )
    after, draw = _apply_card_effects(state, card)
    hand = list(after.hand)
    hand.remove(card)
    after = replace(after, hand=tuple(hand))
    outcomes = _draw_distribution(after, draw)
    results: list[tuple[float, ExpectState]] = []
    for probability, successor in outcomes:
        successor = replace(
            successor, cards_played_total=state.cards_played_total + 1
        )
        successor = fire_p_items(
            successor,
            CARD_PLAY,
            card_category=card.category,
            cards_played_this_turn=successor.plays_used,
            cards_played_total=successor.cards_played_total,
        )
        if card.once:
            successor = replace(successor, excluded=successor.excluded + (card,))
        else:
            successor = replace(successor, discard=successor.discard + (card,))
        results.append((probability, successor))
    return results


def run_sequence(state: ExpectState, cards: Iterable[CardSpec]) -> ExpectState:
    """按顺序打一组牌（抽牌机会节点取概率最大的后继），供测试/回放。"""
    current = state
    for card in cards:
        outcomes = apply_card(current, card)
        if not outcomes:
            break
        outcomes.sort(key=lambda item: item[0], reverse=True)
        current = outcomes[0][1]
        if current.plays_left <= 0:
            break
    return current


def sample_draws(state: ExpectState, count: int, rng: random.Random) -> ExpectState:
    """从真实剩余多重集**无放回抽样** ``count`` 张（牌库空则把弃牌洗回）。"""
    deck = Counter(state.deck)
    discard = Counter(state.discard)
    hand = list(state.hand)
    for _ in range(max(int(count), 0)):
        if not deck:
            if not discard:
                break
            deck, discard = discard, Counter()
        total = sum(deck.values())
        pick = rng.randrange(total)
        chosen: CardSpec | None = None
        for card, available in deck.items():
            if pick < available:
                chosen = card
                break
            pick -= available
        if chosen is None:
            break
        deck[chosen] -= 1
        if deck[chosen] <= 0:
            del deck[chosen]
        hand.append(chosen)
    return replace(
        state,
        hand=tuple(hand),
        deck=_counts_tuple(deck),
        discard=_counts_tuple(discard),
    )


def sample_apply_card(
    state: ExpectState, card: CardSpec, rng: random.Random
) -> ExpectState:
    """打出一张牌并按真实剩余多重集抽样一个抽牌结果（beam 用）。"""
    if card not in state.hand:
        raise ValueError(f"牌不在手牌里：{card.name}")
    if not is_legal(state, card):
        raise ValueError(f"牌不合法：{card.name}")
    after, draw = _apply_card_effects(state, card)
    hand = list(after.hand)
    hand.remove(card)
    after = replace(after, hand=tuple(hand))
    after = sample_draws(after, draw, rng)
    after = replace(after, cards_played_total=state.cards_played_total + 1)
    after = fire_p_items(
        after,
        CARD_PLAY,
        card_category=card.category,
        cards_played_this_turn=after.plays_used,
        cards_played_total=after.cards_played_total,
    )
    if card.once:
        return replace(after, excluded=after.excluded + (card,))
    return replace(after, discard=after.discard + (card,))


_P_ITEM_GROUP_CACHE: dict[int, tuple[tuple[PItemSpec, ...], dict[str, tuple[PItemSpec, ...]]]] = {}


def _p_items_grouped(
    items: tuple[PItemSpec, ...],
) -> dict[str, tuple[PItemSpec, ...]]:
    """按 trigger 预分组（避免每个搜索节点都遍历全部 1000+ 条 P 道具）。

    用 ``id(items)`` 做缓存键并保留 items 引用，防止 id 复用；同一局内
    ``ExpectState.p_items`` 是同一个 tuple 对象（``replace`` 不换引用）。
    """
    cached = _P_ITEM_GROUP_CACHE.get(id(items))
    if cached is not None and cached[0] is items:
        return cached[1]
    grouped: dict[str, tuple[PItemSpec, ...]] = {}
    for item in items:
        grouped[item.trigger] = (*grouped.get(item.trigger, ()), item)
    _P_ITEM_GROUP_CACHE[id(items)] = (items, grouped)
    return grouped


def _passive_state(state: ExpectState) -> PassiveState:
    return PassiveState(
        turn=state.current_turn,
        turns_left=state.turns_left,
        is_final_turn=state.turns_left <= 1,
        stamina=state.stamina,
        stamina_max=state.stamina_max,
        score=state.score,
        stacks={
            "vitality": state.vitality,
            "impression": state.impression,
            "focus": state.focus,
            "aggressive": state.motivation,
            "full_power_point": state.stance_state.full_power_point,
            "parameter_buff": state.condition_turns,
        },
        uses=dict(state.p_item_uses),
    )


def _p_item_event_subset(
    state: ExpectState, kind: str
) -> tuple[PItemSpec, ...]:
    if not state.p_items:
        return ()
    grouped = _p_items_grouped(state.p_items)
    if kind == TURN_START:
        return grouped.get(TURN_START, ())
    if kind == TURN_END:
        return grouped.get(TURN_END, ())
    if kind == STATUS_GAIN:
        return grouped.get(STATUS_GAIN, ())
    return (
        grouped.get("card_play", ())
        + grouped.get("card_played", ())
        + grouped.get("card_play_interval", ())
    )


def fire_p_items(
    state: ExpectState,
    kind: str,
    *,
    card_category: str = "",
    cards_played_this_turn: int = 0,
    cards_played_total: int = 0,
    status: str = "",
    amount: int = 0,
) -> ExpectState:
    """在指定时机触发 P 道具并返回结算后的状态（纯函数）。"""
    if not state.p_items:
        return state
    subset = _p_item_event_subset(state, kind)
    if not subset:
        return state
    event = PassiveEvent(
        kind=kind,
        card_category=card_category,
        cards_played_this_turn=cards_played_this_turn,
        cards_played_total=cards_played_total,
        status=status,
        amount=amount,
    )
    delta = apply_passive(subset, event, _passive_state(state))
    if delta.is_zero():
        return state
    score = state.score + int(delta.score)
    stamina = state.stamina
    if delta.stamina:
        stamina = min(state.stamina_max, max(0, stamina + delta.stamina))
    vitality = state.vitality
    impression = state.impression
    focus = state.focus
    condition_turns = state.condition_turns
    motivation = state.motivation
    stance = state.stance_state
    for key, value in delta.stacks.items():
        value = int(value)
        if key == "vitality":
            vitality += value
        elif key == "impression":
            impression += value
        elif key == "focus":
            focus += value
        elif key == "aggressive":
            motivation += value
        elif key == "full_power_point":
            stance = apply_full_power_point(stance, value)
        elif key == "parameter_buff":
            condition_turns += value
    uses = dict(state.p_item_uses)
    for item_id in delta.applied:
        uses[item_id] = uses.get(item_id, 0) + 1
    return replace(
        state,
        score=score,
        stamina=stamina,
        vitality=vitality,
        impression=impression,
        focus=focus,
        condition_turns=condition_turns,
        motivation=motivation,
        p_item_uses=tuple(sorted(uses.items())),
    ).with_stance(stance)


def start_turn_state(state: ExpectState) -> ExpectState:
    """抽完新手牌后的回合开始结算（P 道具 turn_start）；beam 未来回合用。"""
    return fire_p_items(state, TURN_START)


def end_turn_state(state: ExpectState) -> ExpectState:
    """结算回合末：好印象加分后 -1、好调 -1、持续 buff 倒计时、弃手牌、回合 -1。

    不抽下一手牌：下一回合的牌序属于未知，由 V_leaf 的解析式吸收。
    """
    score = state.score
    impression = state.impression
    if impression > 0:
        value = float(impression)
        if state.review_multiple > 0:
            value = int(impression * (1000 + state.review_multiple) / 1000)
        score += int(value)
        impression -= 1
    condition_turns = state.condition_turns - 1 if state.condition_turns > 0 else 0
    condition_additive_turns = _tick_turns(state.condition_additive_turns)
    condition_additive = state.condition_additive if condition_additive_turns != 0 else 0
    review_multiple_turns = _tick_turns(state.review_multiple_turns)
    review_multiple = state.review_multiple if review_multiple_turns != 0 else 0
    full_power_turns = _tick_turns(state.full_power_lesson_multiple_turns)
    full_power_multiple = state.full_power_lesson_multiple if full_power_turns != 0 else 0
    next_stance = end_turn(state.stance_state)
    next_state = replace(
        state,
        score=score,
        impression=impression,
        condition_turns=condition_turns,
        condition_additive=condition_additive,
        condition_additive_turns=condition_additive_turns,
        review_multiple=review_multiple,
        review_multiple_turns=review_multiple_turns,
        full_power_lesson_multiple=full_power_multiple,
        full_power_lesson_multiple_turns=full_power_turns,
        parameter_buff=0,
        hand=(),
        discard=state.discard + state.hand,
        turns_left=state.turns_left - 1,
        plays_used=0,
        extra_plays=0,
        drinks_used_this_turn=0,
        stance=(
            next_stance.stance,
            next_stance.strong_level,
            next_stance.save_level,
            next_stance.full_power_point,
        ),
    )
    # P 道具：回合结束（好印象/好调结算后、弃手牌前）
    return fire_p_items(next_state, TURN_END)


# ---------------------------------------------------------------- 搜索
def _action_tiebreak(state: ExpectState, card: CardSpec) -> tuple[int, int, int]:
    """效用打平时的通用 tie-break：优先保留更多动作次数/资源（不认牌名）。

    再动卡与"直接打大牌"在 E[分数] 上可能打平；动作经济性（多一张可出牌）是
    真实价值，所以先比打完后剩余出牌位，再比剩余体力+元气，最后比费用。
    """
    plays_after = state.plays_left - 1 + max(int(card.extra_play), 0)
    resource_after = state.total_cost_available - int(card.cost)
    return (plays_after, resource_after, -int(card.cost))


class _Search:
    """一次决策的搜索上下文（memo/nodes/deadline 都是局部的，可重入）。"""

    def __init__(
        self,
        value: AnalyticLeafValue,
        config: ExpectimaxConfig,
        *,
        clock: Callable[[], float],
        deadline: float | None,
    ) -> None:
        self.value = value
        self.config = config
        self.clock = clock
        self.deadline = deadline
        self.memo: dict[tuple[Any, ...], float] = {}
        self.choice_memo: dict[tuple[Any, ...], CardSpec | None] = {}
        self.drink_choice_memo: dict[tuple[Any, ...], int | None] = {}
        self.nodes = 0
        self.aborted = False

    def leaf(self, state: ExpectState) -> float:
        return self.value.utility(end_turn_state(state))

    def _check_deadline(self) -> None:
        if (
            self.deadline is not None
            and (self.nodes == 1 or (self.nodes & 31) == 0)
            and self.clock() >= self.deadline
        ):
            self.aborted = True
            raise _Deadline

    def search(self, state: ExpectState) -> float:
        """状态价值 = max(SKIP 的叶子价值, 各合法牌动作的期望价值)。"""
        self.nodes += 1
        self._check_deadline()
        if self.nodes > self.config.max_nodes:
            self.aborted = True
            raise _Deadline
        if state.plays_left <= 0 or not state.hand:
            return self.leaf(state)
        key = state.canonical()
        cached = self.memo.get(key)
        if cached is not None:
            return cached
        best = self.leaf(state)
        best_card: CardSpec | None = None
        best_drink: int | None = None
        best_key: tuple[int, int, int] | None = (
            state.plays_left,
            state.total_cost_available,
            0,
        )
        for card in legal_cards(state):
            value = self.action_value(state, card)
            key_break = _action_tiebreak(state, card)
            if value > best + 1e-12 or (
                abs(value - best) <= 1e-12
                and (best_key is None or key_break > best_key)
            ):
                best = value
                best_card = card
                best_drink = None
                best_key = key_break
        self.memo[key] = best
        self.choice_memo[key] = best_card
        self.drink_choice_memo[key] = best_drink
        return best

    def action_value(self, state: ExpectState, card: CardSpec) -> float:
        outcomes = apply_card(state, card)
        return sum(
            probability * self.search(next_state)
            for probability, next_state in outcomes
        )

    def root(
        self, state: ExpectState
    ) -> tuple[float, CardSpec | None, int | None, list[tuple[str, float]]]:
        """根节点：返回 (最优价值, 最优首牌或 None, 最优饮料下标或 None, 动作价值)。"""
        skip_value = self.leaf(state)
        best_value = skip_value
        best_card: CardSpec | None = None
        best_drink: int | None = None
        best_key: tuple[int, int, int] | None = (
            state.plays_left,
            state.total_cost_available,
            0,
        )
        actions: list[tuple[str, float]] = []
        for card in legal_cards(state):
            try:
                value = self.action_value(state, card)
            except _Deadline:
                self.aborted = True
                break
            actions.append((card.name, value))
            key_break = _action_tiebreak(state, card)
            if value > best_value + 1e-12 or (
                abs(value - best_value) <= 1e-12
                and (best_key is None or key_break > best_key)
            ):
                best_value = value
                best_card = card
                best_drink = None
                best_key = key_break
        self.memo[state.canonical()] = best_value
        self.choice_memo[state.canonical()] = best_card
        self.drink_choice_memo[state.canonical()] = best_drink
        return best_value, best_card, best_drink, actions


def _config_with_overrides(
    config: ExpectimaxConfig | None,
    *,
    a_clear: float | None,
    a_perfect: float | None,
    sigma: float | None,
    time_budget_ms: float | None,
    draw_enum_limit: int | None,
    max_nodes: int | None,
) -> ExpectimaxConfig:
    base = config or ExpectimaxConfig()
    updates: dict[str, Any] = {}
    if a_clear is not None:
        updates["a_clear"] = float(a_clear)
    if a_perfect is not None:
        updates["a_perfect"] = float(a_perfect)
    if sigma is not None:
        updates["sigma"] = max(float(sigma), 0.0)
    if time_budget_ms is not None:
        updates["time_budget_ms"] = float(time_budget_ms)
    if draw_enum_limit is not None:
        updates["draw_enum_limit"] = max(int(draw_enum_limit), 0)
    if max_nodes is not None:
        updates["max_nodes"] = max(int(max_nodes), 1)
    return replace(base, **updates) if updates else base


def expectimax_with_stats(
    state: ExpectState,
    value: AnalyticLeafValue | None = None,
    *,
    config: ExpectimaxConfig | None = None,
    clock: Callable[[], float] = time.perf_counter,
    deadline: float | None = None,
    time_budget_ms: float | None = None,
    a_clear: float | None = None,
    a_perfect: float | None = None,
    sigma: float | None = None,
    draw_enum_limit: int | None = None,
    max_nodes: int | None = None,
) -> ExpectimaxResult:
    """完整决策：返回动作、价值、节点数、耗时、是否完整（anytime 截止）。"""
    config = _config_with_overrides(
        config,
        a_clear=a_clear,
        a_perfect=a_perfect,
        sigma=sigma,
        time_budget_ms=time_budget_ms,
        draw_enum_limit=draw_enum_limit,
        max_nodes=max_nodes,
    )
    model = value or AnalyticLeafValue(
        sigma=config.sigma, a_clear=config.a_clear, a_perfect=config.a_perfect
    )
    started = clock()
    if deadline is None and config.time_budget_ms is not None:
        deadline = started + max(float(config.time_budget_ms), 0.0) / 1000.0
    search = _Search(model, config, clock=clock, deadline=deadline)
    try:
        best_value, best_card, _best_drink, actions = search.root(state)
    except _Deadline:
        best_value, best_card, _best_drink, actions = (
            search.leaf(state),
            None,
            None,
            [],
        )
        search.aborted = True
    elapsed_ms = (clock() - started) * 1000.0
    return ExpectimaxResult(
        card=best_card,
        utility=float(best_value),
        skip_utility=float(search.leaf(state)),
        actions=tuple(actions),
        nodes=search.nodes,
        elapsed_ms=float(elapsed_ms),
        complete=not search.aborted,
    )


def expectimax(
    state: ExpectState,
    value: AnalyticLeafValue | None = None,
    *,
    config: ExpectimaxConfig | None = None,
    clock: Callable[[], float] = time.perf_counter,
    deadline: float | None = None,
    time_budget_ms: float | None = None,
    **kwargs: Any,
) -> CardSpec | None:
    """返回本回合第一张要打的牌；``None`` = SKIP（结束本回合）。"""
    result = expectimax_with_stats(
        state,
        value,
        config=config,
        clock=clock,
        deadline=deadline,
        time_budget_ms=time_budget_ms,
        **kwargs,
    )
    return result.card


def expectimax_value(
    state: ExpectState,
    value: AnalyticLeafValue | None = None,
    **kwargs: Any,
) -> float:
    """当前状态在档位效用下的最优价值（测试/日志用）。"""
    return expectimax_with_stats(state, value, **kwargs).utility


def best_turn_sequence(
    state: ExpectState,
    value: AnalyticLeafValue | None = None,
    *,
    clock: Callable[[], float] = time.perf_counter,
    deadline: float | None = None,
) -> tuple[list[CardSpec], ExpectState, bool]:
    """本回合的最优**有序出牌序列**（抽牌取最大概率后继；beam 规划用）。"""
    model = value or AnalyticLeafValue()
    search = _Search(model, ExpectimaxConfig(), clock=clock, deadline=deadline)
    cards: list[CardSpec] = []
    current = state
    complete = True
    try:
        while current.plays_left > 0 and current.hand:
            search.search(current)
            card = search.choice_memo.get(current.canonical())
            if card is None:
                break
            outcomes = apply_card(current, card)
            if not outcomes:
                break
            outcomes.sort(key=lambda item: item[0], reverse=True)
            current = outcomes[0][1]
            cards.append(card)
    except _Deadline:
        complete = False
    return cards, current, complete and not search.aborted


# ---------------------------------------------------------------- 跨回合 beam
@dataclass(frozen=True)
class BeamResult:
    """跨回合 beam 的决策结果（按 V_leaf 排序，不按当前分数）。"""

    card: CardSpec | None
    utility: float
    skip_utility: float
    sequence: tuple[str, ...]
    end_state: ExpectState | None
    width: int
    depth_reached: int
    layer_scores: tuple[float, ...]
    elapsed_ms: float
    complete: bool


@dataclass(frozen=True)
class _TurnPlan:
    first_card: CardSpec | None
    sequence: tuple[str, ...]
    end_state: ExpectState
    utility: float
    complete: bool


@dataclass(frozen=True)
class _BeamNode:
    """beam 节点：保留父链和根回合计划，最后按最深层的 V 回溯根动作。"""

    plan: _TurnPlan
    parent: _BeamNode | None
    root_plan: _TurnPlan
    depth: int


def _top_turn_plans(
    state: ExpectState,
    value: AnalyticLeafValue,
    *,
    limit: int,
    rng: random.Random,
    clock: Callable[[], float],
    deadline: float,
) -> list[_TurnPlan]:
    """本回合按 V_leaf 取 top-limit 个**不同出牌序列**（beam 根分支用）。

    手牌里没有抽牌卡时，回合内是确定性的，直接枚举所有有序序列（含提前 SKIP）；
    有抽牌卡时用 ``_plan_turn`` 抽样 limit 次（不确定的抽牌交给随机机会）。
    """
    limit = max(int(limit), 1)
    has_draw = any(card.draw > 0 for card in state.hand)
    if limit == 1 or has_draw:
        # 单计划/有抽牌/有饮料：直接用 expectimax 的最佳序列（比枚举快）
        return [
            _plan_turn(state, value, rng, clock=clock, deadline=deadline)
            for _ in range(limit)
        ]

    results: dict[tuple[Any, ...], _TurnPlan] = {}

    def record(cards: list[CardSpec], current: ExpectState) -> None:
        end = end_turn_state(current)
        names = tuple(card.name for card in cards)
        key = (names, end.canonical())
        if key in results:
            return
        results[key] = _TurnPlan(
            first_card=cards[0] if cards else None,
            sequence=names,
            end_state=end,
            utility=value.utility(end),
            complete=True,
        )

    def recurse(current: ExpectState, cards: list[CardSpec]) -> None:
        if clock() >= deadline:
            return
        record(cards, current)
        if current.plays_left <= 0 or not current.hand:
            return
        for card in legal_cards(current):
            outcomes = apply_card(current, card)
            if len(outcomes) != 1:
                # 手牌里没有 draw 卡时不应出现分支；防御性跳过
                continue
            recurse(outcomes[0][1], [*cards, card])

    recurse(state, [])
    ordered = sorted(results.values(), key=lambda plan: plan.utility, reverse=True)
    return ordered[:limit]


def _plan_turn(
    state: ExpectState,
    value: AnalyticLeafValue,
    rng: random.Random,
    *,
    clock: Callable[[], float],
    deadline: float,
) -> _TurnPlan:
    """一个回合的最佳序列；有抽牌卡时按真实剩余多重集抽样推进。"""
    has_draw = any(card.draw > 0 for card in state.hand)
    first_card: CardSpec | None = None
    names: list[str] = []
    complete = True
    if not has_draw:
        cards, current, complete = best_turn_sequence(
            state, value, clock=clock, deadline=deadline
        )
        names = [card.name for card in cards]
        first_card = cards[0] if cards else None
    else:
        current = state
        try:
            while current.plays_left > 0 and current.hand:
                result = expectimax_with_stats(
                    current, value, clock=clock, deadline=deadline
                )
                if result.card is None:
                    break
                if first_card is None:
                    first_card = result.card
                names.append(result.card.name)
                current = sample_apply_card(current, result.card, rng)
                if not result.complete:
                    complete = False
                    break
        except _Deadline:
            complete = False
    end_state = end_turn_state(current)
    return _TurnPlan(
        first_card=first_card,
        sequence=tuple(names),
        end_state=end_state,
        utility=value.utility(end_state),
        complete=complete,
    )


def search_beam(
    state: ExpectState,
    value: AnalyticLeafValue | None = None,
    *,
    width: int = 24,
    depth: int | None = None,
    deadline_ms: float = DEFAULT_BEAM_DEADLINE_MS,
    time_budget_ms: float | None = None,
    clock: Callable[[], float] = time.perf_counter,
    rng: random.Random | int | None = None,
    branching: int | None = None,
) -> BeamResult:
    """跨回合 beam：每层一个回合，节点是回合末状态，按 V_leaf 保留 top-width。

    根回合先生成 top-``branch`` 个不同出牌序列作为 beam 分支；之后每层用真实
    剩余多重集**无放回抽样**新一手牌（``sample_draws``），回合内用 expectimax
    产出该回合最佳序列。最终按**最深一层**的 V_leaf 回溯根动作——这样"先铺 buff
    的投资线"不会因为当前分数低被剪掉。到 ``deadline_ms`` 返回当前最优。
    """
    model = value or AnalyticLeafValue()
    if time_budget_ms is not None:
        deadline_ms = time_budget_ms
    width = max(int(width), 1)
    total_depth = max(state.turns_left, 1)
    if depth is not None:
        total_depth = max(min(int(depth), total_depth), 1)
    branch = (
        max(int(branching), 1)
        if branching is not None
        else max(2, min(width, 3))
    )
    if isinstance(rng, int):
        rng = random.Random(rng)
    rng = rng or random.Random(0)
    started = clock()
    deadline = started + max(float(deadline_ms), 0.0) / 1000.0
    complete = True

    def timed_out() -> bool:
        nonlocal complete
        if clock() >= deadline:
            complete = False
            return True
        return False

    # 根回合：手牌已在手上。枚举/抽样 top 序列，每个序列一个 beam 节点。
    root_plans: list[_TurnPlan] = []
    try:
        root_plans = _top_turn_plans(
            state,
            model,
            limit=max(branch, width),
            rng=rng,
            clock=clock,
            deadline=deadline,
        )
    except _Deadline:
        complete = False
    if not root_plans:
        result = expectimax_with_stats(state, model, clock=clock, deadline=deadline)
        return BeamResult(
            card=result.card,
            utility=result.utility,
            skip_utility=result.skip_utility,
            sequence=(result.card.name,) if result.card else (),
            end_state=None,
            width=width,
            depth_reached=0,
            layer_scores=(),
            elapsed_ms=(clock() - started) * 1000.0,
            complete=False,
        )
    root_plans.sort(key=lambda plan: plan.utility, reverse=True)
    beam = [
        _BeamNode(plan=plan, parent=None, root_plan=plan, depth=1)
        for plan in root_plans[:width]
    ]
    best_node = beam[0]
    layer_scores = [best_node.plan.utility]
    depth_reached = 1

    for layer in range(2, total_depth + 1):
        if timed_out():
            break
        children: list[_BeamNode] = []
        for node in beam:
            if node.plan.end_state.turns_left <= 0:
                continue
            samples = branch
            for _ in range(samples):
                if timed_out():
                    break
                start = sample_draws(
                    node.plan.end_state, node.plan.end_state.hand_size, rng
                )
                start = start_turn_state(start)
                try:
                    plans = _top_turn_plans(
                        start,
                        model,
                        limit=1,
                        rng=rng,
                        clock=clock,
                        deadline=deadline,
                    )
                except _Deadline:
                    complete = False
                    break
                for plan in plans:
                    children.append(
                        _BeamNode(
                            plan=plan,
                            parent=node,
                            root_plan=node.root_plan,
                            depth=layer,
                        )
                    )
            if not complete:
                break
        if not children:
            break
        children.sort(key=lambda node: node.plan.utility, reverse=True)
        beam = children[:width]
        best_node = beam[0]
        layer_scores.append(best_node.plan.utility)
        depth_reached = layer
        if not complete:
            break

    # 最终按最深层 V 回溯根回合计划（不是按当前分数/根回合叶子）
    return BeamResult(
        card=best_node.root_plan.first_card,
        utility=best_node.plan.utility,
        skip_utility=model.utility(end_turn_state(state)),
        sequence=best_node.root_plan.sequence,
        end_state=best_node.plan.end_state,
        width=width,
        depth_reached=depth_reached,
        layer_scores=tuple(layer_scores),
        elapsed_ms=(clock() - started) * 1000.0,
        complete=complete and depth_reached >= total_depth,
    )


# ---------------------------------------------------------------- LessonSim 适配
def state_from_sim(sim: Any) -> ExpectState:
    """把一个 ``LessonSim`` 的当前局面快照成 ``ExpectState``（离线评测用）。"""
    buffs = getattr(sim, "buffs", Buffs())
    stance = getattr(sim, "stance", StanceState())
    config = getattr(sim, "config", None)
    card_uses: dict[str, int] = {}
    uses_table = getattr(sim, "card_uses", {})
    for group in (sim.hand, sim.deck, sim.discard, getattr(sim, "excluded", ())):
        for card in group:
            count = int(uses_table.get(id(card), 0))
            if count > card_uses.get(card.name, 0):
                card_uses[card.name] = count
    return ExpectState(
        hand=tuple(sim.hand),
        deck=tuple(sim.deck),
        discard=tuple(sim.discard),
        excluded=tuple(getattr(sim, "excluded", ())),
        stamina=max(int(sim.stamina), 0),
        stamina_max=max(int(getattr(sim, "stamina_max", 0)), 0),
        vitality=max(int(sim.vitality), 0),
        score=max(int(sim.score), 0),
        turns_left=max(int(sim.turns_left), 0),
        total_turns=max(int(getattr(sim, "total_turns", 0)), 0),
        plays_used=max(int(sim.plays_this_turn), 0),
        play_limit=max(int(sim.plays_per_turn), 1),
        extra_plays=max(int(getattr(sim, "extra_plays", 0)), 0),
        clear=max(int(getattr(sim, "target_clear", 0)), 0),
        perfect=max(int(getattr(sim, "target_perfect", 0)), 0),
        condition_turns=max(int(buffs.condition_turns), 0),
        focus=max(int(buffs.focus), 0),
        impression=max(int(buffs.impression), 0),
        motivation=max(int(getattr(sim, "motivation", 0)), 0),
        condition_additive=max(int(buffs.condition_additive), 0),
        condition_additive_turns=int(buffs.condition_additive_turns),
        review_multiple=max(int(buffs.review_multiple), 0),
        review_multiple_turns=int(buffs.review_multiple_turns),
        full_power_lesson_multiple=max(int(buffs.full_power_lesson_multiple), 0),
        full_power_lesson_multiple_turns=int(buffs.full_power_lesson_multiple_turns),
        parameter_buff=max(int(getattr(sim, "turn_parameter_buff", 0)), 0),
        stance=(
            stance.stance,
            int(stance.strong_level),
            int(stance.save_level),
            int(stance.full_power_point),
        ),
        save_cards_used=max(int(getattr(sim, "_save_cards_used", 0)), 0),
        attribute_coefficient=float(
            getattr(config, "attribute_coefficient", 1.0) if config else 1.0
        ),
        hand_size=max(int(getattr(config, "hand_size", 3) if config else 3), 1),
        min_cost=max(int(getattr(sim, "_min_cost", 0)), 0),
        p_items=tuple(getattr(config, "p_items", ()) if config else ()),
        p_item_uses=tuple(
            sorted(getattr(sim, "p_item_uses", {}).items())
        ),
        cards_played_total=max(int(getattr(sim, "cards_played_total", 0)), 0),
        drinks=tuple(getattr(config, "drinks", ()) if config else ()),
        drink_uses=tuple(
            max(int(uses), 0) for uses in getattr(sim, "drink_uses", ())
        ),
        drinks_used_this_turn=max(int(getattr(sim, "drinks_used_this_turn", 0)), 0),
        drinks_per_turn=getattr(config, "drinks_per_turn", None) if config else None,
        card_uses=tuple(sorted(card_uses.items())),
    )
