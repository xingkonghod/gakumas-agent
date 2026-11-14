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
    "MAX_STANCE_LEVEL",
    "MULTIPLIER",
    "Stance",
    "StanceState",
    "apply_full_power_point",
    "card_stance_effect",
    "end_turn",
    "score_multiplier",
]

# 攒满 10 点全力值，回合结束时消耗 10 点进入下一回合的「全力」。
FULL_POWER_POINT_COST = 10
# 温存 / 強気都只有 1 段階、2 段階两档。
MAX_STANCE_LEVEL = 2


class Stance(StrEnum):
    """指針的五个对外常量。

    ``SAVE`` 的段階放在 ``StanceState.save_level``；強気的倍率表只有
    1/2 段階两档，因此这里直接给出 ``STRONG1`` / ``STRONG2`` 两个值。
    ``strong_level`` 字段仍保留，用于兼容"只写基础形态 strong + level"的调用方。
    """

    SAVE = "save"
    NORMAL = "normal"
    STRONG1 = "strong1"
    STRONG2 = "strong2"
    FULL = "full"


# 有效的指針倍率。温存按段階拆成两个 key；其余 key 与 Stance 的字符串值一致。
MULTIPLIER: dict[str, float] = {
    "save1": 0.5,
    "save2": 0.25,
    "normal": 1.0,
    "strong1": 2.0,
    "strong2": 2.5,
    "full": 3.0,
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


def end_turn(state: StanceState) -> StanceState:
    """回合结束结算指針，返回新状态。

    近似真机的顺序：

    - 若全力值 ≥ 10：消耗 10 点，下一回合进入「全力」；
      超过 10 的部分保留，供下一次全力使用。
    - 否则若当前是「全力」：全力只持续一个回合，回合结束回到无指針。
    - 其它情况原样返回（不改段階、不扣全力值）。
    """
    if state.full_power_point >= FULL_POWER_POINT_COST:
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

    if kind == "ExamFullPowerPoint":
        return {
            "stance": None,
            "save_level": 0,
            "full_power_point": max(0, value),
        }

    return dict(_NO_STANCE_CHANGE)
