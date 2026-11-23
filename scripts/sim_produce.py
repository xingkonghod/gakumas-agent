"""几十万局培育模拟：比较不同训练/上课/休息打法。

用法：
    python scripts/sim_produce.py --episodes 50000          # 每种策略 5 万局
    python scripts/sim_produce.py --episodes 20000 --only class_best,mixed

输出：每种策略的三维均值、总和、评价分布、训练/过关次数、CPU 时间。
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import NamedTuple

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

from gkagent.sim.stance import leisure_reserve_for  # P1-1 のんびり预约证据表

CARD_TABLE = ROOT / "data" / "knowledge" / "card_table.json"
# 模拟器（sim/lesson.py）真正建模了的效果类型。
# 2026-11-16：新卡池 16 种效果接入后从 13 种扩到 29 种；其中 8 种精确建模
# （体力回复/全力折算/再演/好印象强化/好调加算/全力强化/热意延长/成长），
# 8 种保守近似（检索/生成/移动→抽 1；延迟→立刻；附魔外层展开内层；低下无效
# 与训练无关；出牌干劲→motivation）。近似口径与误差方向见 sim/lesson.py 模块 docstring。
# 2026-11-22 T5②：熱意追加/増加/適用倍数 三种接入 → 32 种。
# 2026-11-24 P1-1：のんびり预约 ExamOverPreservation 接入 → 33 种。
MODELED_EFFECTS = {
    "ExamLesson",
    "ExamBlock",
    "ExamLessonBuff",
    "ExamConcentration",
    "ExamCardDraw",
    "ExamReview",
    "ExamLessonDependExamReview",
    "ExamPreservation",
    "ExamFullPowerPoint",
    "ExamPlayableValueAdd",
    "ExamLessonDependBlock",
    "ExamParameterBuff",
    "ExamParameterBuffMultiplePerTurn",
    # ---- 2026-11-16 新卡池：16 种新效果 ----
    "ExamLessonFullPowerPoint",
    "ExamStatusEnchantEncore",
    "ExamForcePlayCardSearch",
    "ExamStaminaRecoverFix",
    "ExamStatusEnchant",
    "ExamCardMove",
    "ExamEffectTimer",
    "ExamAddGrowEffect",
    "ExamCardCreateId",
    "ExamEffectTimerEndTurn",
    "ExamEnthusiasticTurnAdd",
    "ExamParameterBuffAdditiveFix",
    "ExamFullPowerLessonMultipleAdditive",
    "ExamAntiDebuff",
    "ExamReviewMultiple",
    "ExamCardPlayAggressive",
    # ---- T5② 2026-11-22 熱意（enthusiasm）----
    "ExamEnthusiasticAdditive",
    "ExamEnthusiasticMultiple",
    "ExamMultipleEnthusiasticLesson",
    # ---- P1-1 2026-11-24 のんびり预约（ExamOverPreservation）----
    "ExamOverPreservation",
}
# 卡表里的效果名和卡面语义容易对反，以下以游戏 master 的卡面文本（卡名 + 效果）为准：
#   准备运动「打分+6 / 集中+2」     -> ExamLessonBuff [2]       = 集中
#   平衡感「集中+3」                -> ExamLessonBuff [3]       = 集中
#   打招呼的基础「强气变更」        -> ExamConcentration [1]    = 指針変更（強気 1 段階）
#   不会让出第一「好调 3 回合」     -> ExamParameterBuff turn 3 = 好调 3 回合
#   光之夜「绝好调 2 回合」         -> ExamParameterBuffMultiplePerTurn turn 2
#   祝福+「体力消耗 4 / 打分+40 / 好调 1 回合」
#                                 -> forceStamina 4 + ExamParameterBuff turn 1
# 所以 ExamLessonBuff 给 focus（集中层数）、ExamConcentration 给 strong_level
# （強気段階）、ExamParameterBuff* 给 condition（好调回合数）。不写死 1500‰ 的
# "审查基准加成"兜底：那些 effects 的 values 本来就是空的，兜底会把好调卡变成 ×1.5。
# 其它分析脚本（sim_idols / sim_search / …）还按旧 5 元组解包；在它们迁移前，
# build_pool() 默认只收完全落在旧集合里的卡，避免把抽牌/好印象卡当成"只有白值"。
# 温存/全力值/可出牌次数/元气依赖分/好调回合数/元气同样只能由 rich CardRow 承载，
# 所以只加进 MODELED_EFFECTS：旧 5 元组塞不下这些字段，硬加进来会被旧脚本当成纯白值卡。
# ExamConcentration 现在承载強気段階，旧 5 元组也表达不了，故从旧集合移除。
# 注意：LEGACY_MODELED_EFFECTS 仍含 ExamBlock（旧行为：旧 5 元组不承载元气），
# 只有 rich=True 的 CardRow 才会把 ExamBlock 的 values 映射到 CardSpec.vitality。
LEGACY_MODELED_EFFECTS = {"ExamLesson", "ExamBlock", "ExamLessonBuff"}

# 旧接口：(name, cost, score, condition, focus)
LegacyCardRow = tuple[str, int, int, int, int]


class CardRow(NamedTuple):
    """build_deck(rich=True) / build_pool(rich=True) 返回的完整卡行。"""

    name: str
    cost: int
    score: int
    condition: int
    focus: int
    draw: int = 0
    impression: int = 0
    impression_scale: int = 0
    preservation: int = 0
    full_power_point: int = 0
    extra_play: int = 0
    block_scale: int = 0
    parameter_buff: int = 0
    parameter_buff_turns: int = 1
    strong_level: int = 0
    # ExamBlock：出牌获得的元气（盾）。训练里优先抵牌费，也喂依赖元气的分数
    vitality: int = 0
    # ---- 2026-11-16 新卡池 16 种效果（字段顺序与 _effect_fields 返回值一致）----
    stamina_recover: int = 0          # ExamStaminaRecoverFix
    full_power_scale: int = 0         # ExamLessonFullPowerPoint
    encore: int = 0                   # ExamStatusEnchantEncore（1 = 本牌效果两次）
    review_multiple: int = 0          # ExamReviewMultiple（千分比）
    review_multiple_turns: int = 0    # -1 = 永久
    condition_additive: int = 0       # ExamParameterBuffAdditiveFix
    condition_additive_turns: int = 0
    full_power_lesson_multiple: int = 0  # ExamFullPowerLessonMultipleAdditive（千分比）
    full_power_lesson_multiple_turns: int = 0
    grow_score: int = 0               # ExamAddGrowEffect（卡表 values 常为空）
    motivation: int = 0               # ExamCardPlayAggressive（近似成干劲层数）
    # ---- T5② 2026-11-22 熱意（enthusiasm）----
    enthusiasm_bonus: int = 0         # ExamEnthusiasticAdditive（熱意追加，加算）
    enthusiasm_bonus_turns: int = 0
    enthusiasm_multiple: int = 0      # ExamEnthusiasticMultiple（熱意増加，千分比）
    enthusiasm_multiple_turns: int = 0
    enthusiasm_extension: int = 0     # ExamEnthusiasticTurnAdd（熱意延長，回合数）
    enthusiasm_multiplier: int = 1000  # ExamMultipleEnthusiasticLesson（本牌熱意適用倍数‰）
    # ---- P1-1 2026-11-24 のんびり预约（ExamOverPreservation）----
    leisure_reserve: int = 0          # 剩余触发次数（-1 永久，0 无）
    leisure_reserve_when_save: bool = True  # True 温存中触发 / False 非温存触发


def _buff_turns(effect: dict) -> int:
    """持续类效果的剩余回合：``turn < 0`` = 永久（-1），否则至少 1 回合。"""
    turn = int(effect.get("turn") or 0)
    return -1 if turn < 0 else max(1, turn)


def _merge_turns(current: int, new: int) -> int:
    """合并同一种持续效果的回合：任一永久则永久，否则取更长。"""
    if current < 0 or new < 0:
        return -1
    return max(current, new)


def _effect_fields(row: dict) -> tuple[int, ...]:
    """从卡表一行的 ``effects`` 提取可喂给 ``CardSpec`` 的字段。

    返回 33 元组（前 14 位是 2026-11-15 的旧口径，索引保持不变）：

    =====  ============================================================
    索引   字段
    =====  ============================================================
    0      ``score``（ExamLesson）
    1      ``condition``（好调回合数；ExamParameterBuff* 的 turn）
    2      ``focus``（ExamLessonBuff = 集中）
    3      ``draw``（ExamCardDraw；检索/生成/移动近似 +1）
    4      ``impression``（ExamReview 好印象层数）
    5      ``impression_scale``（ExamLessonDependExamReview 千分比）
    6      ``preservation``（ExamPreservation 温存段階）
    7      ``full_power_point``（ExamFullPowerPoint 全力值增量）
    8      ``extra_play``（ExamPlayableValueAdd 的 count）
    9      ``block_scale``（ExamLessonDependBlock 千分比）
    10     ``parameter_buff``（显式千分比，通常 0）
    11     ``parameter_buff_turns``
    12     ``strong_level``（ExamConcentration 強気段階）
    13     ``vitality``（ExamBlock 元气）
    14     ``stamina_recover``（ExamStaminaRecoverFix）
    15     ``full_power_scale``（ExamLessonFullPowerPoint 折算千分比）
    16     ``encore``（ExamStatusEnchantEncore，1 = 本牌效果两次）
    17     ``review_multiple``（ExamReviewMultiple 千分比）
    18     ``review_multiple_turns``
    19     ``condition_additive``（ExamParameterBuffAdditiveFix）
    20     ``condition_additive_turns``
    21     ``full_power_lesson_multiple``（ExamFullPowerLessonMultipleAdditive 千分比）
    22     ``full_power_lesson_multiple_turns``
    23     ``grow_score``（ExamAddGrowEffect；卡表 values 为空 → 0）
    24     ``motivation``（ExamCardPlayAggressive，近似成干劲层数）
    25     ``enthusiasm_bonus``（ExamEnthusiasticAdditive 熱意追加，加算量）
    26     ``enthusiasm_bonus_turns``
    27     ``enthusiasm_multiple``（ExamEnthusiasticMultiple 熱意増加，千分比）
    28     ``enthusiasm_multiple_turns``
    29     ``enthusiasm_extension``（ExamEnthusiasticTurnAdd 熱意延長，回合数）
    30     ``enthusiasm_multiplier``（ExamMultipleEnthusiasticLesson 本牌熱意適用倍数‰）
    31     ``leisure_reserve``（P1-1 ExamOverPreservation のんびり预约次数，-1 永久）
    32     ``leisure_reserve_when_save``（True 温存中触发 / False 非温存触发）
    =====  ============================================================

    字段语义以游戏 master 卡面文本为准，effect 名容易误读：

    - ``ExamLesson`` = 打分；``ExamLessonBuff`` = **集中**层数（→ ``focus``）；
    - ``ExamConcentration`` = **指針変更（強気）**段階 1/2（→ ``strong_level``）；
    - ``ExamBlock`` = **元气（盾）**获得量（→ ``vitality``）；
    - ``ExamParameterBuff*`` = **好调/绝好调 N 回合**（→ ``condition = turn``），
      不是审查基准加成；卡表里它们的 ``values`` 是空的，所以 ``parameter_buff``
      只认显式 ``values[0]``（千分比），没有默认 1500‰ 兜底；
    - ``ExamReview`` 是好印象层数，``ExamCardDraw`` 是抽牌数，
      ``ExamLessonDependExamReview`` 是依赖好印象的百分比倍率（1000 = 层数×10），
      ``ExamLessonDependBlock`` 是依赖元气的百分比倍率（同构），
      ``ExamPreservation`` 是温存段階（1/2），``ExamFullPowerPoint`` 是全力值增量，
      ``ExamPlayableValueAdd`` 是本回合可出牌次数增量（卡表里通常没有 values，
      用 ``count`` 表示 +1/+2）。

    2026-11-16 新增 16 种（精确 8 / 近似 8，误差方向见 ``sim/lesson.py``）：

    - 精确：``ExamStaminaRecoverFix``、``ExamLessonFullPowerPoint``、
      ``ExamStatusEnchantEncore``、``ExamReviewMultiple``、
      ``ExamParameterBuffAdditiveFix``、``ExamFullPowerLessonMultipleAdditive``、
      ``ExamEnthusiasticTurnAdd``、``ExamAddGrowEffect``；
    - 近似：``ExamForcePlayCardSearch`` / ``ExamCardCreateId`` / ``ExamCardMove``
      → ``draw = max(draw, 1)``（真机是免费检索/生成/移回手牌，这里只算 +1 抽牌，
      **低估**；若本牌同时有 ``ExamPlayableValueAdd`` 则不再加抽牌——资源收益
      已由次数表达，也避免 0 费循环无限过牌）；``ExamStatusEnchant`` → 递归展开
      内层、本回合立刻结算（**通常高估当回合**）；``ExamEffectTimer`` /
      ``ExamEffectTimerEndTurn`` → 无字段，被延迟的效果本回合立刻生效
      （**通常高估当回合**）；``ExamAntiDebuff`` → no-op（训练没有低下状态，
      模型内恒 0）；``ExamCardPlayAggressive`` → ``motivation``（近似永久干劲，
      长期**高估**）；
    - ``ExamLessonFullPowerPoint`` 的双值形态是 ``[固定打分, 折算千分比]``：
      固定打分并入 ``score``，末位作为 ``full_power_scale``（同理单值直接是倍率）。

    T5②（2026-11-22）熱意三种 buff 效果（卡表 ``turn`` 是 buff 持续回合，-1 = 永久）：
    ``ExamEnthusiasticAdditive`` 是**獲得熱意时的加算 buff**（不是立刻加分），
    ``ExamEnthusiasticMultiple`` 是獲得熱意时的**千分比乘数**（+1000‰ = ×2），
    ``ExamEnthusiasticTurnAdd`` 是熱意延長回合数；規則见 ``sim/enthusiasm.py``。
    ``ExamMultipleEnthusiasticLesson`` 是**本牌**熱意適用倍数（values[0]=本牌直接
    打分加算、values[1]=倍数追加‰，1000 → ×2；卡面「熱意效果会2倍生效」）。
    """
    score = condition = focus = draw = impression = impression_scale = 0
    preservation = full_power_point = extra_play = 0
    block_scale = parameter_buff = 0
    parameter_buff_turns = 1
    strong_level = 0
    vitality = 0
    stamina_recover = full_power_scale = encore = 0
    review_multiple = review_multiple_turns = 0
    condition_additive = condition_additive_turns = 0
    full_power_lesson_multiple = full_power_lesson_multiple_turns = 0
    grow_score = motivation = 0
    enthusiasm_bonus = enthusiasm_bonus_turns = 0
    enthusiasm_multiple = enthusiasm_multiple_turns = 0
    enthusiasm_extension = 0
    enthusiasm_multiplier = 1000
    leisure_reserve = 0
    leisure_reserve_when_save = True
    approx_draw = 0

    def absorb(effects: list[dict]) -> None:
        nonlocal score, condition, focus, draw, impression, impression_scale
        nonlocal preservation, full_power_point, extra_play, block_scale
        nonlocal parameter_buff, parameter_buff_turns, strong_level, vitality
        nonlocal stamina_recover, full_power_scale, encore, review_multiple
        nonlocal review_multiple_turns, condition_additive, condition_additive_turns
        nonlocal full_power_lesson_multiple, full_power_lesson_multiple_turns
        nonlocal grow_score, motivation, approx_draw
        nonlocal enthusiasm_bonus, enthusiasm_bonus_turns
        nonlocal enthusiasm_multiple, enthusiasm_multiple_turns
        nonlocal enthusiasm_extension, enthusiasm_multiplier
        nonlocal leisure_reserve, leisure_reserve_when_save
        for effect in effects or []:
            kind = effect.get("type")
            values = [v for v in effect.get("values") or [] if v]
            value = int(values[0]) if values else 0

            # ---- 2026-11-16 新效果：元效果/近似 ----
            if kind == "ExamStatusEnchant":
                # 状态附魔外层：内层效果本回合立刻结算（近似，见 lesson.py）
                absorb(effect.get("inner") or [])
                continue
            if kind == "ExamStatusEnchantEncore":
                encore = 1
                continue
            if kind == "ExamOverPreservation":
                # P1-1：のんびり预约（values 恒空）。条件/次数不在主数据 JSON 里，
                # 按 BSD-3 skill_cards.csv 逐卡交叉验证（stance.LEISURE_RESERVE_SOURCES，
                # 日文卡名↔中文卡名用 card_meta 别名核对）；未知 id 保守 no-op。
                reserve, when_save = leisure_reserve_for(str(row.get("id") or ""))
                if reserve != 0:
                    leisure_reserve = reserve
                    leisure_reserve_when_save = when_save
                continue
            if kind in ("ExamForcePlayCardSearch", "ExamCardCreateId", "ExamCardMove"):
                # 检索/生成/移回手牌 → 至少 +1 抽牌（低估，见 docstring）；
                # 若本牌同时有"可出牌次数追加"，资源收益已由次数表达，不再加抽牌
                # （否则 0 费循环会在 LessonSim 里无限过牌）。
                approx_draw = 1
                continue
            if kind in ("ExamEffectTimer", "ExamEffectTimerEndTurn", "ExamAntiDebuff"):
                # 延迟标记/低下无效：训练里按"立刻生效"或 no-op 处理
                continue
            if kind == "ExamAddGrowEffect":
                grow_score = max(grow_score, value)
                continue
            if kind == "ExamStaminaRecoverFix":
                stamina_recover = max(stamina_recover, value)
                continue
            if kind == "ExamLessonFullPowerPoint":
                if len(values) >= 2:
                    # 双值：[固定打分, 折算千分比]（如 传递勇气的启明星 [20, 6500]）
                    score = max(score, int(values[0]))
                    full_power_scale = max(full_power_scale, int(values[-1]))
                else:
                    full_power_scale = max(full_power_scale, value)
                continue
            if kind == "ExamReviewMultiple":
                review_multiple = max(review_multiple, value)
                review_multiple_turns = _merge_turns(
                    review_multiple_turns, _buff_turns(effect)
                )
                continue
            if kind == "ExamParameterBuffAdditiveFix":
                condition_additive = max(condition_additive, value)
                condition_additive_turns = _merge_turns(
                    condition_additive_turns, _buff_turns(effect)
                )
                continue
            if kind == "ExamFullPowerLessonMultipleAdditive":
                full_power_lesson_multiple = max(full_power_lesson_multiple, value)
                full_power_lesson_multiple_turns = _merge_turns(
                    full_power_lesson_multiple_turns, _buff_turns(effect)
                )
                continue
            if kind == "ExamEnthusiasticTurnAdd":
                # 熱意延長（T5②）：回合末不清零，改为消耗延長回合数
                enthusiasm_extension = max(enthusiasm_extension, value)
                continue
            if kind == "ExamEnthusiasticAdditive":
                # 熱意追加（T5②）：獲得熱意時的加算 buff（不是立刻加熱意）
                enthusiasm_bonus = max(enthusiasm_bonus, value)
                enthusiasm_bonus_turns = _merge_turns(
                    enthusiasm_bonus_turns, _buff_turns(effect)
                )
                continue
            if kind == "ExamEnthusiasticMultiple":
                # 熱意増加（T5②）：獲得熱意時的千分比乘数 buff
                enthusiasm_multiple = max(enthusiasm_multiple, value)
                enthusiasm_multiple_turns = _merge_turns(
                    enthusiasm_multiple_turns, _buff_turns(effect)
                )
                continue
            if kind == "ExamMultipleEnthusiasticLesson":
                # 本牌熱意適用倍数（T5②）：values[0] = 本牌直接打分加算，
                # values[1] = 熱意適用倍数的追加千分比（1000 → ×2；
                # 卡面「熱意效果会2倍生效」，如「手を伸ばした先に」）
                score = max(score, value)
                if len(values) >= 2:
                    enthusiasm_multiplier = max(
                        enthusiasm_multiplier, 1000 + int(values[1])
                    )
                continue
            if kind == "ExamCardPlayAggressive":
                motivation = max(motivation, value)
                continue

            # ---- 旧 13 类（行为保持不变）----
            if kind == "ExamPlayableValueAdd":
                extra_play = max(extra_play, value or int(effect.get("count") or 1))
                continue
            if kind in ("ExamParameterBuff", "ExamParameterBuffMultiplePerTurn"):
                # 卡面是「好调 N 回合 / 绝好调 N 回合」（祝福+、不会让出第一…），
                # 不是 1500‰ 的审查基准加成。turn 才是持续回合数。
                turn = int(effect.get("turn") or 0)
                if turn > 0:
                    condition = max(condition, turn)
                parameter_buff = max(parameter_buff, value)
                if kind == "ExamParameterBuffMultiplePerTurn" and parameter_buff > 0:
                    # 显式数值时才保留"整回合持续"语义；卡表实际 values 为空 → 不生效。
                    parameter_buff_turns = max(parameter_buff_turns, turn or 2)
                continue
            if not value:
                continue
            if kind == "ExamLesson":
                score = max(score, value)
            elif kind == "ExamLessonBuff":
                # 卡面是「集中+2/+3」（准备运动/平衡感），不是好调。
                focus = max(focus, value)
            elif kind == "ExamConcentration":
                # 卡面是「強気変更」（打招呼的基础），values[0] 是 1/2 段階；不是集中。
                strong_level = max(strong_level, value)
            elif kind == "ExamBlock":
                # 元气（盾）：训练里先扣元气再扣体力；没有伤害来源，所以不是"挡伤害"
                vitality = max(vitality, value)
            elif kind == "ExamCardDraw":
                draw = max(draw, value)
            elif kind == "ExamReview":
                impression = max(impression, value)
            elif kind == "ExamLessonDependExamReview":
                impression_scale = max(impression_scale, value)
            elif kind == "ExamLessonDependBlock":
                block_scale = max(block_scale, value)
            elif kind == "ExamPreservation":
                preservation = max(preservation, value)
            elif kind == "ExamFullPowerPoint":
                full_power_point = max(full_power_point, value)

    absorb(list(row.get("effects") or []))
    if approx_draw and extra_play == 0:
        draw = max(draw, 1)
    return (
        score,
        condition,
        focus,
        draw,
        impression,
        impression_scale,
        preservation,
        full_power_point,
        extra_play,
        block_scale,
        parameter_buff,
        parameter_buff_turns,
        strong_level,
        vitality,
        stamina_recover,
        full_power_scale,
        encore,
        review_multiple,
        review_multiple_turns,
        condition_additive,
        condition_additive_turns,
        full_power_lesson_multiple,
        full_power_lesson_multiple_turns,
        grow_score,
        motivation,
        enthusiasm_bonus,
        enthusiasm_bonus_turns,
        enthusiasm_multiple,
        enthusiasm_multiple_turns,
        enthusiasm_extension,
        enthusiasm_multiplier,
        leisure_reserve,
        leisure_reserve_when_save,
    )


def build_deck(*, rich: bool = False) -> list[CardRow] | list[LegacyCardRow]:
    """卡组：(name, cost, score, condition, focus[, draw, impression, ...])。

    数值来自 card_table。``rich=True`` 返回 ``CardRow``（带抽牌/好印象/依赖
    倍率/温存/全力值/可出牌次数/元气），供本脚本自己用；默认返回旧 5 元组，
    保持其它分析脚本兼容。
    """
    table = {}
    if CARD_TABLE.exists():
        table = json.loads(CARD_TABLE.read_text(encoding="utf-8")).get("cards", {})
    import re

    master = {}
    master_path = ROOT / "data" / "master" / "produce_cards.json"
    if master_path.exists():
        for row in json.loads(master_path.read_text(encoding="utf-8")):
            master[row.get("name", "")] = row.get("text", "")

    names = [
        "好调", "集中", "魅力的基础", "魅力的基础+", "表现的基础", "表情的基础",
        "准备运动", "粉丝服务", "聊天时间", "凭势而行", "重新开始", "姿势的基础",
        "今天也早安", "视角的基础", "可爱的举动", "猛烈地",
    ]
    deck: list[CardRow] | list[LegacyCardRow] = []
    for name in names:
        row = table.get(name)
        if not row:
            continue
        fields = _effect_fields(row)
        score = fields[0]
        if score == 0 and name in master:
            match = re.search(r"打分[^0-9]{0,8}(\d{1,3})", master[name])
            if match:
                score = int(match.group(1))
                fields = (score, *fields[1:])
        cost = int(row.get("cost", 4))
        if rich:
            deck.append(_rich_row(name, cost, fields))
        else:
            deck.append((name, cost, score, fields[1], fields[2]))
    return deck


def _rich_row(name: str, cost: int, fields: tuple[int, ...]) -> CardRow:
    """把 ``_effect_fields`` 的 31 元组按顺序转成 rich ``CardRow``。"""
    return CardRow(name, cost, *fields)


def build_pool(
    max_score: int = 60,
    allow_ssr: bool = False,
    *,
    rich: bool = False,
) -> list[CardRow] | list[LegacyCardRow]:
    """奖励池：真机早期能拿到的技能卡。

    默认排除 SSR/Legend（本账号支援卡弱、早期拿不到高分彩卡），并限制分数 <= 40；
    否则模拟器会"每节课都拿 155 分彩卡"，训练平均 320 分，和真机 60-180 完全不符。

    ``rich=False`` 时只收旧集合里的效果类型并返回旧 5 元组（其它脚本兼容）；
    ``rich=True`` 时使用完整 ``MODELED_EFFECTS``（2026-11-16 起 29 种、T5② 后
    32 种：含温存/全力值/可出牌次数/元气依赖分/好调回合数/元气，以及新卡池 16 种、
    熱意追加/増加/適用倍数）并返回
    带 draw/impression/preservation/full_power_point/extra_play/block_scale/
    parameter_buff/strong_level/vitality/stamina_recover/full_power_scale/... 的
    CardRow。
    """
    table = json.loads(CARD_TABLE.read_text(encoding="utf-8")).get("cards", {})
    modeled = MODELED_EFFECTS if rich else LEGACY_MODELED_EFFECTS
    pool: list[CardRow] | list[LegacyCardRow] = []
    for name, row in table.items():
        cost = int(row.get("cost") or 0)
        if cost > 8 or cost < 0:
            continue
        fields = _effect_fields(row)
        score = fields[0]
        rarity = str(row.get("rarity") or "")
        if not allow_ssr and rarity in ("Ssr", "Legend"):
            continue
        if score <= 0 or score > max_score:
            continue
        # 只收"模拟器能建模"的卡：效果类型必须全在 modeled 里，
        # 否则会被当成 0 分卡（状态附魔等还没建模）
        effect_types = {str(e.get("type") or "") for e in row.get("effects") or []}
        if not effect_types or not effect_types <= modeled:
            continue
        if rich:
            pool.append(_rich_row(name, cost, fields))
        else:
            pool.append((name, cost, score, fields[1], fields[2]))
    return pool


def _spec_from_row(row: CardRow | LegacyCardRow):
    """把 build_deck/build_pool 的行转成 LessonSim 的 CardSpec。

    兼容两种行：rich 的 ``CardRow`` 带抽牌/好印象/依赖倍率/指針/可出牌次数/
    元气依赖分/好调回合数/強気段階/元气字段；旧 5 元组只有 score/condition/focus
    （其它分析脚本的默认输出）。
    """
    from gkagent.sim.lesson import CardSpec

    if isinstance(row, CardRow):
        return CardSpec(
            name=row.name,
            cost=row.cost,
            score=row.score,
            condition=row.condition,
            focus=row.focus,
            draw=row.draw,
            impression=row.impression,
            impression_scale=row.impression_scale,
            preservation=row.preservation,
            full_power_point=row.full_power_point,
            extra_play=row.extra_play,
            block_scale=row.block_scale,
            parameter_buff=row.parameter_buff,
            parameter_buff_turns=row.parameter_buff_turns,
            strong_level=row.strong_level,
            vitality=row.vitality,
            stamina_recover=row.stamina_recover,
            full_power_scale=row.full_power_scale,
            encore=bool(row.encore),
            review_multiple=row.review_multiple,
            review_multiple_turns=row.review_multiple_turns,
            condition_additive=row.condition_additive,
            condition_additive_turns=row.condition_additive_turns,
            full_power_lesson_multiple=row.full_power_lesson_multiple,
            full_power_lesson_multiple_turns=row.full_power_lesson_multiple_turns,
            grow_score=row.grow_score,
            motivation=row.motivation,
            enthusiasm_bonus=row.enthusiasm_bonus,
            enthusiasm_bonus_turns=row.enthusiasm_bonus_turns,
            enthusiasm_multiple=row.enthusiasm_multiple,
            enthusiasm_multiple_turns=row.enthusiasm_multiple_turns,
            enthusiasm_extension=row.enthusiasm_extension,
            enthusiasm_multiplier=row.enthusiasm_multiplier,
            leisure_reserve=row.leisure_reserve,
            leisure_reserve_when_save=row.leisure_reserve_when_save,
        )
    name, cost, score, condition, focus = row
    return CardSpec(name=name, cost=cost, score=score, condition=condition, focus=focus)


def _policy_plan_default() -> str:
    """policy.json 的 produce.plan（缺文件/坏值退回 sense）。"""
    from gkagent.data.plans import DEFAULT_PLAN, normalize_plan

    try:
        raw = json.loads((ROOT / "data" / "knowledge" / "policy.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return DEFAULT_PLAN
    produce = raw.get("produce") if isinstance(raw, dict) else None
    candidate = produce.get("plan") if isinstance(produce, dict) else None
    return normalize_plan(candidate) or DEFAULT_PLAN


def _parse_plans(value: str) -> list[str]:
    """``--plans sense,logic,anomaly`` → 去重后的方案列表；空/未知回退默认方案。"""
    from gkagent.data.plans import normalize_plan

    plans: list[str] = []
    for raw in (value or "").split(","):
        name = raw.strip()
        if not name:
            continue
        plan = normalize_plan(name)
        if plan is None:
            print(f"未知方案 {name!r}：只支持 sense/logic/anomaly，已忽略")
            continue
        if plan not in plans:
            plans.append(plan)
    return plans or [_policy_plan_default()]


def run_chunk(task: tuple) -> dict:
    """子进程：跑一段局数，返回聚合结果。"""
    (
        strategy_name,
        episodes,
        seed,
        deck_raw,
        pool_raw,
        reward_pick,
        support,
        audition,
        plan,
    ) = task
    from gkagent.sim.produce import (
        STRATEGIES,
        ProduceConfig,
        ProduceSim,
        eval_value,
        random_strategy,
    )

    deck = [_spec_from_row(row) for row in deck_raw]
    pool = [_spec_from_row(row) for row in pool_raw]
    config = ProduceConfig(
        reward_pick=reward_pick,
        support_bonus=support,
        audition_coefficient=audition,
        plan=plan,
    )
    if strategy_name == "random":
        strategy = random_strategy(seed)
    else:
        strategy = STRATEGIES[strategy_name]

    totals, evals, grades, clears, exams, trainings = [], [], Counter(), 0, 0, 0
    attr_rows: list[tuple[int, int, int]] = []
    exam_scores: list[int] = []
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=seed + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        totals.append(result.total)
        attr_rows.append(result.attrs)
        exam_scores.append(result.exam_score)
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"):
                rank = row["exam"]["rank"]
                break
        # 终试得分已乘考试属性倍率（result.exam_score），再喂官方评价公式
        evals.append(eval_value(result.total, rank, result.exam_score))
        grades[result.grade] += 1
        clears += result.cleared
        exams += result.exams_passed
        trainings += result.trainings
    return {
        "strategy": strategy_name,
        "plan": plan,
        "n": episodes,
        "mean_total": round(stats.mean(totals), 1),
        "mean_attrs": tuple(round(stats.mean(row[i] for row in attr_rows), 1) for i in range(3)),
        "p90_total": round(sorted(totals)[int(len(totals) * 0.9)], 1),
        # 真正的目标指标：官方评价点（均值/P90）+ C+ 达成率
        "mean_eval": round(stats.mean(evals), 1),
        "p50_eval": round(sorted(evals)[len(evals) // 2], 1),
        "p90_eval": round(sorted(evals)[int(len(evals) * 0.9)], 1),
        "p95_eval": round(sorted(evals)[int(len(evals) * 0.95)], 1),
        "cplus_rate": round(sum(1 for e in evals if e >= 4500) / len(evals), 3),
        "grades": dict(grades.most_common()),
        "clear_rate": round(clears / max(trainings, 1), 3),
        # 新键 + 旧键（旧脚本读 lessons_per_run）
        "trainings_per_run": round(trainings / episodes, 2),
        "lessons_per_run": round(trainings / episodes, 2),
        "exams_passed": round(exams / episodes, 2),
        "mean_exam_score": round(stats.mean(exam_scores), 1),
    }


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=20000, help="每种策略的局数")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--only", default="class_best,class_lowest,training_heavy,mixed,random,smart")
    parser.add_argument("--rewards", choices=["best", "random", "none"], default="best")
    parser.add_argument("--support", type=float, default=1.2,
                        help="训练/训练收益倍率（默认 1.2 = 真机支援卡均值 Lv20 校准值）")
    parser.add_argument("--audition-coefficient", type=float, default=4.11,
                        help="考试/舞台属性倍率（默认 4.11 = 真机屏幕「歌唱 411%%」；"
                             "训练仍 1.0，传 1.0 可复现改前口径）")
    parser.add_argument("--plans", default="",
                        help="方案，逗号分隔：sense,logic,anomaly；默认读 "
                             "policy.json 的 produce.plan（缺省 sense）")
    args = parser.parse_args(argv)

    # rich=True：把抽牌/好印象/依赖倍率带进 CardSpec（默认 5 元组给其它脚本兼容）
    deck = build_deck(rich=True)
    pool = build_pool(rich=True) if args.rewards != "none" else []
    plans = _parse_plans(args.plans)
    print(
        f"卡组 {len(deck)} 张, 奖励池 {len(pool)} 张, 选牌={args.rewards}, "
        f"支援加成={args.support}, 考试属性倍率={args.audition_coefficient}, "
        f"方案={','.join(plans)}"
    )
    names = [name.strip() for name in args.only.split(",") if name.strip()]
    tasks = [
        (
            name,
            args.episodes,
            1234 + index * 7919,
            deck,
            pool,
            args.rewards,
            args.support,
            args.audition_coefficient,
            plan,
        )
        for plan in plans
        for index, name in enumerate(names)
    ]
    workers = args.workers or min(8, len(tasks))

    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_chunk, tasks))
    elapsed = time.perf_counter() - started

    for row in results:
        print(
            f"{row['strategy']:14s} plan={row['plan']:7s} n={row['n']:>7} "
            f"三维均值={row['mean_attrs']} 总和均值={row['mean_total']:>7} "
            f"终试分={row['mean_exam_score']:>8.1f} "
            f"评价点均值={row['mean_eval']:>7} P50={row['p50_eval']:>7} "
            f"P90={row['p90_eval']:>7} C+率={row['cplus_rate']*100:3.0f}% "
            f"训练/局={row['trainings_per_run']:.1f} 考试通过={row['exams_passed']:.1f} "
            f"评价={row['grades']}"
        )
    total_runs = sum(row["n"] for row in results)
    print(f"\n合计 {total_runs} 局，{elapsed:.1f}s，{total_runs/max(elapsed,1e-9):.0f} 局/秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
