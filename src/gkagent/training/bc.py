"""BC（Behavior Cloning）训练骨架：numpy 线性 / 逻辑回归。

目标是把 replay 导出的 ``(X, y)`` 先跑通，提供一个可保存、可加载、可离线评估的
基线，而不是追求精度。后续可以替换成 torch 网络，调用方接口保持不变。

支持的模式：

- ``linear``：连续目标回归（例如 reward / 分数）；
- ``logistic``：二分类（例如是否出牌）；
- ``softmax``：多分类（例如 action 类别）；
- ``auto``：浮点 y → linear；整数/字符串 y → 两类 logistic，多类 softmax。

训练使用全批量梯度下降 + 特征标准化，``loss_history`` 记录每轮损失（含初始损失）。
模型保存为 ``.npz``（不依赖 pickle）；ONNX 导出是预留接口：安装可选依赖
``onnx``（``uv sync --extra train``）后可用，否则抛出 RuntimeError。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

Mode = Literal["auto", "linear", "logistic", "softmax"]
MODES = ("linear", "logistic", "softmax")
_FORMAT = "gkagent.bc.v1"
_DEFAULT_LR = {"linear": 0.1, "logistic": 0.5, "softmax": 0.5}
_EPS = 1e-12


@dataclass
class BCModel:
    """一个已训练（或已加载）的线性 / 逻辑回归 BC 模型。"""

    mode: str
    weights: np.ndarray
    bias: np.ndarray
    mean: np.ndarray
    scale: np.ndarray
    classes: np.ndarray | None = None
    feature_names: list[str] = field(default_factory=list)
    loss_history: list[float] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def n_features(self) -> int:
        return int(self.weights.shape[0])

    @property
    def n_classes(self) -> int | None:
        return None if self.classes is None else int(self.classes.size)

    # ------------------------------------------------------------------ 预测
    def predict(self, X: np.ndarray) -> np.ndarray:
        """linear 返回连续值；分类模式返回 ``classes`` 中的原始标签。"""
        if self.mode == "linear":
            return self._transform(X) @ self.weights + self.bias
        probabilities = self.predict_proba(X)
        if self.classes is None:
            raise RuntimeError("classification model has no classes")
        if self.mode == "logistic":
            return self.classes[(probabilities[:, 1] >= 0.5).astype(np.int64)]
        return self.classes[np.argmax(probabilities, axis=1)]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """分类概率：logistic 返回 (n, 2)，softmax 返回 (n, n_classes)。"""
        if self.mode == "linear":
            raise ValueError("linear regression has no probabilities; use predict()")
        scaled = self._transform(X)
        logits = scaled @ self.weights + self.bias
        if self.mode == "logistic":
            positive = _sigmoid(logits)
            return np.column_stack([1.0 - positive, positive])
        return _softmax(logits)

    def loss(self, X: np.ndarray, y: np.ndarray) -> float:
        """在给定数据上的数据损失（不含 L2 正则项）。"""
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)
        y_arr = np.asarray(y)
        if y_arr.ndim == 2 and y_arr.shape[1] == 1:
            y_arr = y_arr[:, 0]
        if y_arr.ndim != 1 or y_arr.size != X_arr.shape[0]:
            raise ValueError("y must be 1-D and match X.shape[0]")
        scaled = self._transform(X_arr)
        if self.mode == "linear":
            return self._loss_and_grad(scaled, y_arr.astype(np.float64))[0]
        return self._loss_and_grad(scaled, self._encode_labels(y_arr))[0]

    # ------------------------------------------------------------------ 保存 / 加载
    def save(self, path: str | Path) -> Path:
        """保存为 ``.npz``，返回实际写入路径（无后缀时自动补 ``.npz``）。"""
        target = _npz_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": _FORMAT,
            "mode": self.mode,
            "feature_names": list(self.feature_names),
            "classes": None if self.classes is None else self.classes.tolist(),
            "meta": self.meta,
        }
        np.savez_compressed(
            target,
            weights=np.asarray(self.weights, dtype=np.float64),
            bias=np.asarray(self.bias, dtype=np.float64),
            mean=np.asarray(self.mean, dtype=np.float64),
            scale=np.asarray(self.scale, dtype=np.float64),
            loss_history=np.asarray(self.loss_history, dtype=np.float64),
            meta_json=np.asarray(_dumps(payload)),
        )
        return target

    @classmethod
    def load(cls, path: str | Path) -> BCModel:
        """从 ``.npz`` 加载模型；不启用 pickle。"""
        source = Path(path)
        if source.suffix.lower() != ".npz":
            candidate = source.with_name(f"{source.name}.npz")
            if not source.exists() and candidate.exists():
                source = candidate
        with np.load(source, allow_pickle=False) as data:
            weights = np.array(data["weights"], dtype=np.float64)
            bias = np.array(data["bias"], dtype=np.float64)
            mean = np.array(data["mean"], dtype=np.float64)
            scale = np.array(data["scale"], dtype=np.float64)
            loss_history = [float(value) for value in data["loss_history"].tolist()]
            payload = json.loads(data["meta_json"].item())
        if payload.get("format") != _FORMAT:
            raise ValueError(f"unsupported BC model format: {payload.get('format')!r}")
        mode = str(payload.get("mode"))
        if mode not in MODES:
            raise ValueError(f"unknown BC mode: {mode!r}")
        classes_payload = payload.get("classes")
        classes = None if classes_payload is None else np.asarray(classes_payload)
        model = cls(
            mode=mode,
            weights=weights,
            bias=bias,
            mean=mean,
            scale=scale,
            classes=classes,
            feature_names=[str(name) for name in payload.get("feature_names") or []],
            loss_history=loss_history,
            meta=dict(payload.get("meta") or {}),
        )
        model._validate_arrays()
        return model

    # ------------------------------------------------------------------ ONNX
    def export_onnx(self, path: str | Path, *, opset: int = 17) -> Path:
        """导出 ONNX（可选依赖）。

        TODO: 当前是预留接口；安装 ``onnx>=1.16`` 后可用。未安装时抛 RuntimeError。
        输入为未标准化特征 ``state``（float32, [None, n_features]）；输出统一叫
        ``prediction``：linear 为 (n, 1) 连续值，logistic 为 (n, 1) 正类概率，
        softmax 为 (n, n_classes) 概率。
        """
        try:
            import onnx
            from onnx import TensorProto, helper, numpy_helper
        except ImportError as exc:  # pragma: no cover - 依赖可选，默认环境不装
            raise RuntimeError(
                "ONNX export requires the optional 'onnx' package; "
                "install with `uv sync --extra train`"
            ) from exc

        if opset < 13:
            raise ValueError("opset must be >= 13")

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        n_features = self.n_features
        weights = np.asarray(self.weights, dtype=np.float32)
        if weights.ndim == 1:
            weights = weights.reshape(n_features, 1)
        bias = np.asarray(self.bias, dtype=np.float32).reshape(-1)
        if bias.size == 1 and weights.shape[1] != 1:
            bias = np.repeat(bias, weights.shape[1])
        mean = np.asarray(self.mean, dtype=np.float32)
        scale = np.asarray(self.scale, dtype=np.float32)

        initializers = [
            numpy_helper.from_array(mean, name="mean"),
            numpy_helper.from_array(scale, name="scale"),
            numpy_helper.from_array(weights, name="weights"),
            numpy_helper.from_array(bias, name="bias"),
        ]
        nodes = [
            helper.make_node("Sub", ["state", "mean"], ["centered"]),
            helper.make_node("Div", ["centered", "scale"], ["scaled"]),
            helper.make_node("MatMul", ["scaled", "weights"], ["logits"]),
            helper.make_node("Add", ["logits", "bias"], ["scores"]),
        ]
        if self.mode == "linear":
            nodes.append(helper.make_node("Identity", ["scores"], ["prediction"]))
            out_dim = 1
        elif self.mode == "logistic":
            nodes.append(helper.make_node("Sigmoid", ["scores"], ["prediction"]))
            out_dim = 1
        else:
            nodes.append(helper.make_node("Softmax", ["scores"], ["prediction"], axis=1))
            out_dim = int(weights.shape[1])

        graph = helper.make_graph(
            nodes,
            "gkagent_bc",
            [helper.make_tensor_value_info("state", TensorProto.FLOAT, [None, n_features])],
            [helper.make_tensor_value_info("prediction", TensorProto.FLOAT, [None, out_dim])],
            initializer=initializers,
        )
        model = helper.make_model(
            graph,
            producer_name="gkagent.bc",
            opset_imports=[helper.make_opsetid("", opset)],
        )
        onnx.checker.check_model(model)
        onnx.save(model, str(target))
        return target

    # ------------------------------------------------------------------ 内部
    def _loss_and_grad(
        self, scaled: np.ndarray, target: np.ndarray
    ) -> tuple[float, np.ndarray, np.ndarray]:
        n_samples = scaled.shape[0]
        if self.mode == "linear":
            diff = scaled @ self.weights + self.bias - target
            loss = float(np.mean(diff**2))
            grad_w = (2.0 / n_samples) * (scaled.T @ diff)
            grad_b = np.asarray([2.0 * float(np.mean(diff))])
        elif self.mode == "logistic":
            probability = _sigmoid(scaled @ self.weights + self.bias)
            loss = float(
                -np.mean(
                    target * np.log(probability + _EPS)
                    + (1.0 - target) * np.log(1.0 - probability + _EPS)
                )
            )
            grad_w = scaled.T @ (probability - target) / n_samples
            grad_b = np.asarray([float(np.mean(probability - target))])
        else:
            probabilities = _softmax(scaled @ self.weights + self.bias)
            loss = float(-np.mean(np.log(probabilities[np.arange(n_samples), target] + _EPS)))
            one_hot = np.zeros_like(probabilities)
            one_hot[np.arange(n_samples), target] = 1.0
            grad_w = scaled.T @ (probabilities - one_hot) / n_samples
            grad_b = np.mean(probabilities - one_hot, axis=0)
        return loss, grad_w, grad_b

    def _transform(self, X: np.ndarray) -> np.ndarray:
        array = np.asarray(X, dtype=np.float64)
        if array.ndim == 1:
            if array.size != self.n_features:
                raise ValueError(f"expected {self.n_features} features, got {array.size}")
            array = array.reshape(1, -1)
        if array.ndim != 2:
            raise ValueError("X must be 1-D (single sample) or 2-D (n_samples, n_features)")
        if array.shape[1] != self.n_features:
            raise ValueError(f"expected {self.n_features} features, got {array.shape[1]}")
        if not np.all(np.isfinite(array)):
            raise ValueError("X must be finite")
        return (array - self.mean) / self.scale

    def _encode_labels(self, y: np.ndarray) -> np.ndarray:
        if self.classes is None:
            raise RuntimeError("classification model has no classes")
        mapping = {value: index for index, value in enumerate(self.classes.tolist())}
        encoded: list[int] = []
        for value in y.tolist():
            if value not in mapping:
                raise ValueError(f"unknown label: {value!r}")
            encoded.append(mapping[value])
        return np.asarray(encoded, dtype=np.int64)

    def _validate_arrays(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"unknown BC mode: {self.mode!r}")
        if self.weights.ndim not in (1, 2):
            raise ValueError("weights must be 1-D or 2-D")
        if self.mean.ndim != 1 or self.scale.ndim != 1 or self.mean.size != self.scale.size:
            raise ValueError("mean/scale must be 1-D arrays of equal length")
        if self.mean.size != self.weights.shape[0]:
            raise ValueError("mean/scale length must match weights.shape[0]")
        if not np.all(np.isfinite(self.weights)):
            raise ValueError("weights must be finite")
        if self.feature_names and len(self.feature_names) != self.n_features:
            raise ValueError("feature_names length must match weights.shape[0]")
        if self.mode == "softmax":
            if self.weights.ndim != 2 or self.bias.size != self.weights.shape[1]:
                raise ValueError(
                    "softmax expects weights (n_features, n_classes) and bias (n_classes,)"
                )
            if self.classes is None or self.classes.size != self.weights.shape[1]:
                raise ValueError("softmax requires one class per output column")
        else:
            if self.weights.ndim != 1 or self.bias.size != 1:
                raise ValueError("linear/logistic expect weights (n_features,) and bias (1,)")
            if self.mode == "logistic" and (self.classes is None or self.classes.size != 2):
                raise ValueError("logistic requires exactly 2 classes")


def train_bc(
    X: np.ndarray,
    y: np.ndarray,
    *,
    mode: Mode = "auto",
    epochs: int = 300,
    lr: float | None = None,
    weight_decay: float = 1e-4,
    standardize: bool = True,
    feature_names: Sequence[str] | None = None,
) -> BCModel:
    """在 ``(X, y)`` 上训练一个线性 / 逻辑回归 BC 模型。

    - X: (n_samples, n_features) float 矩阵；
    - y: (n_samples,) 标签；回归为浮点，分类可为整数或字符串；
    - epochs/lr/weight_decay: 全批量梯度下降参数；lr 缺省按模式取 0.1/0.5；
    - standardize: 是否对 X 做 z-score（均值/方差会存进模型，预测时复用）；
    - feature_names: 可选列名，便于和 replay.export_dataset() 的 meta 对齐。
    """
    X_arr = _check_X(X)
    y_arr = _check_y(y, X_arr.shape[0])
    resolved, classes, target = _resolve_target(mode, y_arr)

    if epochs < 0:
        raise ValueError("epochs must be >= 0")
    if weight_decay < 0:
        raise ValueError("weight_decay must be >= 0")
    effective_lr = _DEFAULT_LR[resolved] if lr is None else float(lr)
    if effective_lr <= 0:
        raise ValueError("lr must be > 0")
    if feature_names is not None and len(feature_names) != X_arr.shape[1]:
        raise ValueError("feature_names length must match X.shape[1]")

    if standardize:
        mean = X_arr.mean(axis=0)
        scale = X_arr.std(axis=0)
        scale = np.where(scale < 1e-8, 1.0, scale)
    else:
        mean = np.zeros(X_arr.shape[1], dtype=np.float64)
        scale = np.ones(X_arr.shape[1], dtype=np.float64)
    scaled = (X_arr - mean) / scale

    if resolved == "softmax":
        assert classes is not None
        weights = np.zeros((X_arr.shape[1], classes.size), dtype=np.float64)
        bias = np.zeros(classes.size, dtype=np.float64)
    else:
        weights = np.zeros(X_arr.shape[1], dtype=np.float64)
        bias = np.zeros(1, dtype=np.float64)

    model = BCModel(
        mode=resolved,
        weights=weights,
        bias=bias,
        mean=np.asarray(mean, dtype=np.float64),
        scale=np.asarray(scale, dtype=np.float64),
        classes=classes,
        feature_names=list(feature_names or []),
        loss_history=[],
        meta={
            "n_samples": int(X_arr.shape[0]),
            "n_features": int(X_arr.shape[1]),
            "epochs": int(epochs),
            "lr": effective_lr,
            "weight_decay": float(weight_decay),
            "standardize": bool(standardize),
        },
    )

    loss, grad_w, grad_b = model._loss_and_grad(scaled, target)
    model.loss_history.append(loss)
    for _ in range(epochs):
        model.weights = model.weights - effective_lr * (grad_w + weight_decay * model.weights)
        model.bias = model.bias - effective_lr * grad_b
        loss, grad_w, grad_b = model._loss_and_grad(scaled, target)
        model.loss_history.append(loss)

    model._validate_arrays()
    return model


def _check_X(X: np.ndarray) -> np.ndarray:
    array = np.asarray(X, dtype=np.float64)
    if array.ndim != 2:
        raise ValueError("X must be 2-D (n_samples, n_features)")
    if array.shape[0] == 0:
        raise ValueError("X must contain at least one sample")
    if array.shape[1] == 0:
        raise ValueError("X must contain at least one feature")
    if not np.all(np.isfinite(array)):
        raise ValueError("X must be finite")
    return array


def _check_y(y: np.ndarray, n_samples: int) -> np.ndarray:
    array = np.asarray(y)
    if array.ndim == 2 and array.shape[1] == 1:
        array = array[:, 0]
    if array.ndim != 1:
        raise ValueError("y must be 1-D")
    if array.size != n_samples:
        raise ValueError("y length must match X.shape[0]")
    if array.dtype.kind == "f" and not np.all(np.isfinite(array)):
        raise ValueError("y must be finite")
    return array


def _resolve_target(mode: str, y: np.ndarray) -> tuple[str, np.ndarray | None, np.ndarray]:
    if mode == "auto":
        if y.dtype.kind == "f":
            resolved = "linear"
        else:
            unique = np.unique(y)
            if unique.size >= 3:
                resolved = "softmax"
            elif unique.size == 2:
                resolved = "logistic"
            else:
                resolved = "linear"
    elif mode in MODES:
        resolved = mode
    else:
        raise ValueError(f"unknown BC mode: {mode!r}")

    if resolved == "linear":
        target = y.astype(np.float64)
        if not np.all(np.isfinite(target)):
            raise ValueError("y must be finite for linear regression")
        return resolved, None, target

    classes, encoded = np.unique(y, return_inverse=True)
    if resolved == "logistic" and classes.size != 2:
        raise ValueError("logistic mode requires exactly 2 classes")
    if resolved == "softmax" and classes.size < 2:
        raise ValueError("softmax mode requires at least 2 classes")
    return resolved, classes, encoded.astype(np.int64, copy=False)


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -60.0, 60.0)))


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=1, keepdims=True)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _npz_path(path: str | Path) -> Path:
    """np.savez 会自动补 .npz，这里先归一化，保证 save() 返回值即真实路径。"""
    target = Path(path)
    if target.suffix.lower() != ".npz":
        target = target.with_name(f"{target.name}.npz")
    return target


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value)!r}")
