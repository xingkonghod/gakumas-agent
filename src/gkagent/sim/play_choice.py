"""实时出牌：用课程模拟器给每张手牌算期望分，选期望最高的那张打。

现有 ``LessonPolicy`` 是规则（分数÷体力、buff 优先、体力门）。这里对**每张手牌**做
N 次前瞻 rollout：先打这张牌，之后按 ``greedy_policy`` 把剩余回合打完，比较期望总分，
取最高的一一真机侧由 ``policy.json`` 的 ``produce.sim_play`` 开关（默认 false）。

anytime：总预算 ``time_budget_ms`` 用完就返回当前最优；第一轮保证每张牌至少 1 次，
避免预算紧时永远只选第一张。拿到不完整牌组时用当前手牌近似牌库。

任何异常/空手牌/一张都出不起都返回 ``None``——调用方必须退回 ``LessonPolicy``，
不能让出牌因此退化。开关与日志样例见 ``scripts/auto_produce.py``。

**考试/舞台**：真机考试里每张牌的分数都吃屏幕上的属性倍率
（「歌唱 411%」= 4.11），课程里 ≈ 1.0。调用方已知当前是考试/舞台时传
``kind="audition"``：rollout 的 ``LessonConfig.attribute_coefficient`` 会设成
4.11，期望分与选择按考试口径算；不传 / ``kind="lesson"`` 仍按课程 1.0
（旧调用方行为不变）。``config`` 显式传入时以 config 为准。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gkagent.sim.lesson import (
    AUDITION_ATTRIBUTE_COEFFICIENT,
    CardSpec,
    LessonConfig,
    LessonSim,
    greedy_policy,
)

if TYPE_CHECKING:
    from gkagent.data.card_table import CardTable
    from gkagent.vision.lesson import LessonCard

DEFAULT_EPISODES = 8
DEFAULT_TIME_BUDGET_MS = 250
DEFAULT_HAND_SIZE = 3
# 近似牌库上限：真机拿不到完整牌组，只把战斗里见过的手牌并进来估后续抽牌
MAX_APPROX_DECK = 12
# 被当成考试/舞台的 kind 取值：这些场景的分数吃屏幕属性倍率（411%）
AUDITION_KINDS = frozenset({"audition", "exam", "stage"})


@dataclass(frozen=True)
class PlayCard:
    """一张手牌 + 它对应的模拟用 ``CardSpec``。"""

    index: int
    name: str
    cost: int
    screen_score: float
    spec: CardSpec
    point: tuple[int, int] | None = None
    # 卡表查不到、只能用屏幕数值 → 期望分只是估计值
    estimated: bool = False


@dataclass(frozen=True)
class CardEstimate:
    """一张手牌的 rollout 结果。"""

    index: int
    name: str
    cost: int
    score: float
    expected: float
    episodes: int
    point: tuple[int, int] | None = None
    estimated: bool = False

    def __str__(self) -> str:
        suffix = "（卡表缺，按屏幕估）" if self.estimated else ""
        return (
            f"{self.name} ({self.score:.0f}分/{self.cost}费) "
            f"期望 {self.expected:.1f}{suffix}"
        )


def _default_table() -> CardTable:
    from gkagent.data.card_table import CardTable

    return CardTable()


def _effect_fields(row: dict) -> dict[str, int]:
    """卡表 effects → CardSpec 的附加字段（只认战斗里已建模的效果）。"""
    fields: dict[str, int] = {
        "condition": 0,
        "focus": 0,
        "draw": 0,
        "impression": 0,
        "impression_scale": 0,
        "vitality": 0,
        "block_scale": 0,
        "extra_play": 0,
        "parameter_buff": 0,
        "preservation": 0,
        "full_power_point": 0,
        "strong_level": 0,
    }
    mapping = {
        "ExamLessonBuff": "condition",
        "ExamConcentration": "focus",
        "ExamCardDraw": "draw",
        "ExamReview": "impression",
        "ExamLessonDependExamReview": "impression_scale",
        "ExamBlock": "vitality",
        "ExamLessonDependBlock": "block_scale",
        "ExamPlayableValueAdd": "extra_play",
        "ExamParameterBuff": "parameter_buff",
        "ExamPreservation": "preservation",
        "ExamOverPreservation": "preservation",
        "ExamFullPowerPoint": "full_power_point",
    }
    for effect in row.get("effects") or []:
        kind = str(effect.get("type") or "")
        values = [value for value in effect.get("values") or [] if value]
        if not values:
            continue
        field = mapping.get(kind)
        if field is None:
            continue
        fields[field] = max(fields[field], int(values[0]))
    return fields


def _score_from_row(name: str, table: CardTable) -> float:
    """卡面打分数值：卡表 ExamLesson（多段 count 要乘上）。"""
    row = table.get(name) or {}
    best = 0
    for effect in row.get("effects") or []:
        if effect.get("type") != "ExamLesson":
            continue
        values = [value for value in effect.get("values") or [] if value]
        if not values:
            continue
        count = int(effect.get("count") or 1)
        best = max(best, int(values[0]) * max(count, 1))
    return float(best)


def specs_from_hand(
    hand: Iterable[LessonCard], *, table: CardTable | None = None
) -> list[PlayCard]:
    """``LessonCard``（屏幕读数）→ ``PlayCard``（模拟用）。

    - 费用优先取卡表真值（卡面爱心小字 12px 常读歪），卡表没有才用屏幕费用；
    - 分数优先用屏幕宝石（含强化/等级的真实值），屏幕读不到再退回卡表；
    - buff/元气/抽牌等效果来自卡表；卡表查不到就只剩 ``name/score/cost`` 并标
      ``estimated=True``（期望分只是估计）。
    """
    table = table if table is not None else _default_table()
    cards = list(hand)
    result: list[PlayCard] = []
    for index, card in enumerate(cards):
        row = table.get(card.name) if card.name else None
        screen_cost = int(card.cost) if card.cost is not None else None
        if row is not None:
            table_cost = row.get("cost")
            cost = int(table_cost) if isinstance(table_cost, int) else (screen_cost or 3)
            screen_score = float(card.total_score)
            score = screen_score if screen_score > 0 else _score_from_row(card.name, table)
            spec = CardSpec(
                name=card.name,
                cost=cost,
                score=score,
                **_effect_fields(row),
            )
            estimated = False
        else:
            cost = screen_cost if screen_cost is not None else 3
            spec = CardSpec(
                name=card.name or f"card{index}",
                cost=cost,
                score=float(card.total_score),
            )
            estimated = True
        result.append(
            PlayCard(
                index=index,
                name=spec.name,
                cost=spec.cost,
                screen_score=float(card.total_score),
                spec=spec,
                point=tuple(card.point) if card.point is not None else None,
                estimated=estimated,
            )
        )
    return result


def _sim_config(
    turns_left: int,
    stamina: int,
    config: LessonConfig | None,
    *,
    kind: str | None = None,
) -> LessonConfig:
    """构造 rollout 配置：课程 1.0；``kind`` 是考试/舞台时用 411% 属性倍率。

    显式传入 ``config`` 时以它为准（调用方可以自己设 ``attribute_coefficient``）。
    """
    if config is not None:
        return config
    coefficient = (
        AUDITION_ATTRIBUTE_COEFFICIENT
        if kind is not None and kind.lower() in AUDITION_KINDS
        else 1.0
    )
    return LessonConfig(
        turns=max(int(turns_left), 1),
        stamina=max(int(stamina), 0),
        target_clear=1,  # 只比较总分，不关心 CLEAR/PERFECT 档位
        hand_size=DEFAULT_HAND_SIZE,
        attribute_coefficient=coefficient,
    )


def _deck_without_hand(deck: list[CardSpec] | None, hand: list[CardSpec]) -> list[CardSpec]:
    """把当前手牌从牌库里扣掉（它们已经在手上，不能再被抽到）。"""
    remaining = list(deck) if deck else list(hand)
    for card in hand:
        for index, item in enumerate(remaining):
            if item.name == card.name:
                remaining.pop(index)
                break
    return remaining or list(hand)


def _new_sim(
    hand_specs: list[CardSpec],
    *,
    deck: list[CardSpec] | None,
    config: LessonConfig,
    turns_left: int,
    stamina: int,
    seed: int,
) -> LessonSim:
    """构造与真机当前局面一致的模拟器：手牌/剩余回合/体力都对齐。"""
    sim = LessonSim(_deck_without_hand(deck, hand_specs), config, rng_seed=seed)
    sim.hand = list(hand_specs)
    sim.turns_left = max(int(turns_left), 1)
    sim.stamina = max(int(stamina), 0)
    sim.stamina_max = max(sim.stamina_max, sim.stamina)
    return sim


def _rollout_score(
    play_cards: list[PlayCard],
    candidate: PlayCard,
    *,
    deck: list[CardSpec] | None,
    config: LessonConfig,
    turns_left: int,
    stamina: int,
    seed: int,
) -> float | None:
    """先打 candidate，再按 greedy_policy 打完剩余回合，返回总分；非法/异常返回 None。"""
    hand_specs = [item.spec for item in play_cards]
    try:
        sim = _new_sim(
            hand_specs,
            deck=deck,
            config=config,
            turns_left=turns_left,
            stamina=stamina,
            seed=seed,
        )
        sim.step(candidate.index)
        if not sim.done:
            sim.run(greedy_policy)
    except (ValueError, RuntimeError, IndexError):
        return None
    return float(sim.score)


def estimate_hand(
    hand: Iterable[LessonCard],
    *,
    turns_left: int,
    stamina: int,
    deck: list[CardSpec] | None = None,
    config: LessonConfig | None = None,
    episodes: int = DEFAULT_EPISODES,
    time_budget_ms: int = DEFAULT_TIME_BUDGET_MS,
    table: CardTable | None = None,
    clock: Callable[[], float] = time.perf_counter,
    kind: str | None = None,
) -> list[CardEstimate]:
    """对每张手牌 rollout，返回可打出的牌的期望分（按手牌顺序，只含打得出的牌）。

    ``kind="audition"``（考试/舞台）时 rollout 用属性倍率 4.11；默认课程 1.0。
    """
    try:
        play_cards = specs_from_hand(hand, table=table)
    except Exception:  # noqa: BLE001 - 读牌失败不能把出牌搞崩
        return []
    if not play_cards:
        return []
    stamina = max(int(stamina), 0)
    turns_left = max(int(turns_left), 1)
    config = _sim_config(turns_left, stamina, config, kind=kind)
    playable = [card for card in play_cards if card.cost <= stamina]
    if not playable:
        return []

    totals = {card.index: 0.0 for card in playable}
    counts = {card.index: 0 for card in playable}
    budget_s = max(float(time_budget_ms), 0.0) / 1000.0
    deadline = clock() + budget_s
    aborted = False
    for episode in range(max(int(episodes), 1)):
        for card in playable:
            # 第一轮不查预算：保证每张牌至少一次，否则预算紧时永远只选第一张
            if episode > 0 and clock() >= deadline:
                aborted = True
                break
            score = _rollout_score(
                play_cards,
                card,
                deck=deck,
                config=config,
                turns_left=turns_left,
                stamina=stamina,
                seed=episode,
            )
            if score is None:
                continue
            totals[card.index] += score
            counts[card.index] += 1
        if aborted:
            break

    estimates: list[CardEstimate] = []
    for card in playable:
        ran = counts[card.index]
        if ran <= 0:
            continue
        estimates.append(
            CardEstimate(
                index=card.index,
                name=card.name,
                cost=card.cost,
                score=card.spec.score,
                expected=totals[card.index] / ran,
                episodes=ran,
                point=card.point,
                estimated=card.estimated,
            )
        )
    return estimates


def best_index(estimates: Iterable[CardEstimate]) -> int | None:
    """期望分最高的手牌下标（同分时优先白值高、下标小）。"""
    items = list(estimates)
    if not items:
        return None
    best = max(items, key=lambda item: (item.expected, item.score, -item.index))
    return best.index


def choose_card_via_sim(
    hand: Iterable[LessonCard],
    *,
    turns_left: int,
    stamina: int,
    deck: list[CardSpec] | None = None,
    config: LessonConfig | None = None,
    episodes: int = DEFAULT_EPISODES,
    time_budget_ms: int = DEFAULT_TIME_BUDGET_MS,
    table: CardTable | None = None,
    clock: Callable[[], float] = time.perf_counter,
    kind: str | None = None,
) -> int | None:
    """对每张手牌 rollout（打这张 + 剩余回合 greedily 打完），返回期望最高的下标。

    空手牌/一张都出不起/异常 → ``None``（调用方退回 ``LessonPolicy``）。
    超预算 anytime 返回当前最优。``kind="audition"`` 时按考试属性倍率（411%）算。
    """
    index, _estimates = plan_pick(
        hand,
        turns_left=turns_left,
        stamina=stamina,
        deck=deck,
        config=config,
        episodes=episodes,
        time_budget_ms=time_budget_ms,
        table=table,
        clock=clock,
        kind=kind,
    )
    return index


def plan_pick(
    hand: Iterable[LessonCard],
    *,
    turns_left: int,
    stamina: int,
    deck: list[CardSpec] | None = None,
    config: LessonConfig | None = None,
    episodes: int = DEFAULT_EPISODES,
    time_budget_ms: int = DEFAULT_TIME_BUDGET_MS,
    table: CardTable | None = None,
    clock: Callable[[], float] = time.perf_counter,
    kind: str | None = None,
) -> tuple[int | None, list[CardEstimate]]:
    """一次 rollout 同时拿到「选择下标 + 每张牌期望分」，供真机日志对比规则选择。

    ``choose_card_via_sim`` 是它的薄封装；任何异常都返回 ``(None, [])``。
    ``kind="audition"`` 时 rollout 走考试属性倍率（411%），默认课程 1.0。
    """
    try:
        estimates = estimate_hand(
            hand,
            turns_left=turns_left,
            stamina=stamina,
            deck=deck,
            config=config,
            episodes=episodes,
            time_budget_ms=time_budget_ms,
            table=table,
            clock=clock,
            kind=kind,
        )
    except Exception:  # noqa: BLE001 - 模拟器异常绝不能让出牌退化
        return None, []
    return best_index(estimates), estimates
