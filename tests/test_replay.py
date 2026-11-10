from __future__ import annotations

import json

import numpy as np
import pytest

from gkagent.contract.models import Action, ActionKind, Card, Observation, Phase
from gkagent.runtime.replay import ReplayDB, ReplayRow, ReplayStats


def _observation(frame_id: int, vocal: int, card_cost: int = 1) -> Observation:
    return Observation(
        frame_id=frame_id,
        ts_ms=frame_id * 100,
        screen="contest_select",
        phase=Phase.CONTEST,
        turn=frame_id,
        hp=80,
        scores={"vocal": vocal, "dance": 10, "visual": 20},
        hand=[Card(card_id=f"c{frame_id}", cost=card_cost, kind="attack")],
        confidence=0.9,
    )


def test_replay_record_read_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "replay.sqlite3"
    obs_json = _observation(1, 100).model_dump_json()
    action_json = Action(kind=ActionKind.PLAY_CARD, index=0).model_dump_json()

    with ReplayDB(db_path, run_id="run-a") as db:
        first = db.record("hash-a", obs_json, action_json, reward=1.5, ts=1000.0)
        second = db.record(
            "hash-b",
            {"frame_id": 2, "scores": {"vocal": 200}},
            {"kind": "end_turn"},
            reward=-0.5,
            ts=1001.0,
        )
        third = db.record(
            "hash-c",
            _observation(3, 300),
            Action(kind=ActionKind.CHOOSE, index=1),
            reward=0.25,
            ts=2000.0,
            run_id="run-b",
        )
        assert (first, second, third) == (1, 2, 3)
        assert len(db) == 3
        assert db.count() == 3
        assert db.count("run-a") == 2
        assert db.run_ids() == ["run-a", "run-b"]

        rows = db.rows("run-a")
        assert [row.frame_hash for row in rows] == ["hash-a", "hash-b"]
        assert isinstance(rows[0], ReplayRow)
        assert rows[0].run_id == "run-a"
        assert rows[0].reward == 1.5
        assert rows[0].ts == 1000.0
        assert json.loads(rows[0].state_json) == json.loads(obs_json)
        assert json.loads(rows[0].action_json) == json.loads(action_json)
        assert rows[0].state()["scores"]["vocal"] == 100
        assert rows[0].action()["kind"] == "play_card"

        stats = db.stats()
        assert isinstance(stats, ReplayStats)
        assert stats.rows == 3
        assert stats.total_reward == 1.25
        assert stats.mean_reward == pytest.approx(1.25 / 3)
        assert stats.first_ts == 1000.0
        assert stats.last_ts == 2000.0
        assert stats.duration_s == 1000.0
        assert db.stats("run-a").rows == 2
        assert db.stats("run-a").total_reward == 1.0
        assert db.stats("missing").rows == 0
        assert db.stats("missing").first_ts is None
        assert db.stats("missing").duration_s == 0.0

    with ReplayDB(db_path) as reopened:
        assert reopened.default_run_id == "default"
        assert reopened.count() == 3
        assert [row.frame_hash for row in reopened.rows("run-a")] == ["hash-a", "hash-b"]


def test_export_dataset_action_roundtrip(tmp_path) -> None:
    with ReplayDB(tmp_path / "replay.sqlite3", run_id="run-a") as db:
        db.record(
            "hash-0",
            _observation(1, 100, card_cost=1),
            Action(kind=ActionKind.PLAY_CARD, index=0),
            reward=1.0,
            ts=1.0,
        )
        db.record(
            "hash-1",
            _observation(2, 200, card_cost=2),
            Action(kind=ActionKind.PLAY_CARD, index=1),
            reward=2.0,
            ts=2.0,
        )
        db.record(
            "hash-2",
            _observation(3, 300, card_cost=3),
            Action(kind=ActionKind.END_TURN),
            reward=0.0,
            ts=3.0,
        )
        db.record(
            "hash-other",
            _observation(4, 400),
            Action(kind=ActionKind.WAIT),
            reward=9.0,
            ts=4.0,
            run_id="run-b",
        )

        X, y, meta = db.export_dataset("run-a", label="action")
        assert X.shape == (3, meta["n_features"])
        assert meta["n_samples"] == 3
        assert meta["n_skipped"] == 0
        assert meta["label"] == "action"
        assert meta["run_ids"] == ["run-a"]
        names = meta["feature_names"]
        assert names == sorted(names)

        vocal = names.index("scores.vocal")
        cost = names.index("hand[0].cost")
        np.testing.assert_allclose(X[:, vocal], [100.0, 200.0, 300.0])
        np.testing.assert_allclose(X[:, cost], [1.0, 2.0, 3.0])

        classes = meta["classes"]
        assert {"kind": "end_turn"} in classes
        assert {"index": 0, "kind": "play_card"} in classes
        assert y.dtype == np.int64
        assert y.tolist() == [
            classes.index({"index": 0, "kind": "play_card"}),
            classes.index({"index": 1, "kind": "play_card"}),
            classes.index({"kind": "end_turn"}),
        ]
        assert sorted(set(y.tolist())) == [0, 1, 2]

        X_reward, y_reward, meta_reward = db.export_dataset("run-a", label="reward")
        assert X_reward.shape == X.shape
        assert y_reward.dtype == np.float64
        np.testing.assert_allclose(y_reward, [1.0, 2.0, 0.0])
        assert meta_reward["classes"] is None

        X_index, y_index, meta_index = db.export_dataset(
            "run-a", label="index", feature_keys=["scores.vocal", "missing.key"]
        )
        assert X_index.shape == (3, 2)
        np.testing.assert_allclose(X_index[:, 0], [100.0, 200.0, 300.0])
        np.testing.assert_allclose(X_index[:, 1], [0.0, 0.0, 0.0])
        np.testing.assert_array_equal(y_index, [0, 1, -1])
        assert meta_index["feature_names"] == ["scores.vocal", "missing.key"]


def test_export_dataset_empty_and_skips_malformed(tmp_path) -> None:
    with ReplayDB(tmp_path / "replay.sqlite3") as db:
        X, y, meta = db.export_dataset()
        assert X.shape == (0, 0)
        assert y.size == 0
        assert meta["n_samples"] == 0
        assert meta["classes"] == []

        db.record("good", _observation(1, 100), Action(kind=ActionKind.WAIT), ts=1.0)
        db.record("bad-state", "{not-json", Action(kind=ActionKind.WAIT), ts=2.0)
        db.record("bad-action", _observation(2, 200), "{not-json", ts=3.0)

        X_ok, y_ok, meta_ok = db.export_dataset()
        assert X_ok.shape[0] == 1
        assert y_ok.size == 1
        assert meta_ok["n_samples"] == 1
        assert meta_ok["n_skipped"] == 2
        assert meta_ok["run_ids"] == ["default"]

        limited = db.rows(limit=1)
        assert [row.frame_hash for row in limited] == ["good"]
