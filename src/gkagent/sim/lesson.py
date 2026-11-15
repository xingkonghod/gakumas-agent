"""无画面课程模拟器：只做数值推演，不渲染、不截图。

用来在离线环境里快速跑课程，为出牌参数（体力预算 / buff 优先级 / 跳过阈值 /
饮料使用）做扫描和自对弈。模型按真机课程界面（720x1280 截图已确认）与
``data/knowledge/mechanics.md`` 的课程规则做简化：

- 一节课 ``turns`` 回合，体力**整节课共享、回合间不回复**；真机开局满体力，
  所以 ``LessonConfig.stamina_max`` 默认取初始体力；
- 每回合从洗好的牌库抽 ``hand_size`` 张，**默认 3 张（与真机一致）**；打出的牌
  进弃牌堆，牌库抽空后把弃牌堆洗回牌库（近似真机）；每回合补满 3 张；
- 一回合内可以连续出牌，直到 SKIP；手牌打完则本回合自动结束；
- 每回合基础可出牌次数 ``plays_per_turn``（默认 3，与标准手牌数一致），本回合
  出牌数达到上限后只能 SKIP；``ExamPlayableValueAdd``（``CardSpec.extra_play``）
  在本回合内追加 +N 次，回合结束清零；
- **元气（盾）**：``ExamBlock`` 产生的元气（``CardSpec.vitality``）**优先抵挡
  出牌体力消耗**——出牌时先扣元气、不够再扣体力（真机语义）。``stamina +
  vitality`` 付不起的牌不合法；依赖元气的分数按**支付牌费前**的元气层数算；
- **SKIP**：结束本回合，手牌进弃牌堆并抽下一手，**本回合剩余牌不回复体力**；
  每次回合末都记进 ``LessonSim.trace``（``skipped=True``；手牌自然打空为
  ``skipped=False``）；
- **饮料**：``LessonConfig.drinks`` 注入 ``DrinkSpec``（真机底部 3 个饮料槽），
  ``use_drink(index)`` 喝一瓶，**每回合最多 1 瓶**（真机限制），每瓶按 ``uses``
  计次、用掉即消耗（``uses=1`` 默认一次性）。效果支持 ``stamina``（回复体力，
  不超过 ``stamina_max``）/ ``focus``（集中 +N）/ ``condition``（好调 N 回合）/
  ``score``（直接加 N 分，不吃倍率）。``DrinkSpec.cost`` 默认 0：真机饮料不耗
  体力，字段保留给自定义饮料；
- 出牌先按**当前** buff 算分，再结算这张卡自带的 buff（本牌不享受自己刚加的 buff）；
- ``ExamCardDraw``：出牌后立即抽 N 张（``CardSpec.draw``），牌库空则把弃牌堆
  洗回牌库再抽（刚打出的牌在抽牌之后才进弃牌堆，所以抽不到自己）；
- ``ExamReview``：叠好印象层数（``CardSpec.impression``）；**回合结束**先按当前
  层数加分（``score += 层数``），再把层数 -1（最低 0）；
- ``ExamLessonDependExamReview``：依赖好印象的分数，按出牌**前**的层数算
  ``int(层数 × 倍率 / 100)``（倍率 1000 = 层数×10）。卡表没给出更细的结算
  顺序，这里沿用"本牌不享受自己刚加的 buff"的保守规则：本牌自带的
  ``impression`` 在算完依赖分之后才生效；这部分分数也不吃好调/集中倍率；
- ``ExamLessonDependBlock``：依赖元气（盾）层数的分数，与好印象依赖分**同构**：
  按出牌**前**（也就是支付牌费前）的元气层数算
  ``int(层数 × 倍率 / 100)``（倍率 1000 = 层数×10），同样不吃好调/集中/指針
  倍率，本牌自带的 ``vitality`` 在算完之后才生效；
- ``parameter_buff``：审查基准加成，近似成"本次打分额外乘
  ``parameter_buff/1000`` 倍"（1500 = ×1.5）。本牌自带的加成叠在**本牌最终分**
  （白值 + 依赖分）上；``parameter_buff_turns > 1`` 时在本回合内持续，同一回合
  后续牌也吃（``turn_parameter_buff``），回合结束清零。注意：卡表里
  ``ExamParameterBuff*`` 的真实语义是「好调/绝好调 N 回合」，解析方
  （``scripts/sim_produce.py``）现在把它映射成 ``condition``；``parameter_buff``
  只由显式数值（``values[0]``）驱动，不再有默认 ×1.5 兜底；
- 非凡指針：分数再乘当前指針倍率（``stance.score_multiplier``）；出牌结算
  最后应用本牌的指針效果（``strong_level`` / ``preservation`` /
  ``full_power_point``），所以**本牌不吃自己刚切的倍率**；``ExamConcentration``
  是卡面「強気変更」，解析成 ``strong_level``（1/2 段階）；
  回合结束调用 ``stance.end_turn`` 结算全力值；
- 回合结束：好印象按当前层数加分并 -1，好调回合数 -1；
- 分数向下取整（``math.floor``）；
- 体力+元气不足以支付牌库里**任何**一张牌、且没有剩余回复饮料时本局提前结束
  （``done``）。真机其实可以继续空回合/喝饮料，这里保留"提前结束"简化。

数值注入：卡面数值直接写在 ``CardSpec`` 的 ``score`` / ``condition`` 等字段里。
读 ``card_table.json`` 的一方把解析出的数值填进 ``CardSpec`` 即可，不需要改卡表。

**未建模（真机有、这里没有；写明影响，避免把简化当成结论）：**

- P 道具 / 角色被动（真机每回合开始触发加分、元气、集中等）：不进课程数值。
  影响：带强力 P 道具的卡组得分被低估；
- 饮料槽位（3 槽）与培育前的饮料配装/获得流程：只按 ``LessonConfig.drinks``
  注入，槽位取舍与商店/事件获得不在模型内；``ProduceSim`` 也尚未配置饮料，
  所以培育级模拟默认没有饮料收益；
- 元气挡伤害：课程没有对手伤害来源，元气只用于抵牌费与依赖分。影响：考试里
  "用盾吃伤害"的场景未建模；
- 饮料/卡牌的其余效果：强化卡牌、生成卡牌、抽牌、回合追加、消耗体力增减、
  干劲、好印象/元气的更多来源等 20+ 种饮料效果没有对应字段（配置时直接报错，
  不会静默当成无用饮料）；好调与绝好调都按 ``condition`` 的 ×1.5 近似；
- 卡牌强化（训练中强化）、偶像固有卡生成、牌序记忆（真机可查看牌堆顺序）：
  影响：强化后的数值和记牌优势不体现；
- 考试专属规则（追击、回合限制、对手行动）：课程模拟器不覆盖。

接口约定：``legal_actions()`` / ``step(action)`` 里的 ``Action`` 是
**手牌下标（int）或 None**，``None`` 表示 SKIP（结束本回合）；饮料是独立接口
``legal_drinks()`` / ``use_drink(index)``，不混进 ``Action``。
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypeAlias

from gkagent.sim.stance import (
    StanceState,
    apply_full_power_point,
    card_stance_effect,
    end_turn,
    score_multiplier,
)

__all__ = [
    "DRINKS_PER_TURN",
    "DRINK_EFFECTS",
    "Action",
    "Buffs",
    "CardSpec",
    "DrinkSpec",
    "LessonConfig",
    "LessonSim",
    "Policy",
    "greedy_policy",
]

# 一个合法动作：手牌下标，或 None = SKIP（结束本回合）
Action: TypeAlias = int | None
Policy: TypeAlias = Callable[["LessonSim"], Action]

# 饮料支持的效果类型（真机饮料的其余 20+ 种效果都未建模，配置时由 DrinkSpec 报错）
DRINK_EFFECTS: tuple[str, ...] = ("stamina", "focus", "condition", "score")
# 真机每回合最多喝 1 瓶（不是每个饮料槽 1 瓶）
DRINKS_PER_TURN = 1

# 防止策略写出死循环（例如全 0 费抽牌卡无限过牌）时的安全阀
_MAX_STEPS = 10_000
# greedy_policy 给指針牌（温存/全力值，通常 score=0）的固定效率，避免永远选不到
_STANCE_CARD_EFFICIENCY = 3.0
# greedy_policy 给「本回合可出牌次数 +N」牌（通常 score=0）的固定效率
_EXTRA_PLAY_CARD_EFFICIENCY = 3.0
# greedy_policy 给「依赖元气分 / 审查基准加成」牌（常常 score=0）的固定效率
_DEPENDENT_CARD_EFFICIENCY = 3.0


@dataclass(frozen=True)
class CardSpec:
    """一张牌的静态数值。

    ``score`` 是卡面打分数值（不含集中/好调/指針）；``condition`` 是这张牌给的
    好调回合数，``focus`` 是集中层数，``impression`` 是好印象层数，
    ``draw`` 是出牌后额外抽几张。``impression_scale`` 是"依赖好印象的分数"
    倍率（百分比，1000 = 每层 10 分，见 ``ExamLessonDependExamReview``）。
    ``vitality`` / ``motivation`` 分别是元气（盾）和干劲（元气获得量加成）。
    ``strong_level`` 是 ``ExamConcentration``（卡面「強気変更」）变更到的
    強気段階（1/2），``preservation`` 是把指針切到温存的段階（1/2），
    ``full_power_point`` 是全力值增量（攒满 10 点后下一回合进入「全力」）。
    ``extra_play`` 是 ``ExamPlayableValueAdd``：出牌后本回合额外可出牌次数 +N
    （默认 0）。``block_scale`` 是"依赖元气的分数"倍率（百分比，1000 = 每层元气
    10 分，见 ``ExamLessonDependBlock``）；``parameter_buff`` 是审查基准加成的
    千分比（1500 = ×1.5），``parameter_buff_turns > 1`` 表示该加成在本回合内
    持续（``ExamParameterBuffMultiplePerTurn``）。
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
    preservation: int = 0
    full_power_point: int = 0
    extra_play: int = 0
    block_scale: int = 0
    parameter_buff: int = 0
    parameter_buff_turns: int = 1
    # ExamConcentration（卡面「強気変更」）的段階：1/2；0 = 不改指針
    strong_level: int = 0


