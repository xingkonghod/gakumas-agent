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

**完全信息（考试牌序已破解）的两个可选输入**（默认都关闭，行为与旧版逐位一致）：

- ``ExpectState.known_draw``：已知的后续抽牌顺序（下标 0 = 下一张）。非空时抽牌机会
  节点退化成确定分支；与 ``deck`` 长度不一致（牌被效果移动过）时自动退回多重集期望。
- ``ExpectState.discard_order``：已知的**弃牌堆顺序**（进弃牌堆先后，旧 → 新）。
  ``None`` = 未知（默认，多重集语义）；``()`` = 已知为空。配合搜索入口的
  ``reshuffle`` 钩子（``Callable[[grave], list[CardSpec]]``，返回**洗后的抽牌顺序**）
  时，牌堆抽空后的重洗也是**确定分支**：新牌堆 = ``reshuffle(discard_order)``。
  钩子拿到的 grave 就是搜索自己模拟出来的弃牌顺序（调用方通常用
  ``ExamDrawOracle.reshuffle`` / ``reshuffle_from_sim`` 生成，纯函数、不推进 RNG）。

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

import logging
import math
import random
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, fields, replace
from dataclasses import field as dataclass_field
from functools import lru_cache
from typing import Any, Protocol

from gkagent.sim.enthusiasm import (
    enthusiasm_gain,
    release_on_stance_change,
    turn_end_enthusiasm,
)
from gkagent.sim.hold import HOLD_LIMIT, HOLD_SELECT_ZONES, hold_pick
from gkagent.sim.lesson import (
    Buffs,
    CardSpec,
    DrinkSpec,
    LessonConfig,
    LessonSim,
    greedy_policy,
    safe_ceil,
)
from gkagent.sim.p_items import (
    CARD_PLAY,
    EXAM_START,
    EXAM_START_AFTER,
    STAMINA_REDUCE,
    STANCE_CHANGE,
    STATUS_GAIN,
    STATUS_GAIN_INTERVAL,
    TURN_END,
    TURN_INTERVAL,
    TURN_START,
    TURN_START_AFTER,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    TimedAmounts,
    add_timed,
    apply_passive,
    intercept_debuff_entries,
    normalize_turns,
    tick_timed,
    timed_dict_add,
    timed_dict_tick,
    total_timed,
)
from gkagent.sim.stance import (
    Stance,
    StanceState,
    apply_full_power_point,
    card_stance_effect,
    end_turn,
    score_multiplier,
    stamina_cost_multiplier,
    stamina_pierce,
    stance_change_allowed,
)

