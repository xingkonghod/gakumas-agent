"""课程/试镜出牌策略：用界面上的分数预览 + 体力，做"像人一样"的取舍。

规则（按优先级）：

1. 只用分数预览判断收益——那是游戏自己算好的值，含好调/集中/属性倍率；
2. 按 ``分数 ÷ 体力`` 选牌；0 费牌按 1 费算，避免被"1 分 0 费"骗；
3. 每个回合的体力预算 ≈ ``体力 / 剩余回合``，先给后面的回合留饭；
4. 剩余回合 ≥2 且本回合还没上过 buff 时，先铺一张便宜的 好调/集中（后续牌吃倍率）；
5. 没有正收益的牌就 **SKIP 结束回合**，不要瞎点卡面空转；
6. 已经过了审查基准、剩下的牌又不值几分时，也别再烧体力。

策略只产出"点哪里"，不负责点击的时序（两段式确认由调用方处理）。
"""

from __future__ import annotations

from dataclasses import dataclass

from gkagent.data.buffs import BuffLibrary
from gkagent.data.card_effects import estimate_value
from gkagent.vision.lesson import LessonCard, LessonState, card_value

# 保留给后续回合的体力下限：每剩 1 回合至少留这么多
RESERVE_PER_TURN = 2.0
# 分数预览为 0 且不是 buff 的牌，视为"没用"
NEGLIGIBLE = 0.5


@dataclass(frozen=True)
class LessonAction:
    kind: str  # card / skip / wait
    index: int | None = None
    point: tuple[int, int] | None = None
    reason: str = ""
    expected: float = 0.0
    card: LessonCard | None = None


