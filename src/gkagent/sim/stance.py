"""非凡（アノマリー）指針（スタンス）的纯函数状态模块。

非凡方案的分数倍率由「指針」决定。以无指針为 100%，官方攻略表的倍率：

===========  ======  ==========================================
指針          倍率    说明
===========  ======  ==========================================
温存 1 段階   0.50    体力消耗降低（本模块不建模）
温存 2 段階   0.25    同上
无指針        1.00    ニュートラル
強気 1 段階   2.00    体力消耗增加（本模块不建模）
強気 2 段階   2.50    同上
全力          3.00    参数上升量 +200%，仅持续下一回合
のんびり      0.00    分数/费用都 ×0（P1-1 2026-11-24 接入）
===========  ======  ==========================================

状态机（按真机规则做的近似）：

1. 出牌时 ``ExamFullPowerPoint`` 增加全力值；``ExamPreservation``
   把指針变更到温存 1/2 段階。
2. 回合结束时（``end_turn``）若全力值 ≥ 10：消耗 10 点，
   下一回合进入「全力」。
3. 「全力」只持续一个回合；全力回合结束时若没有再次攒满 10 点，
   指針回到无指針。
4. 温存 / 強気的段階只影响倍率；切换指針时是否保留段階由调用方状态为准。

本模块只做数值推演，不读卡表、不依赖模拟器；全部是纯函数，
不修改传入的 ``StanceState``。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

__all__ = [
    "FULL_POWER_POINT_COST",
    "LEISURE_RESERVE_SOURCES",
    "MAX_STANCE_LEVEL",
    "MULTIPLIER",
    "Stance",
    "StanceState",
    "apply_full_power_point",
    "card_stance_effect",
    "end_turn",
    "leisure_reserve_for",
    "score_multiplier",
    "stamina_cost_multiplier",
    "stamina_pierce",
    "stance_change_allowed",
]

# 攒满 10 点全力值，回合结束时消耗 10 点进入下一回合的「全力」。
FULL_POWER_POINT_COST = 10
# 温存 / 強気都只有 1 段階、2 段階两档。
MAX_STANCE_LEVEL = 2


class Stance(StrEnum):
    """指針的六个对外常量。

    ``SAVE`` 的段階放在 ``StanceState.save_level``；強気的倍率表只有
    1/2 段階两档，因此这里直接给出 ``STRONG1`` / ``STRONG2`` 两个值。
    ``strong_level`` 字段仍保留，用于兼容"只写基础形态 strong + level"的调用方。
    ``LEISURE``（のんびり）无段階：分数/费用 ×0，解除收益见 enthusiasm.py。
    """

    SAVE = "save"
    NORMAL = "normal"
    STRONG1 = "strong1"
    STRONG2 = "strong2"
    FULL = "full"
    LEISURE = "leisure"


# 有效的指針倍率。温存按段階拆成两个 key；其余 key 与 Stance 的字符串值一致。
# のんびり（leisure）×0：参考引擎 resolveScore ``stance=="leisure" → score*=0``
# （P1-1 2026-11-24，BSD-3 gakumas-engine Executor/resolvers.js）。
MULTIPLIER: dict[str, float] = {
    "save1": 0.5,
    "save2": 0.25,
    "normal": 1.0,
    "strong1": 2.0,
    "strong2": 2.5,
    "full": 3.0,
    "leisure": 0.0,
}


@dataclass
class StanceState:
    """当前指針状态。

    - ``stance``：``Stance`` 的字符串值；默认无指針 ``"normal"``。
    - ``strong_level``：強気段階（1/2）。只在 ``stance="strong"`` 这种
      基础形态写法下参与倍率；用 ``Stance.STRONG1/2`` 时以 stance 为准。
    - ``save_level``：温存段階（1/2），``stance="save"`` 时决定倍率。
    - ``full_power_point``：全力值，≥10 时回合结束切到「全力」。
    """

    stance: str = "normal"
    strong_level: int = 0
    save_level: int = 0
    full_power_point: int = 0


def _clamp_level(level: int) -> int:
    """段階夹到 1/2：0 或负数按 1 段階算，超过 2 按 2 段階算。"""
    return MAX_STANCE_LEVEL if level >= MAX_STANCE_LEVEL else 1


def _multiplier_key(state: StanceState) -> str:
    """把状态折算成 ``MULTIPLIER`` 的 key；认不出的指針按无指針处理。"""
    stance = str(state.stance)
    if stance == Stance.SAVE:
        return f"save{_clamp_level(state.save_level)}"
    if stance in (Stance.STRONG1, Stance.STRONG2):
        return stance
    if stance == "strong":
        # 兼容 stance="strong" + strong_level 的写法。
        return f"strong{_clamp_level(state.strong_level)}"
    return stance if stance in MULTIPLIER else Stance.NORMAL


def score_multiplier(state: StanceState) -> float:
    """当前指針的分数倍率（温存 / 強気 / 全力 / 无指針）。

    未知指針、段階缺失都按保守值处理：未知指針 = 无指針 1.0，
    段階缺失 = 1 段階，不抛异常。
    """
    return MULTIPLIER[_multiplier_key(state)]


def stamina_cost_multiplier(state: StanceState) -> float:
    """出牌体力消耗倍率（wiki 核实，2026-11-16）。

    温存 1 段階 0.5、2 段階 0.25；強気 1/2 段階 ×2；无指針/全力 ×1；
    のんびり ×0（参考引擎 resolveCost ``leisure → cost*=0``，P1-1）。
    实际扣费在 ```LessonSim._pay_card_cost`` 里向上取整。
    """
    key = _multiplier_key(state)
    if key == "save1":
        return 0.5
    if key == "save2":
        return 0.25
    if key in ("strong1", "strong2"):
        return 2.0
    if key == "leisure":
        return 0.0
    return 1.0


def stance_change_allowed(state: StanceState, kind: str, *, locked: bool = False) -> bool:
    """参考引擎 ``BuffManager.setStance`` 的指針変更守卫（P1-1 2026-11-24）。

    - 全力期间不能切指針（``stance=="fullPower"`` 时只允许 ``setStance(none)``，
      那由 ``end_turn`` 的全力解除走，不走这里）；
    - のんびり期间不能切温存（``leisure && stance.startsWith("preservation")``
      直接 return）；
    - **P1-3（2026-11-24）**：``lockStanceTurns``（指針固定）>0 时禁切指針
      （参考 ``else if (state[S.lockStanceTurns]) return;``）。``locked`` 由
      调用方传 ``lock_stance_turns > 0``（默认 False = 旧行为）；来源卡切磋琢磨
      （``StanceLock`` turn=1 ↔ DSL ``lockStanceTurns+=1``）。

    ``kind`` 取 ``"preservation"`` / ``"concentration"`` / ``"leisure"``。
    全力值获得（``ExamFullPowerPoint``）走 ``resolveFullPowerCharge``，
    不受 setStance 守卫影响，不在本函数管辖内。
    """
    stance = str(state.stance)
    if stance == Stance.FULL:
        return False
    if locked:
        return False
    return not (stance == Stance.LEISURE and kind == "preservation")


# のんびり预约来源（P1-1 2026-11-24）：卡 base id → (条件, 次数)。
# 主数据里这些卡的 ``ExamStatusEnchant.inner`` 是 ``ExamOverPreservation``
# （values 空），条件/次数不在主数据 JSON 里，按 BSD-3 参考引擎
# ``packages/gakumas-data/csv/skill_cards.csv`` 的 DSL 逐卡交叉验证
# （日文卡名 ↔ 中文卡名用 data/knowledge/card_meta.json 别名表核对）：
#   540-541 のんびり屋さん（悠闲自在的人）:
#     at:afterStartOfTurn { if:isPreservation { setStance(leisure) } }（永久）
#   542-543 休み休み、前へ（走走停停，继续前进）: 同上（永久）
#   544-545 屋上からの景色（从天台看到的景色）: 同上（永久）
#   834 星々を見下ろす一番星（俯瞰群星的启明星）:
#     at:startOfTurn { if:!isPreservation { setStance(leisure) }; limit:3 }
#     （主数据 ExamStatusEnchant.count=3 与 limit:3 一致）
# 条件 True = 温存中才触发（afterStartOfTurn 时机）；False = 非温存才触发
# （startOfTurn 时机；本模型两时机都在抽牌后结算，期间无其它指針交互，等价）。
# 次数 -1 = 永久（turn=-1）；N = 触发 N 次后失效。未知 id 保守 no-op（不猜）。
LEISURE_RESERVE_SOURCES: dict[str, tuple[bool, int]] = {
    "p_card-03-ido-1_054": (True, -1),
    "p_card-03-ido-2_084": (True, -1),
    "p_card-03-ido-3_077": (True, -1),
    "p_card-03-ido-100_047": (False, 3),
}


def leisure_reserve_for(card_id: str) -> tuple[int, bool]:
    """卡 base id → のんびり预约 ``(剩余次数, 是否温存中触发)``。

    未知 id 返回 ``(0, True)``（不登记预约，保守 no-op）。
    """
    when_save, limit = LEISURE_RESERVE_SOURCES.get(str(card_id), (True, 0))
    return limit, when_save


def stamina_pierce(state: StanceState) -> int:
    """強気 2 段階：额外穿透元气、直接扣体力的点数（wiki：1 点）。"""
    return 1 if _multiplier_key(state) == "strong2" else 0


def apply_full_power_point(state: StanceState, delta: int) -> StanceState:
    """增加全力值，返回新状态。

    ``delta`` 为负时按 0 处理（本模块只表达"增加"；真机的消耗由
    ``end_turn`` 统一结算）。非 int（含 bool）会抛 ``TypeError``，便于
    尽早发现卡表解析错误。
    """
    if isinstance(delta, bool) or not isinstance(delta, int):
        raise TypeError(f"delta 必须是 int：{delta!r}")
    gain = max(0, delta)
    return replace(state, full_power_point=max(0, state.full_power_point + gain))


def end_turn(state: StanceState, *, locked: bool = False) -> StanceState:
    """回合结束结算指針，返回新状态。

    近似真机的顺序：

    - 若全力值 ≥ 10 **且指針未固定**：消耗 10 点，下一回合进入「全力」；
      超过 10 的部分保留，供下一次全力使用。参考 ``FULL_POWER_EFFECTS``：
      ``if:lockStanceTurns==0 & fullPowerCharge>=10 { fullPowerCharge-=10;
      setStance(fullPower) }``——固定期间全力值**不消耗**、指針不变。
    - 否则若当前是「全力」：全力只持续一个回合，回合结束回到无指針
      （全力解除 = ``setStance(none)``，参考 setStance 的 fullPower 分支
      不受 lockStanceTurns 守卫，固定期间也照常解除）。
    - 其它情况原样返回（不改段階、不扣全力值）。

    ``locked`` 由调用方传 ``lock_stance_turns > 0``（P1-3，默认 False = 旧行为）。
    """
    if state.full_power_point >= FULL_POWER_POINT_COST and not locked:
        return replace(
            state,
            stance=Stance.FULL,
            full_power_point=state.full_power_point - FULL_POWER_POINT_COST,
        )
    if state.stance == Stance.FULL:
        return replace(state, stance=Stance.NORMAL)
    return replace(state)


# 保守的 no-op 字段更新；每次返回副本，避免调用方误改模块级常量。
_NO_STANCE_CHANGE: dict[str, object] = {
    "stance": None,
    "save_level": 0,
    "full_power_point": 0,
}


def card_stance_effect(effect_type: str, values: list[int]) -> dict:
    """把卡表的指針效果翻译成 ``StanceState`` 的字段更新。

    支持的 effect_type（``data/knowledge/card_table.json`` 的
    ``effects[].type`` / ``values``）：

    - ``ExamPreservation``：``values[0]`` 是**变更到的温存段階**（1/2）。
      返回 ``{"stance": "save", "save_level": <段階>,
      "full_power_point": 0}``。这里没有当前状态，所以是"设为"而不是
      "叠加"；真机在温存中再用温存牌会升到 2 段階，调用方可以在应用时取
      ``max(current.save_level, delta["save_level"])`` 做保守近似。
    - ``ExamConcentration``：卡面「強気変更」；``values[0]`` 是**变更到的
      強気段階**（1/2，卡表里 1 = 1 段階、2 = 2 段階）。返回
      ``{"stance": "strong1"/"strong2", "save_level": 0,
      "full_power_point": 0}``。未知段階按 no-op 处理。
    - ``ExamFullPowerPoint``：``values[0]`` 是全力值**增量**。
      返回 ``{"stance": None, "save_level": 0,
      "full_power_point": <增量>}``；``stance=None`` 表示不改指針。
      增量负值按 0 处理。

    ``ExamStatusEnchant`` 以及其它未支持类型：这些效果在真机里可能间接
    影响指針（例如状态附魔、指針固定），但本模块没有足够信息，按
    **保守 no-op** 处理（三个字段都为 0/None），保证不崩也不乱猜。

    返回值始终含 ``stance`` / ``save_level`` / ``full_power_point`` 三个键：
    ``stance`` 是新指針或 ``None``（保持当前），``save_level`` 是目标段階
    （只有 ``ExamPreservation`` 非 0），``full_power_point`` 是增量。
    全力期间真机不能改指針；是否忽略这里的更新由调用方按规则决定。
    """
    if not isinstance(effect_type, str):
        return dict(_NO_STANCE_CHANGE)
    kind = effect_type.strip()
    value = values[0] if values else None
    if isinstance(value, bool) or not isinstance(value, int):
        return dict(_NO_STANCE_CHANGE)

    if kind == "ExamPreservation":
        if value not in (1, MAX_STANCE_LEVEL):
            return dict(_NO_STANCE_CHANGE)
        return {
            "stance": Stance.SAVE,
            "save_level": value,
            "full_power_point": 0,
        }

    if kind == "ExamConcentration":
        if value not in (1, MAX_STANCE_LEVEL):
            return dict(_NO_STANCE_CHANGE)
        return {
            "stance": Stance.STRONG1 if value == 1 else Stance.STRONG2,
            "save_level": 0,
            "full_power_point": 0,
        }

    if kind == "ExamFullPowerPoint":
        return {
            "stance": None,
            "save_level": 0,
            "full_power_point": max(0, value),
        }

    return dict(_NO_STANCE_CHANGE)