__all__ = [
    "AnalyticLeafValue",
    "BeamResult",
    "ExpectState",
    "ExpectimaxConfig",
    "ExpectimaxResult",
    "LeafValue",
    "ReshuffleFn",
    "apply_card",
    "available_drinks",
    "best_turn_sequence",
    "effective_cost",
    "end_turn_state",
    "expected_tier_utility",
    "expectimax",
    "expectimax_action",
    "expectimax_value",
    "expectimax_with_stats",
    "fire_p_items",
    "is_legal",
    "legal_cards",
    "reshuffle_from_sim",
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

# 确定性重洗钩子：给「已知弃牌堆顺序」，返回重洗后的**抽牌顺序**（下标 0 = 牌堆顶）。
# 调用方负责保证不推进全局 RNG（如 ``ExamDrawOracle.reshuffle`` 用当前状态的副本）。
ReshuffleFn = Callable[[tuple[CardSpec, ...]], list[CardSpec]]


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
    # P1-1（2026-11-24）：保留区（held）。来源（holdCard/holdThisCard）留 P1-3；
    # 全力回合 moveHeldCardsToHand 回手钩子已实现（end_turn_state 进全力时回手）。
    held: tuple[CardSpec, ...] = ()
    # 全知牌序（完全信息搜索）：已知的后续抽牌顺序，下标 0 = 下一张抽到的牌。
    # 非空时要求它的多重集 == ``deck``；抽牌机会节点退化成确定分支。
    # 空 = 原来「只知多重集」的期望模型（默认，行为不变）。
    known_draw: tuple[CardSpec, ...] = ()
    # 已知弃牌堆顺序（进弃牌堆的先后，旧 → 新）；None = 顺序未知（默认多重集语义），
    # () = 已知为空。配合搜索的 ``reshuffle`` 钩子让重洗后的牌序也变成确定分支。
    discard_order: tuple[CardSpec, ...] | None = None
    stamina: int = 0
    stamina_max: int = 0
    vitality: int = 0
    score: int = 0
    turns_left: int = 1
    # 本课程总回合数（5/6/7/8 回合课的策略不同）；0 = 未知
    total_turns: int = 0
    plays_used: int = 0
    # 每回合基础可出牌次数：真机默认 1 张（B3 2026-11-22 按 gakumas-tools
    # TurnManager 的 cardUsesRemaining=1 + 真机 39 回合日志核实）；
    # ExamPlayableValueAdd 记在 extra_plays。
    play_limit: int = 1
    extra_plays: int = 0
    clear: int = 0
    perfect: int = 0
    condition_turns: int = 0
    # 绝好调 / 不调剩余回合（gakumas-tools 的 perfectConditionTurns / poorConditionTurns）
    perfect_condition_turns: int = 0
    poor_condition_turns: int = 0
    # メタモルフォーゼ："" | "performance"（披露 +25%）| "preparation"（支度 ×0.75）
    metamorphosis: str = ""
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
    # P1-1（2026-11-24）：のんびり预约 ((剩余次数, 是否温存中触发), …)；
    # のんびり→全力 的全体卡打分成长（永久加算，出牌加进白值）。
    leisure_reserves: tuple[tuple[int, bool], ...] = ()
    score_growth_all: int = 0
    # 温存期间已打出牌数：旧「温存解除≈好调回合」近似的状态位，T5② 起不再使用
    # （保留字段只为 B2 学习叶子 104 维特征的兼容，恒为 0；新训练应改用熱意特征）。
    save_cards_used: int = 0
    # T5② 2026-11-22 熱意（enthusiasm）：回合内分数资源（整数，获得时向上取整），
    # 出牌分加算；回合末归 0；有熱意延長时保留并 -1。温存解除给 5/8（见 sim/enthusiasm.py）。
    enthusiasm: int = 0
    enthusiasm_extension_turns: int = 0
    enthusiasm_bonus: int = 0
    enthusiasm_bonus_turns: int = 0
    enthusiasm_multiple: int = 0
    enthusiasm_multiple_turns: int = 0
    attribute_coefficient: float = 1.0
    hand_size: int = 3
    min_cost: int = 0
    # P 道具（被动）：状态里带着，出牌/回合事件会触发；数据来自 sim/p_items.py
    p_items: tuple[PItemSpec, ...] = ()
    p_item_uses: tuple[tuple[str, int], ...] = ()
    cards_played_total: int = 0
    # B8（2026-11-22）：P 道具条件/依赖换算用的本场累计量
    full_power_point_total: int = 0  # 累计全力值（「累计全力值的 N%」换算源）
    consumed_stamina_total: int = 0  # 累计消耗体力（「消耗过的体力的 N%」换算源）
    status_counts: tuple[tuple[str, int], ...] = ()  # 各状态累计增加次数
    # ---- B9（2026-11-22）：P 道具持久倍率 / modifier 状态（与 LessonSim 双镜）----
    # 分数上升量倍率：((千分比, 剩余回合), …)，-1 = 永久；参考引擎 resolveScore f/g。
    score_buffs: tuple[tuple[int, int], ...] = ()
    score_debuffs: tuple[tuple[int, int], ...] = ()
    # ---- P1-2（2026-11-24）：handDecrease 抽牌修正 / pride 自尊（与 LessonSim 双镜）----
    # 手牌减少：((减少量, 剩余回合), …)，-1 = 永久；回合开始抽牌
    # max(hand_size − Σ, 0)（参考 TurnManager.startTurn cardsToDraw）。
    hand_decreases: tuple[tuple[int, int], ...] = ()
    # 自尊剩余回合（prideTurns：回合末 -1；>0 时 resolveScore f 加算
    # min(min(好印象,干劲)×20, 500) 千分比）。
    pride_turns: int = 0
    # ---- P1-4（2026-11-24）：低下状态无效（nullifyDebuff，与 LessonSim 双镜）----
    # 消耗式计数器（无回合倒计时）；>0 时拦截 setScoreDebuff/setHandDecrease 施加。
    nullify_debuff: int = 0
    # ---- P1-3（2026-11-24）：指針固定（lockStanceTurns，与 LessonSim 双镜）----
    # >0 时禁切指針 + 全力进入门不满足；回合末 -1，fresh 保护（卡效果 0→正
    # 的当回合末不扣，锁下一回合；参考 Executor freshBuffs）。
    lock_stance_turns: int = 0
    lock_stance_fresh: bool = False
    # 其它持久倍率：((key, ((数值, 剩余回合), …)), …)，key 见 MODIFIER_TARGETS。
    # 用 tuple 存（canonical 要可哈希）；读取见 mod_total / gain_multiple。
    modifiers: tuple[tuple[str, TimedAmounts], ...] = ()
    # 费用修正：永久加减值 + 「接下来 N 回合」的 ×0.5 / ×2 计数器
    cost_reduction: int = 0
    cost_increase: int = 0
    half_cost_turns: int = 0
    double_cost_turns: int = 0
    # 回合追加（ExamExtraTurn）：pending 在 end_turn_state 里加到 turns_left；
    # granted 累计已追加回合数（effective total_turns = total_turns + granted）。
    extra_turns: int = 0
    extra_turns_granted: int = 0
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
    def turn_draw_count(self) -> int:
        """P1-2：下一回合开始抽牌数 = max(hand_size − Σ handDecrease, 0)
        （参考 TurnManager.startTurn cardsToDraw；卡效果抽牌不受影响）。"""
        return max(self.hand_size - total_timed(self.hand_decreases), 0)

    @property
    def current_turn(self) -> int:
        """当前是第几回合（1 起）；``total_turns`` 未知时返回 0。"""
        total = self.total_turns + self.extra_turns_granted
        if total <= 0 or self.turns_left <= 0:
            return 0
        return max(total - self.turns_left + 1, 1)

    # ---- B9：持久倍率 / modifier 读取 -------------------------------------
    def mod_total(self, key: str) -> int:
        """某个持久 modifier 渠道当前生效的合计值（千分比/次数）。"""
        for name, entries in self.modifiers:
            if name == key:
                return total_timed(entries)
        return 0

    def gain_multiple(self, key: str) -> float:
        """「X 增加量增加 +N%」类增益倍率（1.0 = 不变）。"""
        permil = self.mod_total(key)
        return 1.0 + permil / 1000.0 if permil else 1.0

    def with_modifiers(self, updates: Iterable[tuple[str, int, int]]) -> ExpectState:
        """把若干条 (key, 数值, 回合) 持久 mod 加进状态（copy-on-write）。"""
        table: dict[str, TimedAmounts] = dict(self.modifiers)
        for key, amount, turns in updates:
            table = timed_dict_add(table, key, amount, turns)
        return replace(self, modifiers=tuple(sorted(table.items())))

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

    def status_count(self, key: str) -> int:
        for status, count in self.status_counts:
            if status == key:
                return int(count)
        return 0

    def canonical(self) -> tuple[Any, ...]:
        """记忆化键：所有影响价值/合法动作的字段 + 多重集组成。"""
        return (
            _counts_key(self.hand),
            _counts_key(self.deck),
            # known_draw 的顺序会影响未来抽牌，所以按原样入键（不能只按多重集）
            self.known_draw,
            _counts_key(self.discard),
            # discard_order 的顺序决定重洗结果，也按原样入键（None/() 有区别）
            self.discard_order,
            _counts_key(self.excluded),
            # P1-1：保留区组成 / のんびり预约 / 全体卡打分成长（影响后续价值）
            _counts_key(self.held),
            self.leisure_reserves,
            self.score_growth_all,
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
            self.perfect_condition_turns,
            self.poor_condition_turns,
            self.metamorphosis,
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
            self.enthusiasm,
            self.enthusiasm_extension_turns,
            self.enthusiasm_bonus,
            self.enthusiasm_bonus_turns,
            self.enthusiasm_multiple,
            self.enthusiasm_multiple_turns,
            float(self.attribute_coefficient),
            self.hand_size,
            self.min_cost,
            self.p_item_uses,
            self.cards_played_total,
            self.full_power_point_total,
            self.consumed_stamina_total,
            self.status_counts,
            # B9：P 道具持久倍率 / modifier（全部影响后续价值/合法性）
            self.score_buffs,
            self.score_debuffs,
            # P1-2：手牌减少（影响后续抽牌）/ 自尊（影响后续算分）
            self.hand_decreases,
            self.pride_turns,
            # P1-4：低下状态无效（影响后续 debuff 施加）
            self.nullify_debuff,
            # P1-3：指針固定（影响后续指針切换/全力进入）
            self.lock_stance_turns,
            self.lock_stance_fresh,
            self.modifiers,
            self.cost_reduction,
            self.cost_increase,
            self.half_cost_turns,
            self.double_cost_turns,
            self.extra_turns,
            self.extra_turns_granted,
            self.drinks,
            self.drink_uses,
            self.drinks_used_this_turn,
            self.drinks_per_turn,
            self.card_uses,
        )


class LeafValue(Protocol):
    """叶子估值接口：``AnalyticLeafValue`` 与 ``v_leaf.LinearLeafValue`` 都实现它。

    搜索/beam 只调用 ``utility``；``predict`` 留作日志/诊断与契约的一部分。
    """

    def predict(self, state: ExpectState) -> tuple[float, float]:
        """返回未来得分的 (μ, σ)。"""
        ...

    def utility(self, state: ExpectState) -> float:
        """返回档位期望效用。"""
        ...


@dataclass(frozen=True)
class ExpectimaxConfig:
    """搜索/叶子估值参数（权重与 σ 都可从 policy 覆盖）。"""

    a_clear: float = 1.0
    a_perfect: float = 1.0
    sigma: float = DEFAULT_SIGMA
    draw_enum_limit: int = DEFAULT_DRAW_ENUM_LIMIT
    max_nodes: int = DEFAULT_MAX_NODES
    time_budget_ms: float | None = DEFAULT_TIME_BUDGET_MS
    # 是否把「喝饮料」纳入动作集合（default True；饮料为空时零开销）
    allow_drinks: bool = True


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
    # 最优动作是喝饮料时给出下标（与 card 互斥；card=None 且 drink=None 才是 SKIP）
    drink: int | None = None


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
    # 档位效用是**封顶**的（P(CLEAR)+P(PERFECT) ≤ 2）：深搜里大量"稳过"分支会打成
    # 平手，beam 的 plan 排序在平手时退化成枚举顺序，实测会偏好少打牌/存体力
    # （2026-11-21 T4 实验：小牌组 beam 87.9 → 加 tie-break 100.2）。
    # >0 时在效用上加一个极小的「预测总分」项，让平手按分数/进度排开；
    # 默认 0 = 历史行为完全不变（生产仍用 0，等配对评测达标再开）。
    score_tiebreak: float = 0.0

    def _tiebreak_bonus(self, projected: float, state: ExpectState) -> float:
        """平手用的极小分数项（无量纲：预测总分 / PERFECT 线）。"""
        if self.score_tiebreak <= 0.0:
            return 0.0
        scale = float(state.perfect if state.perfect > 0 else state.clear)
        if scale <= 0.0:
            return 0.0
        return float(self.score_tiebreak) * projected / scale

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
            base = (
                self.a_clear * (1.0 if projected >= state.clear else 0.0)
                + self.a_perfect * (1.0 if projected >= state.perfect else 0.0)
            )
            return base + self._tiebreak_bonus(projected, state)
        clear_gap = state.clear - state.score
        perfect_gap = state.perfect - state.score
        base = self.a_clear * _phi((mu - clear_gap) / sigma) + self.a_perfect * _phi(
            (mu - perfect_gap) / sigma
        )
        return base + self._tiebreak_bonus(projected, state)


# ---------------------------------------------------------------- rollout 叶子
# 背景（T4，2026-11-22）：解析式 V_leaf 的 μ 不准是 beam 的最大短板（真实小牌组
# beam 111.2 vs 回合内 expectimax 143.1）。这里做最小版「rollout 叶子」：
# 搜索叶子/beam 端点处用 LessonSim + greedy 把剩余回合快跑一遍，取最终分数增量
# 当 μ，用多次 rollout（牌序未知时）的标准差当 σ。先验准不准，再谈接进生产。
def _rollout_seed(state: ExpectState, index: int) -> int:
    """同一叶子 + 同一 rollout 编号 → 同一牌序（可复现，且各 rollout 不同）。"""
    return (hash(state.canonical()) & 0xFFFFFFFF) ^ (index * 0x9E3779B1)


def sim_from_state(
    state: ExpectState,
    *,
    rng: random.Random | None = None,
    plan: str = "sense",
) -> LessonSim:
    """把搜索里的纯 ``ExpectState`` 快照重建为可跑的 ``LessonSim``（rollout 用）。

    精度取舍（最小版）：
    - ``known_draw`` 已知 → 牌序 = ``reversed(known_draw)``（LessonSim 从尾部 pop）；
      未知 → 用 ``rng`` 洗牌，多次 rollout 取均值吸收牌序不确定性；
    - 搜索叶子常常已被 ``end_turn_state`` 清空手牌（它不抽下一手），这里按
      ``hand_size`` 从牌堆补一手，近似"下一回合开始"；
    - 除外区/P 道具/成长计数都从状态带过去，不丢机制。
    """
    deck_multiset = list(state.hand) + list(state.deck) + list(state.discard)
    config = LessonConfig(
        turns=max(int(state.total_turns), int(state.turns_left), 1),
        stamina=max(int(state.stamina_max), int(state.stamina), 1),
        target_clear=max(int(state.clear), 1),
        target_perfect=int(state.perfect) if state.perfect > 0 else None,
        hand_size=max(int(state.hand_size), 1),
        plays_per_turn=max(int(state.play_limit), 1),
        drinks=tuple(state.drinks),
        drinks_per_turn=state.drinks_per_turn,
        stamina_max=max(int(state.stamina_max), 1),
        attribute_coefficient=float(state.attribute_coefficient),
        plan=plan,
        p_items=tuple(state.p_items),
    )
    sim = LessonSim(deck_multiset, config, rng_seed=0 if rng is None else rng.randrange(1 << 30))
    # 牌序：全知时按已知顺序，否则本次 rollout 的随机牌序（构造器已洗过一次，
    # 这里统一再按 rng 洗，保证不同 rollout 的牌序确实不同）。
    if state.known_draw:
        sim.deck = list(reversed(state.known_draw))
    else:
        sim.deck = list(state.deck)
        if rng is not None:
            rng.shuffle(sim.deck)
    sim.discard = (
        list(state.discard_order) if state.discard_order is not None else list(state.discard)
    )
    sim.excluded = list(state.excluded)
    sim.hand = list(state.hand)
    # P1-1：保留区 / のんびり预约 / 全体卡打分成长（rollout 必须带上）
    sim.held = list(state.held)
    sim.leisure_reserves = [(int(count), bool(when_save)) for count, when_save in state.leisure_reserves]
    sim.score_growth_all = int(state.score_growth_all)
    if not sim.hand and int(state.turns_left) > 0:
        # P1-2：补手牌也按 cardsToDraw 口径扣掉 handDecrease
        sim._draw(max(config.hand_size - total_timed(state.hand_decreases), 0))
    sim.score = int(state.score)
    sim.stamina = int(state.stamina)
    sim.stamina_max = max(int(state.stamina_max), int(state.stamina), 1)
    sim.vitality = int(state.vitality)
    sim.motivation = int(state.motivation)
    sim.turn_parameter_buff = int(state.parameter_buff)
    sim.turns_left = max(int(state.turns_left), 0)
    sim.plays_this_turn = int(state.plays_used)
    sim.extra_plays = int(state.extra_plays)
    sim.drinks_used_this_turn = int(state.drinks_used_this_turn)
    if state.drink_uses:
        sim.drink_uses = [int(use) for use in state.drink_uses]
        while len(sim.drink_uses) < len(config.drinks):
            sim.drink_uses.append(0)
    sim.cards_played_total = int(state.cards_played_total)
    # B8：累计量 / 状态增加次数（P 道具条件/依赖换算用）
    sim.full_power_point_total = int(state.full_power_point_total)
    sim.consumed_stamina_total = int(state.consumed_stamina_total)
    sim.status_gain_counts = {key: int(count) for key, count in state.status_counts}
    # B9：持久倍率 / modifier（rollout 必须带上，否则叶子估值少算 buff）
    sim.score_buffs = tuple(state.score_buffs)
    sim.score_debuffs = tuple(state.score_debuffs)
    # P1-2：手牌减少 / 自尊（rollout 必须带上，否则抽牌数/算分与搜索不一致）
    sim.hand_decreases = tuple(state.hand_decreases)
    sim.pride_turns = int(state.pride_turns)
    # P1-4：低下状态无效（rollout 必须带上，否则 debuff 拦截与搜索不一致）
    sim.nullify_debuff = int(state.nullify_debuff)
    # P1-3：指針固定（rollout 必须带上，否则指針守卫/全力进入与搜索不一致）
    sim.lock_stance_turns = int(state.lock_stance_turns)
    sim._lock_stance_fresh = bool(state.lock_stance_fresh)
    sim.modifiers = {key: tuple(entries) for key, entries in state.modifiers}
    sim.cost_reduction = int(state.cost_reduction)
    sim.cost_increase = int(state.cost_increase)
    sim.half_cost_turns = int(state.half_cost_turns)
    sim.double_cost_turns = int(state.double_cost_turns)
    sim.extra_turns_pending = int(state.extra_turns)
    sim.extra_turns_granted = int(state.extra_turns_granted)
    sim.enthusiasm = int(state.enthusiasm)
    sim.enthusiasm_extension_turns = int(state.enthusiasm_extension_turns)
    sim.buffs = Buffs(
        condition_turns=int(state.condition_turns),
        perfect_condition_turns=int(state.perfect_condition_turns),
        poor_condition_turns=int(state.poor_condition_turns),
        metamorphosis=str(state.metamorphosis or ""),
        focus=int(state.focus),
        impression=int(state.impression),
        condition_additive=int(state.condition_additive),
        condition_additive_turns=int(state.condition_additive_turns),
        review_multiple=int(state.review_multiple),
        review_multiple_turns=int(state.review_multiple_turns),
        full_power_lesson_multiple=int(state.full_power_lesson_multiple),
        full_power_lesson_multiple_turns=int(state.full_power_lesson_multiple_turns),
        enthusiasm_bonus=int(state.enthusiasm_bonus),
        enthusiasm_bonus_turns=int(state.enthusiasm_bonus_turns),
        enthusiasm_multiple=int(state.enthusiasm_multiple),
        enthusiasm_multiple_turns=int(state.enthusiasm_multiple_turns),
    )
    stance, strong_level, save_level, full_power_point = state.stance
    sim.stance = StanceState(
        stance=stance,
        strong_level=int(strong_level),
        save_level=int(save_level),
        full_power_point=int(full_power_point),
    )
    for card in (*sim.hand, *sim.deck, *sim.discard, *sim.excluded):
        uses = int(state.uses_of(card.name))
        if uses > 0:
            sim.card_uses[id(card)] = uses
    sim.p_item_uses = {name: int(count) for name, count in state.p_item_uses}
    sim._min_cost = min(
        (int(card.cost) for card in (*sim.hand, *sim.deck, *sim.discard, *sim.excluded)),
        default=0,
    )
    return sim


@dataclass(frozen=True)
class RolloutLeafValue:
    """rollout 叶子估值：用 ``LessonSim`` + greedy 快跑剩余回合，替代解析式 μ。

    ``predict`` 返回未来得分增量的 ``(μ, σ)``：
    - μ = 若干次 rollout 的最终分数增量均值；
    - σ = max(``sigma``, 实测标准差)，避免牌序全知时退化成硬阈值。

    ``utility`` 的档位公式与 ``AnalyticLeafValue`` 一致（CLEAR/PERFECT 正态 cdf）。
    ``rollouts`` 只影响精度/耗时；牌序未知时建议 ≥3。
    """

    sigma: float = DEFAULT_SIGMA
    a_clear: float = 1.0
    a_perfect: float = 1.0
    score_tiebreak: float = 0.0
    rollouts: int = 3
    plan: str = "sense"
    # rollout 内部用的策略：greedy=卡面分数/费用基线；within=每回合小预算 expectimax
    # （强但慢，用于验证“叶子估值要跟执行策略同强度”这个假设）。
    policy: str = "greedy"
    rollout_budget_ms: float = 5.0
    # 叶子会被搜索反复问同一个状态：缓存 canonical → (μ, σ)，避免重复 rollout。
    _cache: dict[tuple[Any, ...], tuple[float, float]] = dataclass_field(
        default_factory=dict, compare=False, repr=False
    )

    def _tiebreak_bonus(self, projected: float, state: ExpectState) -> float:
        if self.score_tiebreak <= 0.0:
            return 0.0
        scale = float(state.perfect if state.perfect > 0 else state.clear)
        if scale <= 0.0:
            return 0.0
        return float(self.score_tiebreak) * projected / scale

    def _rollout_score(self, sim: LessonSim) -> float:
        """把一局（快照）跑完，返回最终分数。"""
        if self.policy != "within":
            final, _ = sim.run(greedy_policy)
            return float(final)
        flat = AnalyticLeafValue(sigma=self.sigma, a_clear=self.a_clear, a_perfect=self.a_perfect)
        while not sim.done:
            actions = sim.legal_actions()
            if actions == [None]:
                sim.step(None)
                continue
            state = state_from_sim(sim, known_deck_order=True)
            result = expectimax_with_stats(
                state, flat, time_budget_ms=self.rollout_budget_ms
            )
            index = None
            if result.card is not None:
                index = next(
                    (i for i, card in enumerate(sim.hand) if card == result.card), None
                )
            if index is None:
                index = greedy_policy(sim)
            if index is None:
                break
            sim.step(index)
        return float(sim.score)

    def _samples(self, state: ExpectState) -> list[float]:
        count = max(int(self.rollouts), 1)
        samples: list[float] = []
        for index in range(count):
            rng = random.Random(_rollout_seed(state, index))
            try:
                sim = sim_from_state(state, rng=rng, plan=self.plan)
                final = self._rollout_score(sim)
            except Exception as exc:  # noqa: BLE001 - rollout 是估值，失败不能拖垮搜索
                logging.getLogger(__name__).warning("rollout 叶子失败：%s", exc)
                break
            samples.append(final - float(state.score))
        return samples

    def predict(self, state: ExpectState) -> tuple[float, float]:
        if state.turns_left <= 0:
            return 0.0, 0.0
        cache_key = state.canonical()
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        samples = self._samples(state)
        if not samples:
            mu = 0.0
            sigma = max(float(self.sigma), 0.0)
        else:
            mu = sum(samples) / len(samples)
            if len(samples) > 1:
                variance = sum((value - mu) ** 2 for value in samples) / (len(samples) - 1)
                measured = math.sqrt(max(variance, 0.0))
            else:
                measured = 0.0
            sigma = max(float(self.sigma), measured)
        result = (max(mu, 0.0), sigma)
        if len(self._cache) < 8192:
            self._cache[cache_key] = result
        return result

    def utility(self, state: ExpectState) -> float:
        """E[档位效用] = a·P(score ≥ CLEAR) + b·P(score ≥ PERFECT)。"""
        if state.clear <= 0:
            return 0.0
        mu, sigma = self.predict(state)
        projected = state.score + mu
        if sigma <= 0:
            base = (
                self.a_clear * (1.0 if projected >= state.clear else 0.0)
                + self.a_perfect * (1.0 if projected >= state.perfect else 0.0)
            )
            return base + self._tiebreak_bonus(projected, state)
        clear_gap = state.clear - state.score
        perfect_gap = state.perfect - state.score
        base = self.a_clear * _phi((mu - clear_gap) / sigma) + self.a_perfect * _phi(
            (mu - perfect_gap) / sigma
        )
        return base + self._tiebreak_bonus(projected, state)


def expected_tier_utility(
    state: ExpectState,
    outcomes: Mapping[int, float],
    *,
    value: LeafValue | None = None,
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
    """实际牌费（与 LessonSim._effective_cost 同式：指針 × 费用增减回合，
    取整后加减固定费用、夹到 ≥0）。"""
    multiplier = stamina_cost_multiplier(state.stance_state)
    if state.half_cost_turns > 0:
        multiplier *= 0.5
    if state.double_cost_turns > 0:
        multiplier *= 2.0
    if multiplier == 1.0:
        cost = int(card.cost)
    else:
        cost = math.ceil(card.cost * multiplier)
    cost = cost - int(state.cost_reduction) + int(state.cost_increase)
    return max(cost, 0)


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


def _drink_worth_expanding(state: ExpectState, drink: DrinkSpec) -> bool:
    """饮料动作剪枝：只在「能提升本回合后续得分」时展开。

    理由：饮料不占出牌次数，但每展开一个饮料分支就多一层递归；大多数时候
    （没有后续可打分牌/体力本来够）喝不喝对档位效用几乎无差。只保留：
    - score 饮料：直接加分，总值得算；
    - focus/condition：本回合还有出牌位且有正分牌；
    - stamina：本回合有出牌位、且有正分牌当前付不起（喝了才解锁）。
    这样分支数从「每节点 × 库存瓶数」降到通常 0–1 个。
    """
    if state.plays_left <= 0:
        return drink.effect_type == "score"
    score_cards = [card for card in state.hand if card.score > 0]
    if drink.effect_type == "score":
        return True
    if not score_cards:
        return False
    if drink.effect_type in ("focus", "condition"):
        return True
    if drink.effect_type == "stamina":
        available = state.total_cost_available
        return any(effective_cost(state, card) > available for card in score_cards)
    return False


def _candidate_drinks(state: ExpectState) -> list[int]:
    """返回本状态最多 1 个值得展开的饮料下标（控制分支数）。

    优先级：能解锁当前付不起的正分牌的 stamina → 有正分牌时的 focus/condition
    → score（任意时候都直接加分）。同一状态不把所有库存都展开；每回合仍可
    在不同节点各喝一瓶（受 ``drinks_per_turn``/库存限制）。
    """
    useful: list[tuple[int, int]] = []
    for index in available_drinks(state):
        drink = state.drinks[index]
        if not _drink_worth_expanding(state, drink):
            continue
        priority = 0
        if drink.effect_type == "stamina":
            priority = 3
        elif drink.effect_type in ("focus", "condition"):
            priority = 2
        elif drink.effect_type == "score":
            priority = 1
        useful.append((priority, index))
    if not useful:
        return []
    useful.sort(key=lambda item: (-item[0], item[1]))
    return [useful[0][1]]


def use_drink_state(state: ExpectState, index: int) -> ExpectState:
    """喝一瓶饮料，返回新状态（与 ``LessonSim.use_drink`` 同语义）。

    饮料不占本回合出牌次数；饮品槽/次数进 ``ExpectState``，expectimax 会把
    「喝饮料」作为与打牌并列的动作（`ExpectimaxConfig.allow_drinks`），受库存和
    ``drinks_per_turn`` 限制。
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
        # 熱意追加是加算层数、熱意延長是回合数：再演执行两次 → 数值翻倍
        enthusiasm_bonus=card.enthusiasm_bonus * 2,
        enthusiasm_extension=card.enthusiasm_extension * 2,
        # P1-2：自尊回合数是直接效果（prideTurns+=N），再演同样翻倍
        pride_turns=card.pride_turns * 2,
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
    base_score = card.score + state.score_growth_all
    if base_score > 0 and card.grow_score > 0 and uses > 0:
        base_score = base_score * (100 + uses * card.grow_score) / 100
    if base_score > 0:
        # 与 LessonSim._card_award 同一口径（对照 gakumas-tools resolveScore）：
        #   好调 = 1 + (0.5 + 绝好调 ? 好调回合数×0.1 : 0)；メタモルフォーゼ
        #   披露 +25% / 支度 ×0.75；不调 ×0.67。
        if state.condition_turns > 0:
            condition_bonus = 0.5
            if state.perfect_condition_turns > 0:
                condition_bonus += 0.1 * state.condition_turns
            multiplier = 1.0 + condition_bonus
        else:
            multiplier = 1.0
        # 熱意（T5②）：集中加算之后、好调/指針倍率之前加进白值
        # （参考引擎 resolveScore b；与 LessonSim._card_award 同口径，含本牌適用倍数）。
        enthusiasm_score = state.enthusiasm * card.enthusiasm_multiplier / 1000.0
        # B9：集中强化（ExamLessonBuffMultiple）→ 集中贡献 ×(1+N%)
        focus_score = state.focus * state.gain_multiple("concentration_effect")
        raw = (
            (base_score + focus_score + enthusiasm_score)
            * multiplier
            * score_multiplier(state.stance_state)
        )
        if state.metamorphosis == "performance":
            raw *= 1.25
        # B9：P 道具持久分数倍率（参考引擎 resolveScore f/g；与 LessonSim 同口径）
        score_buff = total_timed(state.score_buffs)
        # P1-2：自尊 pride（resolveScore f，与 LessonSim._card_award 同口径）
        if state.pride_turns > 0:
            score_buff += min(min(state.impression, state.motivation) * 20, 500)
        if score_buff:
            raw *= 1.0 + score_buff / 1000.0
        score_debuff = total_timed(state.score_debuffs)
        if score_debuff:
            raw *= max(1.0 - score_debuff / 1000.0, 0.0)
        if state.metamorphosis == "preparation":
            raw *= 0.75
        if state.poor_condition_turns > 0:
            raw *= 0.67
        # 与 LessonSim 同口径：buff 段 ceil 一次，回合属性倍率乘完再 ceil（参考
        # 引擎 resolveScore 的 safeCeil；B3 2026-11-22 用实机回放黄金值核对）。
        award = safe_ceil(raw)
        if state.attribute_coefficient != 1.0:
            award = safe_ceil(award * state.attribute_coefficient)
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
    previous_stance = state.stance_state
    cost = effective_cost(state, played)
    stamina_before_cost = state.stamina
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
    # B8：本场累计消耗体力 + 「花费值使体力减少时」事件（与 LessonSim 同口径）
    stamina_lost = stamina_before_cost - state.stamina
    if stamina_lost > 0:
        state = replace(
            state, consumed_stamina_total=state.consumed_stamina_total + stamina_lost
        )
        state = fire_p_items(state, STAMINA_REDUCE, stamina_delta=stamina_lost)
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
    # 熱意系（T5②）：追加=加算 buff、増加=千分比 buff、延長=回合数
    if effect_card.enthusiasm_bonus > 0:
        state = replace(
            state,
            enthusiasm_bonus=max(state.enthusiasm_bonus, effect_card.enthusiasm_bonus),
            enthusiasm_bonus_turns=_merge_turns(
                state.enthusiasm_bonus_turns,
                effect_card.enthusiasm_bonus_turns
                if effect_card.enthusiasm_bonus_turns
                else 1,
            ),
        )
    if effect_card.enthusiasm_multiple > 0:
        state = replace(
            state,
            enthusiasm_multiple=max(
                state.enthusiasm_multiple, effect_card.enthusiasm_multiple
            ),
            enthusiasm_multiple_turns=_merge_turns(
                state.enthusiasm_multiple_turns,
                effect_card.enthusiasm_multiple_turns
                if effect_card.enthusiasm_multiple_turns
                else 1,
            ),
        )
    if effect_card.enthusiasm_extension > 0:
        state = replace(
            state,
            enthusiasm_extension_turns=state.enthusiasm_extension_turns
            + effect_card.enthusiasm_extension,
        )
    # P1-2：自尊（与 LessonSim._apply_card_buffs 同口径）——出牌前干劲达到
    # 门槛才给 prideTurns（参考 if:motivation>=9；本牌干劲加成在之后才生效）。
    if effect_card.pride_turns > 0 and state.motivation >= effect_card.pride_min_motivation:
        state = replace(state, pride_turns=state.pride_turns + effect_card.pride_turns)
    # P1-3：指針固定守卫取**本牌 lock 应用前**的值（与 LessonSim._apply_card_stance
    # 同口径：本牌自己的锁不挡自己的指針变更；DSL 里 lockStanceTurns 在指針动作之后）。
    locked = state.lock_stance_turns > 0
    # P1-3：指針固定（StanceLock ↔ lockStanceTurns+=N；0→正 打 fresh 标记，
    # 获得当回合末不扣）。
    if effect_card.lock_stance_turns > 0:
        state = replace(
            state,
            lock_stance_turns=state.lock_stance_turns + effect_card.lock_stance_turns,
            lock_stance_fresh=state.lock_stance_fresh or state.lock_stance_turns == 0,
        )
    condition_gain = effect_card.condition
    if condition_gain > 0 and state.condition_additive > 0:
        condition_gain += state.condition_additive
    vitality_gain = effect_card.vitality + state.motivation
    # B9：P 道具「X 增加量增加 +N%」增益倍率（乘在获得量上、向上取整；与
    # LessonSim._apply_card_buffs 同口径）
    focus_gain = effect_card.focus
    if focus_gain > 0:
        focus_gain = safe_ceil(focus_gain * state.gain_multiple("concentration_gain"))
    impression_gain = effect_card.impression
    if impression_gain > 0:
        impression_gain = safe_ceil(
            impression_gain * state.gain_multiple("impression_gain")
        )
    motivation_gain = effect_card.motivation
    if motivation_gain > 0:
        motivation_gain = safe_ceil(
            motivation_gain * state.gain_multiple("motivation_gain")
        )
    state = replace(
        state,
        condition_turns=state.condition_turns + condition_gain,
        focus=state.focus + focus_gain,
        impression=state.impression + impression_gain,
        vitality=state.vitality + vitality_gain,
        motivation=state.motivation + motivation_gain,
        extra_plays=state.extra_plays + effect_card.extra_play,
        plays_used=state.plays_used + 1,
    )
    stance = state.stance_state
    full_power_gain = effect_card.full_power_point
    if full_power_gain > 0:
        full_power_gain = safe_ceil(
            full_power_gain * state.gain_multiple("full_power_charge")
        )
        stance = apply_full_power_point(stance, full_power_gain)
        state = replace(
            state,
            full_power_point_total=state.full_power_point_total + full_power_gain,
        )
    if effect_card.strong_level > 0 and stance_change_allowed(
        stance, "concentration", locked=locked
    ):
        delta = card_stance_effect("ExamConcentration", [effect_card.strong_level])
        if delta["stance"] is not None:
            stance = replace(
                stance,
                stance=delta["stance"],
                strong_level=effect_card.strong_level,
                save_level=0,
            )
    if effect_card.preservation > 0 and stance_change_allowed(
        stance, "preservation", locked=locked
    ):
        delta = card_stance_effect("ExamPreservation", [effect_card.preservation])
        if delta["stance"] is not None:
            stance = replace(
                stance,
                stance=delta["stance"],
                strong_level=0,
                save_level=max(stance.save_level, int(delta["save_level"])),
            )
    # P1-1：のんびり预约登记（与 LessonSim._apply_card_stance 同口径；encore 不翻倍）
    if effect_card.leisure_reserve != 0:
        state = replace(
            state,
            leisure_reserves=state.leisure_reserves
            + ((int(effect_card.leisure_reserve), bool(effect_card.leisure_reserve_when_save)),),
        )
    state = state.with_stance(stance)
    # B8：指針变化事件（强气/温存/全力切换）；本牌结算后的新指針已经可见。
    if stance != previous_stance:
        state = fire_p_items(state, STANCE_CHANGE)
    # P 道具：获得层数时（status_gain）
    if condition_gain > 0:
        state = fire_p_items(
            state, STATUS_GAIN, status="parameter_buff", amount=condition_gain
        )
    if focus_gain > 0:
        state = fire_p_items(state, STATUS_GAIN, status="focus", amount=focus_gain)
    if impression_gain > 0:
        state = fire_p_items(
            state,
            STATUS_GAIN,
            status="impression",
            amount=impression_gain,
        )
    if effect_card.vitality > 0:
        state = fire_p_items(
            state, STATUS_GAIN, status="vitality", amount=vitality_gain
        )
    if motivation_gain > 0:
        state = fire_p_items(
            state,
            STATUS_GAIN,
            status="aggressive",
            amount=motivation_gain,
        )
    if full_power_gain > 0:
        state = fire_p_items(
            state,
            STATUS_GAIN,
            status="full_power_point",
            amount=full_power_gain,
        )
    # 温存/のんびり解除（参考引擎 STANCE_CHANGED_EFFECTS）：熱意 +5/+8/+10、
    # 固定元気 +5、当回合出牌次数 +1、のんびり→全力全体卡打分成长 +10。
    # _apply_card_effects 只看本牌结算前后指針（中间切换不可见）。
    release_enthusiasm, release_genki, release_plays, release_growth = (
        release_on_stance_change(previous_stance, stance)
    )
    if release_enthusiasm or release_genki or release_plays or release_growth:
        state = replace(
            state,
            enthusiasm=state.enthusiasm
            + enthusiasm_gain(
                release_enthusiasm,
                bonus=state.enthusiasm_bonus,
                multiple_permil=state.enthusiasm_multiple,
            ),
            # 固定元気：不吃「やる気」加成（参考引擎 resolveFixedGenki）
            vitality=state.vitality + release_genki,
            extra_plays=state.extra_plays + release_plays,
            score_growth_all=state.score_growth_all + release_growth,
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


def _discard_push(state: ExpectState, card: CardSpec) -> ExpectState:
    """一张牌进弃牌堆：多重集 + 已知顺序（顺序未知时保持 ``None``）。"""
    order = state.discard_order
    return replace(
        state,
        discard=state.discard + (card,),
        discard_order=None if order is None else order + (card,),
    )


def _remove_first(zone: tuple[CardSpec, ...], card: CardSpec) -> tuple[CardSpec, ...]:
    """从区域多重集移除第一张相等牌（值相等口径，与 LessonSim list.remove 一致）。"""
    cards = list(zone)
    cards.remove(card)
    return tuple(cards)


def _apply_hold_state(state: ExpectState, played: CardSpec) -> tuple[ExpectState, bool]:
    """P1-3：保留区结算（ExpectState 纯函数版，双镜 ``LessonSim._apply_hold``）。

    调用时打出的牌已不在 ``state.hand``（与 LessonSim.step 先 pop 同口径）。
    holdThisCard 条件用**当前指針**（本牌结算后、出牌后 P 道具触发前——参考
    processCard 阶段求值，afterCardUsed 之前）。holdSelected 从目标区按白值分
    降序确定性选牌（``hold.hold_pick``）；移入后 enforceHoldLimit（上限 2，
    最旧进弃牌堆，``discard_order`` 同步）。从牌堆移牌同步 ``known_draw``
    （牌堆顺序 = reversed(known_draw)，移除牌堆首张相等 = 移除 known_draw
    末张相等）；从弃牌堆移牌同步 ``discard_order``（首张相等）。
    返回 ``(新状态, 本牌是否被 holdThisCard 保留)``。
    """
    held_this = False
    held = state.held
    discard = state.discard
    discard_order = state.discard_order
    hand = state.hand
    deck = state.deck
    known_draw = state.known_draw

    def enforce_limit() -> None:
        nonlocal held, discard, discard_order
        while len(held) > HOLD_LIMIT:
            oldest = held[0]
            held = held[1:]
            discard = discard + (oldest,)
            if discard_order is not None:
                discard_order = discard_order + (oldest,)

    if played.hold_this and (
        not played.hold_this_when_save
        or str(state.stance_state.stance) == Stance.SAVE
    ):
        held = held + (played,)
        enforce_limit()
        held_this = True
    if played.hold_select_zones:
        zone_names = HOLD_SELECT_ZONES[played.hold_select_zones]
        pools = {"hand": hand, "deck": deck, "discard": discard}
        candidates = [c for zone in zone_names for c in pools[zone]]
        for picked in hold_pick(candidates, played.hold_select_count):
            for zone in zone_names:
                if picked in pools[zone]:
                    if zone == "hand":
                        hand = _remove_first(hand, picked)
                    elif zone == "deck":
                        deck = _remove_first(deck, picked)
                        if known_draw:
                            # 牌堆首张相等 = known_draw 末张相等（reversed 对应）
                            drawn = list(known_draw)
                            drawn.reverse()
                            drawn.remove(picked)
                            drawn.reverse()
                            known_draw = tuple(drawn)
                    else:
                        discard = _remove_first(discard, picked)
                        if discard_order is not None:
                            discard_order = _remove_first(discard_order, picked)
                    break
            held = held + (picked,)
        enforce_limit()
    if played.hold_move_to_hand:
        # moveHeldCardsToHand：LIFO 回手（参考 pop()），无手牌上限检查
        hand = hand + tuple(reversed(held))
        held = ()
    return (
        replace(
            state,
            hand=hand,
            deck=deck,
            discard=discard,
            held=held,
            known_draw=known_draw,
            discard_order=discard_order,
        ),
        held_this,
    )


def _reshuffle_successor(
    state: ExpectState, need: int, reshuffle: ReshuffleFn | None
) -> ExpectState | None:
    """牌堆空时用「已知弃牌顺序 + 确定性重洗钩子」抽 ``need`` 张；信息不足返回 None。

    要求 ``discard_order`` 与 ``discard`` 多重集一致（不一致 = 搜索模拟的弃牌堆和
    真实线不同，钩子的结果不再可信），钩子返回的牌堆多重集也必须等于弃牌堆。
    """
    order = state.discard_order
    if reshuffle is None or order is None or not state.discard:
        return None
    if Counter(order) != Counter(state.discard):
        return None
    reshuffled = tuple(reshuffle(tuple(order)))
    if Counter(reshuffled) != Counter(state.discard):
        return None
    take = min(max(int(need), 0), len(reshuffled))
    remaining = reshuffled[take:]
    return replace(
        state,
        hand=state.hand + reshuffled[:take],
        deck=remaining,
        known_draw=remaining,
        discard=(),
        discard_order=(),
    )


def _draw_distribution(
    state: ExpectState,
    count: int,
    *,
    enum_limit: int = DEFAULT_DRAW_ENUM_LIMIT,
    reshuffle: ReshuffleFn | None = None,
) -> list[tuple[float, ExpectState]]:
    """抽 ``count`` 张牌的精确机会节点 ``[(概率, 后继状态)]``。

    ``state.known_draw`` 非空（完全信息搜索）时退化成**确定分支**：按已知顺序取前
    ``count`` 张；已知段不够、牌堆抽空时：若给了确定性重洗钩子（``reshuffle``）且
    ``discard_order`` 已知，就用钩子把弃牌堆洗成已知牌堆继续抽（重洗后段也全知）；
    否则这一段退回多重集期望。``known_draw`` 与 ``deck`` 长度不一致时也退回期望模型
    （防御：牌被效果移动过，已知顺序已失效）。
    """
    if count <= 0:
        return [(1.0, state)]
    if reshuffle is not None and not state.deck:
        exact = _reshuffle_successor(state, count, reshuffle)
        if exact is not None:
            return [(1.0, exact)]
    known = state.known_draw
    if known and len(known) == len(state.deck):
        take = min(count, len(known))
        drawn = known[:take]
        remaining = known[take:]
        base = replace(
            state,
            hand=state.hand + drawn,
            deck=remaining,
            known_draw=remaining,
        )
        if count <= take:
            return [(1.0, base)]
        exact = _reshuffle_successor(base, count - take, reshuffle)
        if exact is not None:
            return [(1.0, exact)]
        if not base.discard:
            return [(1.0, base)]
        # 已知段抽完、牌库空：剩余抽牌要洗弃牌，顺序不可知 → 退回多重集期望
        return _draw_distribution(
            replace(base, known_draw=()), count - take, reshuffle=reshuffle
        )
    deck = Counter(state.deck)
    discard = Counter(state.discard)
    swapped = not deck and bool(discard)
    if swapped:
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
                        # 走到期望分支 = 牌序不可知，旧的已知顺序不再成立
                        known_draw=(),
                        discard_order=() if swapped else state.discard_order,
                    ),
                )
            )
        return outcomes

    outcomes = []
    for probability, drawn, left_deck, left_discard in _draw_sequential(
        deck, discard, count
    ):
        # 抽牌途中洗过弃牌 → 剩下的弃牌堆顺序不可知（牌堆顺序也已随机化）
        refilled = swapped or (bool(state.discard) and total < count)
        if refilled:
            order: tuple[CardSpec, ...] | None = () if not left_discard else None
        else:
            order = state.discard_order
        outcomes.append(
            (
                probability,
                replace(
                    state,
                    hand=state.hand + _counts_tuple(drawn),
                    deck=_counts_tuple(left_deck),
                    discard=_counts_tuple(left_discard),
                    known_draw=(),
                    discard_order=order,
                ),
            )
        )
    return outcomes


def apply_card(
    state: ExpectState, card: CardSpec, *, reshuffle: ReshuffleFn | None = None
) -> list[tuple[float, ExpectState]]:
    """打出一张牌，返回抽牌机会节点的后继分布 ``[(p, state)]``。

    打出的牌在抽牌结算**之后**才进弃牌堆/除外区（与 LessonSim.step 一致）。
    ``reshuffle`` 见 :data:`ReshuffleFn`（重洗后段全知用，默认关）。
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
    # P1-3：保留区结算在抽牌之前（参考 DSL hold 先于 drawCard；与 LessonSim 同口径）
    after, held_this = _apply_hold_state(after, card)
    outcomes = _draw_distribution(after, draw, reshuffle=reshuffle)
    results: list[tuple[float, ExpectState]] = []
    for probability, successor in outcomes:
        successor = replace(
            successor, cards_played_total=state.cards_played_total + 1
        )
        successor = fire_p_items(
            successor,
            CARD_PLAY,
            card_category=card.category,
            card_name=card.name,
            cards_played_this_turn=successor.plays_used,
            cards_played_total=successor.cards_played_total,
        )
        if held_this:
            # P1-3：holdThisCard 已进保留区，不再弃牌/除外（参考 thisCardHeld）
            pass
        elif card.once:
            successor = replace(successor, excluded=successor.excluded + (card,))
        else:
            successor = _discard_push(successor, card)
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


def sample_draws(
    state: ExpectState,
    count: int,
    rng: random.Random,
    *,
    reshuffle: ReshuffleFn | None = None,
) -> ExpectState:
    """从真实剩余多重集**无放回抽样** ``count`` 张（牌库空则把弃牌洗回）。

    ``state.known_draw`` 非空（完全信息搜索）时先按已知顺序取牌；已知段不够、
    牌库抽空时：给了确定性重洗钩子（``reshuffle``）且 ``discard_order`` 已知 →
    重洗后按已知顺序继续抽（重洗后段也全知）；否则剩余抽牌按多重集随机
    （顺序不可知，``known_draw`` / ``discard_order`` 随之失效）。
    """
    count = max(int(count), 0)
    if count <= 0:
        return state
    # 牌堆已空：能确定性重洗就直接按已知顺序抽（不消耗 rng）
    if reshuffle is not None and not state.deck:
        exact = _reshuffle_successor(state, count, reshuffle)
        if exact is not None:
            return exact
    hand = list(state.hand)
    known = state.known_draw
    deck = Counter(state.deck)
    discard = Counter(state.discard)
    discard_order = state.discard_order
    known_after: tuple[CardSpec, ...] = ()
    left = count
    if known and len(known) == len(state.deck):
        take = min(left, len(known))
        hand.extend(known[:take])
        left -= take
        known_after = known[take:]
        deck = Counter()
        if left == 0:
            return replace(
                state,
                hand=tuple(hand),
                deck=known_after,
                known_draw=known_after,
            )
        # 已知段抽完、牌堆空：先试确定性重洗（顺序已知）
        exact = _reshuffle_successor(
            replace(
                state,
                hand=tuple(hand),
                deck=(),
                known_draw=known_after,
                discard=_counts_tuple(discard),
                discard_order=discard_order,
            ),
            left,
            reshuffle,
        )
        if exact is not None:
            return exact
    # 多重集随机（原逻辑）：牌序不可知，旧 known_draw / discard_order 失效
    swapped = False
    for _ in range(left):
        if not deck:
            if not discard:
                break
            deck, discard = discard, Counter()
            swapped = True
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
    if swapped:
        discard_order = () if not discard else None
    return replace(
        state,
        hand=tuple(hand),
        deck=_counts_tuple(deck),
        discard=_counts_tuple(discard),
        known_draw=(),
        discard_order=discard_order,
    )


def sample_apply_card(
    state: ExpectState,
    card: CardSpec,
    rng: random.Random,
    *,
    reshuffle: ReshuffleFn | None = None,
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
    # P1-3：保留区结算（与 apply_card / LessonSim.step 同口径）
    after, held_this = _apply_hold_state(after, card)
    after = sample_draws(after, draw, rng, reshuffle=reshuffle)
    after = replace(after, cards_played_total=state.cards_played_total + 1)
    after = fire_p_items(
        after,
        CARD_PLAY,
        card_category=card.category,
        card_name=card.name,
        cards_played_this_turn=after.plays_used,
        cards_played_total=after.cards_played_total,
    )
    if held_this:
        return after
    if card.once:
        return replace(after, excluded=after.excluded + (card,))
    return _discard_push(after, card)


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
    stance = state.stance_state
    stance_text = str(stance.stance)
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
            "full_power_point": stance.full_power_point,
            "parameter_buff": state.condition_turns,
            # B8：依赖换算源（累计量）与指針存在性条件
            "full_power_point_total": state.full_power_point_total,
            "consumed_stamina_total": state.consumed_stamina_total,
            "stance_concentration": 1
            if (stance.strong_level > 0 or "strong" in stance_text)
            else 0,
            "stance_preservation": stance.save_level,
            "stance_full_power": 1 if "full" in stance_text else 0,
            # P1-1：のんびり存在性条件（与 LessonSim._passive_state 同口径）
            "stance_leisure": 1 if stance_text == Stance.LEISURE else 0,
            # B9：「消耗体力减少状态」条件 = halfCostTurns>0
            "half_cost_state": 1 if state.half_cost_turns > 0 else 0,
        },
        status_counts=dict(state.status_counts),
        uses=dict(state.p_item_uses),
        # B10：四个 tracked 区的卡名（区域张数条件 zone_count 求值用）。
        # P1-3：保留区（hold 区张数条件，与 LessonSim._passive_state 同口径）。
        hand=tuple(card.name for card in state.hand),
        deck=tuple(card.name for card in state.deck),
        discard=tuple(card.name for card in state.discard),
        excluded=tuple(card.name for card in state.excluded),
        held=tuple(card.name for card in state.held),
        zones_known=True,
    )


def _p_item_event_subset(
    state: ExpectState, kind: str
) -> tuple[PItemSpec, ...]:
    if not state.p_items:
        return ()
    grouped = _p_items_grouped(state.p_items)
    if kind == EXAM_START:
        # 搜索是从考试中途开始的局面：exam_start 已在进入搜索前结算过，
        # 这里只保留分支语义正确（误传也不会串到出牌类触发）。
        return grouped.get(EXAM_START, ())
    if kind == EXAM_START_AFTER:
        # 同 exam_start：训练开始后的一次性效果已在 LessonSim 构造时结算。
        return grouped.get(EXAM_START_AFTER, ())
    if kind == TURN_START:
        return grouped.get(TURN_START, ())
    if kind == TURN_START_AFTER:
        return grouped.get(TURN_START_AFTER, ())
    if kind == TURN_INTERVAL:
        return grouped.get(TURN_INTERVAL, ())
    if kind == TURN_END:
        return grouped.get(TURN_END, ())
    if kind == STATUS_GAIN:
        return grouped.get(STATUS_GAIN, ()) + grouped.get(STATUS_GAIN_INTERVAL, ())
    if kind == STANCE_CHANGE:
        return grouped.get(STANCE_CHANGE, ())
    if kind == STAMINA_REDUCE:
        return grouped.get(STAMINA_REDUCE, ())
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
    card_name: str = "",
    cards_played_this_turn: int = 0,
    cards_played_total: int = 0,
    status: str = "",
    amount: int = 0,
    stamina_delta: int = 0,
    _depth: int = 0,
) -> ExpectState:
    """在指定时机触发 P 道具并返回结算后的状态（纯函数）。

    B8：新增 ``turn_start_after`` / ``turn_interval`` / ``stance_change`` /
    ``stamina_reduce`` / ``status_gain_interval``；``status_gain`` 事件同时推进
    ``status_counts``（累计增加次数，供 status_gain_interval 判断跨过 N 的整数倍）。

    B9（2026-11-22）：持久倍率 / modifier 增量（分数 buff/debuff、好印象强化、
    追加发动、热意/集中/好印象/干劲/全力值增益倍率、绝好调/不调、费用修正、
    回合追加、指針直给）在这里落进状态；指針直给后按参考引擎 ``setStance``
    语义发一次 ``stance_change``（``_depth`` 防链式递归）。
    """
    if not state.p_items:
        return state
    # B8：状态累计增加次数先推进（即使本次没有匹配的 spec 也要记，供后续
    # status_gain_interval 的「跨过 N 的整数倍」判断；与 LessonSim 同口径）。
    status_counts = dict(state.status_counts)
    status_total = 0
    if kind == STATUS_GAIN:
        if status and amount > 0:
            status_counts[status] = status_counts.get(status, 0) + int(amount)
        status_total = status_counts.get(status, 0)
    subset = _p_item_event_subset(state, kind)
    if not subset:
        if status_counts != dict(state.status_counts):
            return replace(state, status_counts=tuple(sorted(status_counts.items())))
        return state
    event = PassiveEvent(
        kind=kind,
        card_category=card_category,
        card_name=card_name,
        cards_played_this_turn=cards_played_this_turn,
        cards_played_total=cards_played_total,
        status=status,
        amount=amount,
        status_total=status_total,
        stamina_delta=stamina_delta,
    )
    delta = apply_passive(subset, event, _passive_state(state))
    if delta.is_zero():
        if status_counts != dict(state.status_counts):
            return replace(state, status_counts=tuple(sorted(status_counts.items())))
        return state
    score = state.score + int(delta.score)
    stamina = state.stamina
    if delta.stamina:
        stamina = min(state.stamina_max, max(0, stamina + delta.stamina))
    consumed_stamina_total = state.consumed_stamina_total
    if delta.stamina_consumed:
        consumed_stamina_total += int(delta.stamina_consumed)
    extra_plays = state.extra_plays + int(delta.extra_plays)
    vitality = state.vitality
    impression = state.impression
    focus = state.focus
    condition_turns = state.condition_turns
    motivation = state.motivation
    stance = state.stance_state
    full_power_point_total = state.full_power_point_total
    perfect_condition_turns = state.perfect_condition_turns
    poor_condition_turns = state.poor_condition_turns
    for key in delta.zero_stacks:
        if key == "vitality":
            vitality = 0
        elif key == "impression":
            impression = 0
        elif key == "focus":
            focus = 0
        elif key == "aggressive":
            motivation = 0
        elif key == "full_power_point":
            stance = replace(stance, full_power_point=0)
        elif key == "parameter_buff":
            condition_turns = 0
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
            full_power_point_total += max(0, value)
        elif key == "parameter_buff":
            condition_turns += value
    # ---- B9：持久倍率 / modifier 增量（与 LessonSim._fire_p_items 同口径）----
    score_buffs = state.score_buffs
    for buff_amount, buff_turns in delta.score_buffs:
        score_buffs = add_timed(score_buffs, buff_amount, buff_turns)
    score_debuffs = state.score_debuffs
    # P1-4：低下状态无效次数先累加，再拦截 debuff 施加（与 LessonSim._fire_p_items
    # 同口径：score_debuffs → hand_decreases 逐条消耗 nullify_debuff）。
    nullify_debuff = state.nullify_debuff + int(delta.nullify_debuff)
    score_debuff_entries = delta.score_debuffs
    hand_decrease_entries = delta.hand_decreases
    if nullify_debuff > 0:
        nullify_debuff, score_debuff_entries = intercept_debuff_entries(
            nullify_debuff, delta.score_debuffs
        )
        nullify_debuff, hand_decrease_entries = intercept_debuff_entries(
            nullify_debuff, delta.hand_decreases
        )
    for buff_amount, buff_turns in score_debuff_entries:
        score_debuffs = add_timed(score_debuffs, buff_amount, buff_turns)
    # P1-2：手牌减少（setHandDecrease 同口径）/ 自尊回合数（prideTurns+=N）
    hand_decreases = state.hand_decreases
    for hd_amount, hd_turns in hand_decrease_entries:
        hand_decreases = add_timed(hand_decreases, hd_amount, hd_turns)
    pride_turns = state.pride_turns + int(delta.pride_turns)
    modifiers = dict(state.modifiers)
    if delta.perfect_condition_turns:
        perfect_condition_turns += int(delta.perfect_condition_turns)
    if delta.poor_condition_turns:
        poor_condition_turns += int(delta.poor_condition_turns)
    # 好印象强化 / 熱意追加・増加 与卡效果共用标量渠道（不重复放 modifiers，
    # 否则 end_turn_state 的倒计时会算两次）。
    p_review_multiple = state.review_multiple
    p_review_multiple_turns = state.review_multiple_turns
    p_enthusiasm_bonus = state.enthusiasm_bonus
    p_enthusiasm_bonus_turns = state.enthusiasm_bonus_turns
    p_enthusiasm_multiple = state.enthusiasm_multiple
    p_enthusiasm_multiple_turns = state.enthusiasm_multiple_turns
    for key, mod_value, mod_turns in delta.modifiers:
        turns = normalize_turns(mod_turns)
        if key == "review_multiple":
            p_review_multiple = max(p_review_multiple, mod_value)
            p_review_multiple_turns = _merge_turns(p_review_multiple_turns, turns)
        elif key == "enthusiasm_multiple":
            p_enthusiasm_multiple = max(p_enthusiasm_multiple, mod_value)
            p_enthusiasm_multiple_turns = _merge_turns(
                p_enthusiasm_multiple_turns, turns
            )
        elif key == "enthusiasm_bonus":
            p_enthusiasm_bonus = max(p_enthusiasm_bonus, mod_value)
            p_enthusiasm_bonus_turns = _merge_turns(p_enthusiasm_bonus_turns, turns)
        else:
            modifiers = timed_dict_add(modifiers, key, mod_value, mod_turns)
    stance_changed = False
    release_enthusiasm_gain = 0
    release_genki_gain = 0
    release_plays_gain = 0
    release_growth_gain = 0
    locked = state.lock_stance_turns > 0
    for stance_kind in delta.stances:
        previous = stance
        if stance_kind == "preservation" and stance_change_allowed(
            stance, "preservation", locked=locked
        ):
            already = str(stance.stance) == "save"
            level = 2 if already else 1
            stance = replace(
                stance,
                stance="save",
                save_level=max(int(stance.save_level), level) if already else level,
                strong_level=0,
            )
        elif stance_kind == "preservation2" and stance_change_allowed(
            stance, "preservation", locked=locked
        ):
            # P1-3：温存 2 段階直给（「温存阶段变更」↔ setStance(preservation2)，
            # 与 LessonSim._apply_direct_stances 同口径）
            stance = replace(
                stance,
                stance="save",
                save_level=2,
                strong_level=0,
            )
        elif stance_kind == "concentration" and stance_change_allowed(
            stance, "concentration", locked=locked
        ):
            already = "strong" in str(stance.stance)
            level = 2 if already else 1
            stance = replace(
                stance,
                stance="strong2" if level == 2 else "strong1",
                strong_level=level,
                save_level=0,
            )
        elif stance_kind == "leisure" and stance_change_allowed(
            stance, "leisure", locked=locked
        ):
            # P1-1：のんびり变更（ExamOverPreservation，与 LessonSim 同口径）
            stance = replace(
                stance,
                stance=Stance.LEISURE,
                strong_level=0,
                save_level=0,
            )
        if stance != previous:
            stance_changed = True
            rel_enth, rel_genki, rel_plays, rel_growth = release_on_stance_change(
                previous, stance
            )
            if rel_enth or rel_genki or rel_plays or rel_growth:
                release_enthusiasm_gain += enthusiasm_gain(
                    rel_enth,
                    bonus=max(state.enthusiasm_bonus, p_enthusiasm_bonus),
                    multiple_permil=max(
                        state.enthusiasm_multiple, p_enthusiasm_multiple
                    ),
                )
                release_genki_gain += rel_genki
                release_plays_gain += rel_plays
                release_growth_gain += rel_growth
    extra_plays += release_plays_gain
    vitality += release_genki_gain
    enthusiasm = state.enthusiasm + int(release_enthusiasm_gain)
    # ---- B10：生成卡（与 LessonSim._create_p_item_cards 同口径）--------------
    # deck 是多重集：生成到牌堆顶时同步 known_draw（下标 0 = 下一张）；
    # discard_order 已知时同步追加。手牌≥5 不生成（参考 addCardToHand）。
    hand = state.hand
    deck = state.deck
    discard = state.discard
    known_draw = state.known_draw
    discard_order = state.discard_order
    min_cost = state.min_cost
    if delta.create_cards:
        from gkagent.data.card_meta import card_meta_index
        from gkagent.sim.play_choice import spec_from_name

        index = card_meta_index()
        for create in delta.create_cards:
            name = index.name_of(create.card_id, create.upgrade)
            spec = spec_from_name(name) if name else None
            if spec is None:
                continue
            for _ in range(max(int(create.count), 1)):
                if create.zone == "hand":
                    if len(hand) >= 5:
                        continue
                    hand = hand + (spec,)
                elif create.zone == "deck_top":
                    deck = deck + (spec,)
                    if known_draw:
                        known_draw = (spec,) + known_draw
                    min_cost = min(min_cost, spec.cost)
                elif create.zone == "discard":
                    discard = discard + (spec,)
                    if discard_order is not None:
                        discard_order = discard_order + (spec,)
    uses = dict(state.p_item_uses)
    # B10：次数上限按道具计（同事件多效果段只记 1 次，与 LessonSim 同口径）。
    for item_id in dict.fromkeys(delta.applied):
        uses[item_id] = uses.get(item_id, 0) + 1
    new_state = replace(
        state,
        score=score,
        stamina=stamina,
        extra_plays=extra_plays,
        enthusiasm=enthusiasm,
        vitality=vitality,
        score_growth_all=state.score_growth_all + release_growth_gain,
        impression=max(impression, 0),
        focus=max(focus, 0),
        condition_turns=condition_turns,
        motivation=max(motivation, 0),
        p_item_uses=tuple(sorted(uses.items())),
        full_power_point_total=full_power_point_total,
        consumed_stamina_total=consumed_stamina_total,
        status_counts=tuple(sorted(status_counts.items())),
        score_buffs=score_buffs,
        score_debuffs=score_debuffs,
        hand_decreases=hand_decreases,
        pride_turns=pride_turns,
        nullify_debuff=nullify_debuff,
        modifiers=tuple(sorted(modifiers.items())),
        review_multiple=p_review_multiple,
        review_multiple_turns=p_review_multiple_turns,
        enthusiasm_bonus=p_enthusiasm_bonus,
        enthusiasm_bonus_turns=p_enthusiasm_bonus_turns,
        enthusiasm_multiple=p_enthusiasm_multiple,
        enthusiasm_multiple_turns=p_enthusiasm_multiple_turns,
        perfect_condition_turns=perfect_condition_turns,
        poor_condition_turns=poor_condition_turns,
        cost_reduction=state.cost_reduction + int(delta.cost_reduction),
        cost_increase=state.cost_increase + int(delta.cost_increase),
        half_cost_turns=state.half_cost_turns + int(delta.half_cost_turns),
        double_cost_turns=state.double_cost_turns + int(delta.double_cost_turns),
        extra_turns=state.extra_turns + int(delta.extra_turns),
        hand=hand,
        deck=deck,
        discard=discard,
        known_draw=known_draw,
        discard_order=discard_order,
        min_cost=min_cost,
    ).with_stance(stance)
    if stance_changed and _depth < 3:
        new_state = fire_p_items(new_state, STANCE_CHANGE, _depth=_depth + 1)
    return new_state