class LessonPolicy:
    """有状态的出牌策略：跟踪"本回合打了几张、有没有上过 buff"。"""

    def __init__(
        self,
        *,
        buffs: BuffLibrary | None = None,
        buff_first: bool = True,
        min_gain: float = 1.0,
    ) -> None:
        self.buffs = buffs or BuffLibrary.load()
        self.buff_first = buff_first
        self.min_gain = min_gain
        self._last_turns: int | None = None
        self._plays_this_turn = 0
        self._buff_played_this_turn = False

    # ------------------------------------------------------------------ 公共
    def reset(self) -> None:
        self._last_turns = None
        self._plays_this_turn = 0
        self._buff_played_this_turn = False

    def reset_turn(self) -> None:
        """SKIP 之后调用：本回合的计数清零（回合号要等下一帧再同步）。"""
        self._plays_this_turn = 0
        self._buff_played_this_turn = False

    def note_play(self, card: LessonCard | None = None) -> None:
        """调用方真正点出去之后告知，用于回合内计数。"""
        self._plays_this_turn += 1
        if card is not None and card.buff:
            self._buff_played_this_turn = True

    def decide(self, state: LessonState) -> LessonAction:
        self._sync_turn(state.turns_left)
        cards = [card for card in state.cards if card.name or card.score is not None]
        if not cards:
            return LessonAction("wait", reason="没读到手牌")

        stamina = state.stamina
        turns = state.turns_left
        affordable = [
            card
            for card in cards
            if stamina is None or card.cost is None or card.cost <= stamina
        ]
        if not affordable:
            return LessonAction(
                "skip",
                point=state.skip_point,
                reason=f"没有付得起的牌（体力 {stamina}）",
            )

        values = {card.index: self._value(card, turns) for card in affordable}
        budget = self._budget(stamina, turns)

        # 1) 先铺 buff
        buff_action = self._maybe_buff(state, affordable, values, budget)
        if buff_action is not None:
            return buff_action

        # 2) 性价比最高的牌
        best = self._best_score_card(affordable, values, budget, turns)
        if best is None:
            # 分数一个都没读到 ≠ 这些牌没用：读不到数字时打最便宜的，别浪费回合（跳课=不涨属性）
            fallback = self._cheapest_unknown(affordable)
            if fallback is not None:
                return LessonAction(
                    "card",
                    index=fallback.index,
                    point=fallback.point,
                    card=fallback,
                    expected=0.0,
                    reason=f"分数没读到，先打最便宜的「{fallback.name or '卡'}」保成长",
                )
            return LessonAction(
                "skip",
                point=state.skip_point,
                reason="剩下的牌都不值体力",
            )

        card, value = best
        efficiency = value / max(card.cost or 3, 1)
        return LessonAction(
            "card",
            index=card.index,
            point=card.point,
            card=card,
            expected=value,
            reason=(
                f"{card.name or '卡'} 分数{int(value)} / 体力{card.cost if card.cost is not None else '?'}"
                f"（性价比 {efficiency:.1f}，预算 {budget:.0f}）"
            ),
        )

    # ------------------------------------------------------------------ 内部
    def _value(self, card: LessonCard, turns: int | None) -> float:
        # 纯 buff 牌不走"分数"通道，只由 _maybe_buff 决定要不要先铺
        if card.buff:
            return 0.0
        value = card_value(card, turns_left=turns)
        if value <= 0 and card.text:
            value = estimate_value(card.text, turns_left=turns).score
        return value

    def _budget(self, stamina: int | None, turns: int | None) -> float:
        if stamina is None:
            return 99.0
        if not turns or turns <= 1:
            return float(stamina)
        reserve = RESERVE_PER_TURN * (turns - 1)
        return max(float(stamina) - reserve, float(stamina) / max(turns, 1))

    def _maybe_buff(
        self,
        state: LessonState,
        affordable: list[LessonCard],
        values: dict[int, float],
        budget: float,
    ) -> LessonAction | None:
        if not self.buff_first or self._buff_played_this_turn:
            return None
        turns = state.turns_left
        if turns is not None and turns <= 1:
            return None
        buffs = [card for card in affordable if card.buff]
        if not buffs:
            return None
        # 便宜的、能进预算的 buff 优先
        buffs.sort(key=lambda card: (card.cost if card.cost is not None else 9, card.index))
        candidate = None
        for card in buffs:
            cost = card.cost if card.cost is not None else 9
            if cost <= max(budget, 2.0):
                candidate = card
                break
        if candidate is None:
            return None
        # 本回合已经打过牌并且有高收益牌在，就别再上 buff 了
        if self._plays_this_turn > 0:
            return None
        best_score = max((values.get(card.index, 0.0) for card in affordable if not card.buff), default=0.0)
        buff_value = estimate_value(candidate.text, turns_left=turns).score if candidate.text else 6.0
        if best_score >= 5 * max(buff_value, 1.0) and turn_gain_expected(best_score) > 0:
            return None
        return LessonAction(
            "card",
            index=candidate.index,
            point=candidate.point,
            card=candidate,
            expected=buff_value,
            reason=(
                f"先上 buff：{candidate.name or '卡'}（体力 {candidate.cost}，"
                f"等效 {buff_value:.1f}，剩余 {turns} 回合）"
            ),
        )

    @staticmethod
    def _cheapest_unknown(affordable: list[LessonCard]) -> LessonCard | None:
        """分数没读到的牌里挑最便宜的一张（至少让这回合产生成长）。"""
        unknown = [card for card in affordable if card.score is None]
        if not unknown:
            return None
        unknown.sort(key=lambda card: (card.cost if card.cost is not None else 9, card.index))
        return unknown[0]

    def _best_score_card(
        self,
        affordable: list[LessonCard],
        values: dict[int, float],
        budget: float,
        turns: int | None = None,
    ) -> tuple[LessonCard, float] | None:
        scored = [
            (card, values.get(card.index, 0.0))
            for card in affordable
            if values.get(card.index, 0.0) > NEGLIGIBLE
        ]
        if not scored:
            return None
        # 最后一回合：体力不用就是浪费，按总分最大挑（而不是性价比）
        last_turn = turns is not None and turns <= 1
        if last_turn:
            scored.sort(key=lambda item: (item[1], -item[0].index), reverse=True)
            card, value = scored[0]
            return (card, value) if value >= self.min_gain else None
        in_budget = [
            item for item in scored if (item[0].cost or 0) <= budget or item[0].cost is None
        ]
        pool = in_budget or scored
        pool.sort(
            key=lambda item: (
                item[1] / max(item[0].cost or 3, 1),
                item[1],
                -item[0].index,
            ),
            reverse=True,
        )
        card, value = pool[0]
        if value < self.min_gain:
            return None
        return card, value

    def _sync_turn(self, turns: int | None) -> None:
        if turns is None:
            return
        if self._last_turns is None:
            self._last_turns = turns
            return
        if turns != self._last_turns:
            self._last_turns = turns
            self._plays_this_turn = 0
            self._buff_played_this_turn = False


def turn_gain_expected(score: float) -> float:
    """留个钩子：以后按"还差多少分"判断值不值，现在只是把 0 分挡掉。"""
    return float(score)
