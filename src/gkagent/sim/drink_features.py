"""M6 阶段2 ③（2026-11-26）：饮料 catalog 效果特征提取器——**只写不激活**。

背景：r14（EI policy）/ B2 学习叶子的现有饮料特征只读旧单效果字段
（``leaf_mlp.drink_stamina/focus/condition/score``，``effect_type`` 匹配），
M6 多效果段饮料（``DrinkSpec.effects``，effect_type="multi"）在这些特征上**全 0**。
本模块把 loadout 饮料（id 列表或 DrinkSpec 槽位）映射成**定长 catalog 效果向量**，
供后续重训接入。

**激活纪律（lead 排队，本模块不接线）**：
  * 不改 ``leaf_mlp.FEATURE_NAMES`` / ``policy_mlp`` / ``train_ei_policy``——
    改特征维度 = 重训门（分布漂移，旧权重失效），由 lead 排 r14 重训队列；
  * 本模块纯函数、无副作用、不被任何现有训练/推理路径 import（仅测试引用）。

设计（接入方案，详见 out/_drinks_r14_features_design.md，不提交）：
  * 向量 = 每个已实现 kind 的 ``Σ(value × 剩余次数)``（定长，kind 顺序 =
    ``DRINK_EFFECT_KINDS`` 去掉 unknown）+ 4 个汇总位（剩余槽位 / unknown 段数 /
    SAFE 槽位 / 总槽位）。unknown 段保守计段数不计值（不猜）；
  * 千分比/回合类 kind（score_buff/half_cost/…）原始值聚合，训练侧按 kind 归一
    （rescale 先例：r13 norm）；
  * B2 叶子接入：用本向量替换 leaf_mlp 的 5 个 legacy drink_* 位（维度变化 →
    重训门 + 离线 ratio/z 尾部双门）；r14 接入：obs 加本向量 + 动作头加 drink
    槽位（SAFE 划分约束候选，引擎侧全饮料保留——gnrpa-spec 实锤）；
  * 锁定前 worlds 保守口径：``drink_safe_slots`` 供投票特征，青汁 unknown 不喝。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from gkagent.sim.drinks import DRINK_EFFECT_KINDS, DrinkEffect, drink_is_safe
from gkagent.sim.lesson import DrinkSpec

__all__ = [
    "DRINK_FEATURE_KINDS",
    "DRINK_FEATURE_NAMES",
    "DRINK_FEATURE_DIM",
    "drink_feature_vector",
    "drink_features_from_ids",
]

#: 定长 kind 顺序（= catalog 分类顺序，去掉 unknown；新增 kind 自动扩维 → 重训门）。
DRINK_FEATURE_KINDS: tuple[str, ...] = tuple(
    kind for kind in DRINK_EFFECT_KINDS if kind != "unknown"
)

#: 特征名（kind 聚合位 + 4 汇总位）。
DRINK_FEATURE_NAMES: tuple[str, ...] = tuple(
    f"drink_kind_{kind}" for kind in DRINK_FEATURE_KINDS
) + (
    "drink_slots_remaining",
    "drink_unknown_segments",
    "drink_safe_slots",
    "drink_total_slots",
)

DRINK_FEATURE_DIM: int = len(DRINK_FEATURE_NAMES)


def drink_feature_vector(
    drinks: Sequence[DrinkSpec],
    drink_uses: Sequence[int] | None = None,
) -> tuple[float, ...]:
    """饮料槽位 → 定长效果向量（纯函数，剩余次数加权）。

    ``drink_uses`` 缺省按各槽 ``DrinkSpec.uses``（满库存）。每个已实现效果段按
    ``value × 剩余次数`` 累加到对应 kind 位；unknown 段只计段数（``×剩余次数``）
    进 ``drink_unknown_segments``（不猜值）。SAFE 槽位按 :func:`drink_is_safe`
    全段判定（含 unknown / 改牌区 / 再发动类 → 非 SAFE）。
    """
    kind_index = {kind: i for i, kind in enumerate(DRINK_FEATURE_KINDS)}
    vec = [0.0] * DRINK_FEATURE_DIM
    base = len(DRINK_FEATURE_KINDS)
    slots_remaining = 0.0
    unknown_segments = 0.0
    safe_slots = 0.0
    total_slots = 0.0
    for index, drink in enumerate(drinks):
        uses = (
            int(drink_uses[index])
            if drink_uses is not None and index < len(drink_uses)
            else int(drink.uses)
        )
        total_slots += float(drink.uses)
        if uses <= 0:
            continue
        slots_remaining += float(uses)
        effects: tuple[DrinkEffect, ...] = tuple(drink.all_effects)
        if drink_is_safe(effects):
            safe_slots += float(uses)
        for eff in effects:
            if eff.implemented and eff.kind in kind_index:
                vec[kind_index[eff.kind]] += float(eff.value) * uses
            elif not eff.implemented:
                unknown_segments += float(uses)
    vec[base + 0] = slots_remaining
    vec[base + 1] = unknown_segments
    vec[base + 2] = safe_slots
    vec[base + 3] = total_slots
    return tuple(vec)


def drink_features_from_ids(
    drink_ids: Iterable[str] | None,
    catalog=None,
) -> tuple[float, ...]:
    """loadout ``drink_ids`` → 效果向量（不去重，未知 id 不计入——显式上报口径
    见 ``drinks_db.resolve_drink_ids``；本函数只取已知槽位，未知 id 保守忽略）。"""
    from gkagent.data.drinks_db import resolve_drink_ids

    loadout = resolve_drink_ids(drink_ids, catalog)
    return drink_feature_vector(loadout.specs)
