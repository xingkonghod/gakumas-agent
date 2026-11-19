"""UINet（GKMSUINet, MIT）ONNX 推理的运行时封装。

- 模型：``data/models/gkms_uinet.onnx``（Ver1.1-Hingebungsvoll，读 UIObs v1）；
- 主数据：``data/models/uinet_master/`` 下 9 张 gakumasu-diff 表（YAML）；
- 包：``uv pip install --python .venv\\Scripts\\python.exe -e data/GKMSUINet``。

环境变量可覆盖：``GKMS_UINET_MODEL`` / ``GKMS_UINET_MASTER`` /
``GKMS_UINET_THREADS``（ONNX intra-op 线程，默认 1）。

首次加载主数据要解析约 120MB YAML（实测 ~50s）；解析结果缓存在同目录的
``master.pkl``（约 18MB，加载 ~0.2s），表文件有更新时自动重建。这里的 pickle
只读本模块自己写的缓存文件，不接受外部输入。

本模块不吞异常：模型/主数据缺失、ONNX 报错都抛给调用方，由
``LessonPolicy._try_uinet`` 统一退回规则引擎。
"""

from __future__ import annotations

import os
import pickle
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_MASTER",
    "DEFAULT_MODEL",
    "UinetOutput",
    "available",
    "master_dir",
    "model_path",
    "predict",
    "reset_cache",
]

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL = _REPO_ROOT / "data" / "models" / "gkms_uinet.onnx"
DEFAULT_MASTER = _REPO_ROOT / "data" / "models" / "uinet_master"

TABLE_NAMES = (
    "ProduceCard",
    "ProduceCardCustomize",
    "ProduceCardGrowEffect",
    "ProduceCardSearch",
    "ProduceExamEffect",
    "ProduceExamTrigger",
    "ProduceExamStatusEnchant",
    "ProduceDrink",
    "ProduceDrinkEffect",
)
_TABLE_SUFFIXES = (".jsonl", ".json", ".yaml", ".yml")
_CACHE_SCHEMA = "gkms.uinet.master.pkl.v1"


@dataclass(frozen=True)
class UinetOutput:
    """一次 ``Policy.decide`` 的结果（动作是 UIObs ``legal`` 里的一项）。"""

    action: tuple[Any, ...]
    probs: tuple[float, ...]
    score_quantiles: dict[str, int]
    elapsed_ms: float


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else default


def model_path(model: str | Path | None = None) -> Path:
    """模型文件路径：显式参数 > ``GKMS_UINET_MODEL`` > ``data/models/gkms_uinet.onnx``。"""
    if model:
        return Path(model).expanduser()
    return _env_path("GKMS_UINET_MODEL", DEFAULT_MODEL)


def master_dir(master: str | Path | None = None) -> Path:
    """主数据目录：显式参数 > ``GKMS_UINET_MASTER`` > ``data/models/uinet_master``。"""
    if master:
        return Path(master).expanduser()
    return _env_path("GKMS_UINET_MASTER", DEFAULT_MASTER)


def _threads(threads: int | None) -> int:
    if threads is not None:
        return max(1, min(8, int(threads)))
    try:
        parsed = int(os.environ.get("GKMS_UINET_THREADS", "1"))
    except ValueError:
        parsed = 1
    return max(1, min(8, parsed))


def _table_file(directory: Path, table: str) -> Path | None:
    for suffix in _TABLE_SUFFIXES:
        path = directory / (table + suffix)
        if path.is_file():
            return path
    return None


def _missing_tables(directory: Path) -> list[str]:
    return [table for table in TABLE_NAMES if _table_file(directory, table) is None]


def available(
    model: str | Path | None = None, master: str | Path | None = None
) -> bool:
    """模型 + 9 张主数据表都在才返回 True（不 import gkms_uinet/onnxruntime）。"""
    return model_path(model).is_file() and not _missing_tables(master_dir(master))


def _signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    """主数据文件签名：表被更新/替换后 pickle 缓存自动失效。"""
    rows: list[tuple[str, int, int]] = []
    for table in TABLE_NAMES:
        path = _table_file(directory, table)
        if path is None:
            continue
        stat = path.stat()
        rows.append((path.name, int(stat.st_size), int(stat.st_mtime_ns)))
    return tuple(rows)


def _load_master(directory: Path):
    """读主数据：优先 ``master.pkl`` 缓存，否则用 gkms_uinet 的 Master 解析并写回缓存。"""
    missing = _missing_tables(directory)
    if missing:
        raise FileNotFoundError(f"UINet 主数据缺表: {', '.join(missing)}（目录 {directory}）")
    from gkms_uinet.master import Master

    signature = _signature(directory)
    cache = directory / "master.pkl"
    if cache.is_file():
        try:
            doc = pickle.loads(cache.read_bytes())
            if (
                isinstance(doc, dict)
                and doc.get("schema") == _CACHE_SCHEMA
                and doc.get("signature") == signature
                and isinstance(doc.get("attrs"), dict)
            ):
                master = Master.__new__(Master)
                master.__dict__.update(doc["attrs"])
                return master
        except (OSError, pickle.PickleError, AttributeError, ValueError, EOFError):
            pass
    master = Master(directory)
    try:
        cache.write_bytes(
            pickle.dumps(
                {"schema": _CACHE_SCHEMA, "signature": signature, "attrs": master.__dict__},
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        )
    except OSError:
        pass
    return master


@lru_cache(maxsize=4)
def _policy(model_key: str, master_key: str, threads: int):
    from gkms_uinet import Policy

    return Policy(model_key, _load_master(Path(master_key)), threads=threads)


def reset_cache() -> None:
    """清掉已加载的 ONNX 会话/主数据（测试或换模型后调用）。"""
    _policy.cache_clear()


def predict(
    obs: dict[str, Any],
    *,
    model: str | Path | None = None,
    master: str | Path | None = None,
    threads: int | None = None,
) -> UinetOutput:
    """UIObs v1 → UINet 的贪心动作（含每个 legal 动作的概率）。

    模型/主数据缺失、ONNX 报错都直接抛异常；调用方负责退回规则。
    """
    model_file = model_path(model)
    if not model_file.is_file():
        raise FileNotFoundError(f"UINet 模型不存在: {model_file}")
    master_path = master_dir(master)
    started = time.perf_counter()
    policy = _policy(str(model_file), str(master_path), _threads(threads))
    raw = policy.decide(obs)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    action = tuple(raw.get("action") or ())
    probs = tuple(float(value) for value in raw.get("probs") or ())
    quantiles = {
        str(key): int(value) for key, value in (raw.get("score_quantiles") or {}).items()
    }
    return UinetOutput(
        action=action, probs=probs, score_quantiles=quantiles, elapsed_ms=elapsed_ms
    )
