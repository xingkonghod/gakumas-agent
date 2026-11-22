"""P 道具数据接入层（``gkagent.data.p_items_db``）的回归测试。

覆盖：catalog 索引、未知 id 显式上报（不静默丢弃/不猜）、重复 id、缺文件报错、
真数据（1068 件道具）可加载、以及有 gkbench 题模板时 505 个 loadout 的覆盖率
（``data/bench_local/`` gitignore，缺数据自动 skip）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.data.p_items_db import (
    PItemCatalog,
    PItemDataUnavailable,
    PItemLoadout,
    catalog_coverage,
    get_catalog,
    load_p_item_catalog,
    resolve_produce_item_ids,
)

ROOT = Path(__file__).resolve().parents[1]
HIF_SAVES = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif" / "saves.jsonl"


def _record(
    item_id: str,
    *,
    name: str = "测试道具",
    trigger: str = "exam_start",
    effects: list[dict] | None = None,
    trigger_params: dict | None = None,
    condition: str = "",
    max_uses: int = 0,
) -> dict:
    return {
        "id": item_id,
        "name": name,
        "rarity": "SR",
        "trigger": trigger,
        "trigger_params": trigger_params or {},
        "condition": condition,
        "max_uses": max_uses,
        "effects": effects
        if effects is not None
        else [{"type": "ExamLesson", "label": "打分", "values": {"value1": 5}}],
        "text_zh": "测试描述",
    }


def _write_catalog(tmp_path: Path, items: list[dict]) -> Path:
    path = tmp_path / "p_items.json"
    path.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    return path


# ---- catalog ---------------------------------------------------------------


def test_load_catalog_indexes_records_by_id(tmp_path: Path) -> None:
    path = _write_catalog(
        tmp_path,
        [
            _record(
                "pitem_test-001",
                effects=[
                    {"type": "ExamBlock", "label": "元气", "values": {"value1": 3}},
                    {"type": "ExamPlayableValueAdd", "label": "使用数", "values": {"count": 1}},
                ],
            ),
            _record("pitem_test-002", trigger="turn_start"),
        ],
    )
    catalog = load_p_item_catalog(path)
    assert isinstance(catalog, PItemCatalog)
    assert len(catalog) == 2
    assert catalog.ids == ("pitem_test-001", "pitem_test-002")
    specs = catalog.specs_for("pitem_test-001")
    assert [spec.effect_type for spec in specs] == ["ExamBlock", "ExamPlayableValueAdd"]
    assert [spec.target for spec in specs] == ["vitality", "extra_plays"]
    assert catalog.specs_for("pitem_nope") == ()


def test_load_catalog_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PItemDataUnavailable, match="缺少 P 道具数据"):
        load_p_item_catalog(tmp_path / "nope.json")


def test_load_catalog_bad_format_raises(tmp_path: Path) -> None:
    path = tmp_path / "p_items.json"
    path.write_text(json.dumps({"items": "不是列表"}), encoding="utf-8")
    with pytest.raises(PItemDataUnavailable, match="格式不对"):
        load_p_item_catalog(path)


# ---- 单局 loadout 解析 ------------------------------------------------------


def test_resolve_known_ids_keeps_order_and_specs(tmp_path: Path) -> None:
    path = _write_catalog(
        tmp_path,
        [
            _record("pitem_a", effects=[{"type": "ExamLesson", "values": {"value1": 7}}]),
            _record("pitem_b", trigger="turn_start"),
        ],
    )
    catalog = load_p_item_catalog(path)
    loadout = resolve_produce_item_ids(["pitem_b", "pitem_a"], catalog=catalog)
    assert isinstance(loadout, PItemLoadout)
    assert loadout.ids == ("pitem_b", "pitem_a")
    assert loadout.known_ids == ("pitem_b", "pitem_a")
    assert loadout.unknown_ids == ()
    assert [spec.item_id for spec in loadout.specs] == ["pitem_b", "pitem_a"]
    assert loadout.has_unknown is False


def test_resolve_unknown_ids_are_explicit(tmp_path: Path) -> None:
    """catalog 快照之后新增的道具：显式列出，不猜、不静默丢。"""
    path = _write_catalog(tmp_path, [_record("pitem_a")])
    catalog = load_p_item_catalog(path)
    loadout = resolve_produce_item_ids(["pitem_a", "pitem_new-999"], catalog=catalog)
    assert loadout.known_ids == ("pitem_a",)
    assert loadout.unknown_ids == ("pitem_new-999",)
    assert loadout.has_unknown is True
    assert [spec.item_id for spec in loadout.specs] == ["pitem_a"]
    summary = loadout.summary()
    assert summary["unknown_ids"] == ["pitem_new-999"]
    assert summary["ids"] == 2 and summary["known_ids"] == 1


def test_resolve_duplicates_are_reported_once(tmp_path: Path) -> None:
    path = _write_catalog(tmp_path, [_record("pitem_a")])
    catalog = load_p_item_catalog(path)
    loadout = resolve_produce_item_ids(["pitem_a", "pitem_a", "pitem_a"], catalog=catalog)
    assert loadout.ids == ("pitem_a",)
    assert loadout.duplicate_ids == ("pitem_a",)
    assert len(loadout.specs) == 1


def test_resolve_none_or_empty_is_empty_loadout() -> None:
    assert resolve_produce_item_ids(None).ids == ()
    assert resolve_produce_item_ids([]).specs == ()
    empty = resolve_produce_item_ids([])
    assert empty.summary()["unknown_ids"] == []


# ---- 真数据（p_items.json tracked） ----------------------------------------


def test_real_catalog_loads_and_covers_implemented_types() -> None:
    catalog = get_catalog()
    assert len(catalog) == 1068
    coverage = catalog_coverage(catalog)
    assert coverage["items"] == 1068
    assert coverage["implemented"] > 0
    # 与 test_p_items.py 同一批已实现效果类型（防止数据层解析口径变化）。
    implemented = coverage["implemented"]
    assert implemented >= 200

    known_id = catalog.ids[0]
    loadout = resolve_produce_item_ids([known_id, "pitem_no-such-item-999"], catalog=catalog)
    assert loadout.known_ids == (known_id,)
    assert loadout.unknown_ids == ("pitem_no-such-item-999",)
    assert len(loadout.specs) == len(catalog.specs_for(known_id))


def test_get_catalog_is_cached() -> None:
    first = get_catalog()
    second = get_catalog()
    assert first is second


# ---- gkbench 题模板（gitignore；缺数据 skip） ------------------------------


def _load_hif_saves() -> list[dict]:
    if not HIF_SAVES.is_file():
        pytest.skip("缺少 data/bench_local/gkbench_dl/hif/saves.jsonl（见 docs/GKBENCH.md）")
    return [
        json.loads(line)
        for line in HIF_SAVES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_gkbench_saves_p_item_ids_resolve() -> None:
    """505 个 hif 题模板的 loadout.produce_item_ids 全部走接入层。

    期望（p_items.json = 2026-09-16 主数据快照）：2686 个 id（每局 1–10 个）/
    83 个唯一 / 72 个已知 / 11 个未知（快照之后新增的道具，显式上报、不猜）。
    """
    saves = _load_hif_saves()
    assert len(saves) == 505
    catalog = get_catalog()

    total_ids = 0
    unique_known: set[str] = set()
    unique_unknown: set[str] = set()
    duplicate_ids: set[str] = set()
    saves_with_items = 0
    resolved_specs = 0
    for save in saves:
        loadout = save.get("loadout") or {}
        ids = list(loadout.get("produce_item_ids") or [])
        if ids:
            saves_with_items += 1
        total_ids += len(ids)
        resolved = resolve_produce_item_ids(ids, catalog=catalog)
        resolved_specs += len(resolved.specs)
        unique_known.update(resolved.known_ids)
        unique_unknown.update(resolved.unknown_ids)
        duplicate_ids.update(resolved.duplicate_ids)
    assert saves_with_items == 505
    assert total_ids == 2686
    assert resolved_specs > 0
    assert duplicate_ids == set()
    assert len(unique_known) == 72
    assert unique_unknown == {
        "pitem_01-3-349-0",
        "pitem_02-3-336-1",
        "pitem_02-3-348-0",
        "pitem_02-3-354-0",
        "pitem_03-3-334-0",
        "pitem_03-3-337-0",
        "pitem_03-3-345-0",
        "pitem_03-3-345-1",
        "pitem_3-258-research-event-008",
        "pitem_3-258-research-event-009",
        "pitem_3-258-research-event-010",
    }
    # 每局至少 1 个 P 道具能被结算（未知的只是快照缺行，不是洗牌/牌组问题）。
    for save in saves:
        resolved = resolve_produce_item_ids(
            (save.get("loadout") or {}).get("produce_item_ids"), catalog=catalog
        )
        assert resolved.specs, save.get("id")
