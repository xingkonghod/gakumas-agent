"""B2：全知数据训练的结构化特征 MLP 叶子价值（V_leaf）。

背景（见 docs/EXPECTIMAX.md「T4 修正」「拟合 V_leaf 的实验结果」）：

* 解析式 ``AnalyticLeafValue`` 的 μ 是手写 35 维代理（playable_count × mean_score +
  focus + 好调 + 好印象年金），B1 修正评测执行器后 beam 已显著强于 within
  （164.0 / 165.5 vs 143.1），叶子估值仍是进一步上限。
* 历史三次学习 V_leaf 失败（r²≈0.8 但策略更差）的根因：贪心轨迹标签、
  ``ExpectState`` 与 ``LessonSim`` 合法性不同源、35 维线性特征塌缩到 turns_left。

本模块实现 B2 的第一方案：**用搜索策略自己跑出来的「叶子状态 → 后续实际得分」
样本**训练小 MLP，直接实现 ``LeafValue`` 协议（``predict`` / ``utility``），
可替换进 ``expectimax_with_stats`` / ``search_beam``，再用修正后的配对 harness
（``scripts/eval_b2.py``）评估。与旧 ``sim/v_leaf.py`` 的关键区别：

1. 标签 = 搜索策略（不是贪心）真实后续得分（on-policy return），
2. 样本取在**叶子状态分布**上——``end_turn_state`` 之后手牌已并入弃牌堆，
   与搜索内部 ``_Search.leaf`` 的输入同分布，
3. 特征结构化：剩余牌库/弃牌堆拆分、buff 计时、指針状态、饮料/P 道具、
   牌库效果聚合与交互项（而不是 35 维裸线性），
4. 模型 2 隐层 MLP；σ 用残差头（MLP 第二列）由高斯 NLL 拟合，接口与解析式一致。

叶子输入约定：``ExpectState``（手牌通常为空，即 ``end_turn_state`` 之后的形态）。
对带手牌的输入会先把它们并入弃牌堆（与 ``v_leaf.leaf_features`` 同口径），
但推理时搜索只会传叶子形态。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from gkagent.sim.stance import Stance

FORMAT = "gkagent.mlp_leaf.v1"

# 单张牌的静态数值画像（``CardSpec`` 字段顺序固定，缓存按牌对象哈希）。
_P_SCORE = 0
_P_COST = 1
_P_VITALITY = 2
_P_CONDITION = 3
_P_FOCUS = 4
_P_MOTIVATION = 5
_P_IMPRESSION = 6
_P_DRAW = 7
_P_IMPRESSION_SCALE = 8
_P_PRESERVATION = 9
_P_FULL_POWER_POINT = 10
_P_EXTRA_PLAY = 11
_P_BLOCK_SCALE = 12
_P_PARAMETER_BUFF = 13
_P_STRONG_LEVEL = 14
_P_STAMINA_RECOVER = 15
_P_FULL_POWER_SCALE = 16
_P_REVIEW_MULTIPLE = 17
_P_CONDITION_ADDITIVE = 18
_P_FULL_POWER_LESSON = 19
_P_GROW_SCORE = 20
_P_ENCORE = 21
_P_ONCE = 22
_PROFILE_DIM = 23


@lru_cache(maxsize=8192)
def _card_profile(card: Any) -> tuple[float, ...]:
    """把一张 ``CardSpec`` 摊平成固定顺序的数值向量（按牌对象缓存一次）。"""

    def num(name: str) -> float:
        return float(getattr(card, name, 0) or 0)

    return (
        num("score"),
        num("cost"),
        num("vitality"),
        num("condition"),
        num("focus"),
        num("motivation"),
        num("impression"),
        num("draw"),
        num("impression_scale"),
        num("preservation"),
        num("full_power_point"),
        num("extra_play"),
        num("block_scale"),
        num("parameter_buff"),
        num("strong_level"),
        num("stamina_recover"),
        num("full_power_scale"),
        num("review_multiple"),
        num("condition_additive"),
        num("full_power_lesson_multiple"),
        num("grow_score"),
        1.0 if getattr(card, "encore", False) else 0.0,
        1.0 if getattr(card, "once", False) else 0.0,
    )


def _profiles(cards: Any) -> np.ndarray:
    if not cards:
        return np.zeros((0, _PROFILE_DIM), dtype=np.float64)
    return np.asarray([_card_profile(card) for card in cards], dtype=np.float64)


FEATURE_NAMES: tuple[str, ...] = (
    # ---- 状态 / 分数 / 体力（回合末形态：手牌已进弃牌堆） ----
    "turns_left",
    "total_turns",
    "turn_ratio",
    "current_turn",
    "plays_left",
    "play_limit",
    "stamina",
    "stamina_max",
    "stamina_ratio",
    "effective_stamina",
    "vitality",
    "motivation",
    "min_cost",
    "affordable_any",
    "score",
    "clear",
    "perfect",
    "score_over_clear",
    "score_over_perfect",
    "gap_clear_ratio",
    "gap_perfect_ratio",
    "cards_played_total",
    # ---- buff ----
    "focus",
    "condition_turns",
    "perfect_condition_turns",
    "poor_condition_turns",
    "impression",
    "condition_additive",
    "condition_additive_turns",
    "review_multiple",
    "review_multiple_turns",
    "full_power_lesson_multiple",
    "full_power_lesson_multiple_turns",
    "metamorphosis_performance",
    "metamorphosis_preparation",
    "parameter_buff",
    "save_cards_used",
    # ---- 指針（非凡） ----
    "stance_normal",
    "stance_save",
    "stance_strong",
    "stance_full",
    "strong_level",
    "save_level",
    "full_power_point",
    # ---- 饮料（剩余次数 / 效果计数） ----
    "drink_uses_remaining",
    "drink_stamina",
    "drink_focus",
    "drink_condition",
    "drink_score",
    # ---- P 道具 ----
    "p_item_count",
    "p_item_uses_total",
    # ---- 剩余牌库 / 弃牌堆拆分（重洗时机与后续抽牌质量） ----
    "deck_count",
    "discard_count",
    "excluded_count",
    "pool_count",
    "deck_ratio",
    "deck_affordable_count",
    "deck_score_mean",
    "deck_score_max",
    "deck_score_sum",
    "deck_cost_mean",
    "deck_cost_min",
    "deck_expensive_count",
    "deck_score_count",
    # ---- 牌库效果聚合（剩余可抽到的机制牌） ----
    "deck_draw_count",
    "deck_extra_play_count",
    "deck_focus_count",
    "deck_condition_count",
    "deck_impression_count",
    "deck_vitality_count",
    "deck_impression_scale_count",
    "deck_block_scale_count",
    "deck_preservation_count",
    "deck_full_power_count",
    "deck_encore_count",
    "deck_once_count",
    "deck_review_multiple_count",
    "deck_parameter_buff_count",
    "deck_strong_count",
    "deck_stamina_recover_count",
    "deck_draw_sum",
    "deck_focus_sum",
    "deck_condition_sum",
    "deck_impression_sum",
    "deck_vitality_sum",
    # ---- 弃牌堆效果聚合（重洗后才会回来） ----
    "discard_draw_count",
    "discard_extra_play_count",
    "discard_focus_count",
    "discard_condition_count",
    "discard_impression_count",
    "discard_vitality_count",
    "discard_once_count",
    # ---- 交互项 ----
    "turns_x_focus",
    "turns_x_impression",
    "turns_x_condition",
    "turns_x_playable_slots",
    "condition_x_deck_score_mean",
    "focus_x_deck_score_count",
    "stamina_x_focus",
    "gap_clear_ratio_x_turns",
    "gap_perfect_ratio_x_turns",
    "full_power_x_turns",
    "vitality_x_turns",
    "impression_x_turns_left",
)

DIM = len(FEATURE_NAMES)

_EFFECT_COUNT_FEATURES = (
    (_P_DRAW, "deck_draw_count"),
    (_P_EXTRA_PLAY, "deck_extra_play_count"),
    (_P_FOCUS, "deck_focus_count"),
    (_P_CONDITION, "deck_condition_count"),
    (_P_IMPRESSION, "deck_impression_count"),
    (_P_VITALITY, "deck_vitality_count"),
    (_P_IMPRESSION_SCALE, "deck_impression_scale_count"),
    (_P_BLOCK_SCALE, "deck_block_scale_count"),
    (_P_PRESERVATION, "deck_preservation_count"),
    (_P_FULL_POWER_POINT, "deck_full_power_count"),
    (_P_ENCORE, "deck_encore_count"),
    (_P_ONCE, "deck_once_count"),
    (_P_REVIEW_MULTIPLE, "deck_review_multiple_count"),
    (_P_PARAMETER_BUFF, "deck_parameter_buff_count"),
    (_P_STRONG_LEVEL, "deck_strong_count"),
    (_P_STAMINA_RECOVER, "deck_stamina_recover_count"),
)


def _num(value: Any) -> float:
    try:
        result = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _normalize_leaf(state: Any) -> Any:
    """叶子状态规范化：带手牌时并入弃牌堆（搜索只会传叶子形态，这是兜底）。"""
    hand = tuple(getattr(state, "hand", ()) or ())
    if not hand:
        return state
    discard = tuple(getattr(state, "discard", ()) or ())
    try:
        return replace(state, hand=(), discard=discard + hand)
    except TypeError as exc:  # pragma: no cover - 调用方错误
        raise TypeError(
            "leaf_mlp.features 需要 ExpectState（dataclass）；LessonSim 请先经 "
            "expectimax.state_from_sim() 转换"
        ) from exc


def features(state: Any) -> np.ndarray:
    """把叶子形态 ``ExpectState`` 转成固定维特征向量（纯函数、无全局状态）。"""
    state = _normalize_leaf(state)
    turns = _num(getattr(state, "turns_left", 0))
    total = _num(getattr(state, "total_turns", 0))
    stamina = _num(getattr(state, "stamina", 0))
    stamina_max = _num(getattr(state, "stamina_max", 0)) or max(stamina, 1.0)
    vitality = _num(getattr(state, "vitality", 0))
    effective = stamina + vitality
    score = _num(getattr(state, "score", 0))
    clear = _num(getattr(state, "clear", 0))
    perfect = _num(getattr(state, "perfect", 0))
    min_cost = _num(getattr(state, "min_cost", 0))
    focus = _num(getattr(state, "focus", 0))
    impression = _num(getattr(state, "impression", 0))
    condition = _num(getattr(state, "condition_turns", 0))
    play_limit = _num(getattr(state, "play_limit", 0))
    plays_left = max(play_limit + _num(getattr(state, "extra_plays", 0)) - _num(getattr(state, "plays_used", 0)), 0.0)

    deck = list(getattr(state, "deck", ()) or ())
    discard = list(getattr(state, "discard", ()) or ())
    excluded = list(getattr(state, "excluded", ()) or ())
    deck_p = _profiles(deck)
    discard_p = _profiles(discard)

    def col_cards(mat: np.ndarray, column: int) -> np.ndarray:
        return mat[:, column] if mat.shape[0] else np.zeros(0)

    scores = col_cards(deck_p, _P_SCORE)
    costs = col_cards(deck_p, _P_COST)

    def deck_sum(column: int) -> float:
        return float(deck_p[:, column].sum()) if deck_p.shape[0] else 0.0

    deck_count = float(len(deck))
    discard_count = float(len(discard))
    excluded_count = float(len(excluded))

    drinks = tuple(getattr(state, "drinks", ()) or ())
    drink_uses = tuple(getattr(state, "drink_uses", ()) or ())
    drink_remaining = 0.0
    drink_effects = {"stamina": 0.0, "focus": 0.0, "condition": 0.0, "score": 0.0}
    for index, drink in enumerate(drinks):
        uses = _num(drink_uses[index]) if index < len(drink_uses) else 0.0
        if uses <= 0:
            continue
        drink_remaining += uses
        effect = str(getattr(drink, "effect_type", ""))
        if effect in drink_effects:
            drink_effects[effect] += uses

    stance = getattr(state, "stance", None)
    stance_name = str(stance[0] or "") if isinstance(stance, (tuple, list)) and stance else ""
    strong_level = _num(stance[1]) if isinstance(stance, (tuple, list)) and len(stance) > 1 else 0.0
    save_level = _num(stance[2]) if isinstance(stance, (tuple, list)) and len(stance) > 2 else 0.0
    full_power_point = _num(stance[3]) if isinstance(stance, (tuple, list)) and len(stance) > 3 else 0.0

    p_items = tuple(getattr(state, "p_items", ()) or ())
    p_item_uses = tuple(getattr(state, "p_item_uses", ()) or ())

    def effect_count(table: np.ndarray, column: int) -> float:
        return float(np.count_nonzero(table[:, column] > 0)) if table.shape[0] else 0.0

    def effect_sum(table: np.ndarray, column: int) -> float:
        return float(table[:, column].sum()) if table.shape[0] else 0.0

    deck_score_count = effect_count(deck_p, _P_SCORE)
    deck_affordable = (
        float(np.count_nonzero(deck_p[:, _P_COST] <= effective)) if deck_p.shape[0] else 0.0
    )
    deck_expensive = deck_count - deck_affordable
    deck_score_mean = float(scores.mean()) if scores.size else 0.0
    deck_score_max = float(scores.max()) if scores.size else 0.0
    deck_cost_mean = float(costs.mean()) if costs.size else 0.0
    deck_cost_min = float(costs.min()) if costs.size else 0.0

    def count_of(table: np.ndarray, column: int) -> float:
        return float(np.count_nonzero(table[:, column] > 0)) if table.shape[0] else 0.0

    def discard_count_of(column: int) -> float:
        return count_of(discard_p, column)

    gap_clear_ratio = (clear - score) / clear if clear > 0 else 0.0
    gap_perfect_ratio = (perfect - score) / perfect if perfect > 0 else 0.0
    turn_ratio = turns / total if total > 0 else 0.0

    values = [
        turns,
        total,
        turn_ratio,
        _num(getattr(state, "total_turns", 0)) - turns + 1 if total > 0 else 0.0,
        plays_left,
        play_limit,
        stamina,
        stamina_max,
        stamina / stamina_max if stamina_max > 0 else 0.0,
        effective,
        vitality,
        _num(getattr(state, "motivation", 0)),
        min_cost,
        1.0 if effective >= min_cost else 0.0,
        score,
        clear,
        perfect,
        score / clear if clear > 0 else 0.0,
        score / perfect if perfect > 0 else 0.0,
        gap_clear_ratio,
        gap_perfect_ratio,
        _num(getattr(state, "cards_played_total", 0)),
        # buff
        focus,
        condition,
        _num(getattr(state, "perfect_condition_turns", 0)),
        _num(getattr(state, "poor_condition_turns", 0)),
        impression,
        _num(getattr(state, "condition_additive", 0)),
        _num(getattr(state, "condition_additive_turns", 0)),
        _num(getattr(state, "review_multiple", 0)),
        _num(getattr(state, "review_multiple_turns", 0)),
        _num(getattr(state, "full_power_lesson_multiple", 0)),
        _num(getattr(state, "full_power_lesson_multiple_turns", 0)),
        1.0 if str(getattr(state, "metamorphosis", "")) == "performance" else 0.0,
        1.0 if str(getattr(state, "metamorphosis", "")) == "preparation" else 0.0,
        _num(getattr(state, "parameter_buff", 0)),
        _num(getattr(state, "save_cards_used", 0)),
        # stance
        1.0 if stance_name == Stance.NORMAL else 0.0,
        1.0 if stance_name == Stance.SAVE else 0.0,
        1.0 if stance_name in (Stance.STRONG1, Stance.STRONG2) else 0.0,
        1.0 if stance_name == Stance.FULL else 0.0,
        strong_level,
        save_level,
        full_power_point,
        # drinks
        drink_remaining,
        drink_effects["stamina"],
        drink_effects["focus"],
        drink_effects["condition"],
        drink_effects["score"],
        # p items
        float(len(p_items)),
        float(sum(_num(uses) for _, uses in p_item_uses)),
        # deck / discard split
        deck_count,
        discard_count,
        excluded_count,
        deck_count + discard_count + excluded_count,
        deck_count / (deck_count + discard_count) if deck_count + discard_count > 0 else 0.0,
        deck_affordable,
        deck_score_mean,
        deck_score_max,
        float(scores[scores > 0].sum()) if scores.size else 0.0,
        deck_cost_mean,
        deck_cost_min,
        deck_expensive,
        deck_score_count,
        # deck effect aggregates
        *[effect_count(deck_p, column) for column, _ in _EFFECT_COUNT_FEATURES],
        deck_sum(_P_DRAW),
        deck_sum(_P_FOCUS),
        deck_sum(_P_CONDITION),
        deck_sum(_P_IMPRESSION),
        deck_sum(_P_VITALITY),
        # discard effect aggregates
        discard_count_of(_P_DRAW),
        discard_count_of(_P_EXTRA_PLAY),
        discard_count_of(_P_FOCUS),
        discard_count_of(_P_CONDITION),
        discard_count_of(_P_IMPRESSION),
        discard_count_of(_P_VITALITY),
        discard_count_of(_P_ONCE),
        # interactions
        turns * focus,
        turns * impression,
        turns * condition,
        turns * play_limit,
        condition * deck_score_mean,
        focus * deck_score_count,
        stamina * focus,
        gap_clear_ratio * turns,
        gap_perfect_ratio * turns,
        full_power_point * turns,
        vitality * turns,
        impression * turns,
    ]
    vector = np.asarray(values, dtype=np.float64)
    return np.nan_to_num(vector, nan=0.0, posinf=0.0, neginf=0.0)


def _relu(value: np.ndarray) -> np.ndarray:
    return np.maximum(value, 0.0)


def _phi(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _sigmoid_np(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-min(max(value, -60.0), 60.0)))


@dataclass
class MLPLeafValue:
    """结构化特征 MLP 叶子（实现 ``expectimax.LeafValue`` 协议）。"""

    mean: np.ndarray
    scale: np.ndarray
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    mu_w: np.ndarray
    mu_b: np.ndarray
    sig_w: np.ndarray
    sig_b: np.ndarray
    sigma: float = 60.0
    use_sigma_head: bool = True
    # 评测期 σ 缩放（1=用数据学到的 σ；>1 = 更保守/更平滑的档位概率）。
    sigma_scale: float = 1.0
    # 可选：直接预测档位概率（P(CLEAR)/P(PERFECT)）的 logistic 头。
    # 存在时 ``utility`` 用它们（与搜索目标同口径），不再走高斯档位公式。
    p_clear_w: np.ndarray | None = None
    p_clear_b: np.ndarray | None = None
    p_perfect_w: np.ndarray | None = None
    p_perfect_b: np.ndarray | None = None
    a_clear: float = 1.0
    a_perfect: float = 1.0
    score_tiebreak: float = 0.0
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ 推理
    def predict_vector(
        self, vector: np.ndarray, *, standardized: bool = False
    ) -> tuple[float, float]:
        """直接对特征向量前向（训练/诊断用；推理请用 ``predict(state)``）。"""
        x = np.asarray(vector, dtype=np.float64)
        if not standardized:
            x = (x - self.mean) / self.scale
        h1 = _relu(x @ self.w1 + self.b1)
        h2 = _relu(h1 @ self.w2 + self.b2)
        mu = float((h2 @ self.mu_w + self.mu_b)[0])
        if not math.isfinite(mu):
            mu = 0.0
        sigma = float(self.sigma)
        if self.use_sigma_head:
            raw = float((h2 @ self.sig_w + self.sig_b)[0])
            sigma = math.exp(min(max(raw, math.log(1.0)), math.log(2000.0)))
        sigma *= max(float(self.sigma_scale), 1e-9)
        return max(mu, 0.0), max(sigma, 0.0)

    def predict(self, state: Any) -> tuple[float, float]:
        """返回未来得分的 ``(μ, σ)``；回合用完时 ``σ=0``（硬档位，与解析式一致）。"""
        if _num(getattr(state, "turns_left", 0)) <= 0:
            return 0.0, 0.0
        return self.predict_vector(features(state))

    def _tiebreak_bonus(self, projected: float, state: Any) -> float:
        if self.score_tiebreak <= 0.0:
            return 0.0
        scale = _num(getattr(state, "perfect", 0)) or _num(getattr(state, "clear", 0))
        if scale <= 0.0:
            return 0.0
        return float(self.score_tiebreak) * projected / scale

    def utility(self, state: Any) -> float:
        """E[档位效用] = a·P(score ≥ CLEAR) + b·P(score ≥ PERFECT)（与解析式同式）。

        有 logistic 档位头（``p_clear_*``/``p_perfect_*``）时直接用它们给出的
        概率；否则用 ``(μ, σ)`` 的高斯档位公式（与解析式一致）。
        """
        clear = _num(getattr(state, "clear", 0))
        if clear <= 0:
            return 0.0
        mu, sigma = self.predict(state)
        projected = _num(getattr(state, "score", 0)) + mu
        perfect = _num(getattr(state, "perfect", 0))
        if self.p_clear_w is not None and self.p_perfect_w is not None:
            x = (features(state) - self.mean) / self.scale
            h2 = _relu(_relu(x @ self.w1 + self.b1) @ self.w2 + self.b2)
            p_clear = _sigmoid_np(float((h2 @ self.p_clear_w + self.p_clear_b)[0]))
            p_perfect = _sigmoid_np(float((h2 @ self.p_perfect_w + self.p_perfect_b)[0]))
            base = self.a_clear * p_clear + self.a_perfect * p_perfect
            return base + self._tiebreak_bonus(projected, state)
        if sigma <= 0:
            base = self.a_clear * (1.0 if projected >= clear else 0.0) + (
                self.a_perfect * (1.0 if projected >= perfect else 0.0)
            )
            return base + self._tiebreak_bonus(projected, state)
        base = self.a_clear * _phi((mu - (clear - _num(getattr(state, "score", 0)))) / sigma)
        base += self.a_perfect * _phi(
            (mu - (perfect - _num(getattr(state, "score", 0)))) / sigma
        )
        return base + self._tiebreak_bonus(projected, state)

    # ------------------------------------------------------------------ 存取
    def to_payload(self) -> dict:
        return {
            "format": FORMAT,
            "feature_names": list(FEATURE_NAMES),
            "hidden": [int(self.w1.shape[1]), int(self.w2.shape[1])],
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "w1": self.w1.tolist(),
            "b1": self.b1.tolist(),
            "w2": self.w2.tolist(),
            "b2": self.b2.tolist(),
            "mu_w": self.mu_w.tolist(),
            "mu_b": self.mu_b.tolist(),
            "sig_w": self.sig_w.tolist(),
            "sig_b": self.sig_b.tolist(),
            "sigma": self.sigma,
            "sigma_scale": self.sigma_scale,
            "use_sigma_head": self.use_sigma_head,
            "a_clear": self.a_clear,
            "a_perfect": self.a_perfect,
            "score_tiebreak": self.score_tiebreak,
            "p_clear_w": None if self.p_clear_w is None else self.p_clear_w.tolist(),
            "p_clear_b": None if self.p_clear_b is None else self.p_clear_b.tolist(),
            "p_perfect_w": None if self.p_perfect_w is None else self.p_perfect_w.tolist(),
            "p_perfect_b": None if self.p_perfect_b is None else self.p_perfect_b.tolist(),
            "meta": self.meta,
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_payload(), ensure_ascii=False), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> MLPLeafValue:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if doc.get("format") != FORMAT:
            raise ValueError(f"unsupported model format: {doc.get('format')!r}")
        names = tuple(doc.get("feature_names") or ())
        if names != FEATURE_NAMES:
            raise ValueError("leaf_mlp 特征名与当前代码不一致，请重新训练")
        arrays = {
            key: np.asarray(doc[key], dtype=np.float64)
            for key in ("mean", "scale", "w1", "b1", "w2", "b2", "mu_w", "mu_b")
        }
        sig_w = np.asarray(doc.get("sig_w") or [0.0] * arrays["w2"].shape[1], dtype=np.float64)
        sig_b = np.asarray(doc.get("sig_b") or [0.0], dtype=np.float64)

        def _head(key_w: str, key_b: str) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
            if doc.get(key_w) is None or doc.get(key_b) is None:
                return None, None
            return (
                np.asarray(doc[key_w], dtype=np.float64),
                np.asarray(doc[key_b], dtype=np.float64),
            )

        p_clear_w, p_clear_b = _head("p_clear_w", "p_clear_b")
        p_perfect_w, p_perfect_b = _head("p_perfect_w", "p_perfect_b")
        if arrays["mean"].shape != (DIM,):
            raise ValueError(f"mean 维度 {arrays['mean'].shape} != ({DIM},)")
        if arrays["w1"].shape[0] != DIM:
            raise ValueError("w1 输入维度与当前特征不一致")
        return cls(
            mean=arrays["mean"],
            scale=arrays["scale"],
            w1=arrays["w1"],
            b1=arrays["b1"],
            w2=arrays["w2"],
            b2=arrays["b2"],
            mu_w=arrays["mu_w"],
            mu_b=arrays["mu_b"],
            sig_w=sig_w,
            sig_b=sig_b,
            sigma=float(doc.get("sigma") or 60.0),
            sigma_scale=float(doc.get("sigma_scale") or 1.0),
            use_sigma_head=bool(doc.get("use_sigma_head", True)),
            p_clear_w=p_clear_w,
            p_clear_b=p_clear_b,
            p_perfect_w=p_perfect_w,
            p_perfect_b=p_perfect_b,
            a_clear=float(doc.get("a_clear") or 1.0),
            a_perfect=float(doc.get("a_perfect") or 1.0),
            score_tiebreak=float(doc.get("score_tiebreak") or 0.0),
            meta=dict(doc.get("meta") or {}),
        )


class _Adam:
    """最小 Adam 优化器（numpy）：参数是列表引用，原地更新。"""

    def __init__(self, params: list[np.ndarray], lr: float) -> None:
        self.params = params
        self.lr = float(lr)
        self.m = [np.zeros_like(p) for p in params]
        self.v = [np.zeros_like(p) for p in params]
        self.t = 0

    def step(self, grads: list[np.ndarray], *, l2: float = 0.0) -> None:
        self.t += 1
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        for param, grad, m, v in zip(self.params, grads, self.m, self.v):
            if l2:
                grad = grad + l2 * param
            m *= beta1
            m += (1.0 - beta1) * grad
            v *= beta2
            v += (1.0 - beta2) * (grad * grad)
            m_hat = m / (1.0 - beta1**self.t)
            v_hat = v / (1.0 - beta2**self.t)
            param -= self.lr * m_hat / (np.sqrt(v_hat) + eps)


def train_mlp(
    X: np.ndarray,
    y: np.ndarray,
    *,
    hidden: tuple[int, int] = (64, 32),
    epochs: int = 400,
    lr: float = 1e-3,
    l2: float = 1e-4,
    seed: int = 0,
    sigma_epochs: int = 300,
    sigma_lr: float = 5e-3,
) -> tuple[MLPLeafValue, dict]:
    """用 MSE 训练 μ 头（Adam 全批量），再用高斯 NLL 拟合 σ 头。

    返回 ``(model, history)``；``history`` 里带训练/最终损失与 μ 残差统计。
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if X.ndim != 2 or X.shape[0] == 0:
        raise ValueError("X 必须是 (n, DIM) 的非空矩阵")
    if X.shape[1] != DIM:
        raise ValueError(f"特征维度 {X.shape[1]} != {DIM}")
    mean = X.mean(axis=0)
    scale = X.std(axis=0)
    scale[scale < 1e-8] = 1.0
    Xs = (X - mean) / scale
    rng = np.random.default_rng(seed)
    hidden1, hidden2 = hidden
    w1 = rng.normal(0.0, math.sqrt(2.0 / DIM), size=(DIM, hidden1))
    b1 = np.zeros(hidden1)
    w2 = rng.normal(0.0, math.sqrt(2.0 / hidden1), size=(hidden1, hidden2))
    b2 = np.zeros(hidden2)
    mu_w = rng.normal(0.0, math.sqrt(1.0 / hidden2), size=(hidden2, 1))
    mu_b = np.zeros(1)
    sigma = float(max(y.std(), 1.0))
    sig_w = np.zeros((hidden2, 1))
    sig_b = np.asarray([math.log(sigma)])

    params = [w1, b1, w2, b2, mu_w, mu_b]
    adam = _Adam(params, lr)
    for _epoch in range(max(int(epochs), 1)):
        z1 = Xs @ w1 + b1
        h1 = _relu(z1)
        z2 = h1 @ w2 + b2
        h2 = _relu(z2)
        mu = (h2 @ mu_w + mu_b).ravel()
        diff = mu - y
        scale_factor = 2.0 / X.shape[0]
        dmu_w = h2.T @ diff.reshape(-1, 1) * scale_factor
        dmu_b = np.asarray([diff.mean() * 2.0])
        dh2 = diff.reshape(-1, 1) @ mu_w.T * scale_factor
        dz2 = dh2 * (z2 > 0)
        dw2 = h1.T @ dz2
        db2 = dz2.sum(axis=0)
        dh1 = dz2 @ w2.T
        dz1 = dh1 * (z1 > 0)
        dw1 = Xs.T @ dz1
        db1 = dz1.sum(axis=0)
        adam.step([dw1, db1, dw2, db2, dmu_w, dmu_b], l2=l2)

    # σ 头：固定 μ/主干，仅用高斯 NLL 拟合 log σ。
    z1 = Xs @ w1 + b1
    h2 = _relu(_relu(z1) @ w2 + b2)
    mu = (h2 @ mu_w + mu_b).ravel()
    residual_std = float(np.sqrt(np.mean((y - mu) ** 2)))
    sig_adam = _Adam([sig_w, sig_b], sigma_lr)
    for _epoch in range(max(int(sigma_epochs), 0)):
        raw = (h2 @ sig_w + sig_b).ravel()
        sigma_vec = np.exp(np.clip(raw, math.log(0.5), math.log(5000.0)))
        ratio = (y - mu) / sigma_vec
        loss_sigma = float(np.mean(0.5 * ratio**2 + np.log(sigma_vec)))
        dsigma = (1.0 - ratio**2) / sigma_vec
        draw = dsigma.reshape(-1, 1) * sigma_vec.reshape(-1, 1)  # dL/draw
        dsig_w = h2.T @ draw / X.shape[0]
        dsig_b = np.asarray([draw.mean()])
        sig_adam.step([dsig_w, dsig_b])
        if not math.isfinite(loss_sigma):
            break

    model = MLPLeafValue(
        mean=mean,
        scale=scale,
        w1=w1,
        b1=b1,
        w2=w2,
        b2=b2,
        mu_w=mu_w,
        mu_b=mu_b,
        sig_w=sig_w,
        sig_b=sig_b,
        sigma=residual_std,
        use_sigma_head=True,
        meta={"n": int(X.shape[0]), "hidden": [hidden1, hidden2], "epochs": int(epochs)},
    )
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r2 = 1.0 - float(np.sum((y - mu) ** 2)) / ss_tot
    history = {
        "n": int(X.shape[0]),
        "final_mse": float(np.mean((y - mu) ** 2)),
        "residual_std": residual_std,
        "r2": r2,
        "epochs": int(epochs),
        "sigma_epochs": int(sigma_epochs),
        "hidden": [hidden1, hidden2],
    }
    return model, history


