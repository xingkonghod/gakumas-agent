"""T7③ 自动复盘页 + 人工标注转回归闭环单测。

覆盖验收点：
- build_review_html 纯函数（同输入同输出）、HTML 转义、内嵌 JSON 可解析；
- 周重复/轨迹异常高亮、合成轨迹显著标注、空态说明；
- write_review_page 原子写 + 文件名净化；
- parse_expected / normalize_annotations / cases_from_annotations / merge_cases；
- 三个 CLI（replay_run --verify/--compare、review_page、annotations_to_regression）；
- auto_produce 局末自动生成接线（源码级，与 C1 wiring 测试同约定）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from gkagent.data.run_replay import replay, state_to_dict
from gkagent.report.annotations import (
    FIXTURE_SCHEMA,
    SCHEMA,
    cases_from_annotations,
    merge_cases,
    normalize_annotations,
    parse_expected,
)
from gkagent.report.review_page import build_review_html, write_review_page
from gkagent.runtime.trace import summarize_traces

ROOT = Path(__file__).resolve().parents[1]

RECORD = {
    "episode": "ep-demo-review",
    "started_at": "2026-11-24 12:00:00",
    "weeks": [
        {"week": 1, "action": "train", "lesson_score": None, "attrs_after": [132, 165, 224], "stamina": 27},
        {"week": 2, "action": "lesson", "lesson_score": None, "attrs_after": [132, 170, 270],
         "stamina": 27, "note": "lesson_score 未读到（未用属性增量推算）"},
        {"week": 3, "action": "lesson", "lesson_score": 152, "attrs_after": [140, 180, 280], "stamina": 22},
    ],
    "exams": [{"kind": "mid", "rank": 3, "score": 217, "others": [603, 387, 217, 206, 205]}],
    "final": {"attrs": [140, 180, 280], "rank": 1, "exam_score": 17300, "eval_points": 5577, "grade": "C+"},
    "meta": {"audition_coefficient": 4.11},
}

TRACE_ROWS = [
    {"episode": "ep-demo-review", "step": 11, "screen": "action", "action": "tap-card",
     "point": [270, 600], "reason": "演示", "expect_kind": "change", "outcome": "confirmed", "tries": 0},
    {"episode": "ep-demo-review", "step": 12, "screen": "action", "action": "tap-card",
     "point": [270, 600], "reason": "演示", "expect_kind": "change", "outcome": "retap", "tries": 1},
    {"episode": "ep-demo-review", "step": 13, "screen": "dialog", "action": "confirm",
     "point": [300, 700], "reason": "演示", "expect_kind": "dialog-gone", "outcome": "lost", "tries": 2},
]


def _payload(annotations: list[dict]) -> dict:
    return {
        "schema": SCHEMA,
        "episode": "ep-demo-review",
        "fingerprint": "demo",
        "provenance": "synthetic-demo",
        "annotations": annotations,
    }


# ---------------------------------------------------------------- 渲染
def test_build_contains_key_data() -> None:
    html_text = build_review_html(RECORD, TRACE_ROWS)
    for needle in ("ep-demo-review", "152", "C+", "5577", "217", "lesson_score 未读到", "tap-card"):
        assert needle in html_text


def test_build_deterministic() -> None:
    assert build_review_html(RECORD, TRACE_ROWS) == build_review_html(RECORD, TRACE_ROWS)


def test_build_escapes_hostile_text() -> None:
    record = {**RECORD, "episode": "ep-<script>alert(1)</script>"}
    rows = [{**TRACE_ROWS[0], "reason": "<img src=x onerror=alert(1)>"}]
    html_text = build_review_html(record, rows)
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;" in html_text
    assert "<img src=x" not in html_text


def test_embedded_json_parseable() -> None:
    html_text = build_review_html(RECORD, TRACE_ROWS)
    start = html_text.index('<script type="application/json" id="review-data">') + len(
        '<script type="application/json" id="review-data">'
    )
    end = html_text.index("</script>", start)
    payload = json.loads(html_text[start:end].replace("<\\/", "</"))
    assert payload["episode"] == "ep-demo-review"
    assert payload["schema"] == SCHEMA
    assert payload["replay"]["steps"] > 0 and payload["replay"]["consistent"]


def test_trace_anomaly_highlight_and_demo_banner() -> None:
    html_text = build_review_html(RECORD, TRACE_ROWS, trace_source="synthetic-demo")
    assert 'class="anom"' in html_text  # lost 步
    assert "演示轨迹（合成数据" in html_text
    live = build_review_html(RECORD, TRACE_ROWS, trace_source="live")
    assert "演示轨迹（合成数据" not in live


def test_empty_trace_message() -> None:
    assert "无轨迹数据" in build_review_html(RECORD, [])


def test_duplicate_week_highlight() -> None:
    record = {**RECORD, "weeks": [RECORD["weeks"][0], RECORD["weeks"][0]]}
    assert 'class="dup"' in build_review_html(record)


def test_annotation_ui_markers() -> None:
    html_text = build_review_html(RECORD, TRACE_ROWS)
    for needle in ('data-ann-id="week-0"', 'data-ann-id="step-12"', 'data-ann-id="final"',
                   "btn-export", "btn-import", "annotations_ep-demo-review.json", SCHEMA):
        assert needle in html_text


def test_write_review_page_atomic_and_sanitized(tmp_path: Path) -> None:
    record = {**RECORD, "episode": "ep/a b:c"}
    path = write_review_page(record, TRACE_ROWS, out_dir=tmp_path / "review")
    assert path.name == "ep_a_b_c.html" and path.exists()
    assert not path.with_name(path.name + ".tmp").exists()
    assert "ep/a b:c" in path.read_text(encoding="utf-8")  # 页面内显示原始 episode（已转义）


# ---------------------------------------------------------------- 标注 → 回归
def test_parse_expected_json_and_fallback() -> None:
    assert parse_expected("lesson_score=152;outcome=moved;attrs_after=[210,90,95]") == {
        "lesson_score": 152, "outcome": "moved", "attrs_after": [210, 90, 95],
    }
    assert parse_expected("attrs_after=210,90,95") == {"attrs_after": "210,90,95"}
    assert parse_expected("") == {} and parse_expected(None) == {}
    assert parse_expected("noequals;=v;k=") == {"k": ""}


def test_normalize_annotations_rejects_bad_schema() -> None:
    with pytest.raises(ValueError, match="schema"):
        normalize_annotations({"schema": "wrong", "episode": "ep", "annotations": []})
    with pytest.raises(ValueError, match="episode"):
        normalize_annotations({"schema": SCHEMA, "annotations": []})
    norm = normalize_annotations(_payload([
        {"id": "week-1", "target": "week", "key": 1, "verdict": "bad", "expected": {"lesson_score": 152}},
        {"id": "week-2", "target": "week", "key": 2, "verdict": "ok"},
        {"id": "x", "target": "week", "key": 0, "verdict": "nonsense"},
    ]))
    assert len(norm["annotations"]) == 2  # ok 保留作历史；非法 verdict 丢弃


def test_cases_week_correction_frozen_state() -> None:
    payload = _payload([
        {"id": "week-1", "target": "week", "key": 1, "verdict": "bad",
         "comment": "演示：人工补 lesson_score=152", "expected": {"lesson_score": 152}},
    ])
    cases = cases_from_annotations(payload, RECORD)
    assert len(cases) == 1
    case = cases[0]
    assert case["kind"] == "replay" and case["id"] == "ep-demo-review:week:1"
    assert case["provenance"] == "synthetic-demo"
    # 冻结期望 = 转换时重放终态；测试重算必须逐位一致
    assert state_to_dict(replay(case["events"])[-1]) == case["expect"]
    assert case["expect"]["lesson_total"] == 304  # 原 152 + 人工补 152
    assert case["expect"]["lesson_known"] == 2


def test_cases_step_correction_classification() -> None:
    payload = _payload([
        {"id": "step-12", "target": "step", "key": 12, "verdict": "bad",
         "comment": "演示：画面已推进应判 moved", "expected": {"outcome": "moved"}},
        {"id": "step-13", "target": "step", "key": 13, "verdict": "bad",
         "comment": "演示：lost 必须算异常", "expected": {"outcome": "lost"}},
    ])
    cases = cases_from_annotations(payload, RECORD, TRACE_ROWS)
    by_id = {case["id"]: case for case in cases}
    moved = by_id["ep-demo-review:step:12"]
    assert moved["kind"] == "trace"
    assert moved["expect"] == {"anomaly": False, "outcomes": {"moved": 1}, "retaps": 0, "lost": 0}
    summary = summarize_traces(moved["rows"])
    assert bool(summary["anomalies"]) == moved["expect"]["anomaly"]
    lost = by_id["ep-demo-review:step:13"]
    assert lost["expect"]["anomaly"] is True and lost["expect"]["lost"] == 1


def test_cases_skip_ok_and_expectedless() -> None:
    payload = _payload([
        {"id": "week-0", "target": "week", "key": 0, "verdict": "ok", "expected": {"stamina": 1}},
        {"id": "week-1", "target": "week", "key": 1, "verdict": "bad", "comment": "只评论不修正"},
        {"id": "step-99", "target": "step", "key": 99, "verdict": "bad", "expected": {"outcome": "moved"}},
    ])
    assert cases_from_annotations(payload, RECORD, TRACE_ROWS) == []


def test_cases_exam_and_final_targets() -> None:
    payload = _payload([
        {"id": "exam-0", "target": "exam", "key": 0, "verdict": "bad", "expected": {"score": 300}},
        {"id": "final", "target": "final", "key": "final", "verdict": "bad", "expected": {"grade": "A"}},
    ])
    cases = cases_from_annotations(payload, RECORD)
    assert {case["target"] for case in cases} == {"exam", "final"}
    for case in cases:
        assert state_to_dict(replay(case["events"])[-1]) == case["expect"]


def test_merge_cases_dedup_and_sorted() -> None:
    old = {"schema": FIXTURE_SCHEMA, "cases": [{"id": "b", "v": 1}, {"id": "a", "v": 1}]}
    merged = merge_cases(old, [{"id": "b", "v": 2}, {"id": "c", "v": 1}])
    assert merged["schema"] == FIXTURE_SCHEMA
    assert [case["id"] for case in merged["cases"]] == ["a", "b", "c"]
    assert merged["cases"][1]["v"] == 2
    assert merge_cases(None, [])["cases"] == []


# ---------------------------------------------------------------- CLI
def _script_module(name: str):
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import importlib

    return importlib.import_module(name)


def test_replay_run_cli_verify_and_compare(tmp_path: Path) -> None:
    module = _script_module("replay_run")
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "ep-a.json").write_text(json.dumps(RECORD, ensure_ascii=False), encoding="utf-8")
    other = {**RECORD, "episode": "ep-b", "weeks": [dict(RECORD["weeks"][0], stamina=99)]}
    (runs / "ep-b.json").write_text(json.dumps(other, ensure_ascii=False), encoding="utf-8")
    assert module.main(["--episode", "ep-a", "--runs-dir", str(runs), "--verify"]) == 0
    assert module.main(["--episode", "ep-a", "--runs-dir", str(runs), "--json"]) == 0
    assert module.main(["--episode", "ep-a", "--runs-dir", str(runs),
                        "--compare", str(runs / "ep-b.json")]) == 1
    assert module.main(["--episode", "ep-nope", "--runs-dir", str(runs)]) == 2


def test_review_page_cli(tmp_path: Path) -> None:
    module = _script_module("review_page")
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "ep-demo-review.json").write_text(json.dumps(RECORD, ensure_ascii=False), encoding="utf-8")
    trace = tmp_path / "step_trace.jsonl"
    trace.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in TRACE_ROWS), encoding="utf-8")
    out = tmp_path / "review"
    assert module.main(["--episode", "ep-demo-review", "--runs-dir", str(runs),
                        "--trace", str(trace), "--out", str(out)]) == 0
    assert (out / "ep-demo-review.html").exists()


def test_annotations_to_regression_cli(tmp_path: Path) -> None:
    module = _script_module("annotations_to_regression")
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "ep-demo-review.json").write_text(json.dumps(RECORD, ensure_ascii=False), encoding="utf-8")
    trace = tmp_path / "step_trace.jsonl"
    trace.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in TRACE_ROWS), encoding="utf-8")
    ann = tmp_path / "annotations.json"
    ann.write_text(json.dumps(_payload([
        {"id": "week-1", "target": "week", "key": 1, "verdict": "bad",
         "comment": "演示", "expected": {"lesson_score": 152}},
    ]), ensure_ascii=False), encoding="utf-8")
    fixture = tmp_path / "fixture.json"
    assert module.main([str(ann), "--record", str(runs / "ep-demo-review.json"),
                        "--trace", str(trace), "--fixture", str(fixture)]) == 0
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert payload["schema"] == FIXTURE_SCHEMA and len(payload["cases"]) == 1
    # 再跑一遍同标注：幂等（按 id 去重，不重复追加）
    assert module.main([str(ann), "--record", str(runs / "ep-demo-review.json"),
                        "--trace", str(trace), "--fixture", str(fixture)]) == 0
    assert len(json.loads(fixture.read_text(encoding="utf-8"))["cases"]) == 1


def test_auto_produce_wiring_generates_review_page() -> None:
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    assert "write_review_page" in source
    assert "[review]" in source
    assert '"review_page"' in source
