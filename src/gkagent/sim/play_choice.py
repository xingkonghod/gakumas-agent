"""实时出牌：用训练模拟器给每张手牌算期望分，选期望最高的那张打。

现有 ``LessonPolicy`` 是规则（分数÷体力、buff 优先、体力门）。这里对**每张手牌**做
K 次前瞻 rollout（PIMC / determinization）：先打这张牌，之后按 ``greedy_policy``
把剩余回合打完；K 次用**不同的未知牌序**，取期望分与标准差，选期望最高的那张打。
真机侧由 ``policy.json`` 的 ``produce.sim_play`` 开关（默认 false）。

**PIMC 采样（determinization）**：真机看不到牌库顺序，只能把已知手牌 + 调用方
见过的牌（``deck``）并成最多 ``MAX_APPROX_DECK`` 张近似牌库。每次 rollout 用
``seed + episode * 7919`` 重洗这个牌库——**只改顺序、不改组成**。第 0 次 rollout
就是基础 seed，SEED 相同 → 同一组牌序、结果完全可复现；K 越大平均越稳，所以
anytime 预算下 K 有边际收益（旧实现固定牌序时 K 再大期望分也不变）。

anytime：总预算 ``time_budget_ms`` 用完就返回当前最优；第一轮保证每张牌至少 1 次，
避免预算紧时永远只选第一张。拿到不完整牌组时用当前手牌近似牌库。

任何异常/空手牌/一张都出不起都返回 ``None``——调用方必须退回 ``LessonPolicy``，
不能让出牌因此退化。开关与日志样例见 ``scripts/auto_produce.py``。

**考试/舞台**：真机考试里每张牌的分数都吃屏幕上的属性倍率
（「歌唱 411%」= 4.11），训练里 ≈ 1.0。调用方已知当前是考试/舞台时传
``kind="audition"``：rollout 的 ``LessonConfig.attribute_coefficient`` 会设成
4.11，期望分与选择按考试口径算；不传 / ``kind="lesson"`` 仍按训练 1.0
（``kind="lesson"`` 是读屏层的旧 screen kind，保留不改；旧调用方行为不变）。
``config`` 显式传入时以 config 为准。
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from gkagent.sim.lesson import (
    AUDITION_ATTRIBUTE_COEFFICIENT,
    Buffs,
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
DEFAULT_SEED = 0
# PIMC 每次 rollout 的 seed 步长：第 e 次采样 = seed + e * 7919。
# 用质数步长把相邻 episode 的随机流错开，避免 e 和 e+1 洗出相近的牌序。
EPISODE_SEED_STRIDE = 7919
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
    """一张手牌的 PIMC rollout 结果。

    ``expected`` 是 K 次不同牌序的平均分，``stdev`` 是这 K 次样本的总体标准差
    （K=1 时为 0）。标准差大说明这张牌对未知牌序敏感，值得加预算多采样。
    """

    index: int
    name: str
    cost: int
    score: float
    expected: float
    episodes: int
    stdev: float = 0.0
    point: tuple[int, int] | None = None
    estimated: bool = False

    def __str__(self) -> str:
        suffix = "（卡表缺，按屏幕估）" if self.estimated else ""
        return (
            f"{self.name} ({self.score:.0f}分/{self.cost}费) "
            f"期望 {self.expected:.1f}±{self.stdev:.1f} (K={self.episodes}){suffix}"
        )


def _default_table() -> CardTable:
    from gkagent.data.card_table import CardTable

    return CardTable()


# `ExamLessonBuffDependParameterBuff` 的数值依赖「审查基准加成」层数，模拟器没有
# 这个状态，读不出真实好调回合数。但它是货真价实的好调牌（category=MentalSkill、
# tag 含 ExamLessonBuff），如果按 no-op 处理，PIMC 会把一张 0 分 buff 牌当成
# 「和空白牌完全一样」——同回合三张牌都打得完时，三个动作的期望分就会一模一样。
# 保守下限取 1 回合：好调只覆盖本回合后续牌，不虚构跨回合收益。
_DEPENDENT_BUFF_FLOOR = 1


def _effect_turns(effect: dict) -> int:
    """持续类效果的回合：``turn < 0`` = 永久（-1），否则至少 1 回合。"""
    turn = int(effect.get("turn") or 0)
    return -1 if turn < 0 else max(1, turn)


def _merge_effect_turns(current: int, new: int) -> int:
    """合并同类型持续效果的回合：任一永久则永久，否则取更长。"""
    if current < 0 or new < 0:
        return -1
    return max(current, new)


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
        # T5② 熱意（enthusiasm）：追加/増加是 buff（带回合），延長是回合数
        "enthusiasm_bonus": 0,
        "enthusiasm_bonus_turns": 0,
        "enthusiasm_multiple": 0,
        "enthusiasm_multiple_turns": 0,
        "enthusiasm_extension": 0,
        "enthusiasm_multiplier": 1000,
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
        if kind == "ExamLessonBuffDependParameterBuff":
            # 好调层数依赖 parameter buff，模拟器没有该状态：按下限 1 回合记。
            fields["condition"] = max(fields["condition"], _DEPENDENT_BUFF_FLOOR)
            continue
        if kind in ("ExamEnthusiasticAdditive", "ExamEnthusiasticMultiple"):
            # 熱意追加（加算）/ 熱意増加（千分比）：buff 持续回合来自 effect.turn
            field = (
                "enthusiasm_bonus"
                if kind == "ExamEnthusiasticAdditive"
                else "enthusiasm_multiple"
            )
            turns_field = f"{field}_turns"
            fields[field] = max(fields[field], int(values[0]))
            fields[turns_field] = _merge_effect_turns(
                fields[turns_field], _effect_turns(effect)
            )
            continue
        if kind == "ExamEnthusiasticTurnAdd":
            # 熱意延長：回合末不清零的回合数（直接累加）
            fields["enthusiasm_extension"] = max(
                fields["enthusiasm_extension"], int(values[0])
            )
            continue
        if kind == "ExamMultipleEnthusiasticLesson":
            # 本牌熱意適用倍数：values[1] = 追加千分比（1000 → ×2）
            if len(values) >= 2:
                fields["enthusiasm_multiplier"] = max(
                    fields["enthusiasm_multiplier"], 1000 + int(values[1])
                )
            continue
        field = mapping.get(kind)
        if field is None:
            continue
        fields[field] = max(fields[field], int(values[0]))
    return fields


def _score_from_row(name: str, table: CardTable) -> float:
    """卡面打分数值：卡表 ExamLesson（多段 count 要乘上）。

    ``ExamMultipleEnthusiasticLesson`` 的 ``values[0]`` 也是本牌直接打分加算
    （T5② 熱意適用倍数牌，如「手を伸ばした先に」），一并计入。
    """
    row = table.get(name) or {}
    best = 0
    for effect in row.get("effects") or []:
        kind = str(effect.get("type") or "")
        if kind not in ("ExamLesson", "ExamMultipleEnthusiasticLesson"):
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
                category=str(row.get("category") or ""),
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


def spec_from_name(name: str, table: CardTable | None = None) -> CardSpec | None:
    """卡名（卡表键，含强化变体）→ ``CardSpec``（卡表真值）。

    B10：P 道具生成卡（``ExamCardCreateId``）按 id 找到卡名后，用同一套
    ``_effect_fields`` 映射建牌（与出牌/牌组构建同口径）。卡表查不到 → None
    （调用方保守不生成，不猜卡面）。
    """
    if not name:
        return None
    table = table if table is not None else _default_table()
    row = table.get(name)
    if row is None:
        return None
    return CardSpec(
        name=name,
        cost=int(row.get("cost") or 0),
        score=_score_from_row(name, table),
        category=str(row.get("category") or ""),
        **_effect_fields(row),
    )


def _sim_config(
    turns_left: int,
    stamina: int,
    config: LessonConfig | None,
    *,
    kind: str | None = None,
    play_limit: int | None = None,
    target_clear: int | None = None,
    target_perfect: int | None = None,
) -> LessonConfig:
    """构造 rollout 配置：训练 1.0；``kind`` 是考试/舞台时用 411% 属性倍率。

    显式传入 ``config`` 时以它为准（调用方可以自己设 ``attribute_coefficient``），
    但本回合出牌上限 / 审查基准仍按显式参数覆盖，因为它们是**当前局面**的一部分。
    """
    if config is not None:
        return replace(
            config,
            turns=max(int(turns_left), 1),
            stamina=max(int(stamina), 0),
            plays_per_turn=(
                max(int(play_limit), 1)
                if play_limit is not None
                else config.plays_per_turn
            ),
            target_clear=(
                int(target_clear) if target_clear is not None else config.target_clear
            ),
            target_perfect=(
                int(target_perfect)
                if target_perfect is not None
                else config.target_perfect
            ),
        )
    coefficient = (
        AUDITION_ATTRIBUTE_COEFFICIENT
        if kind is not None and kind.lower() in AUDITION_KINDS
        else 1.0
    )
    return LessonConfig(
        turns=max(int(turns_left), 1),
        stamina=max(int(stamina), 0),
        target_clear=int(target_clear) if target_clear is not None else 1,
        target_perfect=(
            int(target_perfect) if target_perfect is not None else None
        ),
        hand_size=DEFAULT_HAND_SIZE,
        # 真机默认每回合 1 张（B3）；play_limit 只在当前局面显式覆盖时使用。
        plays_per_turn=max(int(play_limit), 1) if play_limit is not None else 1,
        attribute_coefficient=coefficient,
    )


def approx_deck(
    hand: Iterable[CardSpec], deck: Iterable[CardSpec] | None = None
) -> list[CardSpec]:
    """PIMC rollout 用的近似牌库：已知手牌 + 调用方见过的牌，去重、上限 12 张。

    真机拿不到完整牌组，只能把已知手牌和 ``deck``（``auto_produce`` 的
    ``sim_deck``：战斗里见过的牌）并成近似牌库。当前手牌已经拿在手上、不会再从
    牌库抽到同名的那一张，所以从结果里扣掉同名牌；扣完为空时退回手牌，保证模拟器
    还有牌可抽。``MAX_APPROX_DECK`` 是**可抽牌库**的上限（扣掉当前手牌之后），
    ``auto_produce`` 里 ``sim_deck`` 的 12 张上限管的是"见过的牌"池，两者不冲突。

    **组成固定**：所有 rollout 共用这一个牌库，采样只改顺序（见 ``_new_sim``），
    不会凭空生成牌，也不会在不同 episode 之间换牌。
    """
    known: list[CardSpec] = []
    seen: set[str] = set()
    for spec in [*hand, *(deck or ())]:
        if spec.name in seen:
            continue
        seen.add(spec.name)
        known.append(spec)

    remaining = list(known)
    for card in hand:
        for index, item in enumerate(remaining):
            if item.name == card.name:
                remaining.pop(index)
                break
    return remaining[:MAX_APPROX_DECK] or list(hand)[:MAX_APPROX_DECK]


def _new_sim(
    hand_specs: list[CardSpec],
    *,
    deck: list[CardSpec],
    config: LessonConfig,
    turns_left: int,
    stamina: int,
    seed: int,
    score: int = 0,
    buffs: Buffs | None = None,
    vitality: int = 0,
    plays_used: int = 0,
) -> LessonSim:
    """构造与真机当前局面一致的模拟器：手牌/剩余回合/体力/分数/buff 都对齐。

    PIMC determinization 在这里做：``LessonSim`` 构造时会先按 ``seed`` 洗一次牌并
    抽走一个假起手牌；``shuffle_deck`` 把完整牌库按同一个 ``seed`` 重新洗好、丢掉
    假起手牌，随后再放上真手牌。于是每个 ``seed`` 对应一个确定、不同的未知牌序，
    而牌库组成始终是 ``deck``（采样只改顺序）。

    **当前局面**（``score`` / ``buffs`` / ``vitality`` / ``plays_used``）必须显式写入
    模拟器：旧版只设 hand/turns/stamina，把已经打出的分数、好调/集中/好印象层数和
    本回合已用次数全部当成 0，rollout 的起点和真机不是同一个局面。
    """
    sim = LessonSim(deck, config, rng_seed=seed)
    sim.shuffle_deck(deck, seed=seed)
    sim.hand = list(hand_specs)
    sim.turns_left = max(int(turns_left), 1)
    sim.stamina = max(int(stamina), 0)
    sim.stamina_max = max(sim.stamina_max, sim.stamina)
    # 当前局面：这些都不是"0"——漏设会让所有候选 rollout 从同一起点开始
    sim.score = max(int(score), 0)
    if buffs is not None:
        sim.buffs = replace(buffs)
    sim.vitality = max(int(vitality), 0)
    sim.plays_this_turn = max(int(plays_used), 0)
    sim.extra_plays = 0
    return sim


def _rollout_score(
    play_cards: list[PlayCard],
    candidate: PlayCard,
    *,
    deck: list[CardSpec],
    config: LessonConfig,
    turns_left: int,
    stamina: int,
    seed: int,
    score: int = 0,
    buffs: Buffs | None = None,
    vitality: int = 0,
    plays_used: int = 0,
) -> float | None:
    """先打 candidate，再按 greedy_policy 打完剩余回合，返回**含当前分数**的总分；非法/异常返回 None。"""
    hand_specs = [item.spec for item in play_cards]
    try:
        sim = _new_sim(
            hand_specs,
            deck=deck,
            config=config,
            turns_left=turns_left,
            stamina=stamina,
            seed=seed,
            score=score,
            buffs=buffs,
            vitality=vitality,
            plays_used=plays_used,
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
    seed: int = DEFAULT_SEED,
    score: int = 0,
    buffs: Buffs | None = None,
    vitality: int = 0,
    plays_used: int = 0,
    play_limit: int | None = None,
    target_clear: int | None = None,
    target_perfect: int | None = None,
) -> list[CardEstimate]:
    """PIMC：每张手牌跑 K 次不同牌序的 rollout，返回期望分与标准差。

    第 ``episode`` 次 rollout 的牌序由 ``seed + episode * EPISODE_SEED_STRIDE``
    决定（只洗 ``approx_deck`` 的顺序，组成不变）：同一 ``seed`` 完全可复现，
    不同 ``seed`` / 不同 K 看到不同的未来抽牌。K 次平均即 PIMC 期望分，
    ``stdev`` 是 K 次样本的总体标准差（K=1 时为 0）。

    **当前局面必须传进来**：``score`` / ``buffs`` / ``vitality`` / ``plays_used``
    是 rollout 的起点；不传时是保守默认（0 分、无 buff、本回合未出牌），不是真机
    实际状态。``play_limit`` / ``target_clear`` / ``target_perfect`` 覆盖配置。

    ``kind="audition"``（考试/舞台）时 rollout 用属性倍率 4.11；默认训练 1.0。
    """
    try:
        play_cards = specs_from_hand(hand, table=table)
    except Exception:  # noqa: BLE001 - 读牌失败不能把出牌搞崩
        return []
    if not play_cards:
        return []
    stamina = max(int(stamina), 0)
    turns_left = max(int(turns_left), 1)
    vitality = max(int(vitality), 0)
    plays_used = max(int(plays_used), 0)
    config = _sim_config(
        turns_left,
        stamina,
        config,
        kind=kind,
        play_limit=play_limit,
        target_clear=target_clear,
        target_perfect=target_perfect,
    )
    limit = config.plays_per_turn
    if plays_used >= limit:
        return []  # 本回合已经出满，没有可评估的候选
    playable = [
        card for card in play_cards if card.cost <= stamina + vitality
    ]
    if not playable:
        return []

    # 近似牌库只建一次：K 次 rollout 的牌库组成完全相同，采样只改顺序
    rollout_deck = approx_deck([card.spec for card in play_cards], deck)
    scores: dict[int, list[float]] = {card.index: [] for card in playable}
    budget_s = max(float(time_budget_ms), 0.0) / 1000.0
    deadline = clock() + budget_s
    aborted = False
    for episode in range(max(int(episodes), 1)):
        episode_seed = int(seed) + episode * EPISODE_SEED_STRIDE
        for card in playable:
            # 第一轮不查预算：保证每张牌至少一次，否则预算紧时永远只选第一张
            if episode > 0 and clock() >= deadline:
                aborted = True
                break
            score_value = _rollout_score(
                play_cards,
                card,
                deck=rollout_deck,
                config=config,
                turns_left=turns_left,
                stamina=stamina,
                seed=episode_seed,
                score=score,
                buffs=buffs,
                vitality=vitality,
                plays_used=plays_used,
            )
            if score_value is None:
                continue
            scores[card.index].append(score_value)
        if aborted:
            break

    estimates: list[CardEstimate] = []
    for card in playable:
        samples = scores[card.index]
        if not samples:
            continue
        estimates.append(
            CardEstimate(
                index=card.index,
                name=card.name,
                cost=card.cost,
                score=card.spec.score,
                expected=statistics.fmean(samples),
                episodes=len(samples),
                stdev=statistics.pstdev(samples),
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
    seed: int = DEFAULT_SEED,
    score: int = 0,
    buffs: Buffs | None = None,
    vitality: int = 0,
    plays_used: int = 0,
    play_limit: int | None = None,
    target_clear: int | None = None,
    target_perfect: int | None = None,
) -> int | None:
    """对每张手牌做 K 次 PIMC rollout，返回期望最高的下标。

    空手牌/一张都出不起/异常 → ``None``（调用方退回 ``LessonPolicy``）。
    超预算 anytime 返回当前最优。``kind="audition"`` 时按考试属性倍率（411%）算。
    ``seed`` 决定 K 次采样的牌序（同一 seed 可复现），见 ``estimate_hand``。
    当前局面参数（score/buffs/vitality/plays_used/...）原样透传。
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
        seed=seed,
        score=score,
        buffs=buffs,
        vitality=vitality,
        plays_used=plays_used,
        play_limit=play_limit,
        target_clear=target_clear,
        target_perfect=target_perfect,
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
    seed: int = DEFAULT_SEED,
    score: int = 0,
    buffs: Buffs | None = None,
    vitality: int = 0,
    plays_used: int = 0,
    play_limit: int | None = None,
    target_clear: int | None = None,
    target_perfect: int | None = None,
) -> tuple[int | None, list[CardEstimate]]:
    """一次 PIMC 同时拿到「选择下标 + 每张牌期望分/标准差」，供真机日志对比规则选择。

    ``choose_card_via_sim`` 是它的薄封装；任何异常都返回 ``(None, [])``。
    ``kind="audition"`` 时 rollout 走考试属性倍率（411%），默认训练 1.0。
    ``seed`` 是采样牌序的基础种子：同 seed 同结果，不同 seed 换一组牌序。
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
            seed=seed,
            score=score,
            buffs=buffs,
            vitality=vitality,
            plays_used=plays_used,
            play_limit=play_limit,
            target_clear=target_clear,
            target_perfect=target_perfect,
        )
    except Exception:  # noqa: BLE001 - 模拟器异常绝不能让出牌退化
        return None, []
    return best_index(estimates), estimates
