"""考试属性倍率（审查倍率）：分段曲线 + 联动惩罚 + 单精度取整。

T5 机制建模（2026-11-22）。真机考试/舞台每回合顶部显示的「歌唱 411%」不是常数，
而是**本场考试开始时按三个培育属性算出来的三个独立倍率**（千分比）：

1. **分段曲线**：每个属性在自己的属性值上，按主数据
   ``ProduceExamBattleScoreConfig`` 的节点表做**折线插值**，得到
   ``component_permil``（例：Vo=373 在节点 320→3000 之间插值）。
2. **联动惩罚**：每个属性低于本场 ``ProduceExamBattleConfig`` 的**审查基准**
   （``vocal`` / ``dance`` / ``visual``；例如期中 320/128/192）时，按
   ``GetPenaltyPermil`` 线性罚分（全局限幅 ``Setting`` 的
   ``produceExamBattleScorePenaltyMinPermil`` / ``...MaxPermil``，本机 100/250）。
   **三项共用同一个惩罚系数**：``common = 1000 − Σpenalties``，所以一项不达标会把
   三个属性的倍率一起压低——社区口径的「联动惩罚」。
3. **归一化**：``bonus = 1000 + (component × common / 1000)`` 向上取整到 10 的倍数。

出牌与回合末好印象得分都乘当前回合属性对应的倍率，取整口径是客户端
``CalcCurrentTurnBattleBonus``：``ceil(f32(f32(bonus/1000) × amount − 1e-4))``
（单精度乘完再减一个单精度 epsilon；参考引擎 ``battle_bonus_score`` 同实现）。

口径来源（只引用语义、不拷贝代码）：
- gakumas-tools（BSD-3）``packages/gakumas-engine/typeMultipliers.js``：
  分段曲线 + ``shortfallRate`` 联动惩罚的 contest 版本；
- hiro-gakumas-hero（AGPL，仓库外参考）``vendor/.../gakumas_produce/attributes.py``：
  从客户端反编译还原的 ``calculate`` / ``battle_bonus_score``（同样的分段 + 联动惩罚，
  用于考试属性倍率）与 ``normalize_bonus`` / ``getPenaltyPermil`` 的精确算术语义；
- 主数据表：``ProduceStepAuditionDifficulty``（偶像卡 → 考试配置）、
  ``ProduceExamBattleConfig``（回合数 / 审查基准 / 分数表 id）、
  ``ProduceExamBattleScoreConfig``（分段节点表）、``Setting``（惩罚上下限）。

局限（写进 ``docs/RULES_REFERENCE.md``）：本模块只算**属性倍率**；
P 道具附魔 / 考试内生成卡 / 依赖分是否吃倍率等仍未建模，真机逐分回放还差这几项。
"""

from __future__ import annotations

import math
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ATTRS: tuple[str, str, str] = ("vocal", "dance", "visual")
# 真机 ExamTurnEndLog.parameterType：1=歌唱(Vo) / 2=舞蹈(Da) / 3=视觉(Vi)
PARAMETER_TYPE_ATTRS: dict[int, str] = {1: "vocal", 2: "dance", 3: "visual"}
PERMIL_COLUMNS: dict[str, str] = {
    "vocal": "vocalPermil",
    "dance": "dancePermil",
    "visual": "visualPermil",
}
# 全局惩罚上下限（主数据 Setting.produceExamBattleScorePenaltyMinPermil / MaxPermil；
# 2026-11-22 快照 f4d9e6e6148d 为 100/250，缺数据时用同值兜底）
DEFAULT_PENALTY_MIN_PERMIL = 100
DEFAULT_PENALTY_MAX_PERMIL = 250
_EPSILON = 1e-4


def f32(value: float) -> float:
    """按 IEEE-754 单精度截断（客户端算术语义；Python 侧用 struct 模拟）。"""
    return struct.unpack("f", struct.pack("f", float(value)))[0]