def start_turn_state(state: ExpectState) -> ExpectState:
    """抽完新手牌后的回合开始结算（P 道具 turn_start → turn_start_after → turn_interval）。"""
    state = fire_p_items(state, TURN_START)
    state = fire_p_items(state, TURN_START_AFTER)
    return fire_p_items(state, TURN_INTERVAL)


def end_turn_state(state: ExpectState) -> ExpectState:
    """结算回合末：好印象加分后 -1、好调 -1、持续 buff 倒计时、弃手牌、回合 -1。

    不抽下一手牌：下一回合的牌序属于未知，由 V_leaf 的解析式吸收。

    T5②（2026-11-22）：好印象结算加**熱意**（与 LessonSim 同口径）；熱意回合末
    归 0（有「熱意延長」则保留并 -1）；温存→全力 的回合边界指針切换结算解除
    收益（熱意 / 固定元気 / 新回合 +1 出牌次数）。

    **回合末体力回复**（参考引擎 ``TurnManager.endTurn``）：回合结束时本回合
    出牌次数还有剩（``plays_left > 0``，即 SKIP / 手牌为空 / 付不起牌）→ 体力
    +2、封顶 ``stamina_max``；出牌次数用尽后结束的回合（含自动结束）不回体力。
    """
    score = state.score
    stamina = state.stamina
    if state.plays_left > 0:
        cap = state.stamina_max if state.stamina_max > 0 else stamina
        stamina = min(int(cap), stamina + 2)
    impression = state.impression
    if impression > 0:
        # B9：好印象追加发动（ExamReviewCountAdd）让结算重复 N+1 次；P 道具持久
        # 分数倍率（参考引擎 resolveScore f/g）也作用在回合末好印象上。
        review_times = max(0, state.mod_total("review_times"))
        score_buff = total_timed(state.score_buffs)
        # P1-2：回合末好印象也吃自尊加成（与 LessonSim._end_turn 同口径）
        if state.pride_turns > 0:
            score_buff += min(min(impression, state.motivation) * 20, 500)
        score_debuff = total_timed(state.score_debuffs)
        for _ in range(1 + review_times):
            value = float(impression)
            if state.review_multiple > 0:
                value = int(impression * (1000 + state.review_multiple) / 1000)
            # 熱意（T5②）：参考引擎回合末好印象也走 resolveScore、会加熱意；
            # 只在熱意 > 0 时改旧取整路径（与 LessonSim._end_turn 同口径）。
            if state.enthusiasm > 0:
                value = float(safe_ceil(value + state.enthusiasm))
            if score_buff:
                value = float(safe_ceil(value * (1.0 + score_buff / 1000.0)))
            if score_debuff:
                value = float(
                    safe_ceil(value * max(1.0 - score_debuff / 1000.0, 0.0))
                )
            score += int(value)
        impression -= 1
    condition_turns = state.condition_turns - 1 if state.condition_turns > 0 else 0
    perfect_condition_turns = (
        state.perfect_condition_turns - 1 if state.perfect_condition_turns > 0 else 0
    )
    poor_condition_turns = (
        state.poor_condition_turns - 1 if state.poor_condition_turns > 0 else 0
    )
    # P1-2：自尊回合末 -1（参考 EOT_DECREMENT_FIELDS 的 prideTurns）
    pride_turns = state.pride_turns - 1 if state.pride_turns > 0 else 0
    # P1-3：指針固定回合末 -1（fresh 保护：获得当回合末不扣，锁下一回合；
    # 与 LessonSim._end_turn 同口径，见该处注释）。
    if state.lock_stance_fresh:
        lock_stance_turns = state.lock_stance_turns
        lock_stance_fresh = False
    else:
        lock_stance_turns = max(state.lock_stance_turns - 1, 0)
        lock_stance_fresh = False
    condition_additive_turns = _tick_turns(state.condition_additive_turns)
    condition_additive = state.condition_additive if condition_additive_turns != 0 else 0
    review_multiple_turns = _tick_turns(state.review_multiple_turns)
    review_multiple = state.review_multiple if review_multiple_turns != 0 else 0
    full_power_turns = _tick_turns(state.full_power_lesson_multiple_turns)
    full_power_multiple = state.full_power_lesson_multiple if full_power_turns != 0 else 0
    # 熱意追加/増加 buff 倒计时；熱意本身回合末归 0（有延長则保留并 -1）
    enthusiasm_bonus_turns = _tick_turns(state.enthusiasm_bonus_turns)
    enthusiasm_bonus = state.enthusiasm_bonus if enthusiasm_bonus_turns != 0 else 0
    enthusiasm_multiple_turns = _tick_turns(state.enthusiasm_multiple_turns)
    enthusiasm_multiple = (
        state.enthusiasm_multiple if enthusiasm_multiple_turns != 0 else 0
    )
    # B9：P 道具持久倍率倒计时（turns>0 的 -1、到 0 移除、-1 永久）
    score_buffs = tick_timed(state.score_buffs)
    score_debuffs = tick_timed(state.score_debuffs)
    # P1-2：手牌减少倒计时（与 LessonSim._end_turn 同口径）
    hand_decreases = tick_timed(state.hand_decreases)
    modifiers = tuple(sorted(timed_dict_tick(dict(state.modifiers)).items()))
    half_cost_turns = state.half_cost_turns - 1 if state.half_cost_turns > 0 else 0
    double_cost_turns = (
        state.double_cost_turns - 1 if state.double_cost_turns > 0 else 0
    )
    # B9：回合追加在「剩余回合 -1」之后补上（与 LessonSim._end_turn 同口径）
    extra_turns_granted = state.extra_turns_granted + int(state.extra_turns)
    turns_left_after = state.turns_left - 1 + int(state.extra_turns)
    enthusiasm, enthusiasm_extension_turns = turn_end_enthusiasm(
        state.enthusiasm, state.enthusiasm_extension_turns
    )
    previous_stance = state.stance_state
    # P1-3：指針固定期间全力进入门不满足（全力值不消耗；与 LessonSim 同口径）
    next_stance = end_turn(state.stance_state, locked=lock_stance_turns > 0)
    stance_changed = next_stance != previous_stance
    hand_order = state.discard_order
    # P1-1：以全力开始的回合——保留牌回手（FULL_POWER_CHANGED_EFFECTS 的
    # moveHeldCardsToHand；下一手从回手牌开始，抽牌由调用方/全知牌序补）。
    # P1-3：LIFO（参考 pop() 从尾部弹，与 LessonSim._move_held_to_hand 对齐）。
    enters_full = str(next_stance.stance) == Stance.FULL
    next_state = replace(
        state,
        score=score,
        stamina=stamina,
        impression=impression,
        condition_turns=condition_turns,
        perfect_condition_turns=perfect_condition_turns,
        poor_condition_turns=poor_condition_turns,
        condition_additive=condition_additive,
        condition_additive_turns=condition_additive_turns,
        review_multiple=review_multiple,
        review_multiple_turns=review_multiple_turns,
        full_power_lesson_multiple=full_power_multiple,
        full_power_lesson_multiple_turns=full_power_turns,
        enthusiasm=enthusiasm,
        enthusiasm_extension_turns=enthusiasm_extension_turns,
        enthusiasm_bonus=enthusiasm_bonus,
        enthusiasm_bonus_turns=enthusiasm_bonus_turns,
        enthusiasm_multiple=enthusiasm_multiple,
        enthusiasm_multiple_turns=enthusiasm_multiple_turns,
        score_buffs=score_buffs,
        score_debuffs=score_debuffs,
        hand_decreases=hand_decreases,
        pride_turns=pride_turns,
        lock_stance_turns=lock_stance_turns,
        lock_stance_fresh=lock_stance_fresh,
        modifiers=modifiers,
        half_cost_turns=half_cost_turns,
        double_cost_turns=double_cost_turns,
        extra_turns=0,
        extra_turns_granted=extra_turns_granted,
        parameter_buff=0,
        hand=tuple(reversed(state.held)) if enters_full else (),
        held=() if enters_full else state.held,
        discard=state.discard + state.hand,
        # 回合末弃手牌：进弃牌堆的顺序 = 手牌顺序（已知顺序时继续累积）
        discard_order=None if hand_order is None else hand_order + state.hand,
        turns_left=turns_left_after,
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
    # P1-1：全力回合 +1 出牌次数（FULL_POWER_CHANGED_EFFECTS，连续全力每回合都有）
    if enters_full and next_state.turns_left > 0:
        next_state = replace(next_state, extra_plays=next_state.extra_plays + 1)
    # 温存/のんびり→全力 的回合边界切换也触发解除收益（参考引擎 startTurn 的
    # FULL_POWER_EFFECTS → setStance(fullPower)）；次数加在新回合基础次数上。
    if next_state.turns_left > 0:
        release_enthusiasm, release_genki, release_plays, release_growth = (
            release_on_stance_change(previous_stance, next_stance)
        )
        if release_enthusiasm or release_genki or release_plays or release_growth:
            next_state = replace(
                next_state,
                enthusiasm=next_state.enthusiasm
                + enthusiasm_gain(
                    release_enthusiasm,
                    bonus=next_state.enthusiasm_bonus,
                    multiple_permil=next_state.enthusiasm_multiple,
                ),
                vitality=next_state.vitality + release_genki,
                extra_plays=next_state.extra_plays + release_plays,
                score_growth_all=next_state.score_growth_all + release_growth,
            )
        # P1-1：のんびり预约（与 LessonSim._apply_leisure_reserves 同口径）
        next_state = _apply_leisure_reserves_state(next_state)
    # B8：回合边界的指針切换（全力进入等）发 stance_change（与 LessonSim 同口径）
    if stance_changed:
        next_state = fire_p_items(next_state, STANCE_CHANGE)
    # P 道具：回合结束（好印象/好调结算后、弃手牌前）
    return fire_p_items(next_state, TURN_END)


def _apply_leisure_reserves_state(state: ExpectState) -> ExpectState:
    """P1-1：回合开始结算のんびり预约（ExpectState 纯函数版，双镜 LessonSim）。

    每条预约独立按当时指針判条件；条件成立触发 setStance(leisure)（受全力守卫）
    并扣次数（-1 永久不扣）；指針变化发 stance_change。进入のんびり无解除收益。
    """
    if not state.leisure_reserves:
        return state
    stance = state.stance_state
    remaining: list[tuple[int, bool]] = []
    changed = False
    for count, when_save in state.leisure_reserves:
        stance_now = str(stance.stance)
        matched = (
            (stance_now == Stance.SAVE) if when_save else (stance_now != Stance.SAVE)
        )
        if matched:
            if stance_change_allowed(
                stance, "leisure", locked=state.lock_stance_turns > 0
            ):
                stance = replace(
                    stance, stance=Stance.LEISURE, strong_level=0, save_level=0
                )
                changed = True
            if count > 0:
                count -= 1
        if count != 0:
            remaining.append((count, when_save))
    state = replace(state, leisure_reserves=tuple(remaining)).with_stance(stance)
    if changed:
        state = fire_p_items(state, STANCE_CHANGE)
    return state


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
        value: LeafValue,
        config: ExpectimaxConfig,
        *,
        clock: Callable[[], float],
        deadline: float | None,
        reshuffle: ReshuffleFn | None = None,
    ) -> None:
        self.value = value
        self.config = config
        self.clock = clock
        self.deadline = deadline
        self.reshuffle = reshuffle
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
        if self.config.allow_drinks:
            for index in _candidate_drinks(state):
                drink = state.drinks[index]
                value = self.search(use_drink_state(state, index))
                # 喝饮料只在严格提升档位效用时替换；打平优先出牌（饮料可留到后面）
                if value > best + 1e-12:
                    best = value
                    best_card = None
                    best_drink = index
                    best_key = (
                        state.plays_left,
                        state.total_cost_available - int(drink.cost),
                        0,
                    )
        self.memo[key] = best
        self.choice_memo[key] = best_card
        self.drink_choice_memo[key] = best_drink
        return best

    def action_value(self, state: ExpectState, card: CardSpec) -> float:
        outcomes = apply_card(state, card, reshuffle=self.reshuffle)
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
        if self.config.allow_drinks:
            for index in _candidate_drinks(state):
                drink = state.drinks[index]
                try:
                    value = self.search(use_drink_state(state, index))
                except _Deadline:
                    self.aborted = True
                    break
                actions.append((f"drink:{drink.name}", value))
                # 打平优先出牌（饮料可留到后面），只有严格提升才替换
                if value > best_value + 1e-12:
                    best_value = value
                    best_card = None
                    best_drink = index
                    best_key = (
                        state.plays_left,
                        state.total_cost_available - int(drink.cost),
                        0,
                    )
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
    allow_drinks: bool | None,
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
    if allow_drinks is not None:
        updates["allow_drinks"] = bool(allow_drinks)
    return replace(base, **updates) if updates else base


