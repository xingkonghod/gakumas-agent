"""无画面课程模拟器：只做数值推演，不渲染、不截图。

用来在离线环境里快速跑课程，为出牌参数（体力预算 / buff 优先级 / 跳过阈值 /
饮料使用）做扫描和自对弈。模型按真机课程界面（720x1280 截图已确认）与
``data/knowledge/mechanics.md`` 的课程规则做简化：

- 一节课 ``turns`` 回合，体力**整节课共享、回合间不回复**；真机开局满体力，
  所以 ``LessonConfig.stamina_max`` 默认取初始体力；
- 每回合从洗好的牌库抽 ``hand_size`` 张，**默认 3 张（与真机一致）**；打出的牌
  进弃牌堆，牌库抽空后把弃牌堆洗回牌库（近似真机）；每回合补满 3 张；
- **除外**：``CardSpec.once``（卡面「訓練中1回」）的卡用掉后进 ``excluded``，
  本场不再回到牌库/弃牌堆——这是真实牌库压缩；没用掉的手牌仍按普通卡弃掉。
  卡表/读屏给不出该属性时默认 ``once=False``（按可重复卡处理）；
- **每回合基础只能出 1 张牌**（``plays_per_turn=1``，2026-11-22 B3 按 gakumas-tools
  ``TurnManager.startTurn`` 的 ``cardUsesRemaining=1`` + 真机 39 回合逐回合日志核实）；
  出完最后一张可出牌**立即自动结束回合**（同 ``CardManager.useCard`` 末尾
  ``cardUsesRemaining < 1 → endTurn``）；``ExamPlayableValueAdd``（``CardSpec.extra_play``）
  在本回合内追加 +N 次，追加用完才结束回合，回合结束清零；
- **跳过回体力**：回合结束时如果本回合出牌次数**没用完**（SKIP / 手牌为空 / 付不起牌），
  体力 +2、封顶 ``stamina_max``（同 ``TurnManager.endTurn``：``cardUsesRemaining > 0``
  时回 2 点）；出牌次数用尽自动结束的回合不回体力；
- **元气（盾）**：``ExamBlock`` 产生的元气（``CardSpec.vitality``）**优先抵挡
  出牌体力消耗**——出牌时先扣元气、不够再扣体力（真机语义）。``stamina +
  vitality`` 付不起的牌不合法；依赖元气的分数按**支付牌费前**的元气层数算；
- **SKIP**：结束本回合，手牌进弃牌堆并抽下一手，**本回合剩余牌不回复体力**；
  每次回合末都记进 ``LessonSim.trace``（``skipped=True``；手牌自然打空为
  ``skipped=False``）；
- **饮料**：``LessonConfig.drinks`` 注入 ``DrinkSpec``（真机底部 3 个饮料槽），
  ``use_drink(index)`` 喝一瓶，**默认不限每回合瓶数**（用户确认真机无此限制），每瓶按 ``uses``
  计次、用掉即消耗（``uses=1`` 默认一次性）。效果支持 ``stamina``（回复体力，
  不超过 ``stamina_max``）/ ``focus``（集中 +N）/ ``condition``（好调 N 回合）/
  ``score``（直接加 N 分，不吃倍率）。``DrinkSpec.cost`` 默认 0：真机饮料不耗
  体力，字段保留给自定义饮料；
- 出牌先按**当前** buff 算分，再结算这张卡自带的 buff（本牌不享受自己刚加的 buff）；
- ``ExamCardDraw``：出牌后立即抽 N 张（``CardSpec.draw``），牌库空则把弃牌堆
  洗回牌库再抽（刚打出的牌在抽牌之后才进弃牌堆，所以抽不到自己）；
- ``ExamReview``：叠好印象层数（``CardSpec.impression``）；**回合结束先按当前
  层数加分（``score += 层数``），下一回合开始时层数才 -1（最低 0）**；
- ``ExamLessonDependExamReview``：依赖好印象的分数，按出牌**前**的层数算
  ``int(层数 × 倍率 / 100)``（倍率 1000 = 层数×10）。卡表没给出更细的结算
  顺序，这里沿用"本牌不享受自己刚加的 buff"的保守规则：本牌自带的
  ``impression`` 在算完依赖分之后才生效；这部分分数也不吃好调/集中倍率；
- ``ExamLessonDependBlock``：依赖元气（盾）层数的分数，与好印象依赖分**同构**：
  按出牌**前**（也就是支付牌费前）的元气层数算
  ``int(层数 × 倍率 / 100)``（倍率 1000 = 层数×10），同样不吃好调/集中/指針
  倍率，本牌自带的 ``vitality`` 在算完之后才生效；
- **属性倍率**（``LessonConfig.attribute_coefficient``）：真机课程里约 1.0，
  考试/舞台里是屏幕上显示的「歌唱 411%」这类倍率（411% = 4.11）。只乘
  ``(卡面分 + 集中) × 好调 × 指針`` 这一段白值，**好印象/元气依赖分不吃**
  （保守口径，卡表没给出依赖分是否参与倍率）。倍率 ≠ 1.0 时按真机**显示值**
  四舍五入：37 分 + 集中 10 + 好调 → 47 × 1.5 × 4.11 = 289.755 → 290
  （真机实测约 290；课程倍率 1.0 仍沿用 ``floor``，保持既有校准）；
- **考试真实属性倍率（分段 + 联动惩罚，T5 2026-11-22）**：
  ``LessonConfig.attribute_bonuses``（Vo/Da/Vi 三项千分比，来自
  ``sim.exam_multiplier.calculate_bonus``：主数据分数表折线 × 审查基准联动惩罚）
  + ``LessonConfig.turn_attributes``（每回合 ``ExamTurnEndLog.parameterType``：
  1=歌唱 / 2=舞蹈 / 3=视觉）时，按**当前回合属性**取倍率，并用客户端
  ``CalcCurrentTurnBattleBonus`` 的取整口径（``ceil(f32(f32(乘) − 1e-4))``）结算：
  出牌分（含好印象/元气/全力值依赖分——参考引擎里依赖分也是普通 ``score +=``，
  会吃属性倍率）与回合末好印象分都乘。不给这两项时行为与旧版逐位相同
  （单标量 ``attribute_coefficient`` 路径保留给生产：屏幕直接读当前回合倍率）；
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
- 回合结束：好印象按当前层数加分（下一回合开始才 -1），好调回合数 -1；
- 分数按参考引擎 ``resolveScore`` 的顺序结算：先加集中、再好调、指針、增益/减益、
  不调，**buff 段取整一次**；考试/舞台再乘回合属性倍率并**再取整一次**，两次都是
  ``safeCeil``（向上取整，整数附近按整数）；
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
- 饮料/卡牌的其余效果：强化卡牌（``ExamCardUpgrade``）、消耗体力增减、
  回合追加、好印象/元气的更多来源等 20+ 种效果没有对应字段（配置时直接报错，
  不会静默当成无用饮料）；好调与绝好调都按 ``condition`` 的 ×1.5 近似；
- 卡牌强化（训练中强化）、偶像固有卡生成、牌序记忆（真机可查看牌堆顺序）：
  影响：强化后的数值和记牌优势不体现；
- 考试专属规则（追击、回合限制、对手行动）：课程模拟器不覆盖。

**2026-11-16 新卡池：16 种新效果的建模口径**（这些效果以前在 ``LessonSim`` 里
恒为 0，奖励池因此把整类卡挡在外面）：

精确建模（8 种，字段都在 ``CardSpec`` 里，默认 0 = 旧行为）：

- ``ExamStaminaRecoverFix`` → ``stamina_recover``：出牌结算（算分/付牌费/结算
  buff）后固定回复 ``values[0]`` 点体力，封顶 ``stamina_max``；
- ``ExamLessonFullPowerPoint`` → ``full_power_scale``：按**出牌前**的全力值
  ``int(全力值 × full_power_scale / 1000)`` 加进本牌得分（卡表 values 是千分比：
  1000 = 卡面「累计全力值的 100%」；**不**沿用 ``block_scale`` 的 /100，否则
  会把 100% 读成 1000%）。本牌自带的全力值增量不参与本牌折算。卡表里双值的
  该效果是 ``[固定打分, 折算千分比]``，解析时固定打分进 ``score``、末位进折算倍率；
- ``ExamStatusEnchantEncore`` → ``encore``：本牌直接效果执行两次——打分/元气/
  好调/集中/干劲/好印象/抽牌/全力值/可出牌次数/体力回复各 ×2；倍率类字段
  （``*_scale`` / ``*_multiple`` / ``parameter_buff``）不翻倍（避免把百分比
  乘方）；牌费只付一次；
- ``ExamReviewMultiple`` → ``review_multiple`` / ``review_multiple_turns``：
  好印象强化。回合结束结算好印象时，分数按
  ``int(层数 × (1000 + review_multiple) / 1000)`` 放大（卡表 values 是千分比：
  2000 = 卡面「+200%」= ×3）；``turn=-1`` 为永久；
- ``ExamParameterBuffAdditiveFix`` → ``condition_additive`` /
  ``condition_additive_turns``：获得好调时额外 +N 回合（加算；本牌自带的
  好调也享受，因为真机是"下个回合"的延迟好调被追加）；``turn=-1`` 为永久；
- ``ExamFullPowerLessonMultipleAdditive`` → ``full_power_lesson_multiple`` /
  ``..._turns``：全力强化，放大 ``ExamLessonFullPowerPoint`` 折算出的分数
  （``int(分 × (1000 + 值) / 1000)``，卡表 100 = 卡面 +10%）；
- ``ExamEnthusiasticTurnAdd`` → ``enthusiasm_extension``：熱意延長，回合末不把
  本回合的熱意清零、改为消耗 1 层延長（参考引擎 ``TurnManager.endTurn``）；
- ``ExamEnthusiasticAdditive`` → ``enthusiasm_bonus`` / ``..._turns``：熱意追加
  加算 buff（获得熱意时 ``+值``）；
- ``ExamEnthusiasticMultiple`` → ``enthusiasm_multiple`` / ``..._turns``：熱意増加
  千分比 buff（获得熱意时 ``×(1+值/1000)``）；
- ``ExamAddGrowEffect`` → ``grow_score``：成长。同一张牌第 k 次使用（k 从 1 起）
  时按 ``score × (1 + (k-1) × grow_score / 100)`` 计分，计数器按牌对象记在
  ``LessonSim.card_uses``。**数据缺口**：卡表里该效果的 ``values`` 为空
  （成长量在未下载的 ``ProduceCardGrowEffect`` 表里），所以真实卡现在
  ``grow_score=0``、不涨分；字段和机制留给有数据时直接填。

近似建模（8 种，误差方向逐条写明，不假装精确）：

- ``ExamForcePlayCardSearch`` → ``draw += 1``（至少 1 张）：真机是"检索并**免费
  强制打出**"，这里只算摸到 1 张、仍要付牌费且受每回合出牌数限制。**低估**；
  如果本牌同时有"可出牌次数追加"，模拟器不再额外加抽牌（资源收益已由次数
  表达，也避免 0 费检索+加次数牌无限过牌）；
- ``ExamCardCreateId`` → ``draw += 1``：真机生成指定卡（位置可控、通常比 1 张
  抽牌值钱）；这里只算 +1 手牌。**低估**；
- ``ExamCardMove`` → ``draw += 1``：真机把保留/弃牌中的卡移回手牌（可能一次
  移多张）；这里只算 +1 手牌。**低估**；
- ``ExamStatusEnchant`` → 递归展开 ``inner``，内层效果**本回合立刻结算**：
  真机是把状态附魔挂到卡上、满足条件/延迟触发；提前兑现通常**高估当回合
  分数**（内层若是回合末/最终回合才结算，长期触发次数可能被低估）；
- ``ExamEffectTimer`` → 无字段，被它标记的延迟效果**本回合立刻生效**：
  提前拿到收益，通常**高估当回合**；若延迟后能吃到更多 buff 则方向不定；
- ``ExamEffectTimerEndTurn`` → 同 ``ExamEffectTimer``，回合结束触发改为立刻；
- ``ExamAntiDebuff`` → no-op：课程没有低下状态来源，模型内收益恒 0；
  若考试/干扰引入 debuff，则**低估**其价值；
- ``ExamCardPlayAggressive`` → ``motivation``（干劲永久叠层）：元气获得量
  +N；真机可能是限时/按次数，这里按永久，长期战斗**高估**元气收益
  （课程里元气只抵牌费，对分数影响小）。

**熱意（enthusiasm）+ 温存解除（T5② 2026-11-22）**：独立的回合内分数资源，
不再是以前「温存解除≈好调回合」的近似——``LessonSim.enthusiasm`` 保存当前值，
本牌算分时 ``score += 熱意 × 本牌熱意適用倍数``（在集中之后、好调/指針倍率之前，同参考引擎
``resolveScore`` b；熱意是整数、获得时向上取整；倍数默认 ×1，``ExamMultipleEnthusiasticLesson``
的牌是 ×2）；回合末归 0（有 ``enthusiasm_extension`` 则消耗 1 层延長并保留）。
温存解除按参考引擎 ``constants.js STANCE_CHANGED_EFFECTS`` 结算：1 段階解除
熱意 +5、2 段階 +8，解除当回合出牌次数 +1，2 段階还额外 +5 固定元気（不吃干劲）。
获得量 ``(熱意追加 + 基础值) × (1 + 熱意増加‰)``，常量与口径见
``sim/enthusiasm.py``（BSD-3 参考引擎 + 官方 wiki 描述；wiki 的 ceil 与参考引擎
不取整的差异记录在那里）。**未建模**：のんびり（leisure）指針的解除规则、
P 道具/附魔触发的熱意、以及同一张牌里「温存→強気→温存」这种净指針不变的
中间解除（我们只看本牌结算前后指針，中间状态看不到）。

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

from gkagent.data.plans import (
    DEFAULT_PLAN,
    PLAN_BUFF_FIELDS,
    Plan,
    default_plan_library,
    normalize_plan,
)
from gkagent.sim.enthusiasm import (
    enthusiasm_gain,
    release_on_stance_change,
    turn_end_enthusiasm,
)
from gkagent.sim.exam_multiplier import battle_bonus_score
from gkagent.sim.p_items import (
    CARD_PLAY,
    STATUS_GAIN,
    TURN_END,
    TURN_START,
    PassiveEvent,
    PassiveState,
    PItemSpec,
    apply_passive,
)
from gkagent.sim.stance import (
    FULL_POWER_POINT_COST,
    StanceState,
    apply_full_power_point,
    card_stance_effect,
    end_turn,
    score_multiplier,
    stamina_cost_multiplier,
    stamina_pierce,
)

__all__ = [
    "AUDITION_ATTRIBUTE_COEFFICIENT",
    "DRINKS_PER_TURN",
    "DRINK_EFFECTS",
    "Action",
    "Buffs",
    "CardSpec",
    "DrinkSpec",
    "LessonConfig",
    "LessonSim",
    "PItemSpec",
    "Policy",
    "greedy_policy",
    "safe_ceil",
]

# 一个合法动作：手牌下标，或 None = SKIP（结束本回合）
Action: TypeAlias = int | None
Policy: TypeAlias = Callable[["LessonSim"], Action]

# 饮料支持的效果类型（真机饮料的其余 20+ 种效果都未建模，配置时由 DrinkSpec 报错）
DRINK_EFFECTS: tuple[str, ...] = ("stamina", "focus", "condition", "score")
# 真机每回合最多喝 1 瓶（不是每个饮料槽 1 瓶）
DRINKS_PER_TURN: int | None = None  # None = 真机实际无每回合上限（用户确认）
# 考试/舞台屏幕显示的属性倍率（「歌唱 411%」= 4.11）真机实测默认值；
# 课程里属性倍率 ≈ 1.0，所以 LessonConfig 默认仍是 1.0。
AUDITION_ATTRIBUTE_COEFFICIENT = 4.11

# 防止策略写出死循环（例如全 0 费抽牌卡无限过牌）时的安全阀
_MAX_STEPS = 10_000


def safe_ceil(value: float) -> int:
    """取整口径 = 参考引擎 ``safeCeil``（gakumas-tools ``utils.js``）。

    真机分数结算在「加算后」「乘完好调/指針/增益/不调后」「乘回合属性倍率后」
    各取整一次，**都是向上取整**（B3 2026-11-22 用 gakumas-tools 实机回放
    黄金值核对：好调 ×1.5 的 5→8、2→3；考试 250% 下基础 9 无好调 23、
    有好调 35）。旧实现课程用 floor / 考试只结尾 round 一次，会每题少 1–2 分。
    """
    rounded = math.floor(value + 0.5)
    if abs(value - rounded) < 1e-9:
        return int(rounded)
    return math.ceil(value)


# greedy_policy 给指針牌（温存/全力值，通常 score=0）的固定效率，避免永远选不到
_STANCE_CARD_EFFICIENCY = 3.0
# greedy_policy 给「本回合可出牌次数 +N」牌（通常 score=0）的固定效率
_EXTRA_PLAY_CARD_EFFICIENCY = 3.0
# greedy_policy 给「依赖元气分 / 审查基准加成」牌（常常 score=0）的固定效率
_DEPENDENT_CARD_EFFICIENCY = 3.0
# 持续类 buff 的回合数哨兵：-1 = 永久（卡表 turn=-1）
_PERMANENT = -1


def _merge_buff_turns(current: int, new: int) -> int:
    """合并同一种持续 buff 的剩余回合：任一为永久则永久，否则取更长的。"""
    if current == _PERMANENT or new == _PERMANENT:
        return _PERMANENT
    return max(current, new)


def _tick_buff_turns(turns: int) -> int:
    """回合结束把持续 buff 剩余回合 -1；0 / 永久（-1）保持不变。"""
    return turns - 1 if turns > 0 else turns


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

    2026-11-16 新卡池补的字段（全部默认 0/False = 旧行为，旧调用不用改）：

    - ``stamina_recover``：``ExamStaminaRecoverFix`` 的固定体力回复，封顶
      ``LessonConfig.stamina_max``；
    - ``full_power_scale``：``ExamLessonFullPowerPoint`` 的折算倍率（千分比，
      1000 = 卡面 100%），``int(出牌前全力值 × 该值 / 1000)`` 加进本牌得分；
    - ``encore``：``ExamStatusEnchantEncore`` 再演，本牌直接效果执行两次
      （打分/抽牌/集中等 ×2，倍率类字段不翻倍，牌费只付一次）；
    - ``review_multiple`` / ``review_multiple_turns``：``ExamReviewMultiple``
      好印象强化（千分比，2000 = 卡面 +200%）；-1 回合数 = 永久；
    - ``condition_additive`` / ``condition_additive_turns``：
      ``ExamParameterBuffAdditiveFix`` 好调增加量追加（获得好调时额外 +N 回合）；
    - ``full_power_lesson_multiple`` / ``..._turns``：
      ``ExamFullPowerLessonMultipleAdditive`` 全力强化（千分比，100 = +10%），
      放大上面 ``full_power_scale`` 折算出的分数；
    - ``grow_score``：``ExamAddGrowEffect`` 成长百分比。同一张牌第 k 次使用时
      按 ``score × (1 + (k-1) × grow_score/100)`` 计分；卡表该效果 ``values``
      为空（成长量在未下载的 ProduceCardGrowEffect 表里），所以真实卡现在
      恒为 0，机制留给有数据时使用。

    T5②（2026-11-22）熱意字段（全部默认 0 = 旧行为）：

    - ``enthusiasm_bonus`` / ``enthusiasm_bonus_turns``：``ExamEnthusiasticAdditive``
      熱意追加（获得熱意时加算；``turns=-1`` 永久）；
    - ``enthusiasm_multiple`` / ``enthusiasm_multiple_turns``：
      ``ExamEnthusiasticMultiple`` 熱意増加（千分比，获得熱意时 ×(1+值/1000)）；
    - ``enthusiasm_extension``：``ExamEnthusiasticTurnAdd`` 熱意延長（本場次回合末
      不清零、改为消耗 1 层延長）；
    - ``enthusiasm_multiplier``：``ExamMultipleEnthusiasticLesson`` 本牌熱意適用倍数
      （千分比，默认 1000 = ×1；卡面「熱意效果会2倍生效」= 2000）。
    """

    name: str
    cost: int
    score: float
    # 卡类别（ActiveSkill / MentalSkill / IdolUnique）；P 道具 card_filter 用
    category: str = ""
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
    # ---- 2026-11-16 新卡池：16 种新效果的落地字段（默认值保持旧行为）----
    # ExamStaminaRecoverFix：出牌结算后固定回复体力，封顶 LessonConfig.stamina_max
    stamina_recover: int = 0
    # ExamLessonFullPowerPoint：按出牌前累计全力值折算打分（千分比，1000 = 100%）
    full_power_scale: int = 0
    # ExamStatusEnchantEncore：再演，本牌直接效果执行两次
    encore: bool = False
    # ExamReviewMultiple：好印象强化（千分比，2000 = 卡面 +200% → ×3）
    review_multiple: int = 0
    review_multiple_turns: int = 0
    # ExamParameterBuffAdditiveFix：好调增加量追加（获得好调时额外 +N 回合）
    condition_additive: int = 0
    condition_additive_turns: int = 0
    # ExamFullPowerLessonMultipleAdditive：全力强化（千分比，100 = 卡面 +10%）
    full_power_lesson_multiple: int = 0
    full_power_lesson_multiple_turns: int = 0
    # ExamAddGrowEffect：成长（第 k 次使用按 1 + (k-1)×grow_score/100 计分）
    grow_score: int = 0
    # 「レッスン中1回」：本场用掉后进除外区，不再回牌库/弃牌堆（牌库压缩）。
    # 卡表/读屏给不出这个属性时默认 False（按可重复卡处理，保守口径见模块 docstring）。
    once: bool = False
    # ---- T5② 2026-11-22：熱意资源（默认 0 = 旧行为，见模块 docstring 与 enthusiasm.py）----
    # ExamEnthusiasticAdditive：熱意追加（获得熱意时加算），turns=-1 永久
    enthusiasm_bonus: int = 0
    enthusiasm_bonus_turns: int = 0
    # ExamEnthusiasticMultiple：熱意増加（获得熱意时乘 1+值/1000），turns=-1 永久
    enthusiasm_multiple: int = 0
    enthusiasm_multiple_turns: int = 0
    # ExamEnthusiasticTurnAdd：熱意延長（回合末不清零，延長回合数 +值）
    enthusiasm_extension: int = 0
    # ExamMultipleEnthusiasticLesson：本牌熱意適用倍数（千分比，1000 = ×1；
    # 卡面「熱意效果会2倍生效」= 2000）
    enthusiasm_multiplier: int = 1000


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
    # PERFECT 线：None = 默认 2×target_clear（三档结算见 LessonSim.reward_tier）
    target_perfect: int | None = None
    # 真机每回合手里 3 张牌
    hand_size: int = 3
    # 每回合基础可出牌次数：**真机默认 1 张**（B3 按 gakumas-tools TurnManager 的
    # cardUsesRemaining=1 + 真机 39 回合日志核实，2026-11-22）；ExamPlayableValueAdd
    # 在本回合内追加，追加用完自动结束回合。
    plays_per_turn: int = 1
    # 饮料槽（真机 3 个）；默认空 = 旧行为
    drinks: tuple[DrinkSpec, ...] = ()
    # None = 不限每回合瓶数（真机实际无此限制）；给整数才限制
    drinks_per_turn: int | None = None
    # 体力上限；None = 初始体力（真机课程开局满体力）。饮料回复不会超过它
    stamina_max: int | None = None
    # 属性倍率：考试/舞台屏幕上的「歌唱 411%」= 4.11；课程 ≈ 1.0（默认）
    attribute_coefficient: float = 1.0
    # 考试真实属性倍率（T5 2026-11-22）：Vo/Da/Vi 三项千分比（4110 = 4.11×），
    # 来自 ``sim.exam_multiplier.calculate_bonus``（分段折线 + 审查基准联动惩罚）。
    # 配合 ``turn_attributes`` 按当前回合属性取倍率；None = 旧行为。
    attribute_bonuses: tuple[int, int, int] | None = None
    # 每回合考试属性（``ExamTurnEndLog.parameterType``：1=Vo / 2=Da / 3=Vi）；
    # 与 ``attribute_bonuses`` 一起用。空 = 没有逐回合属性信息。
    turn_attributes: tuple[int, ...] = ()
    # 指針体力代价（温存减半/強気双倍/2段穿透）；False = 旧口径（仅 ablation）
    stance_costs: bool = True
    # 方案（プラン）：sense=感性 / logic=理性 / anomaly=非凡；未知值退回 sense。
    # 只影响 greedy_policy 的 buff 优先级（见 data/knowledge/plans.json）。
    plan: str = DEFAULT_PLAN
    # P 道具（右上角被动）：接口占位，默认空；数据未到位前不结算（见 PItemSpec）
    p_items: tuple[PItemSpec, ...] = ()


