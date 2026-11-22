"""拟合值函数 V_leaf：用模拟器数据学出「剩余得分」的均值/方差。

替代 ``AnalyticLeafValue`` 的手写公式。解析式只覆盖集中/好印象/牌面三项；
这里用 35 维特征让 ridge 回归学出元气/好调剩余回合/指針/额外次数/抽牌等权重。

接口与 ``AnalyticLeafValue`` 完全一致（``predict`` / ``utility``），可直接互换。

用法::

    from gkagent.sim.v_leaf import LinearLeafValue, features, fit_ridge
    model = LinearLeafValue.load("data/knowledge/v_leaf.json")
    model.predict(state)   # -> (mu, sigma)
    model.utility(state)   # -> E[档位效用]
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from gkagent.sim.stance import Stance

FEATURE_NAMES: tuple[str, ...] = (
    # --- 状态层
    "turns_left",
    "total_turns",
    "turn_ratio",
    "plays_left",
    "stamina",
    "stamina_ratio",
    "vitality",
    "score",
    "score_over_clear",
    "gap_clear",
    "gap_perfect",
    "clear",
    # --- buff 层
    "focus",
    "condition_turns",
    "impression",
    "motivation",
    "extra_plays",
    "plays_used",
    "stance_save",
    "stance_strong",
    "stance_full",
    # --- 手牌聚合层
    "hand_count",
    "hand_mean_score",
    "hand_max_score",
    "hand_mean_cost",
    "hand_affordable",
    "hand_score_cards",
    "pool_mean_score",
    "pool_count",
    # --- 交互层
    "turns_x_focus",
    "turns_x_impression",
    "focus_x_affordable",
    "condition_x_max_score",
    "turns_x_stamina",
    "perfect_x_turns",
)

DIM = len(FEATURE_NAMES)


def _cards(state: Any) -> list[Any]:
    hand = list(getattr(state, "hand", ()) or ())
    deck = list(getattr(state, "deck", ()) or ())
    discard = list(getattr(state, "discard", ()) or ())
    return hand + deck + discard


def features(state: Any) -> np.ndarray:
    """把 ``ExpectState`` 转成固定维度特征向量（缺失字段按 0）。

    只认 ``ExpectState`` 的字段（含 ``play_limit`` / ``plays_used`` /
    ``perfect``）。``LessonSim`` 的字段名不同（``target_clear`` / ``buffs.focus``
    / ``plays_this_turn`` …），直接传进来会静默读成 0；训练采样必须先经
    ``expectimax.state_from_sim()`` 转换，再按叶子形态取特征
    （:func:`leaf_features`）。
    """
    turns = float(getattr(state, "turns_left", 0) or 0)
    total = float(getattr(state, "total_turns", 0) or 0)
    play_limit = float(getattr(state, "play_limit", 1) or 0)
    extra_plays = float(getattr(state, "extra_plays", 0) or 0)
    plays_used = float(getattr(state, "plays_used", 0) or 0)
    # 与 ExpectState.plays_left 同口径：extra_plays 也算可用次数，且不能为负
    plays_left = max(play_limit + extra_plays - plays_used, 0.0)
    stamina = float(getattr(state, "stamina", 0) or 0)
    stamina_max = float(getattr(state, "stamina_max", 0) or 0) or max(stamina, 1.0)
    vitality = float(getattr(state, "vitality", 0) or 0)
    score = float(getattr(state, "score", 0) or 0)
    clear = float(getattr(state, "clear", 0) or 0)
    perfect = float(getattr(state, "perfect", 0) or 0)
    focus = float(getattr(state, "focus", 0) or 0)
    condition = float(getattr(state, "condition_turns", 0) or 0)
    impression = float(getattr(state, "impression", 0) or 0)
    motivation = float(getattr(state, "motivation", 0) or 0)
    extra = float(getattr(state, "extra_plays", 0) or 0)
    stance = getattr(state, "stance", None)
    stance_name = ""
    if isinstance(stance, (tuple, list)) and stance:
        stance_name = str(stance[0] or "")

    hand = list(getattr(state, "hand", ()) or ())
    scores = [float(c.score) for c in hand if float(getattr(c, "score", 0) or 0) > 0]
    costs = [float(max(int(getattr(c, "cost", 0) or 0), 0)) for c in hand]
    affordable = sum(1 for c in hand if float(getattr(c, "cost", 0) or 0) <= stamina + vitality)
    pool = _cards(state)
    pool_scores = [float(c.score) for c in pool if float(getattr(c, "score", 0) or 0) > 0]

    vec = [
        turns,
        total,
        turns / total if total > 0 else 0.0,
        plays_left,
        stamina,
        stamina / stamina_max,
        vitality,
        score,
        score / clear if clear > 0 else 0.0,
        max(clear - score, 0.0),
        max(perfect - score, 0.0),
        clear,
        focus,
        condition,
        impression,
        motivation,
        extra,
        float(getattr(state, "plays_used", 0) or 0),
        1.0 if stance_name == Stance.SAVE else 0.0,
        1.0 if stance_name in (Stance.STRONG1, Stance.STRONG2, "strong") else 0.0,
        1.0 if stance_name == Stance.FULL else 0.0,
        float(len(hand)),
        float(np.mean(scores)) if scores else 0.0,
        float(max(scores)) if scores else 0.0,
        float(np.mean(costs)) if costs else 0.0,
        float(affordable),
        float(len(scores)),
        float(np.mean(pool_scores)) if pool_scores else 0.0,
        float(len(pool)),
        turns * focus,
        turns * impression,
        focus * affordable,
        condition * (max(scores) if scores else 0.0),
        turns * stamina,
        (1.0 if score >= perfect > 0 else 0.0) * turns,
    ]
    arr = np.asarray(vec, dtype=np.float64)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def leaf_features(state: Any) -> np.ndarray:
    """训练采样用：把「回合开始」快照转成搜索叶子形态，再取特征。

    ``Expectimax`` 的 ``_Search`` 只在回合末状态上调 ``utility``（``end_turn_state``
    已经把当前手牌移进弃牌堆、``hand=()``）。拟合脚本如果直接对回合开始的快照
    取特征，``hand_*`` 系列在训练时非零、推理时却恒为零，模型会学到两个分布。
    这里把手牌并进弃牌堆后取特征：牌的**总组成不变**（``pool_*`` 不变），
    手牌聚合归零，与叶子形态一致。

    只应在回合边界（刚抽完手牌、还没出牌）调用；``score`` 在两个时点相同，
    所以标签 ``最终分 - score`` 不需要额外换算。非 dataclass（例如 ``LessonSim``）
    直接报错，避免又静默退回失真的特征。
    """
    hand = tuple(getattr(state, "hand", ()) or ())
    if not hand:
        return features(state)
    discard = tuple(getattr(state, "discard", ()) or ())
    try:
        leaf_state = replace(state, hand=(), discard=discard + hand)
    except TypeError as exc:  # pragma: no cover - 调用方错误
        raise TypeError(
            "leaf_features 需要 ExpectState（或字段同形的 dataclass）；"
            "LessonSim 请先经 expectimax.state_from_sim() 转换"
        ) from exc
    return features(leaf_state)


def fit_ridge(samples: list[tuple[np.ndarray, float]], ridge: float = 1.0) -> tuple[np.ndarray, float, float]:
    """ridge 最小二乘：返回 (权重, σ, r²)。样本是 (特征, 剩余得分)。

    特征先按列标准化再加截距列求解；返回前把权重还原到原始尺度::

        y = Σ w_j·x_j + b,  w_j = w_scaled_j / σ_j,
                            b = b_scaled - Σ w_j·mean_j

    返回的权重数组是 ``[w_0, ..., w_{DIM-1}, 截距]``，与 ``LinearLeafValue``
    的 ``weights`` 一致。
    """
    if not samples:
        return np.zeros(DIM + 1), 60.0, 0.0
    x = np.vstack([s[0] for s in samples])
    y = np.asarray([s[1] for s in samples], dtype=np.float64)
    # 标准化，避免量纲差异（集中是 0-20、分数是 0-2000）
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std < 1e-6] = 1.0
    xs = (x - mean) / std
    xs = np.hstack([xs, np.ones((xs.shape[0], 1))])
    # 标准 ridge 不惩罚截距：只给特征列加岭；否则样本少时截距会被系统性压小
    penalty = ridge * np.eye(xs.shape[1])
    penalty[-1, -1] = 0.0
    gram = xs.T @ xs + penalty
    weights_scaled = np.linalg.solve(gram, xs.T @ y)
    pred = xs @ weights_scaled
    resid = y - pred
    sigma = float(np.sqrt(np.mean(resid**2)))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2 = 1.0 - float(np.sum(resid**2)) / ss_tot
    weights = weights_scaled[:-1] / std
    intercept = float(weights_scaled[-1] - np.sum(weights * mean))
    return np.append(weights, intercept), max(sigma, 1.0), r2


@dataclass
class LinearLeafValue:
    """线性拟合的 V_leaf（接口与 AnalyticLeafValue 一致）。"""

    weights: np.ndarray
    sigma: float = 60.0
    a_clear: float = 1.0
    a_perfect: float = 1.0
    meta: dict = field(default_factory=dict)

    def predict(self, state: Any) -> tuple[float, float]:
        """返回未来得分的 (μ, σ)；回合用完时 σ=0。

        σ 的边界与 ``AnalyticLeafValue`` 一致：显式构造 ``sigma=0`` 时返回 0，
        让 ``utility`` 走硬阈值分支（不再强行夹到 1e-6）。
        """
        if float(getattr(state, "turns_left", 0) or 0) <= 0:
            return 0.0, 0.0
        vec = np.append(features(state), 1.0)
        mu = float(vec @ self.weights)
        if not math.isfinite(mu):
            mu = 0.0
        return max(mu, 0.0), max(float(self.sigma), 0.0)

    def utility(self, state: Any) -> float:
        """E[档位效用] = a·P(score ≥ CLEAR) + b·P(score ≥ PERFECT)。"""
        clear = float(getattr(state, "clear", 0) or 0)
        if clear <= 0:
            return 0.0
        mu, sigma = self.predict(state)
        projected = float(getattr(state, "score", 0) or 0) + mu
        perfect = float(getattr(state, "perfect", 0) or 0)
        if sigma <= 0:
            return self.a_clear * (1.0 if projected >= clear else 0.0) + self.a_perfect * (
                1.0 if projected >= perfect else 0.0
            )
        sqrt2 = math.sqrt(2.0)

        def prob(threshold: float) -> float:
            return 0.5 * (1.0 + math.erf((projected - threshold) / (sigma * sqrt2)))

        return self.a_clear * prob(clear) + self.a_perfect * prob(perfect)

    # ---------------------------------------------------------------- 存取
    def save(self, path: str | Path) -> None:
        payload = {
            "version": 1,
            "feature_names": list(FEATURE_NAMES),
            "weights": [float(w) for w in self.weights],
            "sigma": self.sigma,
            "a_clear": self.a_clear,
            "a_perfect": self.a_perfect,
            "meta": self.meta,
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> LinearLeafValue:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        names = tuple(doc.get("feature_names") or ())
        if names and names != FEATURE_NAMES:
            raise ValueError("v_leaf.json 的特征名与当前代码不一致，请重新拟合")
        weights = np.asarray(doc["weights"], dtype=np.float64)
        if weights.shape[0] != DIM + 1:
            raise ValueError(f"权重维度 {weights.shape[0]} != {DIM + 1}")

        # 用 is None 判断而不是 ``or``：sigma/a_clear/a_perfect 允许显式为 0
        def _num(key: str, default: float) -> float:
            value = doc.get(key)
            return default if value is None else float(value)

        return cls(
            weights=weights,
            sigma=_num("sigma", 60.0),
            a_clear=_num("a_clear", 1.0),
            a_perfect=_num("a_perfect", 1.0),
            meta=doc.get("meta") or {},
        )


@dataclass
class EnsembleLeafValue:
    """集成叶子：把解析式和拟合式的档位效用取加权平均。

    两条路径的偏差方向不同——解析式在已知机制上精确但漏项，拟合式覆盖广但方差大，
    平均后通常能同时拿到较高均值与较低方差。
    """

    primary: Any
    secondary: Any
    weight: float = 0.5

    def predict(self, state: Any) -> tuple[float, float]:
        mu1, sigma1 = self.primary.predict(state)
        mu2, sigma2 = self.secondary.predict(state)
        w = float(min(max(self.weight, 0.0), 1.0))
        mu = w * mu1 + (1.0 - w) * mu2
        sigma = math.sqrt((w * sigma1) ** 2 + ((1.0 - w) * sigma2) ** 2)
        return max(mu, 0.0), max(sigma, 1e-6)

    def utility(self, state: Any) -> float:
        w = float(min(max(self.weight, 0.0), 1.0))
        return w * self.primary.utility(state) + (1.0 - w) * self.secondary.utility(state)
