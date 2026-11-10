"""SQLite 回放库：记录每一步决策，导出 BC 数据集。

表结构::

    replay(id, run_id, frame_hash, state_json, action_json, reward, ts)

- 一行 = 一帧的状态与动作；state_json/action_json 直接存契约对象的 JSON。
- run_id 标识一局/一次运行，查询、统计、导出都可按它过滤。
- export_dataset() 把 state_json 展平成数值特征，供 training/bc.py 训练。

设计约束：只依赖标准库 + numpy，不要求游戏运行，便于离线回放和测试。
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import numpy as np
from pydantic import BaseModel

DEFAULT_DB_PATH = "data/replays/replay.sqlite3"
DEFAULT_RUN_ID = "default"
LABELS = ("action", "index", "reward")

JsonLike = str | bytes | bytearray | Mapping[str, Any] | Sequence[Any] | BaseModel | None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS replay (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    frame_hash TEXT NOT NULL,
    state_json TEXT NOT NULL,
    action_json TEXT NOT NULL,
    reward REAL NOT NULL DEFAULT 0.0,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS replay_run_id ON replay (run_id, id);
CREATE INDEX IF NOT EXISTS replay_frame_hash ON replay (frame_hash);
"""


@dataclass(frozen=True)
class ReplayRow:
    """回放表中的一行。"""

    id: int
    run_id: str
    frame_hash: str
    state_json: str
    action_json: str
    reward: float
    ts: float

    def state(self) -> Any:
        """反序列化状态 JSON。"""
        return json.loads(self.state_json)

    def action(self) -> Any:
        """反序列化动作 JSON。"""
        return json.loads(self.action_json)


@dataclass(frozen=True)
class ReplayStats:
    """一组回放记录的统计。"""

    rows: int
    total_reward: float
    mean_reward: float
    first_ts: float | None
    last_ts: float | None

    @property
    def duration_s(self) -> float:
        """首尾时间差（秒）；空库返回 0。"""
        if self.first_ts is None or self.last_ts is None:
            return 0.0
        return max(0.0, self.last_ts - self.first_ts)


