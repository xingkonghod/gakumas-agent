"""B11 渐退式专家迭代：policy/advantage 学生网（第 1 轮，2026-11-23）。

与 B2/B2-R 学习叶子（状态价值）路线的**目标量区别**（见 docs/EXPECTIMAX.md
「B2 重训（B2-R）」根因诊断：锐利 σ 放大 + 价值-策略失配）：

* 学「该打哪张牌 / 这张比平均好多少」（policy/advantage），**不是**状态价值；
* 优势标签来自**学生自己的对局**（on-policy 分支重放，见 ``policy_data``）——
  打法变了标签跟着变，绕开「teacher return ≠ 有限搜索可执行价值」的失配；
* 推理 = 在**可出牌**里挑 argmax，不做搜索、不估 σ，没有档位概率放大问题。

用户硬规矩在此编码：**SKIP 只在所有牌都付不起时允许**（``net_action``：
有可出牌就只排牌，绝不返回 None；``legal_actions()==[None]`` 才 SKIP）。

特征（复用 B2 的 104 维结构化状态特征 + 33 维动作特征 = 137 维）：

* 状态段 = ``leaf_mlp.features(state)``：决策态带手牌，手牌按叶子口径并入
  弃牌堆聚合（「现在结束回合会怎样」的摘要）， buff/指針/牌库拆分全带上；
* 动作段 = 候选牌 23 维静态画像（``leaf_mlp._card_profile``，与状态段同源）
  + 实际费用/体力上下文 + 手牌聚合（候选之外的选项质量）+ 出牌位上下文。

训练目标（MSE 回归优势）：

* 自对弈样本：``A(s,a) = R(s,a) − mean_b R(s,b)``，R = 分支后学生自己打完的
  终局分（精确重放，无搜索镜像误差）；训练前按全局 std 归一化；
* 教师示范样本：教师出的牌 +1、其余 −1/(k−1)（软目标，k=1 的强制决策无信息，
  采集时剔除）；两类样本按 ``--teacher-frac``（第 1 轮 0.3）混合。

模型存取格式 ``gkagent.policy_mlp.v1``（numpy MLP，与 leaf_mlp 同族）。
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from gkagent.sim.expectimax import ExpectState, effective_cost, legal_cards, state_from_sim
from gkagent.sim.leaf_mlp import (
    DIM as LEAF_DIM,
)
from gkagent.sim.leaf_mlp import (
    _Adam,
    _card_profile,
    _relu,
)
from gkagent.sim.leaf_mlp import (
    features as leaf_features,
)
from gkagent.sim.lesson import CardSpec, LessonSim

FORMAT = "gkagent.policy_mlp.v1"

# 动作特征：候选牌画像 23 维（_card_profile 同序）+ 10 维上下文。
ACTION_FEATURE_NAMES: tuple[str, ...] = (
    *(f"card_{name}" for name in (
        "score", "cost", "vitality", "condition", "focus", "motivation",
        "impression", "draw", "impression_scale", "preservation",
        "full_power_point", "extra_play", "block_scale", "parameter_buff",
        "strong_level", "stamina_recover", "full_power_scale", "review_multiple",
        "condition_additive", "full_power_lesson_multiple", "grow_score",
        "encore", "once",
    )),
    "effective_cost",
    "cost_over_available",
    "affordable_margin",
    "hand_count",
    "hand_playable_count",
    "hand_score_mean",
    "hand_score_max",
    "hand_cost_mean",
    "plays_left_after",
    "candidate_score_share",
)
ACTION_DIM = len(ACTION_FEATURE_NAMES)
INPUT_DIM = LEAF_DIM + ACTION_DIM


def action_features(state: ExpectState, card: CardSpec) -> np.ndarray:
    """候选动作（打出 ``card``）的 33 维特征；纯函数、无全局状态。"""
    profile = _card_profile(card)
    available = float(state.stamina + state.vitality)
    cost = float(effective_cost(state, card))
    hand = tuple(state.hand or ())
    playable = legal_cards(state)
    scores = [float(c.score) for c in hand]
    costs = [float(c.cost) for c in hand]
    score_sum = sum(scores)
    values = [
        *profile,
        cost,
        cost / max(available, 1.0),
        available - cost,
        float(len(hand)),
        float(len(playable)),
        sum(scores) / len(scores) if scores else 0.0,
        max(scores) if scores else 0.0,
        sum(costs) / len(costs) if costs else 0.0,
        float(max(state.plays_left - 1 + int(card.extra_play), 0)),
        float(card.score) / score_sum if score_sum > 0 else 0.0,
    ]
    vector = np.asarray(values, dtype=np.float64)
    return np.nan_to_num(vector, nan=0.0, posinf=0.0, neginf=0.0)


def decision_features(state: ExpectState, card: CardSpec) -> np.ndarray:
    """(决策状态, 候选牌) → 137 维输入向量（状态 104 + 动作 33）。"""
    return np.concatenate([leaf_features(state), action_features(state, card)])


@dataclass
class PolicyMLP:
    """优势学生网：输入 (状态, 候选牌) 特征，输出标量优势分（越大越该打）。"""

    mean: np.ndarray
    scale: np.ndarray
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    out_w: np.ndarray
    out_b: np.ndarray
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ 推理
    def score_vector(self, X: np.ndarray, *, standardized: bool = False) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if not standardized:
            X = (X - self.mean) / self.scale
        h1 = _relu(X @ self.w1 + self.b1)
        h2 = _relu(h1 @ self.w2 + self.b2)
        out = (h2 @ self.out_w + self.out_b).ravel()
        return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)

    def score(self, state: ExpectState, cards: Sequence[CardSpec]) -> np.ndarray:
        """对一组候选牌打优势分（与 ``cards`` 同序）。"""
        if not cards:
            return np.zeros(0, dtype=np.float64)
        X = np.asarray([decision_features(state, card) for card in cards], dtype=np.float64)
        return self.score_vector(X)

    def choose(self, state: ExpectState, cards: Sequence[CardSpec]) -> int:
        """argmax 选牌下标；``cards`` 必须非空（SKIP 由调用方的硬规矩管）。"""
        if not cards:
            raise ValueError("choose 需要至少一张候选牌（无可出牌时调用方应 SKIP）")
        return int(np.argmax(self.score(state, cards)))

    # ------------------------------------------------------------------ 存取
    def to_payload(self) -> dict:
        return {
            "format": FORMAT,
            "leaf_dim": LEAF_DIM,
            "action_feature_names": list(ACTION_FEATURE_NAMES),
            "input_dim": INPUT_DIM,
            "hidden": [int(self.w1.shape[1]), int(self.w2.shape[1])],
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "w1": self.w1.tolist(),
            "b1": self.b1.tolist(),
            "w2": self.w2.tolist(),
            "b2": self.b2.tolist(),
            "out_w": self.out_w.tolist(),
            "out_b": self.out_b.tolist(),
            "meta": self.meta,
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_payload(), ensure_ascii=False), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> PolicyMLP:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if doc.get("format") != FORMAT:
            raise ValueError(f"unsupported model format: {doc.get('format')!r}")
        if tuple(doc.get("action_feature_names") or ()) != ACTION_FEATURE_NAMES:
            raise ValueError("policy_mlp 动作特征名与当前代码不一致，请重新训练")
        if int(doc.get("leaf_dim") or 0) != LEAF_DIM:
            raise ValueError("policy_mlp 状态特征维与当前 leaf_mlp 不一致，请重新训练")
        arrays = {
            key: np.asarray(doc[key], dtype=np.float64)
            for key in ("mean", "scale", "w1", "b1", "w2", "b2", "out_w", "out_b")
        }
        if arrays["mean"].shape != (INPUT_DIM,):
            raise ValueError(f"mean 维度 {arrays['mean'].shape} != ({INPUT_DIM},)")
        if arrays["w1"].shape[0] != INPUT_DIM:
            raise ValueError("w1 输入维度与当前特征不一致")
        return cls(meta=dict(doc.get("meta") or {}), **arrays)


def net_action(sim: LessonSim, model: PolicyMLP) -> int | None:
    """学生网决策（生产口径）：有可出牌 → argmax；全付不起 → SKIP(None)。

    **用户硬规矩**：SKIP 只在所有牌都付不起时允许。这里不返回「有牌却 SKIP」，
    也不做任何静默回退——模型推理异常直接抛出（评测里计为失败，不偷换 rules）。
    """
    legal = sim.legal_actions()
    playable = [index for index in legal if index is not None]
    if not playable:
        return None
    state = state_from_sim(sim)
    cards = [sim.hand[index] for index in playable]
    choice = model.choose(state, cards)
    return playable[choice]


def train_policy_mlp(
    X: np.ndarray,
    y: np.ndarray,
    *,
    hidden: tuple[int, int] = (96, 48),
    epochs: int = 400,
    lr: float = 1e-3,
    l2: float = 1e-4,
    seed: int = 0,
) -> tuple[PolicyMLP, dict]:
    """全批量 Adam MSE 回归优势标签（与 leaf_mlp.train_mlp 同族优化器）。"""
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64).ravel()
    if X.ndim != 2 or X.shape[0] == 0:
        raise ValueError("X 必须是 (n, INPUT_DIM) 的非空矩阵")
    if X.shape[1] != INPUT_DIM:
        raise ValueError(f"特征维度 {X.shape[1]} != {INPUT_DIM}")
    if y.shape[0] != X.shape[0]:
        raise ValueError("X/y 样本数不一致")
    mean = X.mean(axis=0)
    scale = X.std(axis=0)
    scale[scale < 1e-8] = 1.0
    Xs = (X - mean) / scale
    rng = np.random.default_rng(seed)
    hidden1, hidden2 = hidden
    w1 = rng.normal(0.0, math.sqrt(2.0 / INPUT_DIM), size=(INPUT_DIM, hidden1))
    b1 = np.zeros(hidden1)
    w2 = rng.normal(0.0, math.sqrt(2.0 / hidden1), size=(hidden1, hidden2))
    b2 = np.zeros(hidden2)
    out_w = rng.normal(0.0, math.sqrt(1.0 / hidden2), size=(hidden2, 1))
    out_b = np.zeros(1)
    params = [w1, b1, w2, b2, out_w, out_b]
    adam = _Adam(params, lr)
    n = X.shape[0]
    for _epoch in range(max(int(epochs), 1)):
        z1 = Xs @ w1 + b1
        h1 = _relu(z1)
        z2 = h1 @ w2 + b2
        h2 = _relu(z2)
        pred = (h2 @ out_w + out_b).ravel()
        diff = pred - y
        factor = 2.0 / n
        dout_w = h2.T @ diff.reshape(-1, 1) * factor
        dout_b = np.asarray([diff.mean() * 2.0])
        dh2 = diff.reshape(-1, 1) @ out_w.T * factor
        dz2 = dh2 * (z2 > 0)
        dw2 = h1.T @ dz2
        db2 = dz2.sum(axis=0)
        dh1 = dz2 @ w2.T
        dz1 = dh1 * (z1 > 0)
        dw1 = Xs.T @ dz1
        db1 = dz1.sum(axis=0)
        adam.step([dw1, db1, dw2, db2, dout_w, dout_b], l2=l2)
    h2 = _relu(_relu(Xs @ w1 + b1) @ w2 + b2)
    pred = (h2 @ out_w + out_b).ravel()
    mse = float(np.mean((pred - y) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1.0
    model = PolicyMLP(
        mean=mean,
        scale=scale,
        w1=w1,
        b1=b1,
        w2=w2,
        b2=b2,
        out_w=out_w,
        out_b=out_b,
        meta={"n": int(n), "hidden": [hidden1, hidden2], "epochs": int(epochs)},
    )
    history = {
        "n": int(n),
        "final_mse": mse,
        "r2": 1.0 - mse * n / ss_tot,
        "label_mean": float(y.mean()),
        "label_std": float(y.std()),
        "hidden": [hidden1, hidden2],
        "epochs": int(epochs),
    }
    return model, history


def ranking_accuracy(
    model: PolicyMLP, X: np.ndarray, y: np.ndarray, groups: np.ndarray
) -> float:
    """按决策分组：argmax(预测) == argmax(标签) 的比例（验证集口径）。"""
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64).ravel()
    groups = np.asarray(groups).ravel()
    pred = model.score_vector(X)
    correct = 0
    total = 0
    for group in np.unique(groups):
        mask = groups == group
        if int(mask.sum()) < 2:
            continue
        total += 1
        if int(np.argmax(pred[mask])) == int(np.argmax(y[mask])):
            correct += 1
    return correct / total if total else 0.0
