"""P 道具数据接入层（``gkagent.data.p_items_db``）的回归测试。

覆盖：catalog 索引、未知 id 显式上报（不静默丢弃/不猜）、重复 id、缺文件报错、
真数据（**1115 件道具** = 本地中文 master 1068 + 上游新增 47）可加载、以及有
gkbench 题模板时 505 个 loadout 的覆盖率（``data/bench_local/`` gitignore，
缺数据自动 skip）。
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
    assert len(catalog) == 1115
    coverage = catalog_coverage(catalog)
    assert coverage["items"] == 1115
    assert coverage["implemented"] > 0
    # 与 test_p_items.py 同一批已实现效果类型（防止数据层解析口径变化）。
    implemented = coverage["implemented"]
    assert implemented >= 200
    # B7：47 条上游新增里 22 条的新触发 id 没有中文触发句 → 当时条件未知；
    # B8 从 id 解析 16 件、B10 把 p_card_search 限定结构化后条件未知清零。
    assert coverage["condition_unknown"] == 0

    known_id = catalog.ids[0]
    loadout = resolve_produce_item_ids([known_id, "pitem_no-such-item-999"], catalog=catalog)
    assert loadout.known_ids == (known_id,)
    assert loadout.unknown_ids == ("pitem_no-such-item-999",)
    assert len(loadout.specs) == len(catalog.specs_for(known_id))


def test_real_catalog_includes_yaml_only_new_items() -> None:
    """B7：本地 masterTrans（2026-09-16，1068 件）没有、yaml 才有的 47 条已进 catalog。

    - 47 条都能解析出至少 1 段 spec（5 条育成期道具没有考试效果 → 仍是 unknown no-op 段）；
    - 中文描述缺失处用 yaml 日文 + 显式标记（``i18n_text_source="ja"``），不猜译文；
    - 新触发 id 没有中文触发句的记 ``condition_known=False``（条件未知）。
    """
    path = Path(__file__).resolve().parents[1] / "data" / "knowledge" / "p_items.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    items = {row["id"]: row for row in payload["items"]}
    stats = payload["stats"]
    assert stats["count"] == 1115
    assert stats["items_local_master"] == 1068
    assert stats["items_from_yaml"] == 47
    assert stats["items_i18n_text_ja"] == 47
    # B8：新语法 trigger id 从 id 后缀解析（16 件）；B10：p_card_search 限定
    # 结构化（指定卡名/偶像固有/效果组/费用/区域张数）→ 条件未知 6→0、
    # 触发未知 103→3；P1-3：hold 保留区建模 + period810_hotfix 非限定标记
    # 证实 → 触发未知 3→0（B10 遗留清零）。
    assert stats["items_condition_unknown"] == 0
    assert stats["items_trigger_unknown"] == 0
    assert stats["items_trigger_id_parsed"] >= 16
    assert stats["effects_depends_on"] > 0
    assert stats["effects_percent_max"] > 0
    assert stats["effects_zero_stack"] > 0

    new_rows = [row for row in items.values() if row.get("i18n_text_source") == "ja"]
    assert len(new_rows) == 47
    catalog = get_catalog()
    for row in new_rows:
        assert row["text_zh"] == "" and row["text_ja"], row["id"]
        assert row["i18n_name_source"] in {"translation_new.json", "ja"}, row["id"]
        # 47 条全部进 catalog：有考试效果的按效果段展开，没效果的落成 unknown no-op 段。
        assert catalog.specs_for(row["id"]), row["id"]
    assert sum(1 for row in new_rows if row.get("condition_known") is False) == 0
    assert sum(1 for row in new_rows if row.get("trigger_known") is False) == 0

    # gkbench 505 题模板原先的 11 个未知 id 全部落在新增 47 条里（现在都能解析）。
    for item_id in ("pitem_01-3-349-0", "pitem_02-3-336-1", "pitem_03-3-334-0", "pitem_3-258-research-event-009"):
        assert item_id in items and catalog.specs_for(item_id), item_id


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

    期望（p_items.json = 1115 件，B7 已覆盖上游新增 47 条）：2686 个 id
    （每局 1–10 个）/ 83 个唯一 / **83 个已知 / 0 个未知**。
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
    assert len(unique_known) == 83
    assert unique_unknown == set()
    # 每局至少 1 个 P 道具能被结算（B7 后不再有快照缺行的未知 id）。
    for save in saves:
        resolved = resolve_produce_item_ids(
            (save.get("loadout") or {}).get("produce_item_ids"), catalog=catalog
        )
        assert resolved.specs, save.get("id")