class ReplayDB:
    """SQLite 回放库。

    用法::

        with ReplayDB("data/replays/demo.sqlite3", run_id="run-1") as db:
            db.record("frame-hash", obs.model_dump_json(), action.model_dump_json(),
                      reward=1.0, ts=1234.5)
            X, y, meta = db.export_dataset()
    """

    def __init__(
        self,
        path: str | Path = DEFAULT_DB_PATH,
        *,
        run_id: str = DEFAULT_RUN_ID,
    ) -> None:
        self.location = str(path)
        self.path = Path(path)
        if self.location != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.default_run_id = run_id
        self._conn = sqlite3.connect(self.location)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 5000")
        if self.location != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA user_version = 1")
        self._conn.commit()

    # ------------------------------------------------------------------ 生命周期
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __len__(self) -> int:
        return self.count()

    # ------------------------------------------------------------------ 写入
    def record(
        self,
        frame_hash: str,
        state_json: JsonLike,
        action_json: JsonLike,
        reward: float = 0.0,
        ts: float | None = None,
        *,
        run_id: str | None = None,
    ) -> int:
        """写入一步，返回自增行 id。

        state_json / action_json 可以是 JSON 字符串、dict、Pydantic 模型；
        传 dict/模型时会按 sort_keys 规范化为 JSON 字符串。
        ts 缺省使用当前时间（time.time() 秒）。
        """
        state = _dump_json(state_json)
        action = _dump_json(action_json)
        row_ts = time.time() if ts is None else float(ts)
        row_run = run_id or self.default_run_id
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO replay (run_id, frame_hash, state_json, action_json, reward, ts)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (row_run, str(frame_hash), state, action, float(reward), row_ts),
            )
        if cursor.lastrowid is None:
            raise RuntimeError("sqlite 未返回 row id")
        return int(cursor.lastrowid)

    # ------------------------------------------------------------------ 查询
    def rows(
        self,
        run_id: str | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReplayRow]:
        """按 run_id（缺省全部）读取记录，按写入顺序返回。"""
        if limit is not None and limit < 0:
            raise ValueError("limit must be >= 0")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        sql = "SELECT id, run_id, frame_hash, state_json, action_json, reward, ts FROM replay"
        params: list[Any] = []
        if run_id is not None:
            sql += " WHERE run_id = ?"
            params.append(run_id)
        sql += " ORDER BY id"
        if limit is not None or offset:
            sql += " LIMIT ? OFFSET ?"
            params.extend([-1 if limit is None else int(limit), int(offset)])
        cursor = self._conn.execute(sql, params)
        return [
            ReplayRow(
                id=int(row["id"]),
                run_id=str(row["run_id"]),
                frame_hash=str(row["frame_hash"]),
                state_json=str(row["state_json"]),
                action_json=str(row["action_json"]),
                reward=float(row["reward"]),
                ts=float(row["ts"]),
            )
            for row in cursor.fetchall()
        ]

    def count(self, run_id: str | None = None) -> int:
        """记录条数；给 run_id 时只数该局。"""
        if run_id is None:
            cursor = self._conn.execute("SELECT COUNT(*) FROM replay")
        else:
            cursor = self._conn.execute("SELECT COUNT(*) FROM replay WHERE run_id = ?", (run_id,))
        return int(cursor.fetchone()[0])

    def run_ids(self) -> list[str]:
        """全部 run_id，按首次写入顺序。"""
        cursor = self._conn.execute("SELECT run_id FROM replay GROUP BY run_id ORDER BY MIN(id)")
        return [str(row[0]) for row in cursor.fetchall()]

    def stats(self, run_id: str | None = None) -> ReplayStats:
        """聚合统计：条数、奖励总和/均值、首尾时间戳。"""
        sql = (
            "SELECT COUNT(*) AS n, COALESCE(SUM(reward), 0.0) AS total,"
            " COALESCE(AVG(reward), 0.0) AS mean,"
            " MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM replay"
        )
        params: tuple[Any, ...] = ()
        if run_id is not None:
            sql += " WHERE run_id = ?"
            params = (run_id,)
        row = self._conn.execute(sql, params).fetchone()
        return ReplayStats(
            rows=int(row["n"]),
            total_reward=float(row["total"]),
            mean_reward=float(row["mean"]),
            first_ts=None if row["first_ts"] is None else float(row["first_ts"]),
            last_ts=None if row["last_ts"] is None else float(row["last_ts"]),
        )

    # ------------------------------------------------------------------ 导出
    def export_dataset(
        self,
        run_id: str | None = None,
        *,
        label: str = "action",
        feature_keys: Sequence[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        """导出 BC 数据集 ``(X, y, meta)``。

        - label="action"：y 为动作类别 id，meta["classes"] 给出 id→动作字典的映射；
        - label="index"：y 为动作 index（无 index 的动作记 -1）；
        - label="reward"：y 为 reward 列（连续值）。
        - X 的列来自 state_json 的数值字段展平（例如 ``scores.vocal``、
          ``hand[0].cost``）；feature_keys 可显式指定列和顺序。缺失特征补 0.0。
        - meta 含 feature_names / classes / n_samples / n_features / n_skipped / run_ids。
        """
        if label not in LABELS:
            raise ValueError(f"label must be one of {LABELS}, got {label!r}")

        source_rows = self.rows(run_id, limit=limit, offset=offset)
        features: list[dict[str, float]] = []
        raw_labels: list[Any] = []
        used_rows: list[ReplayRow] = []
        skipped = 0

        for row in source_rows:
            try:
                state = json.loads(row.state_json)
            except ValueError:
                skipped += 1
                continue

            if label == "reward":
                value: Any = float(row.reward)
            else:
                try:
                    action = json.loads(row.action_json)
                except ValueError:
                    skipped += 1
                    continue
                if not isinstance(action, Mapping):
                    skipped += 1
                    continue
                if label == "index":
                    index = action.get("index")
                    value = (
                        int(index) if isinstance(index, int) and not isinstance(index, bool) else -1
                    )
                else:
                    action_class = _action_class(action)
                    if action_class is None:
                        skipped += 1
                        continue
                    value = _canonical_json(action_class)

            features.append(_flatten_features(state))
            raw_labels.append(value)
            used_rows.append(row)

        if feature_keys is None:
            names = sorted({name for item in features for name in item})
        else:
            names = [str(name) for name in feature_keys]

        X = np.zeros((len(features), len(names)), dtype=np.float64)
        for row_index, item in enumerate(features):
            for col_index, name in enumerate(names):
                X[row_index, col_index] = item.get(name, 0.0)

        classes: list[dict[str, Any]] | None
        if label == "action":
            unique = sorted(set(raw_labels))
            mapping = {key: index for index, key in enumerate(unique)}
            y = np.asarray([mapping[key] for key in raw_labels], dtype=np.int64)
            classes = [json.loads(key) for key in unique]
        elif label == "index":
            y = np.asarray(raw_labels, dtype=np.int64)
            classes = None
        else:
            y = np.asarray(raw_labels, dtype=np.float64)
            classes = None

        meta: dict[str, Any] = {
            "label": label,
            "feature_names": names,
            "classes": classes,
            "n_samples": int(X.shape[0]),
            "n_features": len(names),
            "n_skipped": skipped,
            "run_ids": sorted({row.run_id for row in used_rows}),
        }
        return X, y, meta


def _dump_json(value: JsonLike) -> str:
    """把 JSON 字符串 / dict / Pydantic 模型统一存成字符串。"""
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8")
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _json_default(value: Any) -> Any:
    """json.dumps 的兜底：支持 numpy 标量/数组。"""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _action_class(action: Mapping[str, Any]) -> dict[str, Any] | None:
    """动作类别：去掉 note 和 None 字段后剩下的内容。"""
    cleaned = {
        str(key): value for key, value in action.items() if key != "note" and value is not None
    }
    return cleaned or None


def _flatten_features(value: Any, prefix: str = "") -> dict[str, float]:
    """把嵌套状态展平成 ``path -> float``；只保留有限数值。"""
    result: dict[str, float] = {}
    if isinstance(value, Mapping):
        for key in sorted(value, key=lambda item: str(item)):
            name = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_features(value[key], name))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            result.update(_flatten_features(item, f"{prefix}[{index}]"))
    elif isinstance(value, bool):
        result[prefix or "value"] = 1.0 if value else 0.0
    elif isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        if np.isfinite(number):
            result[prefix or "value"] = number
    return result