def normalize_bonus(component_permil: int, common_permil: int) -> int:
    """``component × common`` 归一化：``1000 + 乘积/1000`` 向上取整到 10 的倍数。

    与客户端一致：整数乘积 → 乘除后 ceil 到 10（``f32`` 截断前后各一次）。
    """
    product = int(component_permil) * int(common_permil)
    if not -(2**31) <= product < 2**31:
        raise ValueError(f"属性倍率乘积溢出 int32：{component_permil}×{common_permil}")
    value = 1000 + (abs(product) // 1000) * (1 if product >= 0 else -1)
    return math.trunc(f32(math.ceil(f32(f32(value) / f32(10))) * f32(10)))


def interpolate_component(value: int, score_table: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """属性值 → 三项 ``component_permil``（折线插值，节点表按 parameter 升序）。

    ``score_table`` 每行至少含 ``parameter`` 与 ``vocalPermil`` / ``dancePermil`` /
    ``visualPermil`` 三个千分比列。节点必须唯一、含 0；超出最大节点时取最大节点值。
    """
    ordered = sorted(score_table, key=lambda row: int(row["parameter"]))
    if not ordered or int(ordered[0]["parameter"]) != 0:
        raise ValueError("分数表必须从 parameter=0 开始")
    parameters = [int(row["parameter"]) for row in ordered]
    if len(set(parameters)) != len(parameters):
        raise ValueError("分数表节点 parameter 必须唯一")
    value = int(value)
    low_index = max(
        (index for index, parameter in enumerate(parameters) if parameter <= value),
        default=0,
    )
    low = ordered[low_index]
    high = ordered[low_index + 1] if low_index + 1 < len(ordered) else None
    components: dict[str, int] = {}
    for attr in ATTRS:
        column = PERMIL_COLUMNS[attr]
        low_permil = int(low.get(column) or 0)
        if high is None:
            components[attr] = low_permil
            continue
        low_parameter = parameters[low_index]
        high_parameter = int(high["parameter"])
        high_permil = int(high.get(column) or 0)
        if high_parameter <= low_parameter:
            components[attr] = low_permil
            continue
        interpolated = low_permil + math.ceil(
            ((high_permil - low_permil) / (high_parameter - low_parameter))
            * (value - low_parameter)
        )
        components[attr] = int(interpolated)
    return components


def component_permil(value: int, attr: str, score_table: Sequence[Mapping[str, Any]]) -> int:
    """单个属性在自己参数值上的分段插值（千分比）。"""
    if attr not in ATTRS:
        raise ValueError(f"未知属性 {attr!r}：只支持 {ATTRS}")
    return interpolate_component(int(value), score_table)[attr]


def penalty_permil(
    value: int,
    baseline: int,
    *,
    minimum_permil: int = DEFAULT_PENALTY_MIN_PERMIL,
    maximum_permil: int = DEFAULT_PENALTY_MAX_PERMIL,
) -> int:
    """低于审查基准时的罚分（千分比）；``value >= baseline`` 时为 0。

    客户端 ``GetPenaltyPermil``：``(min + (max−min)/baseline × (baseline−value)) × 1000``
    后向零截断（``math.trunc``）。baseline<=0 视为不设基准，恒 0。
    """
    value = int(value)
    baseline = int(baseline)
    if baseline <= 0 or value >= baseline:
        return 0
    if not 0 <= minimum_permil <= maximum_permil <= 1000:
        raise ValueError(
            f"惩罚上下限不合法：{minimum_permil}/{maximum_permil}（要求 0<=min<=max<=1000）"
        )
    raw = (
        minimum_permil / 1000
        + ((maximum_permil / 1000 - minimum_permil / 1000) / baseline) * (baseline - value)
    )
    return math.trunc(raw * 1000)


@dataclass(frozen=True)
class ExamBonus:
    """一场考试的三项属性倍率（千分比）与中间量。"""

    permil: Mapping[str, int]
    components: Mapping[str, int]
    penalties: Mapping[str, int]
    common_permil: int
    criteria: Mapping[str, int] = field(default_factory=dict)

    def multiplier(self, attr: str) -> float:
        """属性名（vocal/dance/visual）→ 系数（4110 → 4.11）。"""
        return int(self.permil[attr]) / 1000.0

    def multiplier_for_parameter_type(self, parameter_type: int) -> float:
        """ExamTurnEndLog 的 parameterType（1/2/3）→ 本回合系数。"""
        attr = PARAMETER_TYPE_ATTRS.get(int(parameter_type))
        if attr is None:
            raise ValueError(f"未知的回合属性 parameterType：{parameter_type}")
        return self.multiplier(attr)

    def permil_for_parameter_type(self, parameter_type: int) -> int:
        attr = PARAMETER_TYPE_ATTRS.get(int(parameter_type))
        if attr is None:
            raise ValueError(f"未知的回合属性 parameterType：{parameter_type}")
        return int(self.permil[attr])

    def coefficients(self) -> tuple[float, float, float]:
        return tuple(self.multiplier(attr) for attr in ATTRS)  # type: ignore[return-value]


def calculate_bonus(
    params: Mapping[str, int],
    criteria: Mapping[str, int],
    score_table: Sequence[Mapping[str, Any]],
    *,
    penalty_min_permil: int = DEFAULT_PENALTY_MIN_PERMIL,
    penalty_max_permil: int = DEFAULT_PENALTY_MAX_PERMIL,
) -> ExamBonus:
    """培育属性值 + 本场审查基准 + 分数表 → 三项属性倍率。

    ``params`` 是考试开始时培育界面的 Vo/Da/Vi（真机采集
    ``UserProduceProgress.vocal/dance/visual``，也就是屏幕「歌唱 411%」的来源）。
    """
    components = {
        attr: component_permil(int(params[attr]), attr, score_table) for attr in ATTRS
    }
    penalties = {
        attr: penalty_permil(
            int(params[attr]),
            int(criteria.get(attr) or 0),
            minimum_permil=penalty_min_permil,
            maximum_permil=penalty_max_permil,
        )
        for attr in ATTRS
    }
    common = 1000 - sum(penalties.values())
    permil = {attr: normalize_bonus(components[attr], common) for attr in ATTRS}
    if min(permil.values()) < 0:
        raise ValueError(f"属性倍率算成负数（{permil}）：检查分数表/惩罚配置")
    return ExamBonus(
        permil=permil,
        components=components,
        penalties=penalties,
        common_permil=common,
        criteria={attr: int(criteria.get(attr) or 0) for attr in ATTRS},
    )


def battle_bonus_score(amount: int, bonus_permil: int) -> int:
    """本牌/本段得分 × 属性倍率后的取整（客户端 ``CalcCurrentTurnBattleBonus``）。

    单精度 ``multiplier = f32(bonus/1000)``，``value = f32(f32(multiplier×amount) +
    f32(−1e-4))``，再 ``ceil``。amount<=0 原样返回（纯 buff 牌不参与倍率）。
    """
    amount = int(amount)
    if amount <= 0:
        return amount
    multiplier = f32(f32(bonus_permil) / f32(1000))
    value = f32(f32(multiplier * f32(amount)) + f32(-_EPSILON))
    return math.ceil(value)


__all__ = [
    "ATTRS",
    "DEFAULT_PENALTY_MAX_PERMIL",
    "DEFAULT_PENALTY_MIN_PERMIL",
    "PARAMETER_TYPE_ATTRS",
    "PERMIL_COLUMNS",
    "ExamBonus",
    "battle_bonus_score",
    "calculate_bonus",
    "component_permil",
    "f32",
    "interpolate_component",
    "normalize_bonus",
    "penalty_permil",
]
