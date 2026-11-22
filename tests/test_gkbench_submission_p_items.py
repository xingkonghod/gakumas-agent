"""gkbench 提交适配器（``submissions/expectimax/algo.py``）的 P 道具接入测试。

不联网、不跑 gkbench 托管：把提交当成普通模块 import（需要本地 ``data/bench_repo``
的 ``gkbench`` 包），验证 ``ctx.loadout.produce_item_ids`` -> ``PItemSpec`` 的
解析、缓存、开关与 ``ExpectState`` 接线。缺 bench_repo/卡表时 skip。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH_REPO = ROOT / "data" / "bench_repo"
SUBMISSION_DIR = ROOT / "submissions" / "expectimax"


@pytest.fixture(scope="module")
def algo():
    if not (BENCH_REPO / "gkbench" / "algos" / "base.py").is_file():
        pytest.skip("缺少 data/bench_repo（gkbench 本地克隆）")
    if not (ROOT / "data" / "knowledge" / "card_table.json").is_file():
        pytest.skip("缺少 data/knowledge/card_table.json")
    # 提交文件按 gkbench 沙盒的口径 import：bench repo + 提交目录加进 sys.path。
    for path in (str(BENCH_REPO), str(SUBMISSION_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(
        "gkbench_submission_algo", SUBMISSION_DIR / "algo.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


#: p_items.json（1115 件；2026-09-16 中文 master + 上游新增 47）里一个「训练/考试开始时」道具。
EXAM_START_ITEM_ID = "pitem_02-3-293-0"


def test_resolve_p_items_from_loadout(algo) -> None:
    policy = algo.ExpectimaxAlgo()
    resolved = policy._resolve_p_items(
        {"produce_item_ids": [EXAM_START_ITEM_ID, "pitem_no-such-item-999"]}
    )
    assert resolved
    meta = policy._p_items_meta
    assert meta["ids"] == 2
    assert meta["known"] == 1
    assert meta["unknown"] == ["pitem_no-such-item-999"]
    assert meta["implemented"] > 0
    # 一局只解析一次（同一实例复用，不重复读数据/解析）。
    again = policy._resolve_p_items({"produce_item_ids": [EXAM_START_ITEM_ID]})
    assert again is resolved


def test_p_items_switch_off(algo) -> None:
    policy = algo.ExpectimaxAlgo(p_items=False)
    assert policy._resolve_p_items({"produce_item_ids": [EXAM_START_ITEM_ID]}) == ()
    assert policy._p_items_meta["enabled"] is False


def test_loadout_without_produce_items(algo) -> None:
    policy = algo.ExpectimaxAlgo()
    assert policy._resolve_p_items({}) == ()
    assert policy._p_items_meta["ids"] == 0
    assert "unknown" not in policy._p_items_meta


def test_missing_p_item_data_is_reported_not_silent(algo, monkeypatch) -> None:
    """数据文件缺失：仍按空清单跑（保证动作合法），但 meta 里显式记原因。"""
    monkeypatch.setattr(
        algo,
        "_p_items_candidates",
        lambda: iter([Path("no/such/p_items.json")]),
    )
    algo._load_p_item_catalog.cache_clear()
    try:
        policy = algo.ExpectimaxAlgo()
        resolved = policy._resolve_p_items({"produce_item_ids": [EXAM_START_ITEM_ID]})
        assert resolved == ()
        assert "error" in policy._p_items_meta
        assert "p_items.json" in policy._p_items_meta["error"]
    finally:
        monkeypatch.undo()
        algo._load_p_item_catalog.cache_clear()


def test_state_carries_p_items_into_expect_state(algo) -> None:
    policy = algo.ExpectimaxAlgo()
    specs = policy._resolve_p_items({"produce_item_ids": [EXAM_START_ITEM_ID]})
    obs = {
        "hand": [],
        "deck": [],
        "grave": [],
        "lost": [],
        "num": {},
        "exam": {},
        "status": [],
        "legal": [["end"]],
    }
    state = policy._state(obs, 1000, 2000, p_items=specs)
    assert state.p_items == specs
    assert state.p_item_uses == ()


def test_decide_reports_p_items_in_meta(algo) -> None:
    """端到端：loadout 的 P 道具进搜索状态，并在 Decision.meta 里可复盘。"""
    policy = algo.ExpectimaxAlgo(budget_ms=80, max_nodes=20_000)
    rows = policy._ensure_rows()
    assert rows, "卡表应能加载"
    (card_id, upgrade), _name, _row = next(
        ((key, value[0], value[1]) for key, value in rows.items())
    )
    obs = {
        "v": "uiobs.v1",
        "i": 0,
        "hand": [{"id": card_id, "u": upgrade}],
        "deck": [],
        "grave": [],
        "lost": [],
        "legal": [["play", 0], ["end"]],
        "num": {
            "score": 0,
            "stamina": 30,
            "max_stamina": 30,
            "block": 0,
            "plays": 0,
            "playable": 0,
        },
        "exam": {"turn": 1, "limit": 3, "permil": [1000, 1000, 1000], "types": [1, 1, 1]},
        "status": [],
        "stance": ["None", 0],
    }
    ctx = types.SimpleNamespace(
        obs=obs,
        budget=1.0,
        meta={},
        loadout={"produce_item_ids": [EXAM_START_ITEM_ID]},
    )
    decision = policy.decide(ctx)
    assert decision.action in {("play", 0), ("end",)}
    assert decision.meta["p_items"]["ids"] == 1
    assert decision.meta["p_items"]["implemented"] > 0
