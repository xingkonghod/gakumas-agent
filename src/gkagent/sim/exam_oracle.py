"""考试牌序全知：从 seed + 牌堆推出整段牌序（完全信息搜索的数据源）。

考试随机数模型见 :mod:`gkagent.sim.exam_shuffle`。本模块把它包成「边打边推」的接口：

* :func:`initial_shuffled_deck` —— 开局消耗 K 次随机数 + Fisher-Yates 后，牌堆的真实顺序
  （下标 0 = 牌堆顶 = 下一张抽到的牌）；
* :class:`ExamDrawOracle` —— 维护当前牌堆顺序和考试 RNG 状态，每回合告诉调用方抽到的牌；
  牌堆抽空时用调用方给的真实弃牌堆顺序（grave，进弃牌堆的先后）重洗。

拿到牌序后，搜索侧把顺序写进 ``ExpectState.known_draw``（``expectimax`` 的抽牌机会节点会
退化成确定分支，见 ``state_from_sim(known_deck_order=True)`` / ``ExpectState.known_draw``）。

用法::

    oracle = ExamDrawOracle(
        seed, deck, config_turns,
        supports=[{"id": ..., "filter": 1, "permil": 91}, ...],
        initial_keys={("p_card-02-men-2_054", 0)},
    )
    for turn in range(1, played_turns + 1):
        hand = oracle.draw_next_turn(turn_parameter_type, grave=grave_order_if_deck_empty)

数据来源（一遍实机采集）：
``StepAuditionStart`` 响应里的 ``examSeedValue``（field 600）、本局牌组
（``userProduceProgressProduceCardList``）、支援卡列表（field 256246388，服务器已算好 permil）、
主数据里的 ``isInitial`` / ``playMovePositionType`` / 「有没有 upgrade+1 变体」。
"""

from __future__ import annotations

from .exam_shuffle import (
    DEFAULT_HAND_LIMIT,
    DEFAULT_NPC_COUNT,
    DEFAULT_TURN_START_DISTRIBUTE,
    Card,
    k_before_shuffle,
    opening_deck_and_rng,
    reshuffle_grave,
    support_upgrade,
)


def initial_shuffled_deck(
    seed: int,
    deck: list[Card],
    config_turns: int,
    npc_count: int = DEFAULT_NPC_COUNT,
) -> list[Card]:
    """开局洗出的牌堆真实顺序（第 0 张 = 牌堆顶）。

    ``config_turns`` 是**配置回合数**（中间考试 forceEndScore 提前结束时也按配置回合算 K）。
    """
    _rng, shuffled = opening_deck_and_rng(
        seed, list(deck), k_before_shuffle(config_turns, npc_count)
    )
    return shuffled


class ExamDrawOracle:
    """考试抽牌全知：维护牌堆真实顺序 + 考试 RNG 状态（支援强化掷点会推进 RNG）。

    一局考试用一个实例；每回合开始时调 :meth:`draw_next_turn`，把返回的手牌交给引擎。
    实例内部只做「抽牌 + 支援强化掷点」，不做出牌决策；重洗需要的弃牌堆顺序由调用方传入。
    """

    def __init__(
        self,
        seed: int,
        deck: list[Card],
        config_turns: int,
        *,
        npc_count: int = DEFAULT_NPC_COUNT,
        supports: list[dict] | None = None,
        initial_keys: frozenset[Card] = frozenset(),
        turn_start_distribute: int = DEFAULT_TURN_START_DISTRIBUTE,
        hand_limit: int = DEFAULT_HAND_LIMIT,
        upgradeable=None,
    ) -> None:
        self._rng, self._deck = opening_deck_and_rng(
            seed, list(deck), k_before_shuffle(config_turns, npc_count)
        )
        self._supports = list(supports or ())
        self._initial_keys = frozenset(initial_keys)
        self._turn_start_distribute = max(int(turn_start_distribute), 0)
        self._hand_limit = max(int(hand_limit), 1)
        self._upgradeable = upgradeable
        self._turn = 0

    @property
    def turn(self) -> int:
        """已经抽过牌的回合数（0 = 考试还没开始）。"""
        return self._turn

    @property
    def remaining(self) -> list[Card]:
        """当前牌堆剩下的牌的真实顺序（下标 0 = 牌堆顶）。"""
        return list(self._deck)

    @property
    def rng_state(self) -> int:
        """当前考试 RNG 状态（uint32），便于和实机核对/续跑。"""
        return self._rng.state

    def peek(self, count: int) -> list[Card]:
        """看牌堆顶接下来 ``count`` 张（不消耗、不推进 RNG）。"""
        return list(self._deck[: max(int(count), 0)])

    def draw_next_turn(self, parameter_type: int, *, grave: list[Card] | None = None) -> list[Card]:
        """抽下一回合的手牌并结算支援强化掷点。

        * 第 1 回合先 ``SetInitialCard``（isInitial 卡从牌堆底→顶扫入手，超手牌上限的接回牌堆底），
          再补抽到 ``turn_start_distribute`` 张；两批各自判支援强化（共用本回合的已用集合）；
        * 第 2 回合起从牌堆顶抽 ``turn_start_distribute`` 张；
        * 抽到一半牌堆空了：用 ``grave``（进弃牌堆的先后顺序）重洗牌堆后继续抽；
          不给 ``grave`` 且牌堆不够抽时抛 ``ValueError``。
        * ``parameter_type``：本回合属性 1 Vo / 2 Da / 3 Vi（支援强化 filter 用）。
        """
        if self._turn >= 100:  # pragma: no cover - 防御死循环
            raise RuntimeError("回合数异常（>100）")
        self._turn += 1
        initial_batch: list[Card] = []
        drawn_batch: list[Card] = []
        if self._turn == 1:
            overflow: list[Card] = []
            for card in reversed(list(self._deck)):
                if card not in self._initial_keys:
                    continue
                self._deck.remove(card)
                if len(initial_batch) < self._hand_limit:
                    initial_batch.append(card)
                else:
                    overflow.append(card)
            self._deck.extend(overflow)
            need = max(0, self._turn_start_distribute - len(initial_batch))
        else:
            need = self._turn_start_distribute
        for _ in range(need):
            if not self._deck:
                if grave is None:
                    raise ValueError(
                        "牌堆已空，抽牌需要洗弃牌堆：请传 grave（进弃牌堆先后顺序）"
                    )
                self._deck = reshuffle_grave(self._rng, grave)
            drawn_batch.append(self._deck.pop(0))
        # 支援强化掷点：两批各自判一次，共用本回合的「已成功支援」集合
        if self._supports:
            used: list[str] = []
            for batch in (initial_batch, drawn_batch):
                if batch:
                    support_upgrade(
                        self._rng,
                        batch,
                        self._supports,
                        parameter_type,
                        used=used,
                        upgradeable=self._upgradeable,
                    )
        return initial_batch + drawn_batch
