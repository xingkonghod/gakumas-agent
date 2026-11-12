"""期末考试估分：按当前手牌/道具，蒙特卡洛模拟 N 局，给出期望分数。

游戏规则简化假设（都有实测依据，后续可校准）：
- 每回合摸 3 张手牌（课程/考试实测手牌数）
- 每回合能量从 100 起、回合结束回 60（考试实测 +60）
- 每张牌消耗 = 卡面费用；只要能量够就能打
- 一张牌的得分 = 卡库按效果文本算出的价值（打分 N 的 N 附近）
- 贪心打法：每回合按「价值/费用」从高到低打，能量不够就跳过

用途：期末前估算「能打多少分」；第一把打完若明显低于期望，就走免费重开。
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class SimCard:
    name: str
    value: float
    cost: int


@dataclass(frozen=True)
class ExamEstimate:
    mean: float
    p10: float
    p90: float
    trials: int

    def __str__(self) -> str:
        return f"mean={self.mean:.1f} p10={self.p10:.1f} p90={self.p90:.1f} (n={self.trials})"


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return float(ordered[index])


def simulate_once(
    cards: list[SimCard],
    turns: int,
    *,
    draw: int = 3,
    energy_start: int = 100,
    energy_per_turn: int = 60,
    rng: random.Random | None = None,
) -> float:
    """模拟一局考试，返回总分。"""
    if not cards or turns <= 0:
        return 0.0
    rng = rng or random.Random()
    deck = list(cards)
    rng.shuffle(deck)
    hand: list[SimCard] = []
    score = 0.0
    energy = energy_start

    def draw_hand() -> None:
        while len(hand) < draw and deck:
            hand.append(deck.pop())
        while len(hand) < draw:
            hand.append(SimCard("空", 0.0, 0))

    draw_hand()
    for _turn in range(turns):
        playable = sorted(
            (card for card in hand if card.cost <= energy),
            key=lambda card: (card.value / max(card.cost, 1), card.value),
            reverse=True,
        )
        for card in playable:
            if card.cost > energy:
                continue
            energy -= card.cost
            score += card.value
            hand.remove(card)
        energy += energy_per_turn
        draw_hand()
    return score


def estimate_score(cards: list[SimCard], turns: int, trials: int = 15, seed: int | None = None, **kwargs) -> ExamEstimate:
    rng = random.Random(seed)
    scores = [simulate_once(cards, turns, rng=rng, **kwargs) for _ in range(max(1, trials))]
    return ExamEstimate(
        mean=sum(scores) / len(scores),
        p10=_percentile(scores, 0.1),
        p90=_percentile(scores, 0.9),
        trials=len(scores),
    )
