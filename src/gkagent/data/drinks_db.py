"""M6 饮料数据接入：对局 loadout 的 ``drink_ids`` → ``DrinkSpec``（效果段列表）。

数据来源：``data/knowledge/drinks.json``（``scripts/build_drinks.py`` 解析
``ProduceDrink.yaml`` + ``ProduceDrinkEffect.yaml`` + ``ProduceExamEffect.yaml`` +
``ProduceExamStatusEnchant.yaml`` + 中文 master 生成，**29 瓶 / 51 效果段**）。

口径（与 ``data/p_items_db.py`` 同纪律，不猜、不静默）：

- **id 精确匹配**；不在 catalog 里的 id 落进 ``unknown_ids`` 显式上报。
- **不去重**：``drink_ids`` 里每个 id 是一瓶（一个槽位），W9 带两瓶同 id 苏打
  （``pdrink_00-2-010`` ×2）就是两个槽位，与 P 道具去重口径不同。
- 未实现的效果段保留 ``implemented=False`` 的 no-op（结算整段跳过），便于统计覆盖率。
- 缺失数据文件直接抛错（:class:`DrinkDataUnavailable`），不当"没有饮料"。

**opt-in**：调用方（local_bench / sim_produce）默认不注入饮料（``drink_ids=None``
→ 空 specs，逐位不变）；显式给 ids 才解析注入 ``LessonConfig.drinks``。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from gkagent.sim.drinks import DrinkEffect
from gkagent.sim.lesson import DrinkSpec

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "data" / "knowledge" / "drinks.json"


class DrinkDataUnavailable(RuntimeError):
    """饮料数据文件缺失/格式不对（显式报错，不静默当空）。"""


def default_path() -> Path:
    return DEFAULT_PATH


def record_to_spec(row: Mapping) -> DrinkSpec:
    """一条饮料 catalog 记录 → ``DrinkSpec``（效果段列表，cost=0/uses=1）。"""
    effects: list[DrinkEffect] = []
    for eff in row.get("effects") or []:
        if not isinstance(eff, Mapping):
            continue
        effects.append(
            DrinkEffect(
                kind=str(eff.get("kind") or "unknown"),
                value=int(eff.get("value") or 0),
                turns=int(eff.get("turns") or 0),
                trigger=str(eff.get("trigger") or ""),
                search=str(eff.get("search") or ""),
                move_to=str(eff.get("move_to") or ""),
                effect_type=str(eff.get("effect_type") or ""),
                implemented=bool(eff.get("implemented", False)),
                rng=str(eff.get("rng") or "none"),
            )
        )
    return DrinkSpec(
        name=str(row.get("name") or row.get("id") or ""),
        cost=0,
        effect_type="multi",
        value=0,
        uses=1,
        effects=tuple(effects),
    )


@dataclass(frozen=True)
class DrinkCatalog:
    """``drinks.json`` 的只读索引：``drink_id -> spec``。"""

    path: Path
    by_id: Mapping[str, DrinkSpec]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self.by_id)

    def spec_for(self, drink_id: str) -> DrinkSpec | None:
        return self.by_id.get(str(drink_id))

    def __len__(self) -> int:
        return len(self.by_id)


def load_drink_catalog(path: str | Path | None = None) -> DrinkCatalog:
    resolved = Path(path) if path is not None else DEFAULT_PATH
    if not resolved.is_file():
        raise DrinkDataUnavailable(
            f"缺少饮料数据 {resolved}；先跑 .venv\\Scripts\\python.exe scripts\\build_drinks.py"
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover
        raise DrinkDataUnavailable(f"读不了饮料数据 {resolved}：{exc!r}") from exc
    rows = payload.get("drinks") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise DrinkDataUnavailable(f"饮料数据格式不对（缺 drinks 列表）：{resolved}")
    by_id: dict[str, DrinkSpec] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        drink_id = str(row.get("id") or "")
        if drink_id:
            by_id[drink_id] = record_to_spec(row)
    return DrinkCatalog(path=resolved, by_id=by_id)


@lru_cache(maxsize=8)
def _cached_catalog(path: str) -> DrinkCatalog:
    return load_drink_catalog(path)


def get_catalog(path: str | Path | None = None) -> DrinkCatalog:
    resolved = Path(path) if path is not None else DEFAULT_PATH
    return _cached_catalog(str(resolved))


@dataclass(frozen=True)
class DrinkLoadout:
    """一次对局 loadout 饮料解析结果：specs（按槽位顺序，含重复）+ 已知/未知 id。"""

    ids: tuple[str, ...] = ()
    known_ids: tuple[str, ...] = ()
    unknown_ids: tuple[str, ...] = ()
    specs: tuple[DrinkSpec, ...] = ()

    @property
    def has_unknown(self) -> bool:
        return bool(self.unknown_ids)

    def summary(self) -> dict:
        total = sum(len(spec.effects) for spec in self.specs)
        impl = sum(
            1 for spec in self.specs for eff in spec.effects if eff.implemented
        )
        return {
            "ids": len(self.ids),
            "known_ids": len(self.known_ids),
            "unknown_ids": list(self.unknown_ids),
            "slots": len(self.specs),
            "segments": total,
            "implemented": impl,
        }


def resolve_drink_ids(
    drink_ids: Iterable[str] | None,
    catalog: DrinkCatalog | None = None,
) -> DrinkLoadout:
    """``loadout.drink_ids`` → :class:`DrinkLoadout`（不去重，未知 id 显式上报）。

    空/缺字段（``None``）→ 空 loadout（opt-in 默认关，逐位不变）。
    """
    if drink_ids is None:
        return DrinkLoadout()
    cat = catalog if catalog is not None else get_catalog()
    ids: list[str] = []
    known: list[str] = []
    unknown: list[str] = []
    specs: list[DrinkSpec] = []
    for raw in drink_ids:
        drink_id = str(raw or "").strip()
        if not drink_id:
            continue
        ids.append(drink_id)
        spec = cat.spec_for(drink_id)
        if spec is not None:
            known.append(drink_id)
            specs.append(spec)
        else:
            unknown.append(drink_id)
    return DrinkLoadout(
        ids=tuple(ids),
        known_ids=tuple(known),
        unknown_ids=tuple(dict.fromkeys(unknown)),
        specs=tuple(specs),
    )


__all__ = [
    "DEFAULT_PATH",
    "DrinkCatalog",
    "DrinkDataUnavailable",
    "DrinkLoadout",
    "default_path",
    "get_catalog",
    "load_drink_catalog",
    "record_to_spec",
    "resolve_drink_ids",
]
