"""熱意（enthusiasm）与温存解除的纯函数规则（T5② 2026-11-22）。

「熱意」是考试/训练里一个**独立的分数资源**，不是好调回合：

- 出牌结算时，在集中加算之后、好调/指針倍率之前 ``score += 熱意``
  （官方描述「熱意1につきパラメータ上昇量を1増加」= 本牌分数加算）；
- 主要来源是**解除温存**：1 段階 +5 熱意、2 段階 +8 熱意；解除当回合
  出牌次数 +1；2 段階解除还额外给 5 点**固定元気**（不吃「やる気」加成）。
  同一回合内反复「温存→強気」可以按次数重复拿（参考引擎逐次触发）；
- 获得量公式：``(熱意追加 + N) × (1 + 熱意増加‰)``。熱意追加 =
  ``ExamEnthusiasticAdditive``（加算 buff），熱意増加 = ``ExamEnthusiasticMultiple``
  （千分比 buff）。参考引擎把熱意当 ``WHOLE_FIELDS``：每次赋值都
  ``Math.ceil(Number(value.toFixed(2)))``（`Executor/index.js` clamp/whole 字段处理），
  等价于**获得时向上取整**（与官方 wiki「計算後小数点以下切り上げ」一致）。
- 回合结束時熱意归 0；有「熱意延長」（``ExamEnthusiasticTurnAdd``）时每回合
  消耗 1 回合延長、保留熱意。
- 本牌「熱意適用倍数」（``ExamMultipleEnthusiasticLesson`` / ``enthusiasmMultiplier``）
  只放大**该牌**的熱意贡献，默认 1.0。

证据（BSD-3 参考引擎 `gakumas-tools` + 官方 wiki 描述）：

- ``packages/gakumas-engine/constants.js`` ``STANCE_CHANGED_EFFECTS``：
  ``prevStance==preservation & stance!=leisure → enthusiasm+=5; cardUsesRemaining+=1``；
  ``prevStance==preservation2 & stance!=leisure → enthusiasm+=8; fixedGenki+=5;
  cardUsesRemaining+=1``；のんびり（leisure）解除（P1-1 2026-11-24 接入）：
  ``prevStance==leisure → fixedGenki+=5; cardUsesRemaining+=1``；
  ``→fullPower`` 时 ``target:all { g.score+=10 }``（全体卡打分成长），
  否则 ``enthusiasm+=10``。
- ``Executor/resolvers.js``：``resolveScore`` b（``score += enthusiasm *
  enthusiasmMultiplier``，之后才 ceil）、``resolveEnthusiasm``（先加算 bonus 再乘
  増加 buff；結果经 ``WHOLE_FIELDS`` 处理向上取整）、``TurnManager.endTurn``
  （``enthusiasmExtensionTurns`` 优先于清零，好印象结算在清零之前）。
- 官方 wiki 温存条（`data/cache/_buffs_before.json`）：「熱意+5・スキルカード使用数
  追加+1」「熱意+8・固定元気+5・スキルカード使用数追加+1」「ターン終了時、熱意を0にする」。

口径限制：本模块只做「解除温存 / 解除のんびり」这两类指針来源；卡牌自带的
熱意追加/増加/延長 buff 由 ``CardSpec`` 承载，出牌后登记进 ``Buffs``。
P 道具/附魔里的熱意触发（数据未接入）留给后续任务。
"""

from __future__ import annotations

import math

from gkagent.sim.stance import Stance, StanceState

__all__ = [
    "LEISURE_RELEASE_ENTHUSIASM",
    "LEISURE_RELEASE_EXTRA_PLAYS",
    "LEISURE_RELEASE_FIXED_GENKI",
    "LEISURE_TO_FULL_SCORE_GROWTH",
    "SAVE_RELEASE_ENTHUSIASM",
    "SAVE_RELEASE_EXTRA_PLAYS",
    "SAVE_RELEASE_FIXED_GENKI",
    "enthusiasm_gain",
    "release_on_stance_change",
    "save_level",
    "turn_end_enthusiasm",
]

# 温存解除的基础熱意：1 段階 +5、2 段階 +8（参考引擎 constants.js）。
SAVE_RELEASE_ENTHUSIASM: dict[int, int] = {1: 5, 2: 8}
# 固定元気：2 段階解除 +5（1 段階没有）；不吃「やる気」加成。
SAVE_RELEASE_FIXED_GENKI: dict[int, int] = {1: 0, 2: 5}
# 解除温存当回合额外可出牌次数 +1（1/2 段階都有）。
SAVE_RELEASE_EXTRA_PLAYS = 1