def expectimax_with_stats(
    state: ExpectState,
    value: LeafValue | None = None,
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
    allow_drinks: bool | None = None,
    reshuffle: ReshuffleFn | None = None,
) -> ExpectimaxResult:
    """完整决策：返回动作、价值、节点数、耗时、是否完整（anytime 截止）。

    ``reshuffle``（可选）：确定性重洗钩子，配合 ``ExpectState.discard_order``
    让牌堆抽空后的重洗也变成确定分支（见 :data:`ReshuffleFn`）。
    """
    config = _config_with_overrides(
        config,
        a_clear=a_clear,
        a_perfect=a_perfect,
        sigma=sigma,
        time_budget_ms=time_budget_ms,
        draw_enum_limit=draw_enum_limit,
        max_nodes=max_nodes,
        allow_drinks=allow_drinks,
    )
    model = value or AnalyticLeafValue(
        sigma=config.sigma, a_clear=config.a_clear, a_perfect=config.a_perfect
    )
    started = clock()
    if deadline is None and config.time_budget_ms is not None:
        deadline = started + max(float(config.time_budget_ms), 0.0) / 1000.0
    search = _Search(model, config, clock=clock, deadline=deadline, reshuffle=reshuffle)
    try:
        best_value, best_card, best_drink, actions = search.root(state)
    except _Deadline:
        best_value, best_card, best_drink, actions = (
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
        drink=best_drink,
    )


