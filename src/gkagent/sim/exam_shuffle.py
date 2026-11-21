"""考试洗牌重放模型（2026-11-21 破解，四场实机验证；含弃牌堆重洗 + 支援强化掷点）。

客户端考试随机数是 xorshift32（与社区 gakumas_exam.rng 的 NativeRandom 一致）。
整场考试只有一条随机数流，消耗顺序：

1. **开局**：回合属性 ``turns-3`` 次 + NPC 分数 ``npc_count*turns`` 次，然后洗初始牌堆。
2. **每回合抽牌后**：支援卡考试内临时强化（:func:`support_upgrade`）——
   按「入手顺序 × 支援卡顺序」每对掷一次 ``integer(0, 1000)``，命中（``roll < permil``）
   的支援本回合不再参与；牌不可再强化（主数据没有 ``upgrade+1`` 变体）时整张跳过。
3. **牌堆抽空时**：洗弃牌堆（:func:`reshuffle_grave`，同一个 Fisher-Yates 倒序）。
   弃牌堆顺序 = 卡进弃牌堆的先后：出牌后去 Grave 的牌按出牌顺序 append，
   回合末剩余手牌按手牌顺序 append；``playMovePositionType=Lost`` / ``isEndTurnLost`` 的卡不进弃牌堆。
4. 之后的抽牌照旧从牌堆顶（下标 0）取。

**开局阶段的 RNG 消耗**（StepAuditionStart → 第 1 回合发牌前）：

1. 回合属性：只有前 ``turns - 3`` 个回合随机，最后 3 个回合固定（静态表按 NPC 权重定序）。
   随机方式 = 按前 ``turns - 3`` 回合的属性池逐个「随机取一个并移除」，消耗 ``turns - 3`` 次抽取。
2. NPC 分数：``npc_count`` 个 NPC × ``turns`` 个回合，每对消耗 1 次抽取（共 ``npc_count * turns`` 次）。
3. 洗牌：Fisher-Yates 倒序，消耗 ``len(deck) - 1`` 次抽取。

所以洗牌前已消耗::

    K = (turns - 3) + npc_count * turns

**turns 是配置回合数，不是实战回合数**：中间考试有 ``forceEndScore``，达到封顶分就提前结束，
客户端只上传实战回合的 ``ExamTurnEndLog``，但回合属性和 NPC 分数在开局仍按完整配置回合生成。
例：produce-002 プロ 中间考试配置 9 回合，实战 7 回合到 1700 提前结束，K 仍 = 51（不是 39）。

produce-002 プロ 的 audition 是 5 个 NPC，因此 ``K = 6 * turns - 3``：
9 回合 → K=51、11 回合 → K=63、12 回合 → K=69（四场都整段精确复现）。

**发牌**：

* 第 1 回合先 ``SetInitialCard``：从牌堆「底 → 顶」扫，把 ``isInitial`` 卡按扫描顺序移入手牌
  （超出手牌上限的接到牌堆底），再从牌堆顶补抽到 ``turnStartDistribute`` 张；
* 第 2 回合起每回合从牌堆顶抽 ``turnStartDistribute`` 张；
* 牌堆抽空时客户端会洗弃牌堆（:func:`reshuffle_grave`），重洗前还会先跑完本回合已抽到的牌的
  支援强化（:func:`support_upgrade`）——2026-11-21 三组实机样本逐张复现：
  11-20 期中 T7（45 次掷点 → 9/9）、11-21 期中 T6（29 次 → 6/6）、11-21 期末 T10（46 次 → 9/9）。
"""

from __future__ import annotations

MASK = 0xFFFFFFFF
DEFAULT_TURN_START_DISTRIBUTE = 3
DEFAULT_HAND_LIMIT = 5
DEFAULT_NPC_COUNT = 5

Card = tuple[str, int]


class NativeRandom:
    """客户端 ``NativeRandom`` 替身：xorshift32，``integer`` 取乘法高 32 位。"""

    __slots__ = ("state",)

    def __init__(self, state: int) -> None:
        self.state = state & MASK

    def advance(self) -> int:
        old = self.state
        x = (old ^ (old << 13)) & MASK
        x = (x ^ (x >> 17)) & MASK
        self.state = (x ^ (x << 5)) & MASK
        return old

    def integer(self, low: int, high: int) -> int:
        """返回 [low, high) 的整数；``high == low`` 时仍消耗一次抽取。"""
        return low + ((self.advance() * (high - low)) >> 32)


def shuffle(values: list, rng: NativeRandom) -> None:
    """Fisher-Yates 倒序洗牌（客户端 NativeRandom.shuffle）。"""
    for n in range(len(values), 1, -1):
        j = rng.integer(0, n)
        values[j], values[n - 1] = values[n - 1], values[j]


def k_before_shuffle(turns: int, npc_count: int = DEFAULT_NPC_COUNT) -> int:
    """洗牌前已消耗的随机数个数：回合属性 (turns-3) + NPC 分数 (npc_count*turns)。

    ``turns`` 要传**配置回合数**（中间考试可能因 forceEndScore 提前结束，实战回合数会更少）。
    """
    return max(0, turns - 3) + npc_count * turns


def generate_turn_types(seed: int, pool: list[int]) -> list[int]:
    """从 RNG 起点复现「前 turns-3 回合」的属性顺序（末 3 回合固定，不在 pool 里）。"""
    rng = NativeRandom(seed)
    rest = list(pool)
    out: list[int] = []
    while rest:
        out.append(rest.pop(rng.integer(0, len(rest))))
    return out


