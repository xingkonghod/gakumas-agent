"""P 道具数据接入：对局 loadout 的 ``produce_item_ids`` → ``PItemSpec``（T5 剩余机制）。

背景（2026-11-22）：``sim/p_items.py`` 早有「事件 → 增量」的被动结算接口，
``LessonSim`` / ``ExpectState`` 也都在触发时机上调它；缺的是**真实对局到底带哪些
P 道具**。真机采集的 ``traffic.jsonl`` 里没有 produce 编成字段（3.2MB 全文件 0 命中
``produceItem/itemIds/p_item``），所以培育侧只能等 T6/D1 补采；离线能接的完整数据源
是 gkbench 的 505 个题模板：``saves.jsonl[].loadout.produce_item_ids``（每局 5 个，
83 个唯一 id）——和 gkbench 适配器/本地跑分器/``LessonSim`` 用的是同一份公开 loadout，
不涉及种子。

数据来源：``data/knowledge/p_items.json``（``scripts/build_p_items.py`` 解析
``ProduceItem.json`` + gakumasu-diff ``ProduceItem.yaml`` 生成，**1115 件道具**：
本地中文 master 1068 件 + 2026-11 上游新增 47 件——新增件卡名用仓库自译表、
描述只有日文、条件未知的 spec 保守不触发，见 ``PItemSpec.condition_known``）。

口径（不猜、不静默）：

- **id 精确匹配**：``pitem_02-3-293-0`` 就是 catalog 里的同名行；不做「去掉 -N 后缀
  当强化前版本」之类的兜底（强化变体数值不同，猜错会凭空加减分）。catalog 快照
  2026-11-22（B7）已覆盖上游 1115 件；仍不在 catalog 里的 id 会落进 ``unknown_ids``，
  由调用方**显式上报**。
- **缺失数据文件直接抛错**（:class:`PItemDataUnavailable`），不当"没有 P 道具"。
- 一个道具记录的每个 ``effects`` 分段展开成一条 ``PItemSpec``（``record_to_specs``
  同口径），未实现的 effect_type 保留为 ``implemented=False`` 的 no-op，便于统计覆盖率。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from gkagent.sim.p_items import PItemSpec, record_to_specs, summarize

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "data" / "knowledge" / "p_items.json"


class PItemDataUnavailable(RuntimeError):
    """P 道具数据文件缺失/格式不对（显式报错，不静默当空）。"""


def default_path() -> Path:
    return DEFAULT_PATH


@dataclass(frozen=True)
class PItemCatalog:
    """``p_items.json`` 的只读索引：``item_id -> (PItemSpec, ...)``。"""

    path: Path
    by_id: Mapping[str, tuple[PItemSpec, ...]]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self.by_id)

    def specs_for(self, item_id: str) -> tuple[PItemSpec, ...]:
        """单个道具 id 的全部 spec 段；未知 id 返回空 tuple（调用方须自行区分）。"""
        return tuple(self.by_id.get(str(item_id), ()))

    def __len__(self) -> int:
        return len(self.by_id)


def load_p_item_catalog(path: str | Path | None = None) -> PItemCatalog:
    """读 ``p_items.json`` 并建 id 索引；文件缺失/格式错**显式报错**。"""
    resolved = Path(path) if path is not None else DEFAULT_PATH
    if not resolved.is_file():
        raise PItemDataUnavailable(
            f"缺少 P 道具数据 {resolved}；先跑 .venv\\Scripts\\python.exe scripts\\build_p_items.py"
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - 坏文件路径
        raise PItemDataUnavailable(f"读不了 P 道具数据 {resolved}：{exc!r}") from exc
    rows = payload.get("items") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise PItemDataUnavailable(f"P 道具数据格式不对（缺 items 列表）：{resolved}")

    by_id: dict[str, tuple[PItemSpec, ...]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        item_id = str(row.get("id") or "")
        if not item_id:
            continue
        stats = record_to_specs(row)
        by_id[item_id] = tuple(stats)
    return PItemCatalog(path=resolved, by_id=by_id)


@lru_cache(maxsize=8)
def _cached_catalog(path: str) -> PItemCatalog:
    return load_p_item_catalog(path)


def get_catalog(path: str | Path | None = None) -> PItemCatalog:
    """带缓存的 catalog（同一路径只读一次；本地跑分器每道题都会调用）。"""
    resolved = Path(path) if path is not None else DEFAULT_PATH
    return _cached_catalog(str(resolved))


@dataclass(frozen=True)
class PItemLoadout:
    """一次对局 loadout 解析结果：specs + 已知/未知/重复 id（全部显式）。"""

    ids: tuple[str, ...] = ()
    known_ids: tuple[str, ...] = ()
    unknown_ids: tuple[str, ...] = ()
    duplicate_ids: tuple[str, ...] = ()
    specs: tuple[PItemSpec, ...] = ()

    @property
    def implemented_specs(self) -> tuple[PItemSpec, ...]:
        return tuple(spec for spec in self.specs if spec.implemented)

    @property
    def has_unknown(self) -> bool:
        return bool(self.unknown_ids)

    def summary(self) -> dict:
        """覆盖率摘要（给跑分报告 / 日志 / 测试断言用）。"""
        stats = summarize(self.specs)
        return {
            "ids": len(self.ids),
            "known_ids": len(self.known_ids),
            "unknown_ids": list(self.unknown_ids),
            "duplicate_ids": list(self.duplicate_ids),
            "specs": stats["specs"],
            "implemented": stats["implemented"],
            "noop": stats["noop"],
            "condition_unknown": stats["condition_unknown"],
            "trigger_unknown": stats["trigger_unknown"],
            "depends_on_specs": stats["depends_on_specs"],
            "percent_max_specs": stats["percent_max_specs"],
            "zero_stack_specs": stats["zero_stack_specs"],
            "noop_reasons": stats["noop_reasons"],
            "implemented_effect_types": stats["implemented_effect_types"],
            "noop_effect_types": stats["noop_effect_types"],
        }


def resolve_produce_item_ids(
    item_ids: Iterable[str] | None,
    catalog: PItemCatalog | None = None,
) -> PItemLoadout:
    """``loadout.produce_item_ids`` → :class:`PItemLoadout`（未知 id 显式上报）。

    - 空/缺字段（``None``）→ 空 loadout（不算错：hajime 题没有这个字段）；
    - 重复 id 去重（保留首次出现顺序），重复项记进 ``duplicate_ids``；
    - 未知 id 不丢、不猜，按出现顺序记进 ``unknown_ids``。
    """
    if item_ids is None:
        return PItemLoadout()
    cat = catalog if catalog is not None else get_catalog()
    ids: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    unknown: list[str] = []
    known: list[str] = []
    specs: list[PItemSpec] = []
    for raw in item_ids:
        item_id = str(raw or "").strip()
        if not item_id:
            continue
        if item_id in seen:
            duplicates.append(item_id)
            continue
        seen.add(item_id)
        ids.append(item_id)
        resolved = cat.specs_for(item_id)
        if resolved:
            known.append(item_id)
            specs.extend(resolved)
        else:
            unknown.append(item_id)
    return PItemLoadout(
        ids=tuple(ids),
        known_ids=tuple(known),
        unknown_ids=tuple(unknown),
        duplicate_ids=tuple(dict.fromkeys(duplicates)),
        specs=tuple(specs),
    )


def catalog_coverage(catalog: PItemCatalog) -> dict:
    """catalog 全量覆盖率（文档/测试用：有多少 spec 实现了）。"""
    all_specs = tuple(spec for group in catalog.by_id.values() for spec in group)
    stats = summarize(all_specs)
    return {
        "items": len(catalog),
        "specs": stats["specs"],
        "implemented": stats["implemented"],
        "noop": stats["noop"],
        "condition_unknown": stats["condition_unknown"],
        "trigger_unknown": stats["trigger_unknown"],
        "depends_on_specs": stats["depends_on_specs"],
        "percent_max_specs": stats["percent_max_specs"],
        "zero_stack_specs": stats["zero_stack_specs"],
        "noop_reasons": stats["noop_reasons"],
    }


__all__ = [
    "DEFAULT_PATH",
    "PItemCatalog",
    "PItemDataUnavailable",
    "PItemLoadout",
    "catalog_coverage",
    "default_path",
    "get_catalog",
    "load_p_item_catalog",
    "resolve_produce_item_ids",
]