def expectimax(
    state: ExpectState,
    value: LeafValue | None = None,
    *,
    config: ExpectimaxConfig | None = None,
    clock: Callable[[], float] = time.perf_counter,
    deadline: float | None = None,
    time_budget_ms: float | None = None,
    allow_drinks: bool | None = None,
    **kwargs: Any,
) -> CardSpec | None:
    """返回本回合第一张要打的牌；``None`` = SKIP（或最优动作是喝饮料）。

    要同时拿饮料动作请用 ``expectimax_action``；只出牌的场景保持旧 API。
    """
    if allow_drinks is not None:
        kwargs["allow_drinks"] = allow_drinks
    card, _drink = expectimax_action(
        state,
        value,
        config=config,
        clock=clock,
        deadline=deadline,
        time_budget_ms=time_budget_ms,
        **kwargs,
    )
    return card


def expectimax_action(
    state: ExpectState,
    value: LeafValue | None = None,
    *,
    config: ExpectimaxConfig | None = None,
    clock: Callable[[], float] = time.perf_counter,
    deadline: float | None = None,
    time_budget_ms: float | None = None,
    **kwargs: Any,
) -> tuple[CardSpec | None, int | None]:
    """返回 ``(首牌, 饮料下标)``；两者都 None = SKIP。"""
    result = expectimax_with_stats(
        state,
        value,
        config=config,
        clock=clock,
        deadline=deadline,
        time_budget_ms=time_budget_ms,
        **kwargs,
    )
    return result.card, result.drink


