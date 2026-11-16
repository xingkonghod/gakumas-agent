"""特征化出牌策略：value(s, a) = w · φ(s, a)，权重从模拟器里学。

取代固定优先级阶梯（`LessonPolicy` 里那套 if/else）。特征都从真机/模拟器都能拿到的
信息算出来，权重用进化在模拟器里搜（`scripts/evolve_policy.py`）。

设计原则：
- 每个特征都可解释、可单独关闭（权重 0）
- 没有"魔法阈值"——阈值等价于两个特征的权重比
- 支持 SKIP 作为动作：所有牌 value < 0 时跳过
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 特征名（顺序固定，权重向量按这个顺序）
FEATURES: tuple[str, ...] = (
    "score",  # 卡面分 / 100
    "cost",  # 体力消耗 / 10
    "score_per_cost",  # 分数/体力
    "is_buff",  # 是不是 buff 牌
    "buff_condition",  # 好调
    "buff_focus",  # 集中
    "buff_impression",  # 好印象
    "buff_block",  # 元气
    "buff_stance",  # 指針（温存/強气/全力）
    "turns_left",  # 剩余回合 / 10
    "stamina_ratio",  # 体力 / 上限
    "affordable",  # 体力够不够打
    "last_turn",  # 最后一回合
    "early_turn",  # 早期回合（≥3）
    "can_clear",  # 打完这张能否清 CLEAR
    "can_perfect",  # 打完这张能否到 PERFECT
    "clear_ratio",  # 当前分 / CLEAR 目标
    "perfect_gap",  # 距 PERFECT 还差多少 / 100
    "buff_count",  # 已有 buff 层数 / 10
    "deck_size",  # 牌库大小 / 20
)


@dataclass
class ScoredPolicy:
    """w·φ 打分策略。默认权重是一套可解释的先验，进化会改它们。"""

    weights: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        base = {name: 0.0 for name in FEATURES}
        base.update(
            {
                "score": 1.0,
                "cost": -0.3,
                "score_per_cost": 0.5,
                "is_buff": 1.2,
                "buff_condition": 2.0,
                "buff_focus": 2.5,
                "buff_impression": 1.5,
                "buff_block": 0.5,
                "buff_stance": 1.0,
                "turns_left": 0.2,
                "stamina_ratio": 0.3,
                "affordable": 5.0,
                "last_turn": 0.5,
                "early_turn": 0.8,
                "can_clear": 1.0,
                "can_perfect": 0.8,
                "clear_ratio": 0.5,
                "perfect_gap": -0.05,
                "buff_count": 0.3,
                "deck_size": 0.0,
            }
        )
        base.update(self.weights)
        self.weights = base

    def vector(self) -> list[float]:
        return [self.weights[name] for name in FEATURES]

    def set_vector(self, values: list[float]) -> None:
        self.weights = {name: float(value) for name, value in zip(FEATURES, values)}

    def score(self, feats: dict[str, float]) -> float:
        return sum(self.weights.get(name, 0.0) * feats.get(name, 0.0) for name in FEATURES)


def _buff_kind(text: str) -> dict[str, float]:
    """从卡的描述文本猜 buff 类型（中文/日文关键词）。"""
    out = {"buff_condition": 0.0, "buff_focus": 0.0, "buff_impression": 0.0, "buff_block": 0.0, "buff_stance": 0.0}
    t = text or ""
    if "好调" in t or "絕好調" in t or "绝好调" in t:
        out["buff_condition"] = 1.0
    if "集中" in t:
        out["buff_focus"] = 1.0
    if "好印象" in t:
        out["buff_impression"] = 1.0
    if "元气" in t or "元気" in t:
        out["buff_block"] = 1.0
    if any(k in t for k in ("温存", "強気", "强气", "全力")):
        out["buff_stance"] = 1.0
    return out


def extract(state: Any, card: Any, *, target_clear: int = 250, target_perfect: int = 500) -> dict[str, float]:
    """从（真机 LessonState / 模拟 LessonSim）和一张牌抽特征。字段缺失按 0 处理。"""
    score = float(getattr(card, "score", 0) or 0)
    cost = float(getattr(card, "cost", 0) or 0)
    text = str(getattr(card, "text", "") or "")
    turns = int(getattr(state, "turns_left", 0) or 0)
    stamina = float(getattr(state, "stamina", 0) or 0)
    stamina_max = float(getattr(state, "stamina_max", 0) or 0) or max(stamina, 1.0)
    cur_score = float(getattr(state, "score", 0) or 0)
    feats: dict[str, float] = {
        "score": score / 100.0,
        "cost": cost / 10.0,
        "score_per_cost": (score / cost / 10.0) if cost > 0 else score / 100.0,
        "is_buff": 1.0 if getattr(card, "buff", False) or score <= 0 else 0.0,
        "turns_left": turns / 10.0,
        "stamina_ratio": stamina / stamina_max,
        "affordable": 1.0 if cost <= stamina else 0.0,
        "last_turn": 1.0 if turns <= 1 else 0.0,
        "early_turn": 1.0 if turns >= 3 else 0.0,
        "can_clear": 1.0 if cur_score + score >= target_clear else 0.0,
        "can_perfect": 1.0 if cur_score + score >= target_perfect else 0.0,
        "clear_ratio": cur_score / max(target_clear, 1),
        "perfect_gap": max(target_perfect - cur_score, 0) / 100.0,
        "buff_count": float(getattr(getattr(state, "buffs", None), "focus", 0) or 0) / 10.0,
        "deck_size": float(len(getattr(state, "deck", []) or [])) / 20.0,
    }
    feats.update(_buff_kind(text))
    return feats


def decide(state: Any, cards: list[Any], policy: ScoredPolicy, *, target_clear: int = 250,
           target_perfect: int = 500, skip_margin: float = 0.0) -> int | None:
    """返回该打的手牌下标；None = SKIP。"""
    best_index: int | None = None
    best_value = skip_margin
    for index, card in enumerate(cards):
        feats = extract(state, card, target_clear=target_clear, target_perfect=target_perfect)
        if feats["affordable"] <= 0:
            continue
        value = policy.score(feats)
        if value > best_value:
            best_value = value
            best_index = index
    return best_index
