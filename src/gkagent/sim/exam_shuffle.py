"""考试洗牌重放模型（2026-11-21 破解，四场实机验证）。

客户端考试随机数是 xorshift32（与社区 gakumas_exam.rng 的 NativeRandom 一致）。

**考试开局的 RNG 消耗顺序**（StepAuditionStart → 第 1 回合发牌前）：

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
* 牌堆抽空时客户端会洗弃牌堆，那一段依赖弃牌/失落区的顺序，本模块不建模。
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
      （客户端此时会洗弃牌堆，超出本模型，故到此为止）。
    """
    rng = NativeRandom(seed)
    for _ in range(k):
        rng.advance()
    remaining = list(deck)
    shuffle(remaining, rng)

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
