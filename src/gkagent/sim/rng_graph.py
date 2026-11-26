"""M1 考试 RNG 消费图（clean-room 自写，阶段1）。

整场考试只有一条 xorshift32 随机数流。本模块把「哪些效果消费随机数、消费几次、
用什么宽度」整理成一张**消费图**，供洗牌 K 计数 / ``known_draw`` 全知门使用。

来历与边界
----------
* 原语（xorshift32 13/17/5、``range`` 乘法高 32 位、``signed_key`` 异或符号位）与
  :mod:`gkagent.sim.exam_shuffle` 的 ``NativeRandom`` 完全一致，已四场实机 + 探针①
  逐位核对（见 ``out/_engine_gap_report.md`` §③.1）。本模块独立自写，不拷任何参考源码。
* 消费次数公式来自**黑盒探针①**（``data/_engine_probe_rng_p1.jsonl``，9 局 unknown=0）
  与莉波 H.I.F 实机样本（``data/_rinami_live`` W7/W9，Frida 逐决策 rng）。AGPL 引擎
  （``data/GKMSMainWheel``）只作外部 oracle 对照，BSD-3 参考只对口径，**均未拷入本文件**。
* 饮料消费入口划归 M6（drink-model）：本模块只留 :class:`DrinkConsumptionHook` 扩展点，
  不实现饮料消费（见 ``consume_drink``）。

消费点覆盖（探针①黑盒结论）
--------------------------
==========================================  ==========================================
消费点                                      消费次数
==========================================  ==========================================
开局回合属性 / NPC / 初始洗牌               见 exam_shuffle（F0 已对齐，不在本模块重做）
弃牌堆重洗 reshuffle                        (弃手牌后 grave 数) − 1
支援强化掷点 support_rolls                  每张入手牌 × 合格支援（回合属性门控 + 本回合未用）
确定式生成入牌堆随机位 create_deck_random   每卡恰 1 次 range(0, 插入前牌堆长)；空堆 width=0 仍消费 1
确定式生成（DECK_FIRST/HAND/GRAVE）         0
随机选取移动 move（search order=Random）    2×nf signed_key（出牌中 nf 次丢弃 + nf 次排序）
随机选取移动 move（pick=Random）            1 次 count roll + nf signed_key
选择/确定式移动 move（select/hold）         0
panic（type78）回合开始                     每手牌 1 次 range(0, 候选数)，费用覆盖 1 回合
type59/38/156/22（费用变化/计数 buff/成长/附魔安装）  0
==========================================  ==========================================

每次 ``range`` / ``signed_key`` 调用恰推进 1 次状态（先取旧状态算值，再 xorshift32 推进）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

MASK32 = 0xFFFFFFFF
SIGN_BIT = 0x80000000

# 考试设置 ``p_exam_setting-1`` 的 panic 费用候选（主数据 produceExamPanicStaminaCandidates）。
PANIC_STAMINA_CANDIDATES: tuple[int, ...] = (
    1, 2, 3, 4, 5, 6, 7, 7, 8, 8, 9, 9, 10, 11, 12, 13, 14, 15,
)


# --------------------------------------------------------------------------- 原语
def xorshift32_next(state: int) -> int:
    """xorshift32 (13, 17, 5) 单步推进，返回新状态（32 位无符号）。"""
    x = state & MASK32
    x ^= (x << 13) & MASK32
    x ^= x >> 17
    x ^= (x << 5) & MASK32
    return x & MASK32


def rng_steps_between(before: int, after: int, cap: int = 200000) -> int | None:
    """从 ``before`` 正向迭代到 ``after`` 的步数（消费次数）；找不到返回 None。

    与探针 ``_engine_probe_rng.rng_steps`` 同口径，用于把实机/引擎前后状态差换算成消费次数。
    """
    if before == after:
        return 0
    s = before & MASK32
    target = after & MASK32
    for i in range(1, cap + 1):
        s = xorshift32_next(s)
        if s == target:
            return i
    return None


class RngStream:
    """考试随机数流替身：每次取值调用恰推进 1 次。

    * :meth:`range` ``lo + ((old_state * width) >> 32)``，``width == 0`` 仍推进、返回 ``lo``。
    * :meth:`signed_key` ``old_state ^ 0x80000000``（排序用带符号键的无符号表示），推进 1 次。
    * :meth:`advance` 只推进、返回旧状态（开局 NPC/回合属性占位推进用）。
    """

    __slots__ = ("state", "calls")

    def __init__(self, state: int) -> None:
        self.state = state & MASK32
        self.calls = 0

    def advance(self) -> int:
        old = self.state
        self.state = xorshift32_next(old)
        self.calls += 1
        return old

    def range(self, lo: int, hi: int) -> int:
        """[lo, hi) 整数；``hi == lo`` 时仍消耗一次（width=0 → lo）。"""
        old = self.advance()
        width = (hi - lo) & MASK32
        return lo + ((old * width) >> 32)

    def signed_key(self) -> int:
        """排序键：旧状态异或符号位后**按带符号 int32 解释**（升序排序用）。

        客户端 ``rng_signed_key`` 返回 ``v = state ^ 0x80000000`` 的带符号值
        （``v < 0x80000000 ? v : v - 2^32``）；排序按带符号升序。推进 1 次。
        """
        old = self.advance()
        v = old ^ SIGN_BIT
        return v if v < SIGN_BIT else v - (1 << 32)


# --------------------------------------------------------------------------- 消费事件
@dataclass(frozen=True)
class RngEvent:
    """消费图里的一次消费事件（用于 ledger / 回归核对）。

    ``kind`` 取值：``reshuffle`` / ``support`` / ``create_deck_random`` /
    ``move_search_random`` / ``move_pick_random`` / ``panic`` / ``advance``。
    ``count`` 是该事件推进状态的次数；``detail`` 记录宽度/候选数等上下文。
    """

    kind: str
    count: int
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ConsumptionGraph:
    """消费 ledger：按顺序记录事件，可累计消费次数 / 复现状态序列。"""

    events: list[RngEvent] = field(default_factory=list)

    def record(self, kind: str, count: int, **detail: Any) -> RngEvent:
        ev = RngEvent(kind, count, dict(detail))
        self.events.append(ev)
        return ev

    @property
    def total(self) -> int:
        return sum(ev.count for ev in self.events)

    def states_from(self, start: int) -> list[int]:
        """从 ``start`` 起按各事件消费次数正向迭代，返回每个事件**之后**的状态。"""
        out: list[int] = []
        s = start & MASK32
        for ev in self.events:
            for _ in range(ev.count):
                s = xorshift32_next(s)
            out.append(s)
        return out


# --------------------------------------------------------------------------- 消费节点
def reshuffle(stream: RngStream, grave_count: int, graph: ConsumptionGraph | None = None) -> int:
    """弃牌堆重洗：Fisher-Yates 倒序，消费 ``grave_count - 1`` 次（ grave 为空则 0）。

    返回消费次数。重洗发生在牌堆抽空、把弃牌堆（弃手牌后）洗入牌堆时。
    """
    n = max(0, grave_count - 1)
    for k in range(grave_count, 1, -1):
        stream.range(0, k)
    if graph is not None:
        graph.record("reshuffle", n, grave_count=grave_count)
    return n


def support_rolls(
    stream: RngStream,
    added: Sequence[Any],
    supports: Sequence[Mapping[str, Any]],
    parameter_type: int,
    *,
    used: list[Any] | None = None,
    upgradeable=None,
    graph: ConsumptionGraph | None = None,
) -> tuple[list[tuple], int]:
    """支援强化掷点：每张入手牌 × 合格支援掷一次 ``range(0, 1000)``。

    与 :func:`exam_shuffle.support_upgrade` 同口径（F0 已对齐）：外层入手顺序、内层支援顺序；
    无下一级变体整张跳过；``filter`` 非 0/None 且 ≠ 本回合属性不掷；命中（roll < permil）后
    该支援本回合不再参与。返回 ``(成功列表, 掷点次数)``。本模块独立自写一份供图使用。
    """
    used = used if used is not None else []
    planned: list[tuple] = []
    rolls = 0
    for card in added:
        if upgradeable is not None and not upgradeable(card):
            continue
        for support in supports:
            sid = support["id"]
            if sid in used:
                continue
            filt = support.get("filter") or 0
            if filt != 0 and filt != parameter_type:
                continue
            rolls += 1
            if stream.range(0, 1000) < support["permil"]:
                used.append(sid)
                planned.append((card, sid))
    if graph is not None:
        graph.record("support", rolls, parameter_type=parameter_type, n_added=len(added))
    return planned, rolls


def create_deck_random(
    stream: RngStream, deck_len: int, count: int = 1, graph: ConsumptionGraph | None = None
) -> list[int]:
    """确定式生成入牌堆随机位（ExamCardCreateId type6，move=DECK_RANDOM）。

    每卡恰 1 次 ``range(0, 插入前牌堆长)``，且是该效果首次 RNG 调用；空堆 width=0 仍消费 1 次
    → index 0。批量生成时每卡都对**插入前**牌堆长取样（与客户端 batch 同口径），返回各卡插入位。
    """
    indices: list[int] = []
    for _ in range(max(0, count)):
        indices.append(stream.range(0, deck_len))
    if graph is not None:
        graph.record("create_deck_random", len(indices), deck_len=deck_len, n_cards=count)
    return indices


def move_search_random(
    stream: RngStream, nf: int, *, playing: bool = True, graph: ConsumptionGraph | None = None
) -> list[int]:
    """随机选取移动的**搜索阶段**（search orderType=Random）：消费 ``2×nf`` 次 signed_key。

    出牌中（``playing=True``）先对 nf 个候选各掷一次「丢弃键」，再各掷一次排序键；
    非出牌上下文（``playing=False``）只掷 nf 次排序键。返回排序键列表（升序排序用）。
    """
    if playing:
        for _ in range(nf):
            stream.signed_key()
    keys = [stream.signed_key() for _ in range(nf)]
    if graph is not None:
        graph.record("move_search_random", (2 * nf if playing else nf), nf=nf, playing=playing)
    return keys


def move_pick_random(
    stream: RngStream, nf: int, pick_min: int, pick_max: int,
    graph: ConsumptionGraph | None = None,
) -> tuple[int, list[int]]:
    """随机选取移动的**选取阶段**（pickRangeType=Random）：1 次 count roll + nf 次 signed_key。

    count = ``range(pick_min, pick_max + 1)``，实际取 ``min(count, nf)``。返回 ``(count, keys)``。
    """
    count = stream.range(pick_min, pick_max + 1)
    keys = [stream.signed_key() for _ in range(nf)]
    if graph is not None:
        graph.record("move_pick_random", 1 + nf, nf=nf, pick_min=pick_min, pick_max=pick_max)
    return count, keys


def panic_tick(
    stream: RngStream, hand_size: int, candidates: Sequence[int] = PANIC_STAMINA_CANDIDATES,
    graph: ConsumptionGraph | None = None,
) -> list[int]:
    """panic（type78）激活后回合开始（turn≥2 且抽≥1）：每手牌 1 次 ``range(0, 候选数)``。

    返回每张手牌的费用覆盖值（覆盖 1 回合）。手牌为空则 0 消费。
    """
    fixes: list[int] = []
    n = len(candidates)
    for _ in range(max(0, hand_size)):
        fixes.append(candidates[stream.range(0, n)])
    if graph is not None:
        graph.record("panic", len(fixes), hand_size=hand_size, n_candidates=n)
    return fixes


# --------------------------------------------------------------------------- 全知门分类
# 消费次数已被探针①/实机完全刻画的效果类型 → 消费图可精确计数，不再停用全知。
MODELED_EFFECT_TYPES: frozenset[str] = frozenset(
    {
        "ExamCardCreateId",  # type6：DECK_RANDOM 每卡 1 range；其余确定式 0
        "ExamCardMove",  # type9：random search 2nf / random pick 1+nf / select 0
        "ExamPanic",  # type78：每手牌 1 range
        "ExamPanicCommand",
        "ExamSearchPlayCardStaminaConsumptionChange",  # type59：0 RNG（探针①）
        "ExamCardSearchEffectPlayCountBuff",  # type38：0 RNG（探针①）
        "ExamForcePlayCardSearch",  # 强制出牌：0 RNG（实机 encore / 探针①）
    }
)

# 消费次数尚未完全刻画 → 仍视为风险（保守，不静默放宽）。
UNMODELED_EFFECT_TYPES: frozenset[str] = frozenset(
    {
        "ExamCardCreateSearch",  # type21：随机池生成，消费远多于生成数，未完全探针
        # (c) 探针 data/_m1b_type21_p1（sup-3_024 ×3 题）：cons≈132/135/136，生成卡入手牌（非牌堆，
        # 无 deck 插入），消费与牌堆长无关（3/7/12 无相关）→ 随机池权重/signed_key 口径未刻画，保守保留。
        "ExamReviewPerSearchCount",  # 按搜索次数给好印象：未探针，保守保留
    }
)


def classify_effect(effect_type: str) -> str:
    """把效果类型分成 ``modeled`` / ``unmodeled`` / ``zero``（不在风险清单的确定式效果）。"""
    if effect_type in MODELED_EFFECT_TYPES:
        return "modeled"
    if effect_type in UNMODELED_EFFECT_TYPES:
        return "unmodeled"
    return "zero"


def graph_rng_risks(
    deck: Iterable[Any], *, index: Mapping[str, frozenset[str]] | None = None
) -> list[dict[str, Any]]:
    """消费图口径的风险扫描：只保留含**未刻画**消费点的卡。

    ``index`` 与 :func:`exam_risk.load_extra_rng_index` 同结构（card_id → 效果类型集合）。
    含 modeled 效果（生成/移动/panic/0 RNG 搜索变体）的卡不再算风险；含 unmodeled
    （随机池生成等）的卡仍算风险。返回结构与 ``exam_risk.deck_rng_risks`` 一致。
    """
    from .exam_risk import default_extra_rng_index, _card_id_of

    rng_index = index if index is not None else default_extra_rng_index()
    risks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in deck:
        card_id = _card_id_of(item)
        if not card_id or card_id in seen:
            continue
        hits = rng_index.get(card_id)
        if not hits:
            continue
        unmodeled = sorted(h for h in hits if classify_effect(h) == "unmodeled")
        if not unmodeled:
            continue
        seen.add(card_id)
        risks.append({"card_id": card_id, "effects": unmodeled})
    risks.sort(key=lambda risk: str(risk["card_id"]))
    return risks


def known_info_ok_graph(
    deck: Iterable[Any], *, index: Mapping[str, frozenset[str]] | None = None
) -> bool:
    """消费图口径：牌组是否可启用全知（无未刻画消费点）。"""
    return not graph_rng_risks(deck, index=index)


# --------------------------------------------------------------------------- 饮料扩展点（M6）
class DrinkConsumptionHook(Protocol):
    """饮料消费入口扩展点（M6 drink-model 实现，本模块不实现）。

    实现方接收饮料 id + 当前牌区上下文，返回该饮料消费随机数的事件列表
    （:class:`RngEvent`）。阶段1 只定义接口，W9 饮料步在回归里标 owned-by-drinks 跳过。
    """

    def consume_drink(
        self, drink_id: str, context: Mapping[str, Any], stream: RngStream
    ) -> list[RngEvent]:
        ...


_DRINK_HOOK: DrinkConsumptionHook | None = None


def register_drink_hook(hook: DrinkConsumptionHook | None) -> None:
    """注册饮料消费 hook（M6 接线用）；None 注销。"""
    global _DRINK_HOOK
    _DRINK_HOOK = hook


def consume_drink(
    drink_id: str, context: Mapping[str, Any], stream: RngStream
) -> list[RngEvent]:
    """饮料消费入口：有 hook 则委托，否则返回空（阶段1 不建模饮料消费）。"""
    if _DRINK_HOOK is None:
        return []
    return _DRINK_HOOK.consume_drink(drink_id, context, stream)
