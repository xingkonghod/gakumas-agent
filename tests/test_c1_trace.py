"""C1 每步可复盘：StepTrace 落盘 + 离线复盘格式 + replay_steps CLI。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from gkagent.runtime.trace import StepTrace, TraceLog, format_trace, summarize_traces


def _auto_produce():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import auto_produce

    return auto_produce


def _rows() -> list[StepTrace]:
    return [
        StepTrace(
            episode="ep-x",
            step=1,
            screen="dialog",
            action="confirm",
            point=(360, 1150),
            reason="弹窗确认「确定」",
            expect_kind="dialog-gone",
            expect_words=("取消",),
            outcome="retap",
            tries=1,
            before_sig="sig-a",
            after_sig="sig-a",
        ),
        StepTrace(
            episode="ep-x",
            step=2,
            screen="dialog",
            action="tap-retap",
            point=(360, 1150),
            reason="上一击 confirm 未生效，同屏重试第 1/2 次",
            outcome="lost",
            tries=2,
        ),
        StepTrace(
            episode="ep-x",
            step=3,
            screen="lesson",
            action="name-pick",
            point=(230, 918),
            reason="[training] name-pick 魅力的基础",
            engine_note="eng=expectimax fallback=无",
            outcome="lesson-confirm",
        ),
    ]


def test_trace_roundtrip(tmp_path: Path) -> None:
    log = TraceLog(tmp_path / "step_trace.jsonl")
    for row in _rows():
        log.write(row)
    rows = log.read()
    assert len(rows) == 3
    assert rows[0]["point"] == [360, 1150]
    assert rows[0]["expect_words"] == ["取消"]
    assert rows[2]["engine_note"] == "eng=expectimax fallback=无"
    assert log.read(limit=1)[0]["step"] == 3


def test_trace_read_missing_file(tmp_path: Path) -> None:
    assert TraceLog(tmp_path / "nope.jsonl").read() == []


def test_trace_read_skips_bad_lines(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text('{"step": 1}\nnot-json\n{"step": 2}\n', encoding="utf-8")
    assert [row["step"] for row in TraceLog(path).read()] == [1, 2]


def test_format_trace_answers_four_questions() -> None:
    text = format_trace(_rows()[0].__dict__)
    assert "001" in text and "[dialog]" in text and "confirm" in text
    assert "(360,1150)" in text
    assert "理由: 弹窗确认「确定」" in text
    assert "预算: dialog-gone（取消）" in text
    assert "→ retap" in text and "重试 1" in text


def test_format_trace_minimal_row() -> None:
    assert format_trace({"step": 7, "screen": "loading", "action": "wait"}) == (
        "007 [loading] wait"
    )


def test_summarize_traces_counts_and_anomalies() -> None:
    rows = [row.__dict__ for row in _rows()]
    summary = summarize_traces(rows)
    assert summary["steps"] == 3
    assert summary["outcomes"] == {"retap": 1, "lost": 1, "lesson-confirm": 1}
    assert summary["lost"] == 1
    assert [row["step"] for row in summary["anomalies"]] == [2]


def test_summarize_flags_stuck_screen() -> None:
    summary = summarize_traces([{"step": 9, "screen": "stuck", "action": "settlement-loop"}])
    assert len(summary["anomalies"]) == 1


def test_replay_cli_prints_episode_steps(tmp_path: Path, capsys) -> None:
    import replay_steps

    path = tmp_path / "step_trace.jsonl"
    log = TraceLog(path)
    for row in _rows():
        log.write(row)
    code = replay_steps.main(["--trace", str(path), "--episode", "ep-x"])
    assert code == 0
    out = capsys.readouterr().out
    assert "复盘 ep-x（3 步）" in out
    assert "理由: 弹窗确认「确定」" in out
    assert "eng=expectimax fallback=无" in out
    assert "lost=1" in out
    assert "异常 1 步" in out


def test_replay_cli_anomalies_only(tmp_path: Path, capsys) -> None:
    import replay_steps

    path = tmp_path / "step_trace.jsonl"
    for row in _rows():
        TraceLog(path).write(row)
    code = replay_steps.main(["--trace", str(path), "--anomalies"])
    assert code == 0
    out = capsys.readouterr().out
    assert "tap-retap" in out
    assert "name-pick" not in out


def test_replay_cli_json(tmp_path: Path, capsys) -> None:
    import replay_steps

    path = tmp_path / "step_trace.jsonl"
    for row in _rows():
        TraceLog(path).write(row)
    code = replay_steps.main(["--trace", str(path), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["episode"] == "ep-x"
    assert payload["summary"]["lost"] == 1
    assert len(payload["rows"]) == 3


def test_replay_cli_missing_file(tmp_path: Path, capsys) -> None:
    import replay_steps

    assert replay_steps.main(["--trace", str(tmp_path / "none.jsonl")]) == 2


def test_auto_produce_writes_trace_each_step() -> None:
    """接线：主循环每步写 StepTrace（落盘字段含理由/预算/互验结果）。"""
    ap = _auto_produce()
    assert hasattr(ap, "TraceLog") and hasattr(ap, "StepTrace")
    source = (Path(__file__).resolve().parents[1] / "scripts" / "auto_produce.py").read_text(
        encoding="utf-8"
    )
    assert "trace_log.write(" in source
    assert "StepTrace(" in source
    assert 'ROOT / "data" / "step_trace.jsonl"' in source
