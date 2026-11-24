"""T7③ 标注闭环的回归端：夹具里每条人工标注用例都必须持续成立。

夹具 ``tests/fixtures/review_regressions.json`` 由
``scripts/annotations_to_regression.py`` 从复盘页导出标注转换而来：
期望值在**转换时**冻结（人工复核过的代码版本算出），本测试只重算比对——
以后 run_replay 重放语义或 trace 复盘口径变了，同观测不再同状态，这里立刻红。

``provenance=synthetic-demo`` 的条目是演示闭环的合成样例（不是真机 ground
truth）；真机跑局标注后追加真实案例，测试自动逐条覆盖（parametrize 收集）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.data.run_replay import replay, state_to_dict
from gkagent.report.annotations import FIXTURE_SCHEMA
from gkagent.runtime.trace import summarize_traces

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "review_regressions.json"


def _load() -> dict:
    if not FIXTURE.exists():
        return {"schema": FIXTURE_SCHEMA, "cases": []}
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _cases() -> list[dict]:
    return [case for case in _load().get("cases") or [] if isinstance(case, dict)]


def test_fixture_schema_and_provenance() -> None:
    payload = _load()
    assert payload["schema"] == FIXTURE_SCHEMA
    for case in payload["cases"]:
        assert isinstance(case.get("id"), str)
        assert case.get("kind") in ("replay", "trace")
        assert isinstance(case.get("expect"), dict)
        assert case.get("provenance"), "用例必须带 provenance（真机标注/合成演示要分清）"


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case.get("id")))
def test_annotation_regression_case(case: dict) -> None:
    if case["kind"] == "replay":
        states = replay(case["events"])
        assert states, "用例观测序列不能为空"
        assert state_to_dict(states[-1]) == case["expect"], (
            f"重放终态与冻结期望不一致（{case['id']}）：同观测序列必须同状态"
        )
    else:
        summary = summarize_traces(case["rows"])
        actual = {
            "anomaly": bool(summary["anomalies"]),
            "outcomes": summary["outcomes"],
            "retaps": summary["retaps"],
            "lost": summary["lost"],
        }
        assert actual == case["expect"], f"轨迹复盘口径与冻结期望不一致（{case['id']}）"