@dataclass
class Buffs:
    """课程内会衰减的 buff。"""

    condition_turns: int = 0  # 好调剩余回合
    # 绝好调：好调回合数每回合再 +0.1 倍（gakumas-tools resolveScore 口径）
    perfect_condition_turns: int = 0
    # 不调（poor condition）：分数 ×0.67
    poor_condition_turns: int = 0
    # メタモルフォーゼ："" | "performance"（披露 +25%）| "preparation"（支度 ×0.75）
    metamorphosis: str = ""
    focus: int = 0  # 集中层数（永久）
    impression: int = 0  # 好印象层数（回合结束加分，下一回合开始 -1）
    # 2026-11-16 新效果带来的持续倍率/加算；turns = 0 未激活、-1 永久
    condition_additive: int = 0  # 好调增加量追加（ExamParameterBuffAdditiveFix）
    condition_additive_turns: int = 0
    review_multiple: int = 0  # 好印象强化千分比（ExamReviewMultiple）
    review_multiple_turns: int = 0
    full_power_lesson_multiple: int = 0  # 全力强化千分比（ExamFullPowerLessonMultipleAdditive）
    full_power_lesson_multiple_turns: int = 0
    # T5② 熱意 buff：熱意追加（加算）/ 熱意増加（千分比）；turns=0 未激活、-1 永久
    enthusiasm_bonus: int = 0
    enthusiasm_bonus_turns: int = 0
    enthusiasm_multiple: int = 0
    enthusiasm_multiple_turns: int = 0


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
        # P 道具接口：只保存，不结算（数据未到位；默认空 tuple）
        self.p_items: tuple[PItemSpec, ...] = tuple(getattr(config, "p_items", ()))
        # P 道具触发次数（max_uses）与本场已出牌总数（card_play_interval 用）
        self.p_item_uses: dict[str, int] = {}
        self.cards_played_total: int = 0
        self._p_items_by_trigger: dict[str, tuple[PItemSpec, ...]] = {}
        for item in self.p_items:
            self._p_items_by_trigger.setdefault(item.trigger, ())
            self._p_items_by_trigger[item.trigger] += (item,)

        self.deck: list[CardSpec] = list(deck)
        self.rng.shuffle(self.deck)
        self.discard: list[CardSpec] = []
        # 除外区：レッスン中1回 的卡用掉后本场消失（不进弃牌堆、不会被重新抽到）
        self.excluded: list[CardSpec] = []
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
        # 熱意（enthusiasm）：回合内分数资源（整数，获得时向上取整），回合末归 0；
        # 温存解除给 5/8（见 enthusiasm.py）
        self.enthusiasm: int = 0
        # 熱意延長（ExamEnthusiasticTurnAdd）：>0 时回合末保留熱意并把延長 -1
        self.enthusiasm_extension_turns: int = 0
        # 方案（プラン）：greedy_policy 按它决定先铺哪些 buff；未知值退回 sense。
        self.plan = normalize_plan(getattr(config, "plan", DEFAULT_PLAN)) or DEFAULT_PLAN
        self.plan_config: Plan = default_plan_library().get(self.plan)
        # 三档目标：score < target_clear → FAILED（0 属性）；≥ target_clear → CLEAR；
        # ≥ target_perfect → PERFECT（拿 CLEAR+PERFECT 满档）。target_perfect 缺省
        # 按用户口径取 target_clear × 2，不再"打到 CLEAR 就收手"。
        self.target_clear = int(config.target_clear)
        self.target_perfect = int(
            config.target_perfect
            if config.target_perfect is not None
            else config.target_clear * 2
        )

        # 元气 / 干劲：元气（ExamBlock）优先抵牌费，也能喂依赖元气的分数
        self.vitality: int = 0
        self.motivation: int = 0
        # 本回合内持续的审查基准加成（ExamParameterBuffMultiplePerTurn），回合结束清零
        self.turn_parameter_buff: int = 0

        # 饮料：每瓶剩余次数（用掉即消耗），每回合最多喝 1 瓶
        self.drink_uses: list[int] = [drink.uses for drink in config.drinks]
        self.drinks_used_this_turn: int = 0
        # ExamAddGrowEffect 的 per-card 使用计数器（按牌对象 id，同一张牌用几次涨几次）
        self.card_uses: dict[int, int] = {}
        # 回合级 trace：每次回合结束记一行（含 skipped），便于回放 SKIP 行为
        self.trace: list[dict] = []

        # 牌库会无限洗回，所以"体力+元气付不起任何牌"是永久性的终端条件
        self._min_cost = min((card.cost for card in self.deck), default=0)

        self._draw_hand()

    def shuffle_deck(self, deck: list[CardSpec], *, seed: int | None = None) -> None:
        """PIMC determinization：重新布置牌库顺序（**只改顺序，不改组成**）。

        ``seed`` 非 None 时重置随机数发生器再洗牌：同一 seed 完全可复现，不同
        seed 得到不同牌序。构造时随机抽出的起手牌会被丢弃并一起重洗，所以调用方
        通常要在本方法之后自己设置 ``hand``（见 ``sim/play_choice.py`` 的
        ``_new_sim``）。``seed=None`` 时沿用当前 RNG 状态。
        """
        self.deck = list(deck)
        if seed is not None:
            self.rng = random.Random(seed)
            self.rng_seed = seed
        self.rng.shuffle(self.deck)
        self.discard.clear()
        self.excluded.clear()
        self._min_cost = min((card.cost for card in self.deck), default=0)

    # ------------------------------------------------------------------ 状态
    @property
    def total_turns(self) -> int:
        """本课程总回合数（配置值；与剩余回合一起决定当前进度）。"""
        return int(self.config.turns)

    @property
    def current_turn(self) -> int:
        """当前是第几回合（1 起；回合用尽后返回 total_turns）。"""
        return max(self.total_turns - self.turns_left + 1, 1)

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
    def reward_tier(self) -> int:
        """三档结算：0=FAILED（0 属性）/ 1=CLEAR（clear 档）/ 2=PERFECT（clear+perfect 档）。"""
        if self.score >= self.target_perfect:
            return 2
        if self.score >= self.target_clear:
            return 1
        return 0

    @property
    def reward_gain(self) -> int:
        """普通课程属性收益：CLEAR 部分逐点 + PERFECT 部分按实际进度。

        wiki 口径（note.com「学マスのレッスンにおけるパラメータ上昇量の計算式」）：
        CLEAR 是"还差多少分 CLEAR"，PERFECT 是达标后"还差多少分 PERFECT"；
        参数按**已达成**的数值计。因此::

            gain = min(score, CLEAR)
                 + min(max(score - CLEAR, 0), PERFECT)

        ``LessonConfig.target_perfect`` 是绝对 PERFECT 线，所以这里
        ``PERFECT = target_perfect - target_clear``。score 未到 CLEAR 时按
        "已达成部分"给 gain（= score），不是整档 0；这是 note.com 口径，见
        ``docs/EXPECTIMAX.md`` §2。CLEAR/PERFECT 档位判定仍由 ``reward_tier``
        给 UI/统计用（两者不矛盾：档位是阈值，收益是连续进度）。
        """
        clear = max(int(self.target_clear), 0)
        perfect = max(int(self.target_perfect) - clear, 0)
        score = max(int(self.score), 0)
        return min(score, clear) + min(max(score - clear, 0), perfect)

    @property
    def result(self) -> str:
        """按当前分数给出评价（三档与 ``reward_tier`` 一致）。

        ``target_perfect`` 缺省 = 2×``target_clear``；真机训练要打满 PERFECT
        才拿 CLEAR+PERFECT 的完整属性。
        """
        return ("FAILED", "CLEAR", "PERFECT")[self.reward_tier]

    def legal_actions(self) -> list[Action]:
        """当前能出的手牌下标 + SKIP（None，固定在最后）。

        体力+元气够付**指針修正后的实际牌费**就合法；本回合出牌数达到
        ``plays_per_turn + extra_plays`` 后只剩 SKIP（但正常流程里出完最后一张
        会**自动结束回合**，这个状态只出现在手牌为空/付不起牌时）。
        """
        if self.done:
            return []
        if self.plays_this_turn >= self.plays_per_turn + self.extra_plays:
            return [None]
        actions: list[Action] = [
            index
            for index, card in enumerate(self.hand)
            if self._effective_cost(card) <= self.stamina + self.vitality
        ]
        actions.append(None)
        return actions

    def legal_drinks(self) -> list[int]:
        """当前能喝的饮料下标（未用完、体力够付 ``cost``、本回合还没喝过）。

        真机限制每回合 1 瓶；``DrinkSpec`` 的 ``uses`` 用完后该下标不再出现。
        """
        cap = getattr(self.config, "drinks_per_turn", None)
        if self.done or (cap is not None and self.drinks_used_this_turn >= cap):
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

        - 每回合瓶数上限由 ``LessonConfig.drinks_per_turn`` 决定（None = 不限）；
        - 按 ``DrinkSpec.uses`` 消耗次数，用完后该槽位不可再用；
        - ``stamina`` 回复不超过 ``stamina_max``；``score`` 直接加分，不吃倍率。
        """
        if self.done:
            raise RuntimeError("本局已经结束，不能再喝饮料")
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError(f"饮料下标必须是 int：{index!r}")
        if not 0 <= index < len(self.config.drinks):
            raise ValueError(f"饮料下标越界：{index}")
        cap = getattr(self.config, "drinks_per_turn", None)
        if cap is not None and self.drinks_used_this_turn >= cap:
            raise ValueError(f"本回合已经喝过饮料（每回合最多 {cap} 瓶）")
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
          结算本牌 buff → 抽牌；**本回合可出牌次数用尽（``plays_per_turn +
          extra_plays``）或手牌打完 → 立即自动结束本回合**（真机语义，同参考
          引擎 ``CardManager.useCard`` 末尾的 ``cardUsesRemaining < 1 → endTurn``）。
        - 传 ``None``：SKIP，结束本回合（剩余手牌弃掉；若本回合还有没用的出牌
          次数则回 2 点体力，见 ``_end_turn``）。
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
        effective_cost = self._effective_cost(card)
        if effective_cost > self.stamina + self.vitality:
            raise ValueError(
                f"体力不足：{card.name} 需要 {effective_cost}（指針修正后），当前体力 "
                f"{self.stamina} + 元气 {self.vitality}"
            )

        self.hand.pop(action)
        self.plays_this_turn += 1
        previous_stance = self.stance
        # 再演（ExamStatusEnchantEncore）：本牌直接效果执行两次；牌费只付一次，
        # 成长计数器仍按"打出这张牌一次"计。倍率类字段不翻倍（避免百分比乘方）。
        effect_card = self._encore_card(card) if card.encore else card
        uses = self.card_uses.get(id(card), 0)
        # 依赖元气的分数按支付牌费前的层数算，所以先算分再付费用
        award = self._card_award(effect_card, uses=uses)
        self.score += award
        self._pay_card_cost(card)
        # ExamStaminaRecoverFix：付完牌费后固定回体力，封顶 stamina_max
        if effect_card.stamina_recover > 0:
            self.stamina = min(
                self.stamina_max, self.stamina + effect_card.stamina_recover
            )
        self._apply_card_buffs(effect_card)
        self._apply_card_stance(effect_card)
        # 温存解除（参考引擎 STANCE_CHANGED_EFFECTS）：熱意 +5/+8、2 段階固定元気 +5、
        # 当回合出牌次数 +1；同回合内反复「温存→強気」按次数重复触发。旧实现把熱意
        # 近似成好调回合，T5② 2026-11-22 改为独立熱意资源（见 enthusiasm.py）。
        if getattr(self.config, "stance_costs", True):
            release_enthusiasm, release_genki, release_plays = (
                release_on_stance_change(previous_stance, self.stance)
            )
            if release_enthusiasm or release_genki or release_plays:
                self.enthusiasm += enthusiasm_gain(
                    release_enthusiasm,
                    bonus=self.buffs.enthusiasm_bonus,
                    multiple_permil=self.buffs.enthusiasm_multiple,
                )
                # 固定元気：不吃「やる気」加成（参考引擎 resolveFixedGenki）
                self.vitality += release_genki
                self.extra_plays += release_plays
        # 本牌结算后追加本回合可出牌次数（本牌本身仍占一次）
        if effect_card.extra_play > 0:
            self.extra_plays += effect_card.extra_play
        if effect_card.draw > 0:
            self._draw(effect_card.draw)
        # 成长计数器要等本牌算完分再 +1，保证第 k 次使用吃 (k-1) 层成长
        self.card_uses[id(card)] = uses + 1
        # P 道具：每次出牌后（含刚打出的这张；card_play/card_played/interval 共用）
        self.cards_played_total += 1
        self._fire_p_items(
            CARD_PLAY,
            card_category=card.category,
            cards_played_this_turn=self.plays_this_turn,
            cards_played_total=self.cards_played_total,
        )
        if card.once:
            # レッスン中1回：用掉后除外，本场不再回到牌库/弃牌堆
            self.excluded.append(card)
        else:
            self.discard.append(card)

        # 体力+元气见底：本局提前结束（不再结算回合末）
        if self.done:
            return
        # 本回合可出牌次数用尽（真机打完最后一张立即换回合）或手牌打空：自动结束
        if not self.hand or self.plays_this_turn >= self.plays_per_turn + self.extra_plays:
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
    @staticmethod
    def _encore_card(card: CardSpec) -> CardSpec:
        """再演（``ExamStatusEnchantEncore``）：返回"效果执行两次"的等效牌。

        只翻倍**直接效果**的数值（打分/元气/好调/集中/干劲/好印象/抽牌/全力值/
        可出牌次数/体力回复）；``block_scale`` / ``impression_scale`` /
        ``full_power_scale`` / ``parameter_buff`` / ``*_multiple`` 这类百分比
        倍率不翻倍——把百分比乘方会把误差放大一个量级。牌费与成长计数器仍按
        原牌结算一次（真机再演是"自动再用一次"，不再付牌费）。
        """
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
        )

    def _card_award(self, card: CardSpec, *, uses: int = 0) -> int:
        """本牌的得分：``(score + focus + 熱意) × 好调倍率 × 属性倍率 × 指針倍率``
        + 好印象依赖分 + 元气依赖分 + 全力值折算分，最后再乘审查基准加成，
        逐段向下取整。

        纯 buff 牌（``score <= 0``）不参与集中/好调/指針/属性倍率加成；但如果有
        ``impression_scale`` / ``block_scale`` / ``full_power_scale``，仍然按
        **出牌前**的好印象 / 元气层数 / 全力值结算依赖分：
        ``int(层数 × 倍率 / 100)``（``full_power_scale`` 是千分比，按 /1000）。
        依赖分不吃好调/集中/指針/属性倍率，因为卡表没给出这部分是否参与倍率
        结算，取保守做法。元气依赖分用的是**支付本牌牌费之前**的元气层数（盾还没
        被这张牌花掉）；全力值折算同样用本牌结算前的全力值（本牌自带的
        ``full_power_point`` 在算分之后才生效）。

        ``ExamAddGrowEffect``（成长）按 ``uses`` 层数放大本牌白值：
        ``score × (1 + uses × grow_score / 100)``，``uses`` 是这张牌**之前**
        已经打出的次数（第 1 次不吃成长）。倍率类分数（依赖分/折算分）不参与
        成长，因为卡面写的是"打分值增加"。

        ``ExamFullPowerLessonMultipleAdditive``（全力强化）只放大
        ``full_power_scale`` 折算出的那一段：``int(分 × (1000 + 加成) / 1000)``；
        本牌自带的加成对自身也生效（卡面是"先强化再结算"），持续回合由
        ``_apply_card_buffs`` 记进 ``Buffs``。

        ``attribute_coefficient`` 是考试/舞台的属性倍率（411% = 4.11）：它作用在
        「buff/指針/不调乘完后」的整数分上，乘完再取整一次——与参考引擎
        ``resolveScore`` 的顺序/取整口径一致（两次都是 ``safeCeil``）。课程倍率 1.0
        时就是 buff 段取整一次。

        配了 ``attribute_bonuses`` + ``turn_attributes``（考试真实倍率，T5）时改用
        当前回合属性对应的千分比，并按客户端 ``CalcCurrentTurnBattleBonus`` 的
        ``ceil(f32(f32(bonus/1000)×amount) − f32(1e-4))`` 取整；此时
        ``attribute_coefficient`` 不参与（两者互斥，避免乘两次）。``parameter_buff``
        （审查基准加成）先乘、属性倍率最后乘，与参考引擎 ③ 在 f/g 之后一致。

        ``parameter_buff``（含本回合遗留的 ``turn_parameter_buff``）在**最终分**
        上叠加倍率 ``int(最终分 × 加成 / 1000)``；1000 = ×1.0（不加不减），
        1500 = ×1.5。两者同一口径，取较大者只乘一次。
        ``parameter_buff_turns > 1`` 时把加成记进 ``turn_parameter_buff``，供本回合
        后续牌继续吃（回合结束清零）。
        """
        award = 0
        turn_bonus = self._turn_bonus_permil()
        base_score = card.score
        if base_score > 0 and card.grow_score > 0 and uses > 0:
            base_score = base_score * (100 + uses * card.grow_score) / 100
        if base_score > 0:
            # 好调倍率（对照 gakumas-tools resolveScore，BSD-3）：
            #   1 + (0.5 + 绝好调 ? 好调回合数×0.1 : 0) × 倍率
            # 不是固定 1.5——绝好调下好调拖得越久越强。
            if self.buffs.condition_turns > 0:
                condition_bonus = 0.5
                if self.buffs.perfect_condition_turns > 0:
                    condition_bonus += 0.1 * self.buffs.condition_turns
                multiplier = 1.0 + condition_bonus
            else:
                multiplier = 1.0
            # 熱意（T5②）：集中加算之后、好调/指針倍率之前加进白值（参考引擎
            # resolveScore b 的 ``score += enthusiasm × enthusiasmMultiplier``；
            # 乘完后统一 safeCeil 一次，与参考引擎在 buff 段 ceil 的口径一致）。
            enthusiasm_score = self.enthusiasm * card.enthusiasm_multiplier / 1000.0
            raw = (
                (base_score + self.buffs.focus + enthusiasm_score)
                * multiplier
                * score_multiplier(self.stance)
            )
            # メタモルフォーゼ：披露 +25% 分数增益；支度 ×0.75（作用在减益基数上）
            if self.buffs.metamorphosis == "performance":
                raw *= 1.25
            elif self.buffs.metamorphosis == "preparation":
                raw *= 0.75
            # 不调：×0.67
            if self.buffs.poor_condition_turns > 0:
                raw *= 0.67
            coefficient = self.config.attribute_coefficient
            if turn_bonus is not None:
                # 考试真实倍率路径：属性倍率最后统一乘（含依赖分），这里先不乘
                coefficient = 1.0
            # 取整口径对齐参考引擎 resolveScore（BSD-3）：buff/指針/不调乘完后
            # 先 ceil 一次；回合属性倍率（考试/舞台）乘完再 ceil 一次。
            award = safe_ceil(raw)
            if coefficient != 1.0:
                award = safe_ceil(award * coefficient)
        if card.impression_scale > 0 and self.buffs.impression > 0:
            award += int(self.buffs.impression * card.impression_scale / 100)
        if card.block_scale > 0 and self.vitality > 0:
            award += int(self.vitality * card.block_scale / 100)
        if card.full_power_scale > 0 and self.stance.full_power_point > 0:
            # 卡表 values 是千分比（1000 = 卡面 100%：ProduceExamEffect
            # e_effect-exam_lesson_full_power_point-...-1000-01 可证），所以 /1000。
            # 不沿用 block_scale 的 /100：那会把"累计全力值的 100%"读成 1000%。
            power_score = int(self.stance.full_power_point * card.full_power_scale / 1000)
            full_power_multiple = max(
                card.full_power_lesson_multiple, self.buffs.full_power_lesson_multiple
            )
            if full_power_multiple > 0:
                power_score = int(power_score * (1000 + full_power_multiple) / 1000)
            award += power_score
        parameter_buff = max(card.parameter_buff, self.turn_parameter_buff)
        if parameter_buff > 0 and award > 0:
            award = int(award * parameter_buff / 1000)
        if card.parameter_buff > 0 and card.parameter_buff_turns > 1:
            self.turn_parameter_buff = max(self.turn_parameter_buff, card.parameter_buff)
        if turn_bonus is not None and award > 0:
            # 考试真实属性倍率（分段 + 联动惩罚）：客户端 CalcCurrentTurnBattleBonus
            award = battle_bonus_score(award, turn_bonus)
        return award

    def _turn_bonus_permil(self) -> int | None:
        """当前回合的属性倍率（千分比）；没配 ``attribute_bonuses``/``turn_attributes``
        时返回 None（旧行为：走单标量 ``attribute_coefficient``）。"""
        bonuses = self.config.attribute_bonuses
        attributes = self.config.turn_attributes
        if not bonuses or not attributes:
            return None
        index = max(self.total_turns - self.turns_left, 0)
        index = min(index, len(attributes) - 1)
        parameter_type = int(attributes[index])
        if parameter_type not in (1, 2, 3):
            raise ValueError(
                f"turn_attributes 只支持 1(Vo)/2(Da)/3(Vi)：{parameter_type}"
            )
        return int(bonuses[parameter_type - 1])

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
            self._fire_p_items(
                STATUS_GAIN,
                status="full_power_point",
                amount=card.full_power_point,
            )
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
        """结算卡面 buff（在算分之后，所以本牌不吃自己刚加的 buff）。

        - ``ExamReviewMultiple`` / ``ExamParameterBuffAdditiveFix`` /
          ``ExamFullPowerLessonMultipleAdditive`` 是**持续倍率/加算**：登记进
          ``Buffs`` 并记剩余回合（卡表 ``turn=-1`` = 永久）。好调加算在本牌
          自带的 ``condition`` 之前登记，所以同一张牌"好调增加量追加 +N"会
          作用到它自己给的好调（卡面这两项常在同一张牌上：先追加、下回合给
          好调；本模拟器把延迟好调也近似成本回合给，见模块 docstring）；
        - 好调回合数 = ``condition`` + 当前生效的 ``condition_additive``；
        - 元气获得量 = ``vitality + motivation``；``motivation`` 来自
          ``ExamCardPlayAggressive``（近似为永久干劲，见模块 docstring）；
        - ``ExamEnthusiasticAdditive`` / ``ExamEnthusiasticMultiple`` 登记成熱意
          追加/増加 buff（影响**之后**的温存解除等熱意获得）；
          ``ExamEnthusiasticTurnAdd`` 直接累加 ``enthusiasm_extension_turns``。
        """
        if card.condition_additive > 0:
            self.buffs.condition_additive = max(
                self.buffs.condition_additive, card.condition_additive
            )
            self.buffs.condition_additive_turns = _merge_buff_turns(
                self.buffs.condition_additive_turns,
                card.condition_additive_turns if card.condition_additive_turns else 1,
            )
        if card.review_multiple > 0:
            self.buffs.review_multiple = max(self.buffs.review_multiple, card.review_multiple)
            self.buffs.review_multiple_turns = _merge_buff_turns(
                self.buffs.review_multiple_turns,
                card.review_multiple_turns if card.review_multiple_turns else 1,
            )
        if card.full_power_lesson_multiple > 0:
            self.buffs.full_power_lesson_multiple = max(
                self.buffs.full_power_lesson_multiple, card.full_power_lesson_multiple
            )
            self.buffs.full_power_lesson_multiple_turns = _merge_buff_turns(
                self.buffs.full_power_lesson_multiple_turns,
                card.full_power_lesson_multiple_turns
                if card.full_power_lesson_multiple_turns
                else 1,
            )
        # 熱意系（T5② 2026-11-22）：追加=加算、増加=千分比、延長=回合数。
        # 同类型多来源时取最大值（参考引擎是加算叠加；卡池里极少同场两张，
        # 这里与其它持续 buff 保持同一保守口径，见模块 docstring）。
        if card.enthusiasm_bonus > 0:
            self.buffs.enthusiasm_bonus = max(
                self.buffs.enthusiasm_bonus, card.enthusiasm_bonus
            )
            self.buffs.enthusiasm_bonus_turns = _merge_buff_turns(
                self.buffs.enthusiasm_bonus_turns,
                card.enthusiasm_bonus_turns if card.enthusiasm_bonus_turns else 1,
            )
        if card.enthusiasm_multiple > 0:
            self.buffs.enthusiasm_multiple = max(
                self.buffs.enthusiasm_multiple, card.enthusiasm_multiple
            )
            self.buffs.enthusiasm_multiple_turns = _merge_buff_turns(
                self.buffs.enthusiasm_multiple_turns,
                card.enthusiasm_multiple_turns
                if card.enthusiasm_multiple_turns
                else 1,
            )
        if card.enthusiasm_extension > 0:
            self.enthusiasm_extension_turns += card.enthusiasm_extension

        condition_gain = card.condition
        if condition_gain > 0 and self.buffs.condition_additive > 0:
            condition_gain += self.buffs.condition_additive
        self.buffs.condition_turns += condition_gain
        self.buffs.focus += card.focus
        self.buffs.impression += card.impression
        vitality_gain = card.vitality + self.motivation
        if card.vitality > 0:
            # 干劲提升元气获得量；元气优先用于抵牌费（真机语义）
            self.vitality += vitality_gain
        self.motivation += card.motivation
        if condition_gain > 0:
            self._fire_p_items(
                STATUS_GAIN, status="parameter_buff", amount=condition_gain
            )
        if card.focus > 0:
            self._fire_p_items(STATUS_GAIN, status="focus", amount=card.focus)
        if card.impression > 0:
            self._fire_p_items(
                STATUS_GAIN, status="impression", amount=card.impression
            )
        if card.vitality > 0:
            self._fire_p_items(STATUS_GAIN, status="vitality", amount=vitality_gain)
        if card.motivation > 0:
            self._fire_p_items(
                STATUS_GAIN, status="aggressive", amount=card.motivation
            )

    def _pay_card_cost(self, card: CardSpec) -> None:
        """支付牌费：先按指針修正实际费用，強気 2 段階再穿透 1 点元气。

        指針体力代价（wiki 核实）：
        - 温存 1 段階 ×0.5、2 段階 ×0.25（向上取整）；
        - 強気 1/2 段階 ×2；2 段階额外 1 点直接扣体力（不吃元气）；
        - 无指針/全力 ×1。
        """
        cost = self._effective_cost(card)
        pierce = (
            min(cost, stamina_pierce(self.stance))
            if getattr(self.config, "stance_costs", True)
            else 0
        )
        if pierce:
            self.stamina -= pierce
        remaining = cost - pierce
        absorbed = min(self.vitality, remaining)
        self.vitality -= absorbed
        self.stamina -= remaining - absorbed

    def _effective_cost(self, card: CardSpec) -> int:
        """指針修正后的实际牌费（向上取整；不改变 card.cost 本身）。"""
        if not getattr(self.config, "stance_costs", True):
            return int(card.cost)
        multiplier = stamina_cost_multiplier(self.stance)
        if multiplier == 1.0:
            return int(card.cost)
        return math.ceil(card.cost * multiplier)

    def _has_unused_stamina_drink(self) -> bool:
        """槽里还有没消耗的回复饮料（真机可以下一回合喝它继续打牌）。"""
        return any(
            uses > 0 and drink.effect_type == "stamina"
            for drink, uses in zip(self.config.drinks, self.drink_uses)
        )

    # ------------------------------------------------------------------ P 道具
    def _passive_state(self) -> PassiveState:
        """把当前 LessonSim 局面投影成 p_items 的只读状态。"""
        return PassiveState(
            turn=self.current_turn,
            turns_left=self.turns_left,
            is_final_turn=self.turns_left <= 1,
            stamina=self.stamina,
            stamina_max=self.stamina_max,
            score=self.score,
            lesson_type="",
            is_sp=False,
            stacks={
                "vitality": self.vitality,
                "impression": self.buffs.impression,
                "focus": self.buffs.focus,
                "aggressive": self.motivation,
                "full_power_point": self.stance.full_power_point,
                "parameter_buff": self.buffs.condition_turns,
            },
            uses=self.p_item_uses,
        )

    def _fire_p_items(
        self,
        kind: str,
        *,
        card_category: str = "",
        cards_played_this_turn: int = 0,
        cards_played_total: int = 0,
        status: str = "",
        amount: int = 0,
    ) -> None:
        """在指定时机触发 P 道具并结算增量（分数/体力/层数）。"""
        if not self.p_items:
            return
        if kind == TURN_START:
            subset = self._p_items_by_trigger.get(TURN_START, ())
        elif kind == TURN_END:
            subset = self._p_items_by_trigger.get(TURN_END, ())
        elif kind == STATUS_GAIN:
            subset = self._p_items_by_trigger.get(STATUS_GAIN, ())
        else:
            # card_play / card_played / card_play_interval 共享同一个事件 kind
            subset = (
                self._p_items_by_trigger.get("card_play", ())
                + self._p_items_by_trigger.get("card_played", ())
                + self._p_items_by_trigger.get("card_play_interval", ())
            )
        if not subset:
            return
        event = PassiveEvent(
            kind=kind,
            card_category=card_category,
            cards_played_this_turn=cards_played_this_turn,
            cards_played_total=cards_played_total,
            status=status,
            amount=amount,
        )
        delta = apply_passive(subset, event, self._passive_state())
        if delta.is_zero():
            return
        self.score += int(delta.score)
        if delta.stamina:
            self.stamina = min(self.stamina_max, max(0, self.stamina + delta.stamina))
        for key, value in delta.stacks.items():
            if key == "vitality":
                self.vitality += int(value)
            elif key == "impression":
                self.buffs.impression += int(value)
            elif key == "focus":
                self.buffs.focus += int(value)
            elif key == "aggressive":
                self.motivation += int(value)
            elif key == "full_power_point":
                self.stance = apply_full_power_point(self.stance, int(value))
            elif key == "parameter_buff":
                # P 道具的「好调」按回合数近似；模拟器没有独立参数 buff 资源
                self.buffs.condition_turns += int(value)
        for item_id in delta.applied:
            self.p_item_uses[item_id] = self.p_item_uses.get(item_id, 0) + 1

    def _end_turn(self, *, skipped: bool) -> None:
        """回合结束：结算好印象得分、衰减好调/持续 buff、记录 trace、弃手牌、抽下一手。

        好印象时序（2026-11-16 wiki 核实）：**回合结束按当前层数加等量分，
        **下一回合开始**才 -1**（不是结束就扣）。最后一回合结束后没有下一回合，
        所以层数不再扣——这一点和旧实现不同，旧实现会在最终回合也扣掉。
        ``ExamReviewMultiple``（好印象强化）在这里放大本回合的好印象结算分。

        T5②（2026-11-22）：好印象结算也会加**熱意**（参考引擎里它走同一个
        ``resolveScore``；我们只在熱意 > 0 时改旧取整路径）；熱意在本回合结束
        归 0，有「熱意延長」则保留并消耗 1 层；温存→全力的**回合边界**指針切换
        也结算解除收益（熱意 / 固定元気 / 新回合 +1 出牌次数）。

        SKIP / 手牌自然打空（付不起牌）走同一条结算路径：剩余手牌直接进弃牌堆，
        下一回合补满 ``hand_size`` 张。**回合末体力回复**：若本回合出牌次数没
        用完（``plays_this_turn < plays_per_turn + extra_plays``，也就是 SKIP 或
        打不起牌），体力 +2、封顶 ``stamina_max``（参考引擎 ``TurnManager.endTurn``
        的 ``cardUsesRemaining > 0 → stamina += 2``）；出牌次数用尽自动结束的回合
        不回体力。
        """
        # 回合末体力回复（参考引擎 endTurn 顺序：先回体力，再触发 endOfTurn 效果）
        if self.plays_this_turn < self.plays_per_turn + self.extra_plays:
            self.stamina = min(self.stamina_max, self.stamina + 2)
        if self.buffs.impression > 0:
            # ExamReviewMultiple（好印象强化）：放大回合末的好印象结算分。
            # 卡表 values 是千分比（2000 = 卡面 +200%），所以 ×(1000+值)/1000。
            impression_score = self.buffs.impression
            if self.buffs.review_multiple > 0:
                impression_score = int(
                    impression_score * (1000 + self.buffs.review_multiple) / 1000
                )
            # 熱意（T5②）：参考引擎里回合末好印象也走 resolveScore、会加熱意；
            # 只在熱意 > 0 时改旧取整路径（对旧行为逐位不变）。
            if self.enthusiasm > 0:
                impression_score = safe_ceil(impression_score + self.enthusiasm)
            turn_bonus = self._turn_bonus_permil()
            if turn_bonus is not None and impression_score > 0:
                # 参考引擎把回合末好印象合成一张 ExamLesson 结算，因此同样吃属性倍率
                impression_score = battle_bonus_score(impression_score, turn_bonus)
            self.score += impression_score
            # 不在这里 -1：下一回合开始时扣（见 _draw_hand）
        if self.buffs.condition_turns > 0:
            self.buffs.condition_turns -= 1
        # 绝好调 / 不调也按剩余回合衰减；メタモルフォーゼ是偶像特性，不随回合消失
        if self.buffs.perfect_condition_turns > 0:
            self.buffs.perfect_condition_turns -= 1
        if self.buffs.poor_condition_turns > 0:
            self.buffs.poor_condition_turns -= 1
        # 持续类 buff 剩余回合 -1；到 0 后同时清掉倍率，永久（-1）保持
        self.buffs.condition_additive_turns = _tick_buff_turns(
            self.buffs.condition_additive_turns
        )
        if self.buffs.condition_additive_turns == 0:
            self.buffs.condition_additive = 0
        self.buffs.review_multiple_turns = _tick_buff_turns(self.buffs.review_multiple_turns)
        if self.buffs.review_multiple_turns == 0:
            self.buffs.review_multiple = 0
        self.buffs.full_power_lesson_multiple_turns = _tick_buff_turns(
            self.buffs.full_power_lesson_multiple_turns
        )
        if self.buffs.full_power_lesson_multiple_turns == 0:
            self.buffs.full_power_lesson_multiple = 0
        # 熱意追加/増加 buff 的剩余回合：到 0 后同时清掉数值，永久（-1）保持
        self.buffs.enthusiasm_bonus_turns = _tick_buff_turns(
            self.buffs.enthusiasm_bonus_turns
        )
        if self.buffs.enthusiasm_bonus_turns == 0:
            self.buffs.enthusiasm_bonus = 0
        self.buffs.enthusiasm_multiple_turns = _tick_buff_turns(
            self.buffs.enthusiasm_multiple_turns
        )
        if self.buffs.enthusiasm_multiple_turns == 0:
            self.buffs.enthusiasm_multiple = 0
        # 熱意：回合末归 0；有「熱意延長」则保留并消耗 1 层（参考引擎 TurnManager.endTurn）
        self.enthusiasm, self.enthusiasm_extension_turns = turn_end_enthusiasm(
            self.enthusiasm, self.enthusiasm_extension_turns
        )
        # 审查基准加成只在本回合内持续
        self.turn_parameter_buff = 0
        # P 道具：回合结束（好印象/好调结算后、弃手牌前）
        self._fire_p_items(TURN_END)
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
        previous_stance = self.stance
        self.stance = end_turn(self.stance)
        if self.turns_left > 0:
            self._draw_hand()
            # 温存→全力 的**回合边界**切换也触发解除收益（参考引擎 startTurn 的
            # FULL_POWER_EFFECTS 里 setStance(fullPower) 会触发 STANCE_CHANGED_EFFECTS）。
            # _draw_hand 已把 extra_plays 清零，所以 +1 次数加在新回合的基础次数上。
            if getattr(self.config, "stance_costs", True):
                release_enthusiasm, release_genki, release_plays = (
                    release_on_stance_change(previous_stance, self.stance)
                )
                if release_enthusiasm or release_genki or release_plays:
                    self.enthusiasm += enthusiasm_gain(
                        release_enthusiasm,
                        bonus=self.buffs.enthusiasm_bonus,
                        multiple_permil=self.buffs.enthusiasm_multiple,
                    )
                    self.vitality += release_genki
                    self.extra_plays += release_plays

    def _draw_hand(self) -> None:
        # 新手牌 = 新回合：好印象在**下一回合开始时** -1（回合末已按当前层数加分）
        if self.buffs.impression > 0:
            self.buffs.impression -= 1
        # 本回合出牌数、额外次数、已喝饮料数从 0 重新计
        self.plays_this_turn = 0
        self.extra_plays = 0
        self.drinks_used_this_turn = 0
        self.hand.clear()
        self._draw(self.config.hand_size)
        # P 道具：回合开始（抽完手牌后、出牌前）
        self._fire_p_items(TURN_START)

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


def _plan_card_matches(card: CardSpec, name: str) -> bool:
    """这张牌是否属于方案优先级里的某一类 buff（按 CardSpec 字段判断）。"""
    return any(getattr(card, field, 0) > 0 for field in PLAN_BUFF_FIELDS.get(name, ()))


def _plan_buff_rank(card: CardSpec, priority: tuple[str, ...]) -> int:
    """方案优先级名次：0 = 最先铺；没命中任何优先 buff 的牌排在最后。"""
    for rank, name in enumerate(priority):
        if _plan_card_matches(card, name):
            return rank
    return len(priority)


def greedy_policy(sim: LessonSim) -> Action:
    """基线策略：能出的牌里挑 ``分数 / 体力`` 最高的，都出不起就 SKIP。

    只按卡面分数算，不评估 buff 收益，也不做体力预算——仅用于验证模拟器
    能跑通、给参数搜索当对照基线。

    指針牌（温存 / 強気 / 全力值）常常 ``score=0``，纯按卡面分数效率恒为 0，
    永远不会被选中；这里把这类牌的效率固定按 ``_STANCE_CARD_EFFICIENCY``
    计，让基线也会打它们（实际收益仍由 LessonSim 的指針结算决定）。
    熱意 buff 牌（熱意追加/増加/延長，T5②）同样常常 ``score=0``，并入这一档。
    「可出牌次数 +N」牌同理，固定按 ``_EXTRA_PLAY_CARD_EFFICIENCY`` 计，
    否则 score=0 的加次数牌永远不会被选中。
    「依赖元气分（``block_scale``）/ 审查基准加成（``parameter_buff``）」的牌
    也常常 ``score=0``，同样给固定效率 ``_DEPENDENT_CARD_EFFICIENCY``，
    避免这类牌永远轮不到；已经有白值的牌仍按白值效率排序。
    ``full_power_scale``（全力值折算分）也是 ``score=0`` 也能得分的牌，按同一档处理。

    **方案（プラン）**：``LessonConfig.plan`` 决定先铺哪些 buff——

    - 感性/理性：前 ``early_buff_turns`` 回合按 ``plans[plan].buff_priority``
      的顺序铺层（感性 好调→集中、理性 好印象→やる気）；
    - 非凡：早期不无脑铺 buff，先切温存（没到 2 段階时）攒全力值，最后 2 回合
      直接兑现打分/全力折算牌。
    """
    playable = [index for index in sim.legal_actions() if index is not None]
    if not playable:
        return None

    plan = getattr(sim, "plan", DEFAULT_PLAN)
    plan_config = getattr(sim, "plan_config", None) or default_plan_library().get(plan)
    turns = sim.turns_left

    def efficiency(index: int) -> tuple[float, float, int, int]:
        card = sim.hand[index]
        # 指針会改实际牌费（温存减半/強気双倍）；基线也要按实际费用比
        cost = sim._effective_cost(card)
        if (
            card.preservation > 0
            or card.full_power_point > 0
            or card.strong_level > 0
            or card.enthusiasm_bonus > 0
            or card.enthusiasm_multiple > 0
            or card.enthusiasm_extension > 0
        ):
            return (_STANCE_CARD_EFFICIENCY, _STANCE_CARD_EFFICIENCY, -cost, -index)
        if card.extra_play > 0:
            return (
                _EXTRA_PLAY_CARD_EFFICIENCY,
                _EXTRA_PLAY_CARD_EFFICIENCY,
                -cost,
                -index,
            )
        if card.score <= 0 and (
            card.block_scale > 0
            or card.parameter_buff > 0
            or card.full_power_scale > 0
            or card.review_multiple > 0
        ):
            return (
                _DEPENDENT_CARD_EFFICIENCY,
                _DEPENDENT_CARD_EFFICIENCY,
                -cost,
                -index,
            )
        # 0 费牌按 1 费算，避免"1 分 0 费"霸榜
        return (card.score / max(cost, 1), card.score, -cost, -index)

    # 目标函数是 PERFECT，不是 CLEAR：最后一回合还没到 PERFECT 线时按"总分最大"
    # 选牌（而不是性价比），把 CLEAR+PERFECT 的完整属性档打满。
    if turns is not None and turns <= 1 and sim.score < sim.target_perfect:
        return max(
            playable,
            key=lambda index: (
                sim.hand[index].score,
                sim.hand[index].full_power_scale,
                -sim._effective_cost(sim.hand[index]),
                -index,
            ),
        )

    if plan == "anomaly":
        if turns is not None and turns <= 2:
            # 全力窗口：最后 1-2 回合不再铺指針，直接兑现打分 / 全力值折算牌。
            cash = [
                index
                for index in playable
                if sim.hand[index].score > 0 or sim.hand[index].full_power_scale > 0
            ]
            if cash:
                return max(cash, key=efficiency)
        else:
            # 温存优先：先切到温存（未满 2 段階时）攒全力值，再考虑其它动作。
            if sim.stance.save_level < 2:
                save = [index for index in playable if sim.hand[index].preservation > 0]
                if save:
                    return max(
                        save,
                        key=lambda index: (
                            sim.hand[index].full_power_point,
                            -sim.hand[index].cost,
                            -index,
                        ),
                    )
            # 全力值没攒满前，优先打全力值牌，否则「全力 ×3」的窗口永远不来。
            if sim.stance.stance != "full" and sim.stance.full_power_point < FULL_POWER_POINT_COST:
                build = [index for index in playable if sim.hand[index].full_power_point > 0]
                if build:
                    return max(
                        build,
                        key=lambda index: (
                            sim.hand[index].full_power_point,
                            -sim.hand[index].cost,
                            -index,
                        ),
                    )
    elif turns is not None and turns >= plan_config.early_buff_turns > 0:
        # 前几个回合先铺层数类 buff：集中/好调/印象/干劲会让后续每张牌更强，
        # 越早铺越值钱；顺序按方案 buff_priority（感性 好调→集中、理性 好印象→やる気）。
        buffs = [
            index
            for index in playable
            if sim.hand[index].focus > 0
            or sim.hand[index].condition > 0
            or sim.hand[index].impression > 0
            or sim.hand[index].motivation > 0
        ]
        if buffs:
            def _buff_key(index: int) -> tuple[int, float, int, int]:
                card = sim.hand[index]
                rank = _plan_buff_rank(card, plan_config.buff_priority)
                weight = (
                    card.focus * 30.0
                    + card.condition * 40.0
                    + card.impression * 20.0
                    + card.motivation * 10.0
                )
                return (-rank, weight, -card.cost, -index)

            return max(buffs, key=_buff_key)

    return max(playable, key=efficiency)
