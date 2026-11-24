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
不取整的差异记录在那里）。**P1-1（2026-11-24）补全**：のんびり（leisure）指針
（分数/费用 ×0、解除 +5 固定元気/+1 次数/熱意+10 或全体卡打分成长+10）与
全力回合 +1 出牌/保留牌回手（``FULL_POWER_CHANGED_EFFECTS``）；来源见
``stance.LEISURE_RESERVE_SOURCES``（卡预约）与 P 道具 ``stance_leisure`` 直给。
**仍未建模**：P 道具/附魔触发的熱意、同一张牌里「温存→強気→温存」这种净指針
不变的中间解除（我们只看本牌结算前后指針，中间状态看不到）、指針固定
（lockStanceTurns，来源卡切磋琢磨含保留区效果，留 P1-3）、保留区来源
（holdCard/holdThisCard，P1-3；回手钩子已按参考实现）。

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
from gkagent.sim.hold import HOLD_LIMIT, HOLD_SELECT_ZONES, hold_pick
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
    PItemDelta,
    PItemSpec,
    add_timed,
    apply_passive,
    intercept_debuff_entries,
    normalize_turns,
    tick_timed,
    timed_dict_add,
    timed_dict_tick,
    timed_dict_total,
    total_timed,
)
from gkagent.sim.stance import (
    FULL_POWER_POINT_COST,
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


def genki_gate(gain: int, nullify_genki_turns: int, unease_turns: int) -> int:
    """P1-7（2026-11-24）：resolveGenki 的 genki+= 渠道闸门（纯函数，双镜共用）。

    参考 ``resolvers.js::resolveGenki``：``if (nullifyGenkiTurns) return;``（整段
    不增元气）→ ``genki += motivation×motivationMultiplier`` → ``if (uneaseTurns)
    genki *= 0.67``（随后 WHOLE_FIELDS 向上取整）。``gain`` 是已含干劲加成的获得量
    （卡渠道 = vitality+motivation）；nullify>0 → 0，unease>0 → ×0.67 向上取整。
    **fixedGenki（resolveFixedGenki）不走本函数**（不受无效/不安影响）。
    """
    if gain <= 0 or nullify_genki_turns > 0:
        return 0
    if unease_turns > 0:
        return safe_ceil(gain * 0.67)
    return gain


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
    # ---- P1-1 2026-11-24：のんびり预约（ExamOverPreservation，默认 0 = 旧行为）----
    # 打出后登记一个回合开始预约：条件满足时把指針切到 のんびり。
    # leisure_reserve = 剩余触发次数（-1 永久，0 无预约）；
    # leisure_reserve_when_save = True 温存中才触发（のんびり屋さん等 3 族），
    # False 非温存才触发（俯瞰群星的启明星，limit 3）。
    # 证据：stance.LEISURE_RESERVE_SOURCES（BSD-3 skill_cards.csv 逐卡交叉）。
    leisure_reserve: int = 0
    leisure_reserve_when_save: bool = True
    # ---- P1-2 2026-11-24：自尊 pride（ExamLessonValueMultipleDependReviewOrAggressive）----
    # 打出后 prideTurns += N（参考 skill_cards.csv 632/633「私は、決して」prideTurns+=5；
    # 主数据卡表 turn 列）。pride_min_motivation 是触发门槛（参考 conditions
    # if:motivation>=9，主数据 trigger e_trigger-none-card_play_aggressive_up-9）：
    # 出牌前干劲 >= 门槛才给自尊；0 = 无门槛。 prideTurns > 0 期间出牌分/回合末
    # 好印象分享受 resolveScore f 的 min(好印象,干劲)×0.02（上限 +0.5）加成。
    pride_turns: int = 0
    pride_min_motivation: int = 0
    # ---- P1-3 2026-11-24：hold 保留区（ExamCardMove）+ 指針固定（StanceLock）----
    # 主数据 ExamCardMove 的 values 恒空，语义按 BSD-3 skill_cards.csv 逐卡证据表
    # （hold.HOLD_SOURCES）；表外卡保留旧 +1 抽牌近似（交互未建模，不猜）。
    # hold_this：holdThisCard（保留自身，温存中触发时 when_save=True，参考
    # if:isPreservation { holdThisCard }，主数据 trigger preservation_up 交叉）；
    # hold_select_zones：holdSelected 目标区（""=无 / hand / deck / deck_grave）；
    # hold_select_count：选牌张数（那一天，在这里 +/++/+++ = 2）；
    # hold_move_to_hand：moveHeldCardsToHand 卡效果版（一点一滴的进步）；
    # lock_stance_turns：StanceLock turn=N ↔ lockStanceTurns+=N（切磋琢磨），
    # 回合末 -1（fresh 保护：获得当回合末不扣，锁下一回合，见 _end_turn）。
    hold_this: int = 0
    hold_this_when_save: bool = False
    hold_select_zones: str = ""
    hold_select_count: int = 1
    hold_move_to_hand: bool = False
    lock_stance_turns: int = 0


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
    # P 道具（训练/考试右上角被动）：真实对局列表来自 loadout 的
    # ``produce_item_ids``（本仓库离线数据 = gkbench 题模板；解析见
    # ``gkagent.data.p_items_db``）；默认空 = 旧行为（不结算任何 P 道具）。
    # 训练/考试开始时的效果在构造时结算一次（见 LessonSim.__init__）。
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
        # B8（2026-11-22）：P 道具条件/依赖换算用的本场累计量
        self.full_power_point_total: int = 0  # 累计全力值（「累计全力值的 N% 数值变为…」源）
        self.consumed_stamina_total: int = 0  # 累计消耗体力（「消耗过的体力的 N%」源）
        self.status_gain_counts: dict[str, int] = {}  # 各状态累计增加次数（status_gain_interval）
        # ---- B9（2026-11-22）：P 道具持久倍率 / modifier 状态 -----------------
        # 分数上升量倍率：((千分比, 剩余回合), …)，-1 = 永久。参考引擎同类 buff
        # 按 turns 分组、amount 加算（resolveScore f）；回合末倒计时。
        self.score_buffs: tuple[tuple[int, int], ...] = ()
        # 分数上升量减少（resolveScore g：score *= max(1−Σ, 0)）
        self.score_debuffs: tuple[tuple[int, int], ...] = ()
        # ---- P1-2（2026-11-24）：handDecrease 抽牌修正 / pride 自尊 ------------
        # 手牌减少：((减少量, 剩余回合), …)，-1 = 永久（参考 BuffManager.handDecreases
        # 列表：setHandDecrease(amount, turns?) 按 turns 分组加算、回合末倒计时）。
        # 回合开始抽牌 max(hand_size − Σ, 0)（TurnManager.startTurn cardsToDraw）；
        # 只影响回合开始抽牌，不影响卡效果抽牌（wiki buffs.json 口径）。
        self.hand_decreases: tuple[tuple[int, int], ...] = ()
        # 自尊剩余回合（参考 prideTurns：EOT_DECREMENT_FIELDS 回合末 -1；
        # >0 时 resolveScore f 加算 min(min(好印象,干劲)×20, 500) 千分比）。
        self.pride_turns: int = 0
        # ---- P1-4（2026-11-24）：低下状态无效（nullifyDebuff，消耗式计数器）----
        # 参考 BuffManager.initializeState 标量、不在 EOT_DECREMENT_FIELDS（无回合
        # 倒计时）；Executor.executeAssignment/executeCallAction：>0 时拦截一次
        # debuff 施加（setScoreDebuff/setHandDecrease 等）并 -1。来源 ExamAntiDebuff
        # values.count（P 道具侧；卡侧 4 SSR 族 values 恒空延迟，见 RULES_REFERENCE §5.7）。
        self.nullify_debuff: int = 0
        # ---- P1-7（2026-11-24）：元气增加无效 / 不安（resolveGenki 两个 debuff 闸门）----
        # 参考 EOT_DECREMENT_FIELDS（回合末 -1）+ DEBUFF_FIELDS（nullifyDebuff 拦截施加）。
        # nullify_genki_turns>0：genki+= 渠道整段不增元气（resolveGenki return）；
        # unease_turns>0：genki+= 渠道获得量 ×0.67（向上取整）。fixedGenki 不受影响。
        self.nullify_genki_turns: int = 0
        self.unease_turns: int = 0
        # P1-7：延迟生效 P 道具增量 [(剩余回合, PItemDelta), …]。触发回合登记
        # （次数当时计），剩余回合每回合末 -1（参考 EffectManager.decrementDelay），
        # 到 0 的下一回合开始结算（参考嵌套 at:turn / delay:N 在 turn 阶段触发）。
        self._delayed_deltas: list[tuple[int, PItemDelta]] = []
        # 其它持久倍率：key -> ((数值, 剩余回合), …)
        # （review_times / concentration_effect / concentration_gain / impression_gain /
        #   motivation_gain / full_power_charge）
        self.modifiers: dict[str, tuple[tuple[int, int], ...]] = {}
        # 费用修正：永久加减值 + 「接下来 N 回合」的 ×0.5 / ×2 计数器
        self.cost_reduction: int = 0
        self.cost_increase: int = 0
        self.half_cost_turns: int = 0
        self.double_cost_turns: int = 0
        # 回合追加（ExamExtraTurn）：pending 在本回合结束（turns_left-1 之后）加上；
        # granted 累计已追加回合数，``total_turns`` 随之增长（当前回合号不跳变）。
        self.extra_turns_pending: int = 0
        self.extra_turns_granted: int = 0
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
        # P1-1（2026-11-24）：保留区（held）。P1-3（2026-11-24）来源接通：
        # holdThisCard/holdSelected/moveHeldCardsToHand 卡效果（hold.HOLD_SOURCES
        # 逐卡证据表）；上限 2（超限最旧进弃牌堆，参考 enforceHoldLimit）；
        # 跨回合保留（endTurn 只弃手牌）；全力回合 moveHeldCardsToHand 回手（P1-1）。
        self.held: list[CardSpec] = []
        # P1-3：指針固定剩余回合（参考 lockStanceTurns：EOT_DECREMENT_FIELDS
        # 回合末 -1；>0 时禁切指針 + 全力进入门不满足）。fresh 保护：卡效果
        # 0→正 的当回合末不扣（参考 Executor freshBuffs），锁的是下一回合。
        self.lock_stance_turns: int = 0
        self._lock_stance_fresh: bool = False

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
        # 非凡指針：温存 / 強気 / 全力 / のんびり 的倍率状态（纯函数模块 stance.py）
        self.stance = StanceState()
        # P1-1（2026-11-24）：のんびり预约列表 [(剩余次数, 是否温存中触发), …]
        # （出牌登记，回合开始结算；-1 永久）。参考引擎 afterStartOfTurn/startOfTurn
        # 预约在本模型里都在抽牌后结算（期间无其它指針交互，等价）。
        self.leisure_reserves: list[tuple[int, bool]] = []
        # P1-1：のんびり→全力 的全体卡打分成长（target:all g.score+=10，永久加算，
        # 每次出牌加进白值；参考引擎 cardMap growth + resolveScore）。
        self.score_growth_all: int = 0
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

        # P 道具：训练/考试开始时的一次性效果（抽第一手牌**之前**；回合开始类
        # P 道具在 _draw_hand 里触发，保证"考试开始 → 回合开始"的先后）。
        # exam_start 给的额外出牌次数属于第 1 回合，所以初始抽牌不清零。
        self._fire_p_items(EXAM_START)
        self._draw_hand(keep_extra_plays=True)
        # B10：训练开始后（exam_start_after，参考 at:afterStartOfStage）——
        # 抽完第一手牌之后结算一次（生成卡到手牌等）。
        self._fire_p_items(EXAM_START_AFTER)

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
        # P1-3：保留区也是 tracked 区，重布置时一并清（与 discard/excluded 同口径）
        self.held.clear()
        self._min_cost = min((card.cost for card in self.deck), default=0)

    # ------------------------------------------------------------------ 状态
    @property
    def total_turns(self) -> int:
        """本课程总回合数（配置值 + 考试内追加回合；与剩余回合一起决定进度）。"""
        return int(self.config.turns) + int(self.extra_turns_granted)

    # ---- B9：持久倍率 / modifier 读取 -------------------------------------
    def _mod_total(self, key: str) -> int:
        """某个持久 modifier 渠道当前生效的合计值（千分比/次数）。"""
        return timed_dict_total(self.modifiers, key)

    def _gain_multiple(self, key: str) -> float:
        """「X 增加量增加 +N%」类增益倍率（1.0 = 不变）。"""
        permil = self._mod_total(key)
        return 1.0 + permil / 1000.0 if permil else 1.0

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
        # 温存/のんびり解除（参考引擎 STANCE_CHANGED_EFFECTS）：熱意 +5/+8/+10、
        # 固定元気 +5、当回合出牌次数 +1、のんびり→全力全体卡打分成长 +10；
        # 同回合内反复解除按次数重复触发。旧实现把熱意近似成好调回合，
        # T5② 2026-11-22 改为独立熱意资源（见 enthusiasm.py）。
        if getattr(self.config, "stance_costs", True):
            release_enthusiasm, release_genki, release_plays, release_growth = (
                release_on_stance_change(previous_stance, self.stance)
            )
            if release_enthusiasm or release_genki or release_plays or release_growth:
                self.enthusiasm += enthusiasm_gain(
                    release_enthusiasm,
                    bonus=self.buffs.enthusiasm_bonus,
                    multiple_permil=self.buffs.enthusiasm_multiple,
                )
                # 固定元気：不吃「やる気」加成（参考引擎 resolveFixedGenki）
                self.vitality += release_genki
                self.extra_plays += release_plays
                self.score_growth_all += release_growth
        # P1-3：保留区结算（holdThisCard/holdSelected/moveHeldCardsToHand）。
        # 在抽牌/出牌后 P 道具之前——参考 DSL 里 hold 动作先于 drawCard，
        # holdThisCard 的条件在 processCard 阶段求值（afterCardUsed 触发之前）。
        held_this = self._apply_hold(card)
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
            card_name=card.name,
            cards_played_this_turn=self.plays_this_turn,
            cards_played_total=self.cards_played_total,
        )
        if held_this:
            # P1-3：holdThisCard 已把本牌放进保留区（参考 useCard 末尾
            # thisCardHeld 为真时不进弃牌堆/除外区），这里不再落牌。
            pass
        elif card.once:
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
            # P1-2：自尊回合数是直接效果（prideTurns+=N），再演同样翻倍
            pride_turns=card.pride_turns * 2,
            # P1-3：指針固定回合数是直接效果（lockStanceTurns+=N），再演翻倍；
            # hold 字段不翻倍——参考 hold() 按卡索引幂等（再演重复 holdThisCard
            # 是 no-op），holdSelected 重执行属策略选择，保守不翻倍。
            lock_stance_turns=card.lock_stance_turns * 2,
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
        # P1-1：のんびり→全力 的全体卡打分成长加进白值（参考引擎 resolveScore
        # 的 growth[g.score]，在集中/熱意/倍率之前；score=0 的牌吃了成长也进算分）。
        base_score = card.score + self.score_growth_all
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
            # B9：集中强化（ExamLessonBuffMultiple，P 道具）→ 集中对分数的贡献
            # ×(1+N%)（参考引擎 resolveScore a 的 concentrationEffectBuffs）。
            focus_score = self.buffs.focus * self._gain_multiple("concentration_effect")
            raw = (
                (base_score + focus_score + enthusiasm_score)
                * multiplier
                * score_multiplier(self.stance)
            )
            # メタモルフォーゼ：披露 +25% 分数增益；支度 ×0.75（作用在减益基数上）
            if self.buffs.metamorphosis == "performance":
                raw *= 1.25
            # B9：P 道具持久分数倍率（参考引擎 resolveScore f/g）
            score_buff = total_timed(self.score_buffs)
            # P1-2：自尊 pride（resolveScore f）——prideTurns>0 时加算
            # min(min(好印象,干劲)×0.02, 0.5)，千分比即 min(min×20, 500)。
            if self.pride_turns > 0:
                score_buff += min(min(self.buffs.impression, self.motivation) * 20, 500)
            if score_buff:
                raw *= 1.0 + score_buff / 1000.0
            score_debuff = total_timed(self.score_debuffs)
            if score_debuff:
                raw *= max(1.0 - score_debuff / 1000.0, 0.0)
            if self.buffs.metamorphosis == "preparation":
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

        B8：全力值获得累计进 ``full_power_point_total``（「累计全力值的 N%」换算源），
        指針变化后发一次 ``stance_change`` 事件。

        P1-1（2026-11-24）：指針変更过 ``stance_change_allowed`` 守卫（参考引擎
        ``BuffManager.setStance``：全力期间不能切指針、のんびり期间不能切温存）；
        全力值获得不受守卫影响（resolveFullPowerCharge 独立）。``leisure_reserve``
        牌打出后登记のんびり预约（回合开始结算，见 ``_apply_leisure_reserves``）。
        """
        previous_stance = self.stance
        if card.full_power_point > 0:
            # B9：全力值增加量增加（ExamFullPowerPointAdditive）→ 获得量 ×(1+N%)
            points = safe_ceil(
                card.full_power_point * self._gain_multiple("full_power_charge")
            )
            self.stance = apply_full_power_point(self.stance, points)
            self.full_power_point_total += points
            self._fire_p_items(
                STATUS_GAIN,
                status="full_power_point",
                amount=points,
            )
        locked = self.lock_stance_turns > 0
        if card.strong_level > 0 and stance_change_allowed(
            self.stance, "concentration", locked=locked
        ):
            delta = card_stance_effect("ExamConcentration", [card.strong_level])
            if delta["stance"] is not None:
                self.stance = replace(
                    self.stance,
                    stance=delta["stance"],
                    strong_level=card.strong_level,
                    save_level=0,
                )
        if card.preservation > 0 and stance_change_allowed(
            self.stance, "preservation", locked=locked
        ):
            delta = card_stance_effect("ExamPreservation", [card.preservation])
            if delta["stance"] is not None:
                # 温存段階只升不降：已在 2 段階时再打 1 段階温存牌保持 2 段階
                self.stance = replace(
                    self.stance,
                    stance=delta["stance"],
                    strong_level=0,
                    save_level=max(self.stance.save_level, int(delta["save_level"])),
                )
        # P1-3：指針固定（StanceLock turn=N ↔ DSL lockStanceTurns+=N，切磋琢磨）。
        # 0→正 打 fresh 标记（参考 Executor freshBuffs：获得当回合末不扣）。
        if card.lock_stance_turns > 0:
            before = self.lock_stance_turns
            self.lock_stance_turns += int(card.lock_stance_turns)
            if before == 0:
                self._lock_stance_fresh = True
        if card.leisure_reserve != 0:
            # のんびり预约（ExamOverPreservation）：登记到回合开始结算。
            # 再演（encore）不翻倍预约——它是延迟效果，不是本牌直接效果。
            self.leisure_reserves.append(
                (int(card.leisure_reserve), bool(card.leisure_reserve_when_save))
            )
        if self.stance != previous_stance:
            self._fire_p_items(STANCE_CHANGE)

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
        # P1-2：自尊（ExamLessonValueMultipleDependReviewOrAggressive）——
        # 出牌前干劲达到门槛才给 prideTurns（参考 if:motivation>=9 条件门；
        # 本牌自己的干劲加成在之后才生效，门槛用出牌前的层数）。
        if card.pride_turns > 0 and self.motivation >= card.pride_min_motivation:
            self.pride_turns += card.pride_turns

        condition_gain = card.condition
        if condition_gain > 0 and self.buffs.condition_additive > 0:
            condition_gain += self.buffs.condition_additive
        # P1-7：好调增加量增加（ExamParameterBuffAdditive / setGoodConditionTurnsBuff）
        # 增益倍率，乘在获得量上向上取整（参考 resolveGoodConditionTurns：先加算
        # condition_additive 再 ×(1+Σ goodConditionTurnsBuffs)）。
        if condition_gain > 0:
            condition_gain = safe_ceil(condition_gain * self._gain_multiple("condition_gain"))
        self.buffs.condition_turns += condition_gain
        # B9：P 道具「X 增加量增加 +N%」增益倍率（参考引擎 setConcentrationBuff /
        # setGoodImpressionTurnsBuff / setMotivationBuff，乘在获得量上、向上取整）。
        focus_gain = card.focus
        if focus_gain > 0:
            focus_gain = safe_ceil(focus_gain * self._gain_multiple("concentration_gain"))
        impression_gain = card.impression
        if impression_gain > 0:
            impression_gain = safe_ceil(impression_gain * self._gain_multiple("impression_gain"))
        motivation_gain = card.motivation
        if motivation_gain > 0:
            motivation_gain = safe_ceil(motivation_gain * self._gain_multiple("motivation_gain"))
        self.buffs.focus += focus_gain
        self.buffs.impression += impression_gain
        vitality_gain = card.vitality + self.motivation
        if card.vitality > 0:
            # 干劲提升元气获得量；元气优先用于抵牌费（真机语义）。
            # P1-7：genki+= 渠道过 resolveGenki 闸门（元气增加无效→0 / 不安×0.67）。
            vitality_gain = genki_gate(
                vitality_gain, self.nullify_genki_turns, self.unease_turns
            )
            self.vitality += vitality_gain
        self.motivation += motivation_gain
        if condition_gain > 0:
            self._fire_p_items(
                STATUS_GAIN, status="parameter_buff", amount=condition_gain
            )
        if focus_gain > 0:
            self._fire_p_items(STATUS_GAIN, status="focus", amount=focus_gain)
        if impression_gain > 0:
            self._fire_p_items(
                STATUS_GAIN, status="impression", amount=impression_gain
            )
        if card.vitality > 0 and vitality_gain > 0:
            self._fire_p_items(STATUS_GAIN, status="vitality", amount=vitality_gain)
        if motivation_gain > 0:
            self._fire_p_items(
                STATUS_GAIN, status="aggressive", amount=motivation_gain
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
        stamina_before = self.stamina
        if pierce:
            self.stamina -= pierce
        remaining = cost - pierce
        absorbed = min(self.vitality, remaining)
        self.vitality -= absorbed
        self.stamina -= remaining - absorbed
        # B8：本场累计消耗体力（「消耗过的体力的 N% 数值变为…」的换算源）；
        # 体力实际减少时发一次 stamina_reduce（花费值使体力减少时）。
        stamina_lost = stamina_before - self.stamina
        if stamina_lost > 0:
            self.consumed_stamina_total += stamina_lost
            self._fire_p_items(STAMINA_REDUCE, stamina_delta=stamina_lost)

    def _effective_cost(self, card: CardSpec) -> int:
        """实际牌费：指針倍率 × 消耗体力减少/增加回合，取整后再加减固定费用。

        参考引擎 ``resolveCost``：``cost = floor(cost × 指針 × halfCostTurns ×
        doubleCostTurns)``，再 ``cost += costReduction − costIncrease``、夹到 ≥0；
        费用是负数，``floor`` 对绝对值就是向上取整（我们用 ``ceil``）。
        """
        multiplier = 1.0
        if getattr(self.config, "stance_costs", True):
            multiplier *= stamina_cost_multiplier(self.stance)
        if self.half_cost_turns > 0:
            multiplier *= 0.5
        if self.double_cost_turns > 0:
            multiplier *= 2.0
        if multiplier == 1.0:
            cost = int(card.cost)
        else:
            cost = math.ceil(card.cost * multiplier)
        cost = cost - int(self.cost_reduction) + int(self.cost_increase)
        return max(cost, 0)

    def _has_unused_stamina_drink(self) -> bool:
        """槽里还有没消耗的回复饮料（真机可以下一回合喝它继续打牌）。"""
        return any(
            uses > 0 and drink.effect_type == "stamina"
            for drink, uses in zip(self.config.drinks, self.drink_uses)
        )

    # ------------------------------------------------------------------ P 道具
    def _passive_state(self) -> PassiveState:
        """把当前 LessonSim 局面投影成 p_items 的只读状态。"""
        stance = str(self.stance.stance)
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
                # B8：依赖换算源（累计量）与指針存在性条件（强气/温存/全力）
                "full_power_point_total": self.full_power_point_total,
                "consumed_stamina_total": self.consumed_stamina_total,
                "stance_concentration": 1
                if (self.stance.strong_level > 0 or "strong" in stance)
                else 0,
                "stance_preservation": self.stance.save_level,
                "stance_full_power": 1 if "full" in stance else 0,
                # P1-1：のんびり存在性条件（悠闲变更类 P 道具/条件用）
                "stance_leisure": 1 if stance == Stance.LEISURE else 0,
                # B9：「消耗体力减少状态」条件 = halfCostTurns>0
                "half_cost_state": 1 if self.half_cost_turns > 0 else 0,
            },
            status_counts=self.status_gain_counts,
            uses=self.p_item_uses,
            # B10：四个 tracked 区的卡名（区域张数条件 zone_count 求值用）。
            # P1-3：保留区（hold 区张数条件，实现的觉悟 countCards[held]>=1）。
            hand=tuple(card.name for card in self.hand),
            deck=tuple(card.name for card in self.deck),
            discard=tuple(card.name for card in self.discard),
            excluded=tuple(card.name for card in self.excluded),
            held=tuple(card.name for card in self.held),
            zones_known=True,
        )

    def _fire_p_items(
        self,
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
    ) -> None:
        """在指定时机触发 P 道具并结算增量（分数/体力/层数/额外出牌次数/清零）。

        B8：新增 ``turn_start_after`` / ``turn_interval`` / ``stance_change`` /
        ``stamina_reduce`` / ``status_gain_interval`` 五类事件。``status_gain_interval``
        的累计次数在这里推进（``status_gain_counts``），事件带 ``status_total``。

        B9（2026-11-22）：持久倍率 / modifier 增量（分数 buff/debuff、好印象强化、
        追加发动、热意/集中/好印象/干劲/全力值增益倍率、绝好调/不调、费用修正、
        回合追加、指針直给）在这里落进状态；指針直给后按参考引擎
        ``setStance`` 语义发一次 ``stance_change``（深度上限防链式递归）。
        """
        if not self.p_items:
            return
        status_total = 0
        if kind == STATUS_GAIN:
            if status and amount > 0:
                self.status_gain_counts[status] = (
                    self.status_gain_counts.get(status, 0) + int(amount)
                )
            status_total = self.status_gain_counts.get(status, 0)
            subset = self._p_items_by_trigger.get(
                STATUS_GAIN, ()
            ) + self._p_items_by_trigger.get(STATUS_GAIN_INTERVAL, ())
        elif kind == EXAM_START:
            subset = self._p_items_by_trigger.get(EXAM_START, ())
        elif kind == EXAM_START_AFTER:
            subset = self._p_items_by_trigger.get(EXAM_START_AFTER, ())
        elif kind == TURN_START:
            subset = self._p_items_by_trigger.get(TURN_START, ())
        elif kind == TURN_START_AFTER:
            subset = self._p_items_by_trigger.get(TURN_START_AFTER, ())
        elif kind == TURN_INTERVAL:
            subset = self._p_items_by_trigger.get(TURN_INTERVAL, ())
        elif kind == TURN_END:
            subset = self._p_items_by_trigger.get(TURN_END, ())
        elif kind == STANCE_CHANGE:
            subset = self._p_items_by_trigger.get(STANCE_CHANGE, ())
        elif kind == STAMINA_REDUCE:
            subset = self._p_items_by_trigger.get(STAMINA_REDUCE, ())
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
            card_name=card_name,
            cards_played_this_turn=cards_played_this_turn,
            cards_played_total=cards_played_total,
            status=status,
            amount=amount,
            status_total=status_total,
            stamina_delta=stamina_delta,
        )
        state = self._passive_state()
        # P1-7：延迟段（delay_turns>0）按延迟回合数分组登记——条件/次数在登记时
        # 求值（参考外层效果触发即注册内层 at:turn/delay:N），增量到点才结算。
        immediate = tuple(s for s in subset if s.delay_turns <= 0)
        delayed_groups: dict[int, list[PItemSpec]] = {}
        for spec in subset:
            if spec.delay_turns > 0:
                delayed_groups.setdefault(spec.delay_turns, []).append(spec)
        delta = apply_passive(immediate, event, state)
        delayed_deltas = [
            (dt, apply_passive(tuple(group), event, state))
            for dt, group in sorted(delayed_groups.items())
        ]
        # B10：次数上限按**道具**计（参考 limit:N = 每事件触发一次）；立即 + 延迟
        # 同事件触发只记 1 次（登记时计，延迟到点结算不再计）。
        applied_ids = list(delta.applied)
        for _, d in delayed_deltas:
            applied_ids.extend(d.applied)
        for item_id in dict.fromkeys(applied_ids):
            self.p_item_uses[item_id] = self.p_item_uses.get(item_id, 0) + 1
        for dt, d in delayed_deltas:
            if not d.is_zero():
                self._delayed_deltas.append((dt, d))
        if not delta.is_zero():
            self._apply_p_delta(delta, _depth=_depth)

    def _apply_p_delta(self, delta: PItemDelta, _depth: int = 0) -> None:
        """P1-7：结算一份 P 道具增量（立即触发或延迟到点共用；次数已在登记时计）。"""
        self.score += int(delta.score)
        if delta.stamina_consumed:
            self.consumed_stamina_total += int(delta.stamina_consumed)
        if delta.stamina:
            self.stamina = min(self.stamina_max, max(0, self.stamina + delta.stamina))
        for key in delta.zero_stacks:
            if key == "vitality":
                self.vitality = 0
            elif key == "impression":
                self.buffs.impression = 0
            elif key == "focus":
                self.buffs.focus = 0
            elif key == "aggressive":
                self.motivation = 0
            elif key == "full_power_point":
                self.stance = replace(self.stance, full_power_point=0)
            elif key == "parameter_buff":
                self.buffs.condition_turns = 0
        for key, value in delta.stacks.items():
            if key == "vitality":
                # P1-7：ExamBlock（genki+=）渠道过 resolveGenki 闸门（无效→0/不安×0.67）。
                # P 道具元气获得不吃干劲加成是既有近似（卡渠道才加干劲），如实记录。
                self.vitality += genki_gate(
                    int(value), self.nullify_genki_turns, self.unease_turns
                )
            elif key == "impression":
                self.buffs.impression += int(value)
            elif key == "focus":
                self.buffs.focus += int(value)
            elif key == "aggressive":
                self.motivation += int(value)
            elif key == "full_power_point":
                self.stance = apply_full_power_point(self.stance, int(value))
                self.full_power_point_total += max(0, int(value))
            elif key == "parameter_buff":
                # P 道具的「好调」按回合数近似；模拟器没有独立参数 buff 资源。
                # P1-7：好调增加量增加增益倍率同样作用于 P 道具 goodConditionTurns+=
                # （参考 resolveGoodConditionTurns 对所有 += 渠道生效）。
                gain = int(value)
                if gain > 0:
                    gain = safe_ceil(gain * self._gain_multiple("condition_gain"))
                self.buffs.condition_turns += gain
        # P1-7：固定元气（ExamBlockFix / fixedGenki+=）直接进元气，不受无效/不安拦截。
        if delta.fixed_vitality:
            self.vitality += int(delta.fixed_vitality)
        # P1-5：全力值减少（fullPowerCharge-=N，夹取 ≥0；不计累计全力值，参考
        # decreaseFullPowerCharge 不动 cumulativeFullPowerCharge）。
        if delta.full_power_point_reduce:
            self.stance = replace(
                self.stance,
                full_power_point=max(
                    0, self.stance.full_power_point - int(delta.full_power_point_reduce)
                ),
            )
        if delta.extra_plays:
            # ExamPlayableValueAdd：本回合额外可出牌次数（与卡效果同口径）
            self.extra_plays += int(delta.extra_plays)
        # ---- B9：持久倍率 / modifier 增量 -----------------------------------
        if delta.score_buffs:
            for buff_amount, buff_turns in delta.score_buffs:
                self.score_buffs = add_timed(self.score_buffs, buff_amount, buff_turns)
        # P1-4：低下状态无效次数先累加（本事件的 ExamAntiDebuff），再拦截本事件的
        # debuff 施加（参考 Executor：nullifyDebuff>0 时每条 setScoreDebuff/
        # setHandDecrease 消耗 1 次并整条跳过）。拦截顺序 score_debuffs → hand_decreases
        # （delta 批量聚合，固定顺序近似参考逐动作顺序；评测无来源零触达）。
        if delta.nullify_debuff:
            self.nullify_debuff += int(delta.nullify_debuff)
        score_debuff_entries = delta.score_debuffs
        hand_decrease_entries = delta.hand_decreases
        if self.nullify_debuff > 0:
            self.nullify_debuff, score_debuff_entries = intercept_debuff_entries(
                self.nullify_debuff, delta.score_debuffs
            )
            self.nullify_debuff, hand_decrease_entries = intercept_debuff_entries(
                self.nullify_debuff, delta.hand_decreases
            )
        if score_debuff_entries:
            for buff_amount, buff_turns in score_debuff_entries:
                self.score_debuffs = add_timed(
                    self.score_debuffs, buff_amount, buff_turns
                )
        # P1-2：手牌减少（setHandDecrease 同口径 timed 列表）/ 自尊回合数
        if hand_decrease_entries:
            for hd_amount, hd_turns in hand_decrease_entries:
                self.hand_decreases = add_timed(self.hand_decreases, hd_amount, hd_turns)
        # P1-7：元气增加无效 / 不安 回合数（nullifyGenkiTurns / uneaseTurns ∈
        # DEBUFF_FIELDS，nullifyDebuff 拦截其施加；参考 executeAssignment 每条 +=
        # 动作消耗 1 次。delta 批量聚合丢失逐动作粒度，整块拦截一次，同 P1-4 标量近似）。
        if delta.nullify_genki_turns:
            if self.nullify_debuff > 0:
                self.nullify_debuff -= 1
            else:
                self.nullify_genki_turns += int(delta.nullify_genki_turns)
        if delta.unease_turns:
            if self.nullify_debuff > 0:
                self.nullify_debuff -= 1
            else:
                self.unease_turns += int(delta.unease_turns)
        if delta.pride_turns:
            self.pride_turns += int(delta.pride_turns)
        for key, mod_value, mod_turns in delta.modifiers:
            if key == "review_multiple":
                # 好印象强化：与卡效果共用 Buffs.review_multiple 渠道（千分比）
                self.buffs.review_multiple = max(self.buffs.review_multiple, mod_value)
                self.buffs.review_multiple_turns = _merge_buff_turns(
                    self.buffs.review_multiple_turns,
                    normalize_turns(mod_turns),
                )
            elif key == "enthusiasm_multiple":
                self.buffs.enthusiasm_multiple = max(
                    self.buffs.enthusiasm_multiple, mod_value
                )
                self.buffs.enthusiasm_multiple_turns = _merge_buff_turns(
                    self.buffs.enthusiasm_multiple_turns,
                    normalize_turns(mod_turns),
                )
            elif key == "enthusiasm_bonus":
                self.buffs.enthusiasm_bonus = max(self.buffs.enthusiasm_bonus, mod_value)
                self.buffs.enthusiasm_bonus_turns = _merge_buff_turns(
                    self.buffs.enthusiasm_bonus_turns,
                    normalize_turns(mod_turns),
                )
            else:
                self.modifiers = timed_dict_add(
                    self.modifiers, key, mod_value, mod_turns
                )
        if delta.perfect_condition_turns:
            self.buffs.perfect_condition_turns += int(delta.perfect_condition_turns)
        if delta.poor_condition_turns:
            self.buffs.poor_condition_turns += int(delta.poor_condition_turns)
        if delta.cost_reduction or delta.cost_increase:
            self.cost_reduction += int(delta.cost_reduction)
            self.cost_increase += int(delta.cost_increase)
            self._min_cost = max(
                0,
                self._min_cost - int(delta.cost_reduction) + int(delta.cost_increase),
            )
        if delta.half_cost_turns:
            self.half_cost_turns += int(delta.half_cost_turns)
        if delta.double_cost_turns:
            self.double_cost_turns += int(delta.double_cost_turns)
        if delta.extra_turns:
            self.extra_turns_pending += int(delta.extra_turns)
        # B10：生成卡（ExamCardCreateId 确定式）——按 zone 落牌（参考 addCardTo*）。
        if delta.create_cards:
            self._create_p_item_cards(delta.create_cards)
        # 好印象减少（ExamReviewReduce）等负层数：夹到 ≥0（层数没有负值）
        self.buffs.impression = max(self.buffs.impression, 0)
        self.buffs.focus = max(self.buffs.focus, 0)
        self.vitality = max(self.vitality, 0)
        self.motivation = max(self.motivation, 0)
        stance = self._apply_direct_stances(delta.stances)
        if stance and _depth < 3:
            self._fire_p_items(STANCE_CHANGE, _depth=_depth + 1)

    def _create_p_item_cards(self, creates: list) -> None:
        """B10：结算 P 道具生成卡（``ExamCardCreateId`` 确定式）。

        参考引擎 ``CardManager.addCardTo*`` 语义：手牌生成**手牌≥5 不生成**；
        牌堆顶 = ``deck`` 末尾（``_draw`` 从末尾 pop）；弃牌堆直接 append。
        卡名按 (id, upgrade) 从卡表找，``spec_from_name`` 建牌（与牌组同口径）；
        卡表查不到 → 保守不生成（不猜卡面）。随机基础卡（H.I.F应援棒）是考试
        RNG 入口、真机流未知 → 数据层只记语义，这里不结算。
        """
        from gkagent.data.card_meta import card_meta_index
        from gkagent.sim.play_choice import spec_from_name

        index = card_meta_index()
        for create in creates:
            name = index.name_of(create.card_id, create.upgrade)
            spec = spec_from_name(name) if name else None
            if spec is None:
                continue
            for _ in range(max(int(create.count), 1)):
                if create.zone == "hand":
                    if len(self.hand) >= 5:
                        continue
                    self.hand.append(spec)
                elif create.zone == "deck_top":
                    self.deck.append(spec)
                    self._min_cost = min(self._min_cost, spec.cost)
                elif create.zone == "discard":
                    self.discard.append(spec)

    def _apply_direct_stances(self, kinds: list[str]) -> bool:
        """B9：结算 P 道具的指針直给（温存变更 / 强气变更）；返回指針是否变化。

        参考引擎 ``setStance``：已在同指針时升到 2 段階（``preservation`` →
        ``preservation2`` / ``strength`` → ``strength2``）；否则切到 1 段階。
        P1-1（2026-11-24）：新增 ``leisure``（のんびり变更，ExamOverPreservation）；
        所有直给都过 ``stance_change_allowed`` 守卫（全力期间禁切、のんびり禁温存）。
        """
        changed = False
        locked = self.lock_stance_turns > 0
        for kind in kinds:
            previous = self.stance
            if kind == "preservation" and stance_change_allowed(
                self.stance, "preservation", locked=locked
            ):
                level = 2 if str(self.stance.stance) == "save" else 1
                self.stance = replace(
                    self.stance,
                    stance="save",
                    save_level=max(int(self.stance.save_level), level)
                    if str(self.stance.stance) == "save"
                    else level,
                    strong_level=0,
                )
            elif kind == "preservation2" and stance_change_allowed(
                self.stance, "preservation", locked=locked
            ):
                # P1-3：温存 2 段階直给（「温存阶段变更」value1=2 ↔ 参考
                # setStance(preservation2)：叶える覚悟+/はつぼしフィギュア/
                # まあるい春色/夢見る星，从任何指針直接到 2 段階）。
                self.stance = replace(
                    self.stance,
                    stance="save",
                    save_level=2,
                    strong_level=0,
                )
            elif kind == "concentration" and stance_change_allowed(
                self.stance, "concentration", locked=locked
            ):
                level = 2 if "strong" in str(self.stance.stance) else 1
                self.stance = replace(
                    self.stance,
                    stance="strong2" if level == 2 else "strong1",
                    strong_level=level,
                    save_level=0,
                )
            elif kind == "leisure" and stance_change_allowed(
                self.stance, "leisure", locked=locked
            ):
                self.stance = replace(
                    self.stance,
                    stance=Stance.LEISURE,
                    strong_level=0,
                    save_level=0,
                )
            if self.stance != previous:
                changed = True
                if getattr(self.config, "stance_costs", True):
                    release_enthusiasm, release_genki, release_plays, release_growth = (
                        release_on_stance_change(previous, self.stance)
                    )
                    if release_enthusiasm or release_genki or release_plays or release_growth:
                        self.enthusiasm += enthusiasm_gain(
                            release_enthusiasm,
                            bonus=self.buffs.enthusiasm_bonus,
                            multiple_permil=self.buffs.enthusiasm_multiple,
                        )
                        self.vitality += release_genki
                        self.extra_plays += release_plays
                        self.score_growth_all += release_growth
        return changed

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
            # 好印象结算：ExamReviewMultiple（好印象强化）放大层数；「好印象追加发动」
            # （ExamReviewCountAdd，B9）让这次结算重复 N+1 次（参考引擎
            # GOOD_IMPRESSION_EFFECTS 的 goodImpressionTurnsTimesBuffs）。
            review_times = max(0, self._mod_total("review_times"))
            score_buff = total_timed(self.score_buffs)
            # P1-2：回合末好印象也走 resolveScore f，自尊加成同样生效
            # （用结算时的好印象/干劲层数，与出牌分同口径）。
            if self.pride_turns > 0:
                score_buff += min(min(self.buffs.impression, self.motivation) * 20, 500)
            score_debuff = total_timed(self.score_debuffs)
            turn_bonus = self._turn_bonus_permil()
            for _ in range(1 + review_times):
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
                # B9：P 道具持久分数倍率（参考引擎 resolveScore f/g）
                if score_buff:
                    impression_score = safe_ceil(
                        impression_score * (1.0 + score_buff / 1000.0)
                    )
                if score_debuff:
                    impression_score = safe_ceil(
                        impression_score * max(1.0 - score_debuff / 1000.0, 0.0)
                    )
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
        # P1-2：自尊回合末 -1（参考 EOT_DECREMENT_FIELDS 的 prideTurns，
        # 在好印象结算之后倒计时；WHOLE_FIELDS 整数资源）。
        if self.pride_turns > 0:
            self.pride_turns -= 1
        # P1-7：元气增加无效 / 不安 回合末 -1（参考 EOT_DECREMENT_FIELDS 的
        # nullifyGenkiTurns / uneaseTurns）。fresh 保护差一回合缺口同一般标量
        # （pride/poor_condition 口径，留真机核实，RULES_REFERENCE §3）。
        if self.nullify_genki_turns > 0:
            self.nullify_genki_turns -= 1
        if self.unease_turns > 0:
            self.unease_turns -= 1
        # P1-3：指針固定回合末 -1（参考 EOT_DECREMENT_FIELDS 的 lockStanceTurns）。
        # **fresh 保护**（参考 Executor/index.js「Protect fresh stats from
        # decrement」+ BuffManager.decrementBuffTurns 的 freshBuffs 位）：卡效果
        # 0→正 的当回合末跳过递减——指針固定锁的是**下一回合**（全力进入门在
        # 回合开始检查 lockStanceTurns==0，若当回合就扣完则固定毫无作用）。
        # 一般 buff 的 fresh 差一回合缺口仍留真机核实（RULES_REFERENCE §3），
        # 本字段按参考语义实现是因为「锁下一回合」是卡面「指针固定1回合」的
        # 确定语义（切磋琢磨 ↔ DSL 424/425 交叉）。
        if self._lock_stance_fresh:
            self._lock_stance_fresh = False
        elif self.lock_stance_turns > 0:
            self.lock_stance_turns -= 1
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
        # B9：P 道具持久倍率 / modifier 倒计时（参考引擎 decrementBuffTurns：
        # turns>0 的 -1、到 0 移除、-1 永久保持）。
        self.score_buffs = tick_timed(self.score_buffs)
        self.score_debuffs = tick_timed(self.score_debuffs)
        # P1-2：手牌减少倒计时（参考 decrementBuffTurns 对 handDecreases 列表：
        # turns>0 的 -1、到 0 移除、永久保持）。
        self.hand_decreases = tick_timed(self.hand_decreases)
        self.modifiers = timed_dict_tick(self.modifiers)
        if self.half_cost_turns > 0:
            self.half_cost_turns -= 1
        if self.double_cost_turns > 0:
            self.double_cost_turns -= 1
        # 熱意：回合末归 0；有「熱意延長」则保留并消耗 1 层（参考引擎 TurnManager.endTurn）
        self.enthusiasm, self.enthusiasm_extension_turns = turn_end_enthusiasm(
            self.enthusiasm, self.enthusiasm_extension_turns
        )
        # 审查基准加成只在本回合内持续
        self.turn_parameter_buff = 0
        # P 道具：回合结束（好印象/好调结算后、弃手牌前）
        self._fire_p_items(TURN_END)
        # P1-7：延迟生效倒计时 -1（参考 EffectManager.decrementDelay，在 endOfTurn
        # 效果/buff 倒计时之后）；到 0 的增量在下一回合开始结算（_draw_hand）。
        if self._delayed_deltas:
            self._delayed_deltas = [(n - 1, d) for n, d in self._delayed_deltas]
        self.trace.append(
            {
                "turn": self.total_turns - self.turns_left + 1,
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
        # B9：本回合获得的「回合追加」（ExamExtraTurn）在回合结束、剩余回合 -1
        # 之后补上；total_turns 同步增长，当前回合号不跳变（参考引擎
        # TurnManager.endTurn 里 turnsRemaining+=1 后同帧 --1 等价）。
        if self.extra_turns_pending:
            self.turns_left += int(self.extra_turns_pending)
            self.extra_turns_granted += int(self.extra_turns_pending)
            self.extra_turns_pending = 0
        # 回合结束结算全力值：攒满 10 点则下一回合进入「全力」
        # P1-3：指針固定期间全力进入门不满足（参考 FULL_POWER_EFFECTS
        # if:lockStanceTurns==0 & fullPowerCharge>=10），全力值不消耗。
        previous_stance = self.stance
        self.stance = end_turn(self.stance, locked=self.lock_stance_turns > 0)
        # B8：回合边界的指針切换（全力进入等）也发 stance_change
        if self.stance != previous_stance:
            self._fire_p_items(STANCE_CHANGE)
        if self.turns_left > 0:
            self._draw_hand()
            # P1-1（2026-11-24）：FULL_POWER_CHANGED_EFFECTS——以全力开始的回合
            # +1 出牌次数、保留牌回手（参考 TurnManager.startTurn 抽牌后触发）。
            # 连续全力回合每回合都 +1（参考先 fullPower→none 再按 charge 进全力，
            # 最后检查 stance==fullPower；本模型 end_turn 净效果等价）。
            if str(self.stance.stance) == Stance.FULL:
                self.extra_plays += 1
                self._move_held_to_hand()
            # 温存/のんびり→全力 的**回合边界**切换也触发解除收益（参考引擎 startTurn
            # 的 FULL_POWER_EFFECTS 里 setStance(fullPower) 会触发 STANCE_CHANGED_EFFECTS）。
            # _draw_hand 已把 extra_plays 清零，所以次数加在新回合的基础次数上。
            if getattr(self.config, "stance_costs", True):
                release_enthusiasm, release_genki, release_plays, release_growth = (
                    release_on_stance_change(previous_stance, self.stance)
                )
                if release_enthusiasm or release_genki or release_plays or release_growth:
                    self.enthusiasm += enthusiasm_gain(
                        release_enthusiasm,
                        bonus=self.buffs.enthusiasm_bonus,
                        multiple_permil=self.buffs.enthusiasm_multiple,
                    )
                    self.vitality += release_genki
                    self.extra_plays += release_plays
                    self.score_growth_all += release_growth
            # P1-1：のんびり预约（afterStartOfTurn/startOfTurn，抽牌后结算）
            self._apply_leisure_reserves()

    def _move_held_to_hand(self) -> None:
        """P1-1：全力回合保留牌回手（参考 ``CardManager.moveHeldCardsToHand``）。

        保留区全部牌弹出加进手牌（该接口无手牌上限检查，与参考一致）；
        **LIFO**（参考 ``pop()`` 从尾部弹，P1-3 对齐；P1-1 时 held 恒空无行为差）。
        P1-3：卡效果版（一点一滴的进步 ``moveHeldCardsToHand``）也走这里。
        """
        if self.held:
            self.hand.extend(reversed(self.held))
            self.held.clear()

    def _enforce_hold_limit(self) -> None:
        """P1-3：保留区上限 2（参考 ``CardManager.enforceHoldLimit``）。

        超限把**最旧**的牌（``shift()``）推进弃牌堆。
        """
        while len(self.held) > HOLD_LIMIT:
            self.discard.append(self.held.pop(0))

    def _apply_hold(self, card: CardSpec) -> bool:
        """P1-3：结算本牌的保留区效果；返回本牌是否被 holdThisCard 保留。

        参考 ``CardManager``：holdThisCard 把刚打出的牌放进保留区（``useCard``
        末尾据此跳过弃牌/除外）；holdSelected 从目标区选牌移入保留区；
        moveHeldCardsToHand 把保留区全部弹回手牌。每次移入后 enforceHoldLimit。
        选牌是玩家选择——本模型按白值分降序确定性选（``hold.hold_pick``，
        与参考 HeuristicStrategy 的全力预览分排序等价，见该函数 docstring）。
        再演不翻倍 hold（参考 hold 按卡索引幂等）。
        """
        held_this = False
        if card.hold_this and (
            not card.hold_this_when_save or str(self.stance.stance) == Stance.SAVE
        ):
            self.held.append(card)
            self._enforce_hold_limit()
            held_this = True
        if card.hold_select_zones:
            zone_names = HOLD_SELECT_ZONES[card.hold_select_zones]
            pools = {"hand": self.hand, "deck": self.deck, "discard": self.discard}
            candidates = [c for zone in zone_names for c in pools[zone]]
            for picked in hold_pick(candidates, card.hold_select_count):
                for zone in zone_names:
                    pool = pools[zone]
                    if picked in pool:
                        pool.remove(picked)
                        break
                self.held.append(picked)
            self._enforce_hold_limit()
        if card.hold_move_to_hand:
            self._move_held_to_hand()
        return held_this

    def _apply_leisure_reserves(self) -> None:
        """P1-1：回合开始结算のんびり预约（出牌时登记，见 _apply_card_stance）。

        参考 ``skill_cards.csv``：``at:afterStartOfTurn { if:isPreservation
        { setStance(leisure) } }``（永久）/ ``at:startOfTurn { if:!isPreservation
        { setStance(leisure) }; limit:3 }``。每条预约独立按**当时**指針判条件；
        条件成立即触发 setStance(leisure)（受全力守卫）并扣次数（永久 -1 不扣）；
        条件不成立不扣次数。进入のんびり本身无解除收益（温存→のんびり不触发
        温存解除，见 release_on_stance_change）。
        """
        if not self.leisure_reserves:
            return
        remaining: list[tuple[int, bool]] = []
        for count, when_save in self.leisure_reserves:
            stance_now = str(self.stance.stance)
            matched = (
                (stance_now == Stance.SAVE) if when_save else (stance_now != Stance.SAVE)
            )
            if matched:
                previous = self.stance
                if stance_change_allowed(
                    self.stance, "leisure", locked=self.lock_stance_turns > 0
                ):
                    self.stance = replace(
                        self.stance,
                        stance=Stance.LEISURE,
                        strong_level=0,
                        save_level=0,
                    )
                if self.stance != previous:
                    self._fire_p_items(STANCE_CHANGE)
                if count > 0:
                    count -= 1
            if count != 0:
                remaining.append((count, when_save))
        self.leisure_reserves = remaining

    def _draw_hand(self, *, keep_extra_plays: bool = False) -> None:
        # 新手牌 = 新回合：好印象在**下一回合开始时** -1（回合末已按当前层数加分）
        if self.buffs.impression > 0:
            self.buffs.impression -= 1
        # 本回合出牌数、额外次数、已喝饮料数从 0 重新计
        # keep_extra_plays 只给构造时用：exam_start P 道具给的次数属于第 1 回合。
        self.plays_this_turn = 0
        if not keep_extra_plays:
            self.extra_plays = 0
        self.drinks_used_this_turn = 0
        self.hand.clear()
        # P1-2：回合开始抽牌 = max(hand_size − Σ handDecrease, 0)（参考
        # TurnManager.startTurn cardsToDraw；只减回合开始抽牌，卡效果抽牌不受影响）。
        self._draw(max(self.config.hand_size - total_timed(self.hand_decreases), 0))
        # P 道具：回合开始（抽完手牌后、出牌前）
        self._fire_p_items(TURN_START)
        # B8：回合开始后 / 每 N 回合（新语法触发 id 的两种时机，同一位置发射）
        self._fire_p_items(TURN_START_AFTER)
        self._fire_p_items(TURN_INTERVAL)
        # P1-7：延迟生效 P 道具到点结算（参考嵌套 at:turn / delay:N 在回合开始的
        # turn 阶段触发，位于 startOfTurn/afterStartOfTurn 之后）。
        self._fire_delayed_p_items()

    def _fire_delayed_p_items(self) -> None:
        """P1-7：结算延迟到点（剩余回合 ≤0）的 P 道具增量；次数已在登记时计。"""
        if not self._delayed_deltas:
            return
        due = [d for n, d in self._delayed_deltas if n <= 0]
        self._delayed_deltas = [(n, d) for n, d in self._delayed_deltas if n > 0]
        for d in due:
            self._apply_p_delta(d, _depth=0)

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
