"""跑局数据管道（data/runs/<episode>.json）的单元测试。

覆盖验收点：
- 增量写盘：每个 note_* 立刻落盘，硬 kill 后已写数据还在，重启能接着写；
- 读不到的字段写 null + note（lesson_score 缺失绝不用属性增量推算冒充）；
- 考试 others 乱序输入 → 从高到低；
- 最终 grade / eval_points 解析；
- 原子写失败不回滚（旧文件不丢）；
- run_report 摘要 + 「模拟器预测 vs 实际」对账行。
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from gkagent.data import run_record
from gkagent.data.run_record import (
    RunRecorder,
    action_of,
    parse_eval_points,
    parse_exam_result,
    parse_grade,
    week_from_countdown,
)

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class FakeLine:
    """最小 OCR 行：parse_exam_result 只依赖 text/box。"""

    text: str
    box: tuple[int, int, int, int]


def _recorder(tmp_path: Path, episode: str = "ep-test") -> RunRecorder:
    return RunRecorder(
        episode,
        runs_dir=tmp_path / "runs",
        started_at="2026-11-15 18:47:00",
        meta={"audition_coefficient": 4.11, "lesson_min_stamina": 10},
    )


def _record_path(tmp_path: Path, episode: str = "ep-test") -> Path:
    return tmp_path / "runs" / f"{episode}.json"


# ---------------------------------------------------------------- 增量 / 原子写
def test_incremental_flush_survives_hard_kill(tmp_path: Path) -> None:
    """每写一条就落盘；进程 os._exit（模拟被 kill）后已写数据仍在，重启可续写。"""
    episode = "ep-kill"
    script = "; ".join(
        [
            f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r})",
            "from gkagent.data.run_record import RunRecorder",
            f"r = RunRecorder({episode!r}, runs_dir={str(tmp_path / 'runs')!r})",
            "r.note_action(1, 'lesson', [210, 90, 95], 22)",
            "r.note_lesson(152)",
            "import os; os._exit(0)",
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(_record_path(tmp_path, episode).read_text(encoding="utf-8"))
    assert payload["weeks"][0]["lesson_score"] == 152
    assert payload["weeks"][0]["attrs_after"] == [210, 90, 95]

    # 重启同一个 episode：加载旧数据继续写，不覆盖已跑完的周
    recorder = RunRecorder(episode, runs_dir=tmp_path / "runs", started_at="2026-11-15 19:00:00")
    assert len(recorder.data["weeks"]) == 1
    recorder.note_action(2, "train", [220, 100, 100], 12)
    assert len(json.loads(_record_path(tmp_path, episode).read_text(encoding="utf-8"))["weeks"]) == 2


def test_atomic_replace_failure_keeps_previous_file(tmp_path: Path, monkeypatch) -> None:
    """写 .tmp 后 replace 失败：正式文件仍是上一次的完整内容，不回滚/不截断。"""
    recorder = _recorder(tmp_path)
    recorder.note_action(1, "lesson", [210, 90, 95], 22)
    path = _record_path(tmp_path)
    before = path.read_text(encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(run_record.os, "replace", _boom)
    recorder.note_action(2, "rest", [210, 90, 95], 35)
    assert recorder.flush() is False
    assert path.read_text(encoding="utf-8") == before
    assert not path.with_name(path.name + ".tmp").exists()


# ---------------------------------------------------------------- 每周行动
def test_lesson_score_missing_is_null_with_note(tmp_path: Path) -> None:
    """只拿到行动页（没读到课程分）：lesson_score=null + note，不拿属性增量推算。"""
    recorder = _recorder(tmp_path)
    recorder.note_lesson(None)
    record = recorder.note_action(3, "lesson", [210, 90, 95], 22)
    assert record["lesson_score"] is None
    assert "lesson_score 未读到" in record["note"]
    assert "未用属性增量" in record["note"]


def test_action_missing_attrs_and_stamina_are_null_with_note(tmp_path: Path) -> None:
    recorder = _recorder(tmp_path)
    record = recorder.note_action(4, "rest", None, None)
    assert record["attrs_after"] is None
    assert record["stamina"] is None
    assert "attrs_after 未读到" in record["note"]
    assert "stamina 未读到" in record["note"]


def test_lesson_score_backfill_updates_same_week(tmp_path: Path) -> None:
    """课程结束先落 lesson_score，下一行动页补三维/体力：更新同一条，不追加。"""
    recorder = _recorder(tmp_path)
    recorder.note_action(3, "lesson", None, None)
    recorder.note_lesson(152)
    record = recorder.note_action(3, "lesson", [210, 90, 95], 22)
    assert len(recorder.data["weeks"]) == 1
    assert record["lesson_score"] == 152
    assert record["attrs_after"] == [210, 90, 95]
    assert record["stamina"] == 22
    assert "note" not in record


def test_lesson_score_does_not_fill_previous_missing_week(tmp_path: Path) -> None:
    """上一周没读到分时，本周的分只能补本周，不能回填到上一周。"""
    recorder = _recorder(tmp_path)
    recorder.note_action(1, "lesson", [210, 90, 95], 22)  # 第 1 周缺 lesson_score
    recorder.note_action(2, "lesson", None, None)  # 第 2 周先落盘（attrs 稍后补）
    recorder.note_lesson(152)
    weeks = recorder.data["weeks"]
    assert weeks[0]["lesson_score"] is None
    assert "lesson_score 未读到" in weeks[0]["note"]
    assert weeks[1]["lesson_score"] == 152


def test_action_of_maps_driver_ticks() -> None:
    assert action_of("lesson") == "lesson"
    assert action_of("sim-lesson") == "lesson"
    assert action_of("train-Da") == "train"
    assert action_of("sim-train-Vi") == "train"
    assert action_of("go-out") == "outing"
    assert action_of("consult") == "outing"
    assert action_of("lesson-skip") is None
    assert action_of("stamina-wait") is None


# ---------------------------------------------------------------- 考试
def test_exam_others_sorted_descending(tmp_path: Path) -> None:
    recorder = _recorder(tmp_path)
    record = recorder.note_exam("mid", 2, 8421, [7003, 9210, 3980, 8421, 5120, 4110])
    assert record["kind"] == "mid"
    assert record["rank"] == 2
    assert record["score"] == 8421
    assert record["others"] == [9210, 8421, 7003, 5120, 4110, 3980]


def test_parse_exam_result_pairs_own_row_and_sorts() -> None:
    """自己的行用「日志」按钮定位；分数行乱序输入，others 仍从高到低。"""
    lines = [
        FakeLine("5th", (44, 876, 92, 63)),
        FakeLine("197pt", (214, 914, 83, 31)),
        FakeLine("1st", (37, 296, 95, 74)),
        FakeLine("581Pt", (214, 339, 83, 30)),
        FakeLine("3rd", (36, 582, 97, 74)),
        FakeLine("日志", (613, 607, 44, 27)),
        FakeLine("263Pt", (212, 625, 85, 33)),
        FakeLine("2nd", (34, 440, 111, 75)),
        FakeLine("387pt", (214, 482, 83, 31)),
        FakeLine("4th", (45, 741, 85, 55)),
        FakeLine("229Pt", (213, 771, 83, 30)),
    ]
    result = parse_exam_result(lines)
    assert result is not None
    assert result["rank"] == 3
    assert result["score"] == 263
    assert result["others"] == [581, 387, 263, 229, 197]
    assert "5/6" in result["note"]  # 第 6 名被底部按钮遮挡，如实记 note


def test_parse_exam_result_without_scores_returns_none() -> None:
    assert parse_exam_result([FakeLine("1st", (37, 296, 95, 74))]) is None


# ---------------------------------------------------------------- 结算
@pytest.mark.parametrize(
    ("text", "expected"),
    [("C+", "C+"), ("Ａ＋", "A+"), ("B", "B"), ("S", "S"), ("CB", None), ("", None)],
)
def test_parse_grade(text: str, expected: str | None) -> None:
    assert parse_grade(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("5577", 5577), ("12 345", 12345), ("557", None), ("1234567", None), ("", None)],
)
def test_parse_eval_points(text: str, expected: int | None) -> None:
    assert parse_eval_points(text) == expected


def test_note_final_falls_back_to_last_attrs_and_exam(tmp_path: Path) -> None:
    recorder = _recorder(tmp_path)
    recorder.note_action(5, "lesson", [344, 235, 533], 30)
    recorder.note_lesson(152)
    recorder.note_exam("final", 1, 17300, [17300, 9210, 8000, 7000, 6000, 5000])
    final = recorder.note_final(None, None, None, 5577, "C+")
    assert final["attrs"] == [344, 235, 533]
    assert final["rank"] == 1
    assert final["exam_score"] == 17300
    assert final["eval_points"] == 5577
    assert final["grade"] == "C+"


def test_week_from_countdown_matches_real_screens() -> None:
    assert week_from_countdown("4周@", "mid") == 2
    assert week_from_countdown("5周", "mid") == 1
    assert week_from_countdown("6周", "final") == 7
    assert week_from_countdown("周", "mid") is None
    assert week_from_countdown("4周", None) is None


def test_auto_produce_wiring_calls_recorder() -> None:
    """auto_produce 必须真的接上 RunRecorder 的四个 note_* 和三个读取入口。"""
    source = (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")
    assert "RunRecorder(episode)" in source
    for name in (
        "note_action",
        "note_lesson",
        "note_exam",
        "note_final",
        "driver.read_week",
        "driver.read_exam_result",
        "driver.read_final_result",
    ):
        assert name in source, f"auto_produce 没接 {name}"
    assert "[record]" in source


# ---------------------------------------------------------------- run_report
def _run_report_module():
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import run_report

    return run_report


RECORD = {
    "episode": "ep-report",
    "started_at": "2026-11-15 18:47:00",
    "weeks": [
        {"week": 3, "action": "lesson", "lesson_score": 152, "attrs_after": [210, 90, 95], "stamina": 22},
        {"week": 4, "action": "train", "lesson_score": None, "attrs_after": [344, 235, 533], "stamina": 12},
    ],
    "exams": [
        {"kind": "mid", "rank": 2, "score": 8421, "others": [9210, 8421, 7003, 5120, 4110, 3980]}
    ],
    "final": {
        "attrs": [344, 235, 533],
        "rank": 1,
        "exam_score": 17300,
        "eval_points": 5577,
        "grade": "C+",
    },
    "meta": {"audition_coefficient": 4.11, "lesson_min_stamina": 10},
}


def test_run_report_summary_and_reconciliation(tmp_path: Path) -> None:
    report = _run_report_module()
    runs = tmp_path / "runs"
    runs.mkdir()
    path = runs / "ep-report.json"
    path.write_text(json.dumps(RECORD, ensure_ascii=False), encoding="utf-8")
    record, loaded = report.load_run("ep-report", runs)
    text = report.build_report(record, path=loaded)
    assert "周记录: 2 周" in text
    assert "最终属性: 344/235/533（总 1112）" in text
    assert "期中 rank=2 / 8421 Pt" in text
    assert "评价: C+ / 5577 评价点" in text
    assert "模拟器预测 vs 实际" in text
    assert "实际 5577" in text
    assert "不一致" in text  # 模拟器预测评价等级与真机 C+ 不同，必须显式对账

    assert report.main(["ep-report", str(runs)]) == 0


def test_run_report_handles_missing_final(tmp_path: Path) -> None:
    report = _run_report_module()
    record = {**RECORD, "final": None, "weeks": []}
    text = report.build_report(record, path=None)
    assert "评价: 未采集到（final=null）" in text
    assert "数据不全" in text
    assert report.main([]) == 2