def _sigmoid_array(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(value, -60.0, 60.0)))


def train_utility_heads(
    model: MLPLeafValue,
    X: np.ndarray,
    y: np.ndarray,
    *,
    epochs: int = 400,
    lr: float = 5e-3,
    l2: float = 1e-4,
) -> dict:
    """在已训练的主干上拟合两个 P(档位) logistic 头（搜索目标同口径）。

    目标：该叶子状态的真实后续得分 ``y`` 是否够到 ``clear - score`` /
    ``perfect - score``。只用 ``turns_left > 0`` 的样本（终局样本 ``predict``
    直接返回 0，不需要概率头）。训练后 ``model.utility`` 改用概率头。
    """
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    turns_col = FEATURE_NAMES.index("turns_left")
    score_col = FEATURE_NAMES.index("score")
    clear_col = FEATURE_NAMES.index("clear")
    perfect_col = FEATURE_NAMES.index("perfect")
    valid = X[:, turns_col] > 0
    if int(valid.sum()) < 8:
        raise ValueError("没有 turns_left>0 的样本，无法训练档位概率头")
    Xs = (X[valid] - model.mean) / model.scale
    h1 = _relu(Xs @ model.w1 + model.b1)
    h2 = _relu(h1 @ model.w2 + model.b2)
    score = X[valid, score_col]
    clear = X[valid, clear_col]
    perfect = X[valid, perfect_col]
    targets = np.column_stack(
        [
            (y[valid] >= (clear - score)).astype(np.float64),
            (y[valid] >= (perfect - score)).astype(np.float64),
        ]
    )

    def logit(rate: float) -> float:
        rate = min(max(float(rate), 1e-3), 1.0 - 1e-3)
        return math.log(rate / (1.0 - rate))

    weights = np.zeros((h2.shape[1], 2), dtype=np.float64)
    bias = np.asarray([logit(targets[:, 0].mean()), logit(targets[:, 1].mean())])
    adam = _Adam([weights, bias], lr)
    n = h2.shape[0]
    for _epoch in range(max(int(epochs), 0)):
        probability = _sigmoid_array(h2 @ weights + bias)
        grad = h2.T @ (probability - targets) / n
        grad_bias = (probability - targets).mean(axis=0)
        adam.step([grad, grad_bias], l2=l2)
    probability = _sigmoid_array(h2 @ weights + bias)
    model.p_clear_w = weights[:, 0:1].copy()
    model.p_clear_b = np.asarray([bias[0]])
    model.p_perfect_w = weights[:, 1:2].copy()
    model.p_perfect_b = np.asarray([bias[1]])
    return {
        "n": int(n),
        "clear_rate": float(targets[:, 0].mean()),
        "perfect_rate": float(targets[:, 1].mean()),
        "clear_pred_mean": float(probability[:, 0].mean()),
        "perfect_pred_mean": float(probability[:, 1].mean()),
        "clear_accuracy": float(((probability[:, 0] >= 0.5) == targets[:, 0]).mean()),
        "perfect_accuracy": float(((probability[:, 1] >= 0.5) == targets[:, 1]).mean()),
        "clear_brier": float(np.mean((probability[:, 0] - targets[:, 0]) ** 2)),
        "perfect_brier": float(np.mean((probability[:, 1] - targets[:, 1]) ** 2)),
    }