@dataclass(frozen=True)
class DrinkSpec:
    """一瓶饮料（真机底部 3 个饮料槽，每回合最多喝 1 瓶）。

    ``cost`` 是喝这瓶饮料需要支付的体力；真机饮料不耗体力，通常填 0，
    字段保留给自定义/特殊饮料。``effect_type`` 只支持 ``DRINK_EFFECTS``：

    - ``stamina``：回复 ``value`` 点体力（不超过 ``LessonConfig.stamina_max``）；
    - ``focus``：集中 +``value``；
    - ``condition``：好调 +``value`` 回合；
    - ``score``：直接加 ``value`` 分（不吃好调/集中/指針/审查基准倍率）。

    ``uses`` 是这瓶饮料的可使用次数；真机是一次性消耗，默认 1。用完后该槽位
    不可再用（``LessonSim.drink_uses`` 会记 0）。
    """

    name: str
    cost: int
    effect_type: str
    value: int
    uses: int = 1

    def __post_init__(self) -> None:
        if self.effect_type not in DRINK_EFFECTS:
            raise ValueError(
                f"未建模的饮料效果 {self.effect_type!r}：只支持 {DRINK_EFFECTS}"
            )
        if self.cost < 0:
            raise ValueError(f"饮料体力消耗不能为负：{self.cost}")
        if self.value <= 0:
            raise ValueError(f"饮料效果数值必须为正：{self.value}")
        if self.uses < 1:
            raise ValueError(f"饮料使用次数必须 >= 1：{self.uses}")