def expectimax_value(
    state: ExpectState,
    value: LeafValue | None = None,
    **kwargs: Any,
) -> float:
    """当前状态在档位效用下的最优价值（测试/日志用）。"""
    return expectimax_with_stats(state, value, **kwargs).utility


def best_turn_sequence(
    state: ExpectState,
    value: LeafValue | None = None,
    *,
    clock: Callable[[], float] = time.perf_counter,
    deadline: float | None = None,
    reshuffle: ReshuffleFn | None = None,
) -> tuple[list[CardSpec], ExpectState, bool]:
    """本回合的最优**有序出牌序列**（抽牌取最大概率后继；beam 规划用）。"""
    model = value or AnalyticLeafValue()
    search = _Search(
        model,
        ExpectimaxConfig(),
        clock=clock,
        deadline=deadline,
        reshuffle=reshuffle,
    )
    cards: list[CardSpec] = []
    current = state
    complete = True
    try:
        while current.plays_left > 0 and current.hand:
            search.search(current)
            card = search.choice_memo.get(current.canonical())
            if card is None:
                break
            outcomes = apply_card(current, card, reshuffle=reshuffle)
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
    value: LeafValue,
    *,
    limit: int,
    rng: random.Random,
    clock: Callable[[], float],
    deadline: float,
    reshuffle: ReshuffleFn | None = None,
) -> list[_TurnPlan]:
    """本回合按 V_leaf 取 top-limit 个**不同出牌序列**（beam 根分支用）。

    手牌里没有抽牌卡时，回合内是确定性的，直接枚举所有有序序列（含提前 SKIP）；
    有抽牌卡时用 ``_plan_turn`` 抽样 limit 次（不确定的抽牌交给随机机会）。
    """
    limit = max(int(limit), 1)
    has_draw = any(card.draw > 0 for card in state.hand)
    has_drinks = bool(available_drinks(state))
    if limit == 1 or has_draw or has_drinks:
        # 单计划/有抽牌/有饮料：直接用 expectimax 的最佳序列（比枚举快）
        return [
            _plan_turn(
                state,
                value,
                rng,
                clock=clock,
                deadline=deadline,
                reshuffle=reshuffle,
            )
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
            outcomes = apply_card(current, card, reshuffle=reshuffle)
            if len(outcomes) != 1:
                # 手牌里没有 draw 卡时不应出现分支；防御性跳过
                continue
            recurse(outcomes[0][1], [*cards, card])

    recurse(state, [])
    ordered = sorted(results.values(), key=lambda plan: plan.utility, reverse=True)
    return ordered[:limit]


def _plan_turn(
    state: ExpectState,
    value: LeafValue,
    rng: random.Random,
    *,
    clock: Callable[[], float],
    deadline: float,
    reshuffle: ReshuffleFn | None = None,
) -> _TurnPlan:
    """一个回合的最佳序列；有抽牌卡时按真实剩余多重集抽样推进。"""
    has_draw = any(card.draw > 0 for card in state.hand)
    has_drinks = bool(available_drinks(state))
    first_card: CardSpec | None = None
    names: list[str] = []
    complete = True
    if not has_draw and not has_drinks:
        cards, current, complete = best_turn_sequence(
            state, value, clock=clock, deadline=deadline, reshuffle=reshuffle
        )
        names = [card.name for card in cards]
        first_card = cards[0] if cards else None
    else:
        current = state
        try:
            while current.plays_left > 0 and current.hand:
                result = expectimax_with_stats(
                    current,
                    value,
                    clock=clock,
                    deadline=deadline,
                    reshuffle=reshuffle,
                )
                if result.card is None and result.drink is None:
                    break
                if result.drink is not None:
                    drink = current.drinks[result.drink]
                    names.append(f"drink:{drink.name}")
                    current = use_drink_state(current, result.drink)
                    if not result.complete:
                        complete = False
                        break
                    continue
                if first_card is None:
                    first_card = result.card
                names.append(result.card.name)
                current = sample_apply_card(
                    current, result.card, rng, reshuffle=reshuffle
                )
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
    value: LeafValue | None = None,
    *,
    width: int = 24,
    depth: int | None = None,
    deadline_ms: float = DEFAULT_BEAM_DEADLINE_MS,
    time_budget_ms: float | None = None,
    clock: Callable[[], float] = time.perf_counter,
    rng: random.Random | int | None = None,
    branching: int | None = None,
    reshuffle: ReshuffleFn | None = None,
    frontier_value: LeafValue | None = None,
) -> BeamResult:
    """跨回合 beam：每层一个回合，节点是回合末状态，按 V_leaf 保留 top-width。

    根回合先生成 top-``branch`` 个不同出牌序列作为 beam 分支；之后每层用真实
    剩余多重集**无放回抽样**新一手牌（``sample_draws``），回合内用 expectimax
    产出该回合最佳序列。最终按**最深一层**的 V_leaf 回溯根动作——这样"先铺 buff
    的投资线"不会因为当前分数低被剪掉。到 ``deadline_ms`` 返回当前最优。

    ``reshuffle``（可选）：确定性重洗钩子；``state.discard_order`` 已知时，
    牌堆抽空后的重洗与后续抽牌也按真实顺序走（配合 known_draw 的完全信息规划）。

    ``frontier_value``（可选，受控 policy evaluation）：只在 beam **最深端点**
    （预算截断后的前沿，``end_state.turns_left > 0``）用更强的叶子重排一次，
    替代浅层解析式 V 决定最终根动作。已经到终局（``turns_left == 0``）的端点
    直接用精确档位效用，不浪费 rollout。默认 ``None`` = 历史行为逐位不变。
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
            reshuffle=reshuffle,
        )
    except _Deadline:
        complete = False
    if not root_plans:
        result = expectimax_with_stats(
            state, model, clock=clock, deadline=deadline, reshuffle=reshuffle
        )
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
                    node.plan.end_state,
                    # P1-2：回合开始抽牌数扣掉 handDecrease（参考 cardsToDraw）
                    node.plan.end_state.turn_draw_count,
                    rng,
                    reshuffle=reshuffle,
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
                        reshuffle=reshuffle,
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

    # 受控 policy evaluation：beam 被预算截断时，最深端点（前沿）只有解析式 V，
    # 平手项/存体力偏置会直接把根动作带偏。这里只对前沿做一次更强叶子重排；
    # 终局端点用精确档位效用，不 rollout。
    if frontier_value is not None:
        polished: list[tuple[float, _BeamNode]] = []
        for node in beam:
            end_state = node.plan.end_state
            if end_state.turns_left > 0:
                score = float(frontier_value.utility(end_state))
            else:
                score = node.plan.utility
            polished.append((score, node))
        best_score, best_node = polished[0]
        for score, node in polished[1:]:
            # 严格大于：同分保留原 analytic 顺序（稳定、可复现）
            if score > best_score:
                best_score = score
                best_node = node
    else:
        best_score = best_node.plan.utility

    # 最终按最深层 V 回溯根回合计划（不是按当前分数/根回合叶子）
    return BeamResult(
        card=best_node.root_plan.first_card,
        utility=best_score,
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
def state_from_sim(sim: Any, *, known_deck_order: bool = False) -> ExpectState:
    """把一个 ``LessonSim`` 的当前局面快照成 ``ExpectState``（离线评测用）。

    ``known_deck_order=True`` 时把 ``sim.deck`` 的**真实顺序**写成 ``known_draw``
    （``LessonSim`` 从列表尾部 ``pop()`` 抽牌，所以抽牌顺序 = ``reversed(sim.deck)``），
    用来离线评测「完全信息搜索」。

    ``discard_order`` 总是从 ``sim.discard`` 带过来（``LessonSim`` 的弃牌堆是
    append 顺序 = 进弃牌堆先后）。配合 :func:`reshuffle_from_sim` 的钩子，搜索在
    牌堆抽空后也能按真实顺序重洗 →「重洗后段全知」的离线评测入口。
    """
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
        # P1-1：保留区 / のんびり预约 / 全体卡打分成长（与 sim_from_state 双镜）
        held=tuple(getattr(sim, "held", ())),
        leisure_reserves=tuple(
            (int(count), bool(when_save))
            for count, when_save in getattr(sim, "leisure_reserves", ())
        ),
        score_growth_all=max(int(getattr(sim, "score_growth_all", 0)), 0),
        known_draw=(tuple(reversed(sim.deck)) if known_deck_order else ()),
        discard_order=tuple(sim.discard),
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
        perfect_condition_turns=max(int(buffs.perfect_condition_turns), 0),
        poor_condition_turns=max(int(buffs.poor_condition_turns), 0),
        metamorphosis=str(buffs.metamorphosis or ""),
        focus=max(int(buffs.focus), 0),
        impression=max(int(buffs.impression), 0),
        motivation=max(int(getattr(sim, "motivation", 0)), 0),
        condition_additive=max(int(buffs.condition_additive), 0),
        condition_additive_turns=int(buffs.condition_additive_turns),
        review_multiple=max(int(buffs.review_multiple), 0),
        review_multiple_turns=int(buffs.review_multiple_turns),
        full_power_lesson_multiple=max(int(buffs.full_power_lesson_multiple), 0),
        full_power_lesson_multiple_turns=int(buffs.full_power_lesson_multiple_turns),
        enthusiasm=int(getattr(sim, "enthusiasm", 0) or 0),
        enthusiasm_extension_turns=max(
            int(getattr(sim, "enthusiasm_extension_turns", 0) or 0), 0
        ),
        enthusiasm_bonus=max(int(buffs.enthusiasm_bonus), 0),
        enthusiasm_bonus_turns=int(buffs.enthusiasm_bonus_turns),
        enthusiasm_multiple=max(int(buffs.enthusiasm_multiple), 0),
        enthusiasm_multiple_turns=int(buffs.enthusiasm_multiple_turns),
        parameter_buff=max(int(getattr(sim, "turn_parameter_buff", 0)), 0),
        stance=(
            stance.stance,
            int(stance.strong_level),
            int(stance.save_level),
            int(stance.full_power_point),
        ),
        save_cards_used=0,
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
        # B8：累计量 / 状态增加次数（P 道具条件/依赖换算用）
        full_power_point_total=max(int(getattr(sim, "full_power_point_total", 0)), 0),
        consumed_stamina_total=max(int(getattr(sim, "consumed_stamina_total", 0)), 0),
        status_counts=tuple(
            sorted((str(key), int(count)) for key, count in getattr(sim, "status_gain_counts", {}).items())
        ),
        # B9：持久倍率 / modifier（与 sim_from_state 双镜）
        score_buffs=tuple(getattr(sim, "score_buffs", ())),
        score_debuffs=tuple(getattr(sim, "score_debuffs", ())),
        # P1-2：手牌减少 / 自尊（与 sim_from_state 双镜）
        hand_decreases=tuple(getattr(sim, "hand_decreases", ())),
        pride_turns=max(int(getattr(sim, "pride_turns", 0)), 0),
        # P1-4：低下状态无效（与 sim_from_state 双镜）
        nullify_debuff=max(int(getattr(sim, "nullify_debuff", 0)), 0),
        # P1-3：指針固定（与 sim_from_state 双镜）
        lock_stance_turns=max(int(getattr(sim, "lock_stance_turns", 0)), 0),
        lock_stance_fresh=bool(getattr(sim, "_lock_stance_fresh", False)),
        modifiers=tuple(
            sorted(
                (str(key), tuple(tuple(entry) for entry in entries))
                for key, entries in getattr(sim, "modifiers", {}).items()
            )
        ),
        cost_reduction=max(int(getattr(sim, "cost_reduction", 0)), 0),
        cost_increase=max(int(getattr(sim, "cost_increase", 0)), 0),
        half_cost_turns=max(int(getattr(sim, "half_cost_turns", 0)), 0),
        double_cost_turns=max(int(getattr(sim, "double_cost_turns", 0)), 0),
        extra_turns=max(int(getattr(sim, "extra_turns_pending", 0)), 0),
        extra_turns_granted=max(int(getattr(sim, "extra_turns_granted", 0)), 0),
        drinks=tuple(getattr(config, "drinks", ()) if config else ()),
        drink_uses=tuple(
            max(int(uses), 0) for uses in getattr(sim, "drink_uses", ())
        ),
        drinks_used_this_turn=max(int(getattr(sim, "drinks_used_this_turn", 0)), 0),
        drinks_per_turn=getattr(config, "drinks_per_turn", None) if config else None,
        card_uses=tuple(sorted(card_uses.items())),
    )


def reshuffle_from_sim(sim: Any) -> ReshuffleFn:
    """用 ``LessonSim.rng`` 的**当前状态**造一个纯重洗钩子（不推进 ``sim.rng``）。

    ``LessonSim`` 抽牌是 ``deck.pop()``（尾部）：牌堆抽空时把弃牌堆直接 shuffle
    再从尾部 pop，所以**重洗后的抽牌顺序 = reversed(shuffled_discard)**。
    钩子只在模拟器真正重洗前（期间不消耗 rng）与真实重洗完全一致；同一局多次
    重洗时每次都按同一快照算（第二次起可能不准，考试里通常只重洗一次）。
    """
    rng_state = sim.rng.getstate()

    def reshuffle(grave: tuple[CardSpec, ...]) -> list[CardSpec]:
        rng = random.Random()
        rng.setstate(rng_state)
        cards = list(grave)
        rng.shuffle(cards)
        return list(reversed(cards))

    return reshuffle
