from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from gkagent.contract.models import Action, ActionKind, Observation
from gkagent.runtime.replay import ReplayDB
from gkagent.training.bc import BCModel, train_bc


def test_linear_bc_loss_decreases_and_fits() -> None:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 3))
    coefficients = np.array([2.0, -1.5, 0.5])
    y = X @ coefficients + 0.01 * rng.normal(size=200)

    model = train_bc(X, y, mode="linear", epochs=300)
    assert model.mode == "linear"
    assert len(model.loss_history) == 301
    assert model.loss_history[-1] < model.loss_history[0]
    assert model.loss_history[-1] < 1e-3

    predicted = model.predict(X)
    np.testing.assert_allclose(predicted, y, atol=0.05)
    assert np.corrcoef(predicted, y)[0, 1] > 0.999


def test_logistic_bc_classifies() -> None:
    rng = np.random.default_rng(1)
    X = rng.normal(size=(400, 4))
    coefficients = np.array([1.2, -0.8, 0.5, 1.0])
    y = (X @ coefficients > 0.3).astype(np.int64)

    model = train_bc(X, y, mode="logistic", epochs=400, lr=0.5)
    assert model.mode == "logistic"
    assert model.n_classes == 2
    assert model.loss_history[-1] < model.loss_history[0]
    assert np.mean(model.predict(X) == y) > 0.95

    probabilities = model.predict_proba(X)
    assert probabilities.shape == (400, 2)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_softmax_bc_on_multiclass_labels() -> None:
    rng = np.random.default_rng(2)
    centers = np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 3.0]])
    labels = np.repeat(np.arange(3), 100)
    X = centers[labels] + rng.normal(scale=0.5, size=(300, 2))
    y = labels.astype(np.int64)

    model = train_bc(X, y, epochs=300)  # auto -> softmax
    assert model.mode == "softmax"
    assert model.n_classes == 3
    assert model.loss_history[-1] < model.loss_history[0]
    assert np.mean(model.predict(X) == y) > 0.9

    probabilities = model.predict_proba(X)
    assert probabilities.shape == (300, 3)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, rtol=1e-9)


def test_auto_mode_selection() -> None:
    rng = np.random.default_rng(3)
    X = rng.normal(size=(60, 2))

    assert train_bc(X, X[:, 0], epochs=1).mode == "linear"
    assert train_bc(X, (X[:, 0] > 0).astype(np.int64), epochs=1).mode == "logistic"
    assert train_bc(X, np.arange(60) % 3, epochs=1).mode == "softmax"


def test_bc_save_load_roundtrip(tmp_path) -> None:
    rng = np.random.default_rng(4)
    X = rng.normal(size=(150, 3))
    y = (X @ np.array([1.0, -2.0, 0.5]) > 0.0).astype(np.int64)
    model = train_bc(X, y, mode="logistic", epochs=200, feature_names=["vocal", "dance", "visual"])

    path = model.save(tmp_path / "bc.npz")
    assert path.exists()
    loaded = BCModel.load(path)

    suffixless = model.save(tmp_path / "bc_suffixless")
    assert suffixless == tmp_path / "bc_suffixless.npz"
    assert BCModel.load(tmp_path / "bc_suffixless").loss_history == model.loss_history

    assert loaded.mode == model.mode
    assert loaded.feature_names == ["vocal", "dance", "visual"]
    assert loaded.loss_history == model.loss_history
    assert loaded.meta["epochs"] == 200
    np.testing.assert_allclose(loaded.weights, model.weights)
    np.testing.assert_allclose(loaded.bias, model.bias)
    np.testing.assert_allclose(loaded.mean, model.mean)
    np.testing.assert_allclose(loaded.scale, model.scale)
    np.testing.assert_array_equal(loaded.classes, model.classes)
    np.testing.assert_array_equal(loaded.predict(X), model.predict(X))
    np.testing.assert_allclose(loaded.predict_proba(X), model.predict_proba(X))
    assert loaded.loss(X, y) == pytest.approx(model.loss(X, y))


def test_bc_trains_on_replay_export(tmp_path) -> None:
    with ReplayDB(tmp_path / "replay.sqlite3", run_id="produce") as db:
        for index in range(120):
            action_index = index % 3
            observation = Observation(
                frame_id=index,
                ts_ms=index,
                scores={
                    "vocal": 50.0 + 100.0 * action_index,
                    "dance": 10.0,
                    "visual": 20.0,
                },
                confidence=0.9,
            )
            action = Action(kind=ActionKind.PLAY_CARD, index=action_index)
            db.record(
                f"hash-{index}",
                observation.model_dump_json(),
                action.model_dump_json(),
                reward=float(action_index),
                ts=float(index),
            )
        X, y, meta = db.export_dataset()

    model = train_bc(X, y, epochs=200, feature_names=meta["feature_names"])
    assert model.mode == "softmax"
    assert model.n_classes == 3
    assert model.loss_history[-1] < model.loss_history[0]
    assert np.mean(model.predict(X) == y) > 0.9


def test_onnx_export_contract(tmp_path) -> None:
    rng = np.random.default_rng(5)
    X = rng.normal(size=(20, 2))
    y = X[:, 0] + X[:, 1]
    model = train_bc(X, y, mode="linear", epochs=10)
    target = tmp_path / "bc.onnx"

    if importlib.util.find_spec("onnx") is None:
        with pytest.raises(RuntimeError, match="onnx"):
            model.export_onnx(target)
        assert not target.exists()
    else:
        output = model.export_onnx(target)
        assert output.exists()
        assert output.stat().st_size > 0