@dataclass(frozen=True)
class LessonConfig:
    """一节课的配置：回合数、初始体力、审查基准、每回合手牌数、出牌上限、饮料。"""

    turns: int
    stamina: int
    target_clear: int
    target_perfect: int | None = None
    # 真机每回合手里 3 张牌
    hand_size: int = 3
    # 每回合基础可出牌次数（默认 3 = 标准手牌数）；ExamPlayableValueAdd 在此之上追加
    plays_per_turn: int = 3
    # 饮料槽（真机 3 个）；默认空 = 旧行为
    drinks: tuple[DrinkSpec, ...] = ()
    # 体力上限；None = 初始体力（真机课程开局满体力）。饮料回复不会超过它
    stamina_max: int | None = None


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
        # 真机课程开局满体力：没显式给上限时按初始体力当上限
        self.stamina_max: int = (
            config.stamina_max if config.stamina_max is not None else config.stamina
        )
        self.turns_left: int = config.turns
        self.buffs = Buffs()
        # 本回合已出牌数 / 本回合额外可出牌次数（ExamPlayableValueAdd），换手牌时清零
        self.plays_per_turn: int = config.plays_per_turn
        self.plays_this_turn: int = 0
        self.extra_plays: int = 0
        # 非凡指針：温存 / 強気 / 全力 的倍率状态（纯函数模块 stance.py）
        self.stance = StanceState()

        # 元气 / 干劲：元气（ExamBlock）优先抵牌费，也能喂依赖元气的分数
        self.vitality: int = 0
        self.motivation: int = 0
        # 本回合内持续的审查基准加成（ExamParameterBuffMultiplePerTurn），回合结束清零
        self.turn_parameter_buff: int = 0

        # 饮料：每瓶剩余次数（用掉即消耗），每回合最多喝 1 瓶
        self.drink_uses: list[int] = [drink.uses for drink in config.drinks]
        self.drinks_used_this_turn: int = 0
        # 回合级 trace：每次回合结束记一行（含 skipped），便于回放 SKIP 行为
        self.trace: list[dict] = []

        # 牌库会无限洗回，所以"体力+元气付不起任何牌"是永久性的终端条件
        self._min_cost = min((card.cost for card in self.deck), default=0)

        self._draw_hand()

    # ------------------------------------------------------------------ 状态
    @property
    def done(self) -> bool:
        """回合用尽，或体力+元气付不起任何牌、且没有剩余回复饮料。

        真机里面临"这回合一张牌都打不出"时还能喝体力饮料继续；所以只要槽里
        还有未消耗的 ``stamina`` 饮料，就不提前判负（策略仍可选择 SKIP）。
        """
        if self.turns_left <= 0:
            return True
        if self.stamina + self.vitality >= self._min_cost:
            return False
        return not self._has_unused_stamina_drink()

    @property
    def result(self) -> str:
        """按当前分数给出评价；``target_perfect`` 为 None 时永远不会 PERFECT。"""
        if self.config.target_perfect is not None and self.score >= self.config.target_perfect:
            return "PERFECT"
        if self.score >= self.config.target_clear:
            return "CLEAR"
        return "FAILED"

    def legal_actions(self) -> list[Action]:
        """当前能出的手牌下标 + SKIP（None，固定在最后）。

        体力+元气够付牌费就合法；本回合出牌数达到
        ``plays_per_turn + extra_plays`` 后只剩 SKIP。
        """
        if self.done:
            return []
        if self.plays_this_turn >= self.plays_per_turn + self.extra_plays:
            return [None]
        actions: list[Action] = [
            index
            for index, card in enumerate(self.hand)
            if card.cost <= self.stamina + self.vitality
        ]
        actions.append(None)
        return actions

    def legal_drinks(self) -> list[int]:
        """当前能喝的饮料下标（未用完、体力够付 ``cost``、本回合还没喝过）。

        真机限制每回合 1 瓶；``DrinkSpec`` 的 ``uses`` 用完后该下标不再出现。
        """
        if self.done or self.drinks_used_this_turn >= DRINKS_PER_TURN:
            return []
        return [
            index
            for index, (drink, uses) in enumerate(
                zip(self.config.drinks, self.drink_uses)
            )
            if uses > 0 and drink.cost <= self.stamina
        ]

    # ------------------------------------------------------------------ 一步
    def use_drink(self, index: int) -> None:
        """喝一瓶饮料（``index`` 是 ``LessonConfig.drinks`` 的下标）。

        - 每回合最多 1 瓶（``DRINKS_PER_TURN``），喝过再喝报 ``ValueError``；
        - 按 ``DrinkSpec.uses`` 消耗次数，用完后该槽位不可再用；
        - ``stamina`` 回复不超过 ``stamina_max``；``score`` 直接加分，不吃倍率。
        """
        if self.done:
            raise RuntimeError("本局已经结束，不能再喝饮料")
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError(f"饮料下标必须是 int：{index!r}")
        if not 0 <= index < len(self.config.drinks):
            raise ValueError(f"饮料下标越界：{index}")
        if self.drinks_used_this_turn >= DRINKS_PER_TURN:
            raise ValueError(
                f"本回合已经喝过饮料（每回合最多 {DRINKS_PER_TURN} 瓶）"
            )
        drink = self.config.drinks[index]
        if self.drink_uses[index] <= 0:
            raise ValueError(f"饮料已经用完：{drink.name}")
        if drink.cost > self.stamina:
            raise ValueError(
                f"体力不足：喝「{drink.name}」需要 {drink.cost}，当前 {self.stamina}"
            )

        self.stamina -= drink.cost
        if drink.effect_type == "stamina":
            self.stamina = min(self.stamina_max, self.stamina + drink.value)
        elif drink.effect_type == "focus":
            self.buffs.focus += drink.value
        elif drink.effect_type == "condition":
            self.buffs.condition_turns += drink.value
        else:  # score（DrinkSpec 已在构造时校验，这里只剩 score）
            self.score += drink.value
        self.drink_uses[index] -= 1
        self.drinks_used_this_turn += 1

    def step(self, action: Action) -> None:
        """执行一个动作。

        - 传手牌下标：出牌 → 算分 → 付牌费（**先扣元气、再扣体力**）→
          结算本牌 buff → 抽牌；手牌打完则自动结束本回合。
        - 传 ``None``：SKIP，结束本回合（剩余手牌弃掉、不回复体力）。
        """
        if self.done:
            raise RuntimeError("本局已经结束，不能再 step")
        if action is None:
            self._end_turn(skipped=True)
            return
        if isinstance(action, bool) or not isinstance(action, int):
            raise TypeError(f"action 必须是手牌下标或 None：{action!r}")
        if not 0 <= action < len(self.hand):
            raise ValueError(f"手牌下标越界：{action}")
        if self.plays_this_turn >= self.plays_per_turn + self.extra_plays:
            raise ValueError(
                f"本回合出牌次数已用尽：{self.plays_this_turn}/"
                f"{self.plays_per_turn + self.extra_plays}（先 SKIP 结束本回合）"
            )
        card = self.hand[action]
        if card.cost > self.stamina + self.vitality:
            raise ValueError(
                f"体力不足：{card.name} 需要 {card.cost}，当前体力 {self.stamina} "
                f"+ 元气 {self.vitality}"
            )

        self.hand.pop(action)
        self.plays_this_turn += 1
        # 依赖元气的分数按支付牌费前的层数算，所以先算分再付费用
        award = self._card_award(card)
        self.score += award
        self._pay_card_cost(card)
        self._apply_card_buffs(card)
        self._apply_card_stance(card)
        # 本牌结算后追加本回合可出牌次数（本牌本身仍占一次）
        if card.extra_play > 0:
            self.extra_plays += card.extra_play
        if card.draw > 0:
            self._draw(card.draw)
        self.discard.append(card)

        # 体力+元气见底：本局提前结束（不再结算回合末）
        if self.done:
            return
        # 手牌打空：本回合自然结束
        if not self.hand:
            self._end_turn(skipped=False)

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
        """本牌的得分：``(score + focus) × 好调倍率 × 指針倍率`` + 好印象依赖分 + 元气依赖分，
        最后再乘审查基准加成，逐段向下取整。

        纯 buff 牌（``score <= 0``）不参与集中/好调/指針加成；但如果有
        ``impression_scale`` / ``block_scale``，仍然按**出牌前**的好印象 /
        元气层数结算依赖分：``int(层数 × 倍率 / 100)``。依赖分不吃好调/集中/指針，
        因为卡表没给出这部分是否参与倍率结算，取保守做法。元气依赖分用的是
        **支付本牌牌费之前**的元气层数（盾还没被这张牌花掉）。

        ``parameter_buff``（含本回合遗留的 ``turn_parameter_buff``）在**最终分**
        上叠加倍率 ``int(最终分 × 加成 / 1000)``；1000 = ×1.0（不加不减），
        1500 = ×1.5。两者同一口径，取较大者只乘一次。
        ``parameter_buff_turns > 1`` 时把加成记进 ``turn_parameter_buff``，供本回合
        后续牌继续吃（回合结束清零）。
        """
        award = 0
        if card.score > 0:
            multiplier = 1.5 if self.buffs.condition_turns > 0 else 1.0
            award = math.floor(
                (card.score + self.buffs.focus) * multiplier * score_multiplier(self.stance)
            )
        if card.impression_scale > 0 and self.buffs.impression > 0:
            award += int(self.buffs.impression * card.impression_scale / 100)
        if card.block_scale > 0 and self.vitality > 0:
            award += int(self.vitality * card.block_scale / 100)
        parameter_buff = max(card.parameter_buff, self.turn_parameter_buff)
        if parameter_buff > 0 and award > 0:
            award = int(award * parameter_buff / 1000)
        if card.parameter_buff > 0 and card.parameter_buff_turns > 1:
            self.turn_parameter_buff = max(self.turn_parameter_buff, card.parameter_buff)
        return award

    def _apply_card_stance(self, card: CardSpec) -> None:
        """结算本牌的指針效果（在算分与 buff 之后，所以本牌不吃自己刚切的倍率）。

        ``ExamConcentration`` 是卡面「強気変更」：``strong_level`` 1/2 → 切到
        強気 1/2 段階。``ExamPreservation`` 是「温存変更」：沿用原有逻辑。
        极少数同时带两种指針效果的卡（如「倾注我的一生」一项是下回合延迟变更），
        数据里没有延迟信息：按"温存收尾"处理，保持接入 ExamConcentration 之前
        的行为，不额外猜延迟结算。
        """
        if card.full_power_point > 0:
            self.stance = apply_full_power_point(self.stance, card.full_power_point)
        if card.strong_level > 0:
            delta = card_stance_effect("ExamConcentration", [card.strong_level])
            if delta["stance"] is not None:
                self.stance = replace(
                    self.stance,
                    stance=delta["stance"],
                    strong_level=card.strong_level,
                    save_level=0,
                )
        if card.preservation > 0:
            delta = card_stance_effect("ExamPreservation", [card.preservation])
            if delta["stance"] is not None:
                # 温存段階只升不降：已在 2 段階时再打 1 段階温存牌保持 2 段階
                self.stance = replace(
                    self.stance,
                    stance=delta["stance"],
                    strong_level=0,
                    save_level=max(self.stance.save_level, int(delta["save_level"])),
                )

    def _apply_card_buffs(self, card: CardSpec) -> None:
        """结算卡面 buff（在算分之后，所以本牌不吃自己刚加的 buff）。"""
        self.buffs.condition_turns += card.condition
        self.buffs.focus += card.focus
        self.buffs.impression += card.impression
        if card.vitality > 0:
            # 干劲提升元气获得量；元气优先用于抵牌费（真机语义）
            self.vitality += card.vitality + self.motivation
        self.motivation += card.motivation

    def _pay_card_cost(self, card: CardSpec) -> None:
        """支付牌费：**先扣元气（盾）、不够再扣体力**（真机语义）。"""
        remaining = card.cost
        absorbed = min(self.vitality, remaining)
        self.vitality -= absorbed
        remaining -= absorbed
        self.stamina -= remaining

    def _has_unused_stamina_drink(self) -> bool:
        """槽里还有没消耗的回复饮料（真机可以下一回合喝它继续打牌）。"""
        return any(
            uses > 0 and drink.effect_type == "stamina"
            for drink, uses in zip(self.config.drinks, self.drink_uses)
        )

    def _end_turn(self, *, skipped: bool) -> None:
        """回合结束：结算好印象、衰减好调、记录 trace、弃手牌、抽下一手。

        好印象的结算顺序固定为**先加分、再减层**：本回合按完整层数拿分，
        下一回合才少一层；这样 N 层在剩余 T 回合里的总分是 N+(N-1)+…。

        SKIP（``skipped=True``）与手牌自然打空走同一条结算路径：剩余手牌
        直接进弃牌堆，**不回复体力**，下一回合补满 ``hand_size`` 张。
        """
        if self.buffs.impression > 0:
            self.score += self.buffs.impression
            self.buffs.impression -= 1
        if self.buffs.condition_turns > 0:
            self.buffs.condition_turns -= 1
        # 审查基准加成只在本回合内持续
        self.turn_parameter_buff = 0
        self.trace.append(
            {
                "turn": self.config.turns - self.turns_left + 1,
                "turns_left": self.turns_left,
                "skipped": skipped,
                "score": self.score,
                "stamina": self.stamina,
                "vitality": self.vitality,
                "plays": self.plays_this_turn,
                "drinks": self.drinks_used_this_turn,
            }
        )

        self.discard.extend(self.hand)
        self.hand.clear()
        self.turns_left -= 1
        # 回合结束结算全力值：攒满 10 点则下一回合进入「全力」
        self.stance = end_turn(self.stance)
        if self.turns_left > 0:
            self._draw_hand()

    def _draw_hand(self) -> None:
        # 新手牌 = 新回合：本回合出牌数、额外次数、已喝饮料数从 0 重新计
        self.plays_this_turn = 0
        self.extra_plays = 0
        self.drinks_used_this_turn = 0
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

    指針牌（温存 / 強気 / 全力值）常常 ``score=0``，纯按卡面分数效率恒为 0，
    永远不会被选中；这里把这类牌的效率固定按 ``_STANCE_CARD_EFFICIENCY``
    计，让基线也会打它们（实际收益仍由 LessonSim 的指針结算决定）。
    「可出牌次数 +N」牌同理，固定按 ``_EXTRA_PLAY_CARD_EFFICIENCY`` 计，
    否则 score=0 的加次数牌永远不会被选中。
    「依赖元气分（``block_scale``）/ 审查基准加成（``parameter_buff``）」的牌
    也常常 ``score=0``，同样给固定效率 ``_DEPENDENT_CARD_EFFICIENCY``，
    避免这类牌永远轮不到；已经有白值的牌仍按白值效率排序。
    """
    playable = [index for index in sim.legal_actions() if index is not None]
    if not playable:
        return None

    # 前几个回合（剩余回合数 >= 3）先铺层数类 buff：集中/好调/印象/干劲会让后续每张
    # 牌更强，越早铺越值钱（2026-11-15 用户打法；与真机 LessonPolicy.buff_early_turns 对齐）。
    if sim.turns_left >= 3:
        buffs = [
            index
            for index in playable
            if sim.hand[index].focus > 0
            or sim.hand[index].condition > 0
            or sim.hand[index].impression > 0
            or sim.hand[index].motivation > 0
        ]
        if buffs:
            def _buff_key(index: int) -> tuple[float, int, int]:
                card = sim.hand[index]
                weight = (
                    card.focus * 30.0
                    + card.condition * 40.0
                    + card.impression * 20.0
                    + card.motivation * 10.0
                )
                return (weight, -card.cost, -index)

            return max(buffs, key=_buff_key)

    def efficiency(index: int) -> tuple[float, float, int, int]:
        card = sim.hand[index]
        if card.preservation > 0 or card.full_power_point > 0 or card.strong_level > 0:
            return (_STANCE_CARD_EFFICIENCY, _STANCE_CARD_EFFICIENCY, -card.cost, -index)
        if card.extra_play > 0:
            return (
                _EXTRA_PLAY_CARD_EFFICIENCY,
                _EXTRA_PLAY_CARD_EFFICIENCY,
                -card.cost,
                -index,
            )
        if card.score <= 0 and (card.block_scale > 0 or card.parameter_buff > 0):
            return (
                _DEPENDENT_CARD_EFFICIENCY,
                _DEPENDENT_CARD_EFFICIENCY,
                -card.cost,
                -index,
            )
        # 0 费牌按 1 费算，避免"1 分 0 费"霸榜
        return (card.score / max(card.cost, 1), card.score, -card.cost, -index)

    return max(playable, key=efficiency)