# のんびり解除（P1-1 2026-11-24，参考引擎 STANCE_CHANGED_EFFECTS）：
#   prevStance==leisure → fixedGenki+=5; cardUsesRemaining+=1
#   prevStance==leisure & stance!=fullPower → enthusiasm+=10
#   prevStance==leisure & stance==fullPower → target:all { g.score+=10 }
# 注意第三条是**全体卡打分成长 +10**（cardManager.grow 对 cardMap 每张卡
# executeGrowthActions(g.score+=10)，之后每次出牌走 resolveScore 加进白值），
# 不是即时 +10 考试分；也不是熱意。熱意公式 wiki 核实：N = 温存1=5/温存2=8/
# のんびり=10（data/knowledge/buffs.json 熱意条 jp_desc）。
LEISURE_RELEASE_ENTHUSIASM = 10
LEISURE_RELEASE_FIXED_GENKI = 5
LEISURE_RELEASE_EXTRA_PLAYS = 1
LEISURE_TO_FULL_SCORE_GROWTH = 10


def save_level(state: StanceState) -> int:
    """温存段階折算成 1/2：段階缺失按 1 段階（保守），≥2 一律 2 段階。"""
    level = int(getattr(state, "save_level", 0) or 0)
    return 2 if level >= 2 else 1


def release_on_stance_change(
    prev: StanceState, new: StanceState
) -> tuple[int, int, int, int]:
    """指針解除的即时收益 ``(熱意基础值, 固定元気, 額外出牌次数, 全体卡打分成长)``。

    参考引擎 ``constants.js STANCE_CHANGED_EFFECTS``（P1-1 2026-11-24 补全
    のんびり）：

    - 温存解除：``prevStance==preservation(2) & stance!=leisure`` → 熱意 5/8、
      2 段階固定元気 +5、+1 出牌次数。**切到 のんびり 不触发温存解除**
      （``stance!=leisure`` 条件）；``save`` 段階升级（1→2）也不触发。
    - のんびり解除：``prevStance==leisure`` → 固定元気 +5、+1 出牌次数；
      新指針不是全力 → 熱意 +10；新指針是全力 → **全体卡打分成长 +10**
      （``target:all { g.score+=10 }``，不是熱意也不是即时分）。

    返回的熱意是**基础值**，调用方还要过 :func:`enthusiasm_gain` 吃熱意追加/増加 buff。
    打分成长是永久加算（参考引擎 cardMap growth），调用方累进
    ``LessonSim.score_growth_all`` / ``ExpectState.score_growth_all``。
    """
    if prev.stance == Stance.SAVE and new.stance not in (Stance.SAVE, Stance.LEISURE):
        level = save_level(prev)
        return (
            SAVE_RELEASE_ENTHUSIASM[level],
            SAVE_RELEASE_FIXED_GENKI[level],
            SAVE_RELEASE_EXTRA_PLAYS,
            0,
        )
    if prev.stance == Stance.LEISURE and new.stance != Stance.LEISURE:
        to_full = new.stance == Stance.FULL
        return (
            0 if to_full else LEISURE_RELEASE_ENTHUSIASM,
            LEISURE_RELEASE_FIXED_GENKI,
            LEISURE_RELEASE_EXTRA_PLAYS,
            LEISURE_TO_FULL_SCORE_GROWTH if to_full else 0,
        )
    return (0, 0, 0, 0)


def enthusiasm_gain(base: int, *, bonus: int = 0, multiple_permil: int = 0) -> int:
    """一次熱意获得的数值：``(base + bonus) × (1 + multiple_permil / 1000)``，向上取整。

    ``bonus`` = 熱意追加（``ExamEnthusiasticAdditive``）的加算；``multiple_permil``
    = 熱意増加（``ExamEnthusiasticMultiple``）的千分比。参考引擎把熱意当整数
    （``WHOLE_FIELDS``：``Math.ceil(Number(value.toFixed(2)))``），所以这里取整，
    与官方 wiki 的「計算後切り上げ」一致。
    """
    additive = int(base) + int(bonus)
    multiplier = 1.0 + int(multiple_permil) / 1000.0
    return math.ceil(round(additive * multiplier, 2))


def turn_end_enthusiasm(enthusiasm: int, extension_turns: int) -> tuple[int, int]:
    """回合结束时熱意的去留：有「熱意延長」回合则保留并把延長 -1，否则归 0。"""
    if int(extension_turns) > 0:
        return int(enthusiasm), int(extension_turns) - 1
    return 0, 0