def evaluate_utility_heads(model: MLPLeafValue, X: np.ndarray, y: np.ndarray) -> dict:
    """在给定样本上评估档位概率头（准确率/Brier/预测均值）。"""
    if model.p_clear_w is None or model.p_perfect_w is None:
        raise ValueError("模型没有档位概率头")
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    turns_col = FEATURE_NAMES.index("turns_left")
    valid = X[:, turns_col] > 0
    Xs = (X[valid] - model.mean) / model.scale
    h1 = _relu(Xs @ model.w1 + model.b1)
    h2 = _relu(h1 @ model.w2 + model.b2)
    score = X[valid, FEATURE_NAMES.index("score")]
    clear = X[valid, FEATURE_NAMES.index("clear")]
    perfect = X[valid, FEATURE_NAMES.index("perfect")]
    targets = np.column_stack(
        [
            (y[valid] >= (clear - score)).astype(np.float64),
            (y[valid] >= (perfect - score)).astype(np.float64),
        ]
    )
    weights = np.column_stack([model.p_clear_w[:, 0], model.p_perfect_w[:, 0]])
    bias = np.asarray([model.p_clear_b[0], model.p_perfect_b[0]])
    probability = _sigmoid_array(h2 @ weights + bias)
    return {
        "n": int(valid.sum()),
        "clear_rate": float(targets[:, 0].mean()),
        "perfect_rate": float(targets[:, 1].mean()),
        "clear_pred_mean": float(probability[:, 0].mean()),
        "perfect_pred_mean": float(probability[:, 1].mean()),
        "clear_accuracy": float(((probability[:, 0] >= 0.5) == targets[:, 0]).mean()),
        "perfect_accuracy": float(((probability[:, 1] >= 0.5) == targets[:, 1]).mean()),
        "clear_brier": float(np.mean((probability[:, 0] - targets[:, 0]) ** 2)),
        "perfect_brier": float(np.mean((probability[:, 1] - targets[:, 1]) ** 2)),
    }