def infer_turn_type_pool(turn_types: list[int]) -> list[int] | None:
    """从实机回合属性反推随机池（只用于验证）。

    ``turn_types`` 末尾 3 个是固定的「低权重→高权重」，反过来就是权重降序；
    前面的部分按这个顺序统计各属性个数，得到生成时使用的池。
    """
    if len(turn_types) < 3:
        return None
    order = list(reversed(turn_types[-3:]))
    if sorted(order) != [1, 2, 3]:
        return None
    head = turn_types[:-3]
    counts = {t: head.count(t) for t in (1, 2, 3)}
    return [t for t in order for _ in range(counts[t])]


def opening_deck_and_rng(
    seed: int, deck: list[Card], k: int
) -> tuple[NativeRandom, list[Card]]:
    """考试开局：RNG 先 advance ``k`` 次（回合属性 + NPC 分数），再 Fisher-Yates 洗牌。

    返回 ``(洗牌后的 RNG, 洗后的牌堆)``。后续支援强化掷点、弃牌堆重洗都用这条随机数流。
    """
    rng = NativeRandom(seed)
    for _ in range(k):
        rng.advance()
    shuffled = list(deck)
    shuffle(shuffled, rng)
    return rng, shuffled


def replay_initial_deck(
    seed: int,
    deck: list[Card],
    k: int,
    *,
    initial_keys: frozenset[Card] = frozenset(),
    turn_start_distribute: int = DEFAULT_TURN_START_DISTRIBUTE,
    hand_limit: int = DEFAULT_HAND_LIMIT,
) -> list[list[Card]]:
    """重放「初始牌堆抽完前」的逐回合手牌。

    * ``deck``：考试时刻牌堆，**按 number 升序**（客户端的输入顺序）；
    * ``k``：洗牌前 RNG 消耗次数（用 :func:`k_before_shuffle` 算）；
    * ``initial_keys``：``isInitial`` 的卡（(produceCardId, upgradeCount)）；
    * 返回逐回合手牌；最后回合不足 ``turn_start_distribute`` 张表示牌堆已抽空
      （下一张牌要洗弃牌堆，见 :func:`reshuffle_grave`；若该回合还没抽满就空了，
      说明重洗发生在**回合内**，前几张是原牌堆的）。
    """
    _rng, remaining = opening_deck_and_rng(seed, deck, k)

    turns: list[list[Card]] = []
    turn = 1
    while remaining:
        hand: list[Card] = []
        if turn == 1:
            overflow: list[Card] = []
            for card in reversed(list(remaining)):
                if card not in initial_keys:
                    continue
                remaining.remove(card)
                if len(hand) < hand_limit:
                    hand.append(card)
                else:
                    overflow.append(card)
            remaining.extend(overflow)  # 超出手牌上限的初始卡接到牌堆底
            need = max(0, turn_start_distribute - len(hand))
        else:
            need = turn_start_distribute
        for _ in range(need):
            if not remaining:
                break  # 牌堆已空，下一张要洗弃牌堆
            hand.append(remaining.pop(0))
        if hand:
            turns.append(hand)
        if not remaining:
            break
        turn += 1
        if turn > 100:  # pragma: no cover - 防御死循环
            break
    return turns


def support_upgrade(
    rng: NativeRandom,
    added: list,
    supports: list[dict],
    parameter_type: int,
    *,
    used: list[str] | None = None,
    upgradeable=None,
) -> list[tuple]:
    """支援卡考试内临时强化：**每张入手牌 × 每张支援卡** 掷一次 ``integer(0, 1000)``。

    客户端 `ExamSupportCard` 的规则（社区 gakumas_exam 已对原生核对，2026-11-21 三组实机验证）：

    * 外层按入手顺序，内层按**支援卡列表顺序**（= 编成槽位号 ``number`` 升序）；
    * 卡在主数据里没有 ``upgrade+1`` 变体（已叠满）时整张跳过，不掷；
    * 支援卡 ``filter_parameter_type`` 不是 0/None 且 ≠ 本回合属性时不掷；
    * 命中（``roll < permil``）后该支援**本回合不再参与**（``used`` 里记 id）；
    * 同一张牌可以被多张支援叠强化（每张支援每回合至多成功一次）。

    :param rng: 考试随机数流（会就地消耗）。
    :param added: 本批入手的卡（按入手顺序），元素为可哈希的卡标识（如 ``(id, upgrade)``）。
    :param supports: 支援卡列表，每项 ``{"id": str, "filter": int, "permil": int}``。
    :param parameter_type: 本回合属性 1 Vo / 2 Da / 3 Vi。
    :param used: 本回合已成功的支援 id（就地追加；每回合开头清空）。
    :param upgradeable: ``callable(card) -> bool``，主数据里是否还有下一级变体；None 表示都可强化。
    :return: ``(成功列表, 掷点次数)``；成功列表元素为 ``(card, support_id)``，按判定顺序。
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
            if rng.integer(0, 1000) < support["permil"]:
                used.append(sid)
                planned.append((card, sid))
    return planned, rolls


def reshuffle_grave(rng: NativeRandom, grave: list) -> list:
    """牌堆抽空时洗弃牌堆：对弃牌堆做 Fisher-Yates 倒序洗（同一随机数流），返回洗后的新牌堆顺序。

    ``grave`` 是「进弃牌堆的先后顺序」（出牌后去 Grave 的按出牌顺序 append，回合末剩余手牌按
    手牌顺序 append；Lost 卡不在里面）。客户端洗完后把手牌堆接到牌堆上（此时牌堆为空），
    所以返回顺序就是之后抽牌的顺序（下标 0 = 牌堆顶）。
    """
    cards = list(grave)
    shuffle(cards, rng)
    return cards
