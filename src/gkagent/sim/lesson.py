"""无画面课程模拟器：只做数值推演，不渲染、不截图。

用来在离线环境里快速跑课程，为出牌参数（体力预算 / buff 优先级 / 跳过阈值）
做扫描和自对弈。模型按 ``data/knowledge/mechanics.md`` 的课程规则做简化：

- 一节课 ``turns`` 回合，体力**整节课共享、回合间不回复**；
- 每回合从洗好的牌库抽 ``hand_size`` 张；打出的牌进弃牌堆，牌库抽空后
  把弃牌堆洗回牌库（近似真机）；
- 一回合内可以连续出牌，直到 SKIP；手牌打完则本回合自动结束；
- 出牌先按**当前** buff 算分，再结算这张卡自带的 buff（本牌不享受自己刚加的 buff）；
- ``ExamCardDraw``：出牌后立即抽 N 张（``CardSpec.draw``），牌库空则把弃牌堆
  洗回牌库再抽（刚打出的牌在抽牌之后才进弃牌堆，所以抽不到自己）；
- ``ExamReview``：叠好印象层数（``CardSpec.impression``）；**回合结束**先按当前
  层数加分（``score += 层数``），再把层数 -1（最低 0）；
- ``ExamLessonDependExamReview``：依赖好印象的分数，按出牌**前**的层数算
  ``int(层数 × 倍率 / 100)``（倍率 1000 = 层数×10）。卡表没给出更细的结算
  顺序，这里沿用"本牌不享受自己刚加的 buff"的保守规则：本牌自带的
  ``impression`` 在算完依赖分之后才生效；这部分分数也不吃好调/集中倍率；
- 回合结束：好印象按当前层数加分并 -1，好调回合数 -1；
- 分数向下取整（``math.floor``）；
- 体力不足以支付牌库里**任何**一张牌时本局提前结束（``done``）。

数值注入：卡面数值直接写在 ``CardSpec`` 的 ``score`` / ``condition`` 等字段里。
读 ``card_table.json`` 的一方把解析出的数值填进 ``CardSpec`` 即可，不需要改卡表。

接口约定：``legal_actions()`` / ``step(action)`` 里的 ``Action`` 是
**手牌下标（int）或 None**，``None`` 表示 SKIP（结束本回合）。
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

__all__ = [
    "Action",
    "Buffs",
    "CardSpec",
    "LessonConfig",
    "LessonSim",
    "Policy",
    "greedy_policy",
]

# 一个合法动作：手牌下标，或 None = SKIP（结束本回合）
Action: TypeAlias = int | None
Policy: TypeAlias = Callable[["LessonSim"], Action]

# 防止策略写出死循环（例如全 0 费抽牌卡无限过牌）时的安全阀
_MAX_STEPS = 10_000


@dataclass(frozen=True)
class CardSpec:
    """一张牌的静态数值。

    ``score`` 是卡面打分数值（不含集中/好调）；``condition`` 是这张牌给的
    好调回合数，``focus`` 是集中层数，``impression`` 是好印象层数，
    ``draw`` 是出牌后额外抽几张。``impression_scale`` 是"依赖好印象的分数"
    倍率（百分比，1000 = 每层 10 分，见 ``ExamLessonDependExamReview``）。
    ``vitality`` / ``motivation`` 分别是元气（盾）和干劲（元气获得量加成）。
    """

    name: str
    cost: int
    score: float
    vitality: int = 0
    condition: int = 0
    focus: int = 0
    motivation: int = 0
    impression: int = 0
    draw: int = 0
    impression_scale: int = 0


@dataclass(frozen=True)
class LessonConfig:
    """一节课的配置：回合数、初始体力、审查基准、每回合手牌数。"""

    turns: int
    stamina: int
    target_clear: int
    target_perfect: int | None = None
    hand_size: int = 3


@dataclass
class Buffs:
    """课程内会衰减的 buff。"""

    condition_turns: int = 0  # 好调剩余回合
    focus: int = 0  # 集中层数（永久）
    impression: int = 0  # 好印象层数（回合结束加分后 -1）


class LessonSim:
    """单局课程模拟器：同 seed 完全可复现。"""

    def __init__(
        self,
        deck: list[CardSpec],
        config: LessonConfig,
        rng_seed: int = 0,
    ) -> None:
        self.config = config
        self.rng_seed = rng_seed
        self.rng = random.Random(rng_seed)

        self.deck: list[CardSpec] = list(deck)
        self.rng.shuffle(self.deck)
        self.discard: list[CardSpec] = []
        self.hand: list[CardSpec] = []

        self.score: int = 0
        self.stamina: int = config.stamina
        self.turns_left: int = config.turns
        self.buffs = Buffs()

        # 元气 / 干劲：课程里没有对手伤害，元气只累积（留给考试模拟用）
        self.vitality: int = 0
        self.motivation: int = 0

        # 牌库会无限洗回，所以"体力付不起任何牌"是永久性的终端条件
        self._min_cost = min((card.cost for card in self.deck), default=0)

        self._draw_hand()

    # ------------------------------------------------------------------ 状态
    @property
    def done(self) -> bool:
        """回合用尽，或体力已经付不起牌库里任何一张牌。"""
        return self.turns_left <= 0 or self.stamina < self._min_cost

    @property
    def result(self) -> str:
        """按当前分数给出评价；``target_perfect`` 为 None 时永远不会 PERFECT。"""
        if self.config.target_perfect is not None and self.score >= self.config.target_perfect:
            return "PERFECT"
        if self.score >= self.config.target_clear:
            return "CLEAR"
        return "FAILED"

    def legal_actions(self) -> list[Action]:
        """当前能出的手牌下标 + SKIP（None，固定在最后）。"""
        if self.done:
            return []
        actions: list[Action] = [
            index for index, card in enumerate(self.hand) if card.cost <= self.stamina
        ]
        actions.append(None)
        return actions

    # ------------------------------------------------------------------ 一步
    def step(self, action: Action) -> None:
        """执行一个动作。

        - 传手牌下标：出牌 → 扣体力 → 算分 → 结算本牌 buff → 抽牌；
          手牌打完则自动结束本回合。
        - 传 ``None``：SKIP，直接结束本回合。
        """
        if self.done:
            raise RuntimeError("本局已经结束，不能再 step")
        if action is None:
            self._end_turn()
            return
        if isinstance(action, bool) or not isinstance(action, int):
            raise TypeError(f"action 必须是手牌下标或 None：{action!r}")
        if not 0 <= action < len(self.hand):
            raise ValueError(f"手牌下标越界：{action}")
        card = self.hand[action]
        if card.cost > self.stamina:
            raise ValueError(f"体力不足：{card.name} 需要 {card.cost}，当前 {self.stamina}")

        self.hand.pop(action)
        self.stamina -= card.cost
        self.score += self._card_award(card)
        self._apply_card_buffs(card)
        if card.draw > 0:
            self._draw(card.draw)
        self.discard.append(card)

        # 体力见底：本局提前结束（不再结算回合末）
        if self.done:
            return
        # 手牌打空：本回合自然结束
        if not self.hand:
            self._end_turn()

    def run(self, policy: Policy) -> tuple[int, str]:
        """跑完整一局，返回 ``(score, grade)``。"""
        steps = 0
        while not self.done:
            self.step(policy(self))
            steps += 1
            if steps > _MAX_STEPS:
                raise RuntimeError(f"策略在 {_MAX_STEPS} 步内没有结束本局（疑似死循环）")
        return self.score, self.result

    # ------------------------------------------------------------------ 内部
    def _card_award(self, card: CardSpec) -> int:
        """本牌的得分：``(score + focus) × 好调倍率`` + 好印象依赖分，向下取整。

        纯 buff 牌（``score <= 0``）不参与集中/好调加成；但如果有
        ``impression_scale``，仍然按**出牌前**的好印象层数结算依赖分：
        ``int(层数 × impression_scale / 100)``。依赖分不吃好调/集中，
        因为卡表没给出这部分是否参与倍率结算，取保守做法。
        """
        award = 0
        if card.score > 0:
            multiplier = 1.5 if self.buffs.condition_turns > 0 else 1.0
            award = math.floor((card.score + self.buffs.focus) * multiplier)
        if card.impression_scale > 0 and self.buffs.impression > 0:
            award += int(self.buffs.impression * card.impression_scale / 100)
        return award

    def _apply_card_buffs(self, card: CardSpec) -> None:
        """结算卡面 buff（在算分之后，所以本牌不吃自己刚加的 buff）。"""
        self.buffs.condition_turns += card.condition
        self.buffs.focus += card.focus
        self.buffs.impression += card.impression
        if card.vitality > 0:
            # 干劲提升元气获得量（课程里元气只累积，没有消耗方）
            self.vitality += card.vitality + self.motivation
        self.motivation += card.motivation

    def _end_turn(self) -> None:
        """回合结束：结算好印象、衰减好调、弃手牌、抽下一手。

        好印象的结算顺序固定为**先加分、再减层**：本回合按完整层数拿分，
        下一回合才少一层；这样 N 层在剩余 T 回合里的总分是 N+(N-1)+…。
        """
        if self.buffs.impression > 0:
            self.score += self.buffs.impression
            self.buffs.impression -= 1
        if self.buffs.condition_turns > 0:
            self.buffs.condition_turns -= 1

        self.discard.extend(self.hand)
        self.hand.clear()
        self.turns_left -= 1
        if self.turns_left > 0:
            self._draw_hand()

    def _draw_hand(self) -> None:
        self.hand.clear()
        self._draw(self.config.hand_size)

    def _draw(self, count: int) -> None:
        for _ in range(count):
            card = self._draw_one()
            if card is None:
                break
            self.hand.append(card)

    def _draw_one(self) -> CardSpec | None:
        if not self.deck:
            if not self.discard:
                return None
            self.deck = self.discard
            self.discard = []
            self.rng.shuffle(self.deck)
        return self.deck.pop()


def greedy_policy(sim: LessonSim) -> Action:
    """基线策略：能出的牌里挑 ``分数 / 体力`` 最高的，都出不起就 SKIP。

    只按卡面分数算，不评估 buff 收益，也不做体力预算——仅用于验证模拟器
    能跑通、给参数搜索当对照基线。
    """
    playable = [index for index in sim.legal_actions() if index is not None]
    if not playable:
        return None

    def efficiency(index: int) -> tuple[float, float, int, int]:
        card = sim.hand[index]
        # 0 费牌按 1 费算，避免"1 分 0 费"霸榜
        return (card.score / max(card.cost, 1), card.score, -card.cost, -index)

    return max(playable, key=efficiency)
