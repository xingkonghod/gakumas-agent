"""T7② 纯函数状态重放单测：假观测序列重放 / 同序列同状态 / 逐步比对。

覆盖验收点：
- apply_event 纯函数（不改输入、无 I/O）；null 观测不抹已知值；
- 同观测序列两遍重放指纹逐位相等；扰动一条观测 → 首个分歧步定位；
- 旧格式汇总确定式重建（legacy_events）与 events 日志终态语义一致；
- RunRecorder 观测日志接线（补写/暂存/考试去重/结算兜底）+ 续跑旧文件；
- 三方对账能抓记录器漂移（暂存覆盖丢分）与记录篡改。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.data.run_record import RunRecorder
from gkagent.data.run_replay import (
    CONSISTENCY_FIELDS,
    apply_event,
    compare_replays,
    compare_states,
    consistency_check,
    events_of,
    fingerprint,
    initial_state,
    legacy_events,
    replay,
    state_to_dict,
)

_DEFAULT_ATTRS = object()


def _action(seq: int, week: int, action: str = "train", attrs=_DEFAULT_ATTRS, stamina=20) -> dict:
    return {
        "seq": seq,
        "kind": "action",
        "week": week,
        "action": action,
        "attrs_after": [100 + week, 100, 100] if attrs is _DEFAULT_ATTRS else attrs,
        "stamina": stamina,
    }


def _rich_events() -> list[dict]:
    return [
        _action(0, 1, "train", [132, 165, 224], 27),
        _action(1, 2, "lesson", None, None),
        {"seq": 2, "kind": "lesson", "score": 152},
        {"seq": 3, "kind": "backfill", "week": 2, "attrs_after": [132, 170, 270], "stamina": 27},
        _action(4, 3, "rest", [132, 170, 270], 35),
        {"seq": 5, "kind": "exam", "exam_kind": "mid", "rank": 2, "score": 8421,
         "others": [7003, 9210, 3980, 8421, 5120, 4110]},
        _action(6, 7, "train", [200, 200, 200], 20),
        {"seq": 7, "kind": "exam", "exam_kind": "final", "rank": 1, "score": 17300,
         "others": [17300, 9210, 8000, 7000, 6000, 5000]},
        {"seq": 8, "kind": "final", "attrs": None, "rank": None, "exam_score": None,
         "eval_points": 5577, "grade": "C+"},
    ]


# ---------------------------------------------------------------- 纯函数 / 状态推进
def test_initial_state_is_empty() -> None:
    state = initial_state()
    assert state.week is None and state.attrs is None and state.n_events == 0
    assert state.exams == () and state.final is None and state.lesson_total == 0


def test_action_updates_week_attrs_stamina_phase() -> None:
    state = apply_event(initial_state(), _action(0, 3, "lesson", [210, 90, 95], 22))
    assert state.week == 3 and state.phase == "mid"
    assert state.attrs == (210, 90, 95) and state.stamina == 22
    assert state.weeks_seen == 1 and state.action_counts == (("lesson", 1),)
    assert state.seq == 0 and state.n_events == 1


def test_null_observation_keeps_last_known() -> None:
    state = apply_event(initial_state(), _action(0, 3, "lesson", [210, 90, 95], 22))
    state = apply_event(state, _action(1, 3, "lesson", None, None))
    assert state.attrs == (210, 90, 95) and state.stamina == 22 and state.week == 3
    assert state.weeks_seen == 2  # 观测计数照算，已知值不被 null 抹掉


def test_missing_fields_counted_per_observation() -> None:
    state = apply_event(initial_state(), {"kind": "action", "week": None, "action": None,
                                          "attrs_after": None, "stamina": None})
    assert state.missing_fields == 4


def test_backfill_does_not_double_count_week() -> None:
    state = apply_event(initial_state(), _action(0, 2, "lesson", None, None))
    state = apply_event(state, {"kind": "backfill", "week": 2, "attrs_after": [132, 170, 270], "stamina": 27})
    assert state.weeks_seen == 1 and state.duplicates == 0
    assert state.attrs == (132, 170, 270) and state.stamina == 27


def test_duplicate_week_action_counted() -> None:
    """ep-t1-g 真实故障形态：同周同行动重复观测 29 次 → duplicates 必须显式计数。"""
    state = initial_state()
    for index in range(29):
        state = apply_event(state, _action(index, 8, "outing", [262, 282, 539], 22))
    assert state.weeks_seen == 29 and state.duplicates == 28


def test_action_counts_sorted_and_none_skipped() -> None:
    state = initial_state()
    for kind in ("train", "lesson", "train", None):
        state = apply_event(state, {"kind": "action", "week": 1, "action": kind})
    assert state.action_counts == (("lesson", 1), ("train", 2))


def test_lesson_total_known_unread() -> None:
    state = initial_state()
    state = apply_event(state, {"kind": "lesson", "score": 152})
    state = apply_event(state, {"kind": "lesson", "score": None})
    state = apply_event(state, {"kind": "lesson", "score": 8})
    assert state.lesson_total == 160 and state.lesson_known == 2 and state.lesson_unread == 1


def test_exam_sorted_merged_and_dedup() -> None:
    event = {"kind": "exam", "exam_kind": "mid", "rank": 3, "score": 263,
             "others": [197, 581, 387, 229]}
    state = apply_event(initial_state(), event)
    assert state.exams[0].others == (581, 387, 263, 229, 197)  # 自己分数并入 + 从高到低
    state = apply_event(state, event)
    assert len(state.exams) == 1 and state.exam_score_total == 263  # 重复结算不重复入账
    assert state.n_events == 2


def test_exam_score_total_accumulates() -> None:
    state = initial_state()
    state = apply_event(state, {"kind": "exam", "exam_kind": "mid", "rank": 2, "score": 8421})
    state = apply_event(state, {"kind": "exam", "exam_kind": "final", "rank": 1, "score": 17300})
    assert state.exam_score_total == 25721 and len(state.exams) == 2


def test_final_fallback_attrs_and_final_exam() -> None:
    state = initial_state()
    state = apply_event(state, _action(0, 7, "train", [344, 235, 533], 30))
    state = apply_event(state, {"kind": "exam", "exam_kind": "final", "rank": 1, "score": 17300})
    state = apply_event(state, {"kind": "final", "attrs": None, "rank": None,
                                "exam_score": None, "eval_points": 5577, "grade": "C+"})
    assert state.final is not None
    assert state.final.attrs == (344, 235, 533)
    assert state.final.rank == 1 and state.final.exam_score == 17300
    assert state.final.eval_points == 5577 and state.final.grade == "C+"


def test_final_midterm_does_not_fill_rank() -> None:
    """期中名次不冒充期末（与 note_final 同口径）。"""
    state = apply_event(initial_state(), {"kind": "exam", "exam_kind": "mid", "rank": 2, "score": 8421})
    state = apply_event(state, {"kind": "final", "eval_points": 5577, "grade": "C+"})
    assert state.final.rank is None and state.final.exam_score is None


def test_final_merge_keeps_previous() -> None:
    state = apply_event(initial_state(), {"kind": "final", "eval_points": 5577, "grade": "C+"})
    state = apply_event(state, {"kind": "final", "attrs": [344, 235, 533]})
    assert state.final.eval_points == 5577 and state.final.grade == "C+"
    assert state.final.attrs == (344, 235, 533)


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="未知观测事件种类"):
        apply_event(initial_state(), {"kind": "teleport"})


def test_apply_event_does_not_mutate_input() -> None:
    events = _rich_events()
    states = replay(events[:4])
    state = states[-1]
    before_state = json.dumps(state_to_dict(state), sort_keys=True, ensure_ascii=False)
    before_event = json.dumps(events[4], sort_keys=True, ensure_ascii=False)
    apply_event(state, events[4])
    assert json.dumps(state_to_dict(state), sort_keys=True, ensure_ascii=False) == before_state
    assert json.dumps(events[4], sort_keys=True, ensure_ascii=False) == before_event


def test_invalid_values_become_none_not_zero() -> None:
    state = apply_event(initial_state(), {"kind": "action", "week": 0, "action": "fly",
                                          "attrs_after": [1, 2], "stamina": -1})
    assert state.week is None and state.attrs is None and state.stamina is None
    assert state.action_counts == () and state.missing_fields == 4
    state = apply_event(state, {"kind": "final", "grade": "CB", "eval_points": 557})
    assert state.final.grade is None and state.final.eval_points is None


@pytest.mark.parametrize(
    ("week", "phase"),
    [(1, "mid"), (5, "mid"), (6, None), (7, "final"), (12, "final"), (None, None)],
)
def test_phase_mapping(week, phase) -> None:
    state = apply_event(initial_state(), {"kind": "action", "week": week, "action": "train"})
    assert state.phase == phase


# ---------------------------------------------------------------- 确定性 / 逐步比对
def test_replay_determinism_fingerprint() -> None:
    events = _rich_events()
    assert fingerprint(replay(events)) == fingerprint(replay(events))
    assert replay(events) == replay(events)


def test_fingerprint_changes_on_perturbation() -> None:
    events = _rich_events()
    other = [dict(event) for event in events]
    other[4]["stamina"] = 99
    assert fingerprint(replay(events)) != fingerprint(replay(other))


def test_compare_replays_identical() -> None:
    states = replay(_rich_events())
    result = compare_replays(states, states)
    assert result["equal"] and result["first_divergence"] is None and result["diffs"] == []


def test_compare_replays_first_divergence() -> None:
    events = _rich_events()
    other = [dict(event) for event in events]
    other[4]["stamina"] = 99  # 第 5 条观测（index 4）起分歧
    result = compare_replays(replay(events), replay(other))
    assert not result["equal"]
    assert result["first_divergence"] == 4
    assert "stamina" in result["diffs"][0]["fields"]


def test_compare_replays_length_mismatch() -> None:
    events = _rich_events()
    result = compare_replays(replay(events), replay(events[:4]))
    assert not result["equal"] and result["length_mismatch"]
    assert result["first_divergence"] == 4 and result["diffs"] == []


def test_compare_states_lists_only_diff_fields() -> None:
    a = apply_event(initial_state(), _action(0, 1))
    b = apply_event(initial_state(), _action(0, 2))
    diff = compare_states(a, b)
    assert "week" in diff and "attrs" in diff and "lesson_total" not in diff


# ---------------------------------------------------------------- 旧格式重建 / 记录器接线
def test_legacy_events_order_and_seq() -> None:
    record = {
        "weeks": [
            {"week": 2, "action": "lesson", "lesson_score": 152, "attrs_after": None, "stamina": None},
            {"week": 3, "action": "rest", "lesson_score": None, "attrs_after": [1, 2, 3], "stamina": 30},
        ],
        "exams": [{"kind": "mid", "rank": 2, "score": 8421, "others": [8421, 7000]}],
        "final": {"attrs": [1, 2, 3], "rank": 1, "exam_score": 17300, "eval_points": 5577, "grade": "C+"},
    }
    events = legacy_events(record)
    assert [event["kind"] for event in events] == ["action", "lesson", "action", "exam", "final"]
    assert [event["seq"] for event in events] == list(range(5))
    assert events[0]["week"] == 2 and events[1]["score"] == 152


def test_events_of_prefers_events_log() -> None:
    record = {"weeks": [{"week": 1, "action": "train"}], "events": [{"seq": 0, "kind": "lesson", "score": 9}]}
    events, source = events_of(record)
    assert source == "events" and events[0]["kind"] == "lesson"
    events, source = events_of({"weeks": [{"week": 1, "action": "train"}]})
    assert source == "legacy" and events[0]["kind"] == "action"


def test_empty_record_consistent() -> None:
    check = consistency_check({"episode": "ep-empty", "weeks": [], "exams": [], "final": None})
    assert check["consistent"] and check["steps"] == 0


def _recorder(tmp_path: Path, episode: str = "ep-replay") -> RunRecorder:
    return RunRecorder(
        episode,
        runs_dir=tmp_path / "runs",
        started_at="2026-11-24 12:00:00",
        meta={"audition_coefficient": 4.11, "lesson_min_stamina": 10},
    )


def test_recorder_events_log_written(tmp_path: Path) -> None:
    recorder = _recorder(tmp_path)
    recorder.note_action(1, "train", [132, 165, 224], 27)
    recorder.note_lesson(152)
    payload = json.loads((tmp_path / "runs" / "ep-replay.json").read_text(encoding="utf-8"))
    assert [event["kind"] for event in payload["events"]] == ["action", "lesson"]
    assert [event["seq"] for event in payload["events"]] == [0, 1]


def test_recorder_replay_matches_legacy_final(tmp_path: Path) -> None:
    """补写/暂存/考试去重/结算兜底全走一遍：events 重放终态 = 旧格式重建终态 = 记录汇总。"""
    recorder = _recorder(tmp_path)
    recorder.note_action(1, "train", [100, 100, 100], 30)
    recorder.note_action(2, "lesson", None, None)
    recorder.note_lesson(152)
    recorder.note_action(2, "lesson", [110, 120, 130], 25)  # 补写
    recorder.note_action(3, "lesson", None, None)
    recorder.note_lesson(None)  # 没读到分
    recorder.note_action(4, "rest", [110, 120, 130], 35)
    recorder.note_exam("mid", 2, 8421, [7003, 9210, 3980, 8421, 5120, 4110])
    recorder.note_exam("mid", 2, 8421, [7003, 9210, 3980, 8421, 5120, 4110])  # 去重
    recorder.note_action(7, "train", [200, 200, 200], 20)
    recorder.note_exam("final", 1, 17300, [17300, 9210, 8000, 7000, 6000, 5000])
    recorder.note_final(None, None, None, 5577, "C+")

    check = consistency_check(recorder.data)
    assert check["source"] == "events"
    assert check["consistent"], check
    events, _ = events_of(recorder.data)
    live = state_to_dict(replay(events)[-1])
    legacy = state_to_dict(replay(legacy_events(recorder.data))[-1])
    for field in CONSISTENCY_FIELDS:
        assert live[field] == legacy[field], field
    assert live["lesson_total"] == 152 and live["lesson_unread"] == 1
    assert live["weeks_seen"] == 5 and live["duplicates"] == 0
    assert live["final"]["grade"] == "C+" and live["final"]["exam_score"] == 17300


def test_recorder_resume_legacy_backfills_events(tmp_path: Path) -> None:
    """旧格式文件续跑：先把汇总重建成观测日志，新观测接着编号，重放覆盖整局。"""
    runs = tmp_path / "runs"
    runs.mkdir()
    old = {
        "episode": "ep-old",
        "started_at": "2026-11-15 18:47:00",
        "weeks": [{"week": 1, "action": "train", "lesson_score": None,
                   "attrs_after": [132, 165, 224], "stamina": 27}],
        "exams": [],
        "final": None,
        "meta": {},
    }
    (runs / "ep-old.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    recorder = RunRecorder("ep-old", runs_dir=runs)
    assert len(recorder.data["events"]) == 1  # 旧周已重建
    recorder.note_action(2, "lesson", [140, 170, 230], 25)
    events, source = events_of(recorder.data)
    assert source == "events" and len(events) == 2
    assert consistency_check(recorder.data)["consistent"]
    assert replay(events)[-1].week == 2


def test_consistency_flags_pending_overwrite(tmp_path: Path) -> None:
    """note_lesson 暂存被覆盖丢分：重放对账必须抓出来（不静默）。"""
    recorder = _recorder(tmp_path)
    recorder.note_lesson(100)  # 无 lesson 周 → 暂存
    recorder.note_lesson(200)  # 覆盖暂存（100 丢了）
    recorder.note_action(1, "lesson", [110, 120, 130], 25)
    check = consistency_check(recorder.data)
    assert not check["consistent"]
    fields = {item["field"] for item in check["discrepancies"]}
    assert "lesson_total" in fields


def test_consistency_flags_record_tamper(tmp_path: Path) -> None:
    recorder = _recorder(tmp_path)
    recorder.note_action(1, "train", [132, 165, 224], 27)
    recorder.data["weeks"][0]["stamina"] = 999  # 篡改汇总（观测日志没变）
    check = consistency_check(recorder.data)
    assert not check["consistent"]
    assert any(item["field"] == "stamina" for item in check["discrepancies"])


def test_week_regression_replays() -> None:
    """ep-rule1 真实形态：周数回退（10 → 8）也如实重放，最后已知周优先。"""
    events = [_action(0, 7, "rest"), _action(1, 8, "outing"), _action(2, 9, "train"),
              _action(3, 10, "lesson"), _action(4, 8, "outing", stamina=1)]
    states = replay(events)
    assert states[-1].week == 8 and states[-1].stamina == 1
    assert states[-1].weeks_seen == 5 and states[-1].duplicates == 0


def test_exam_event_kind_field_separation() -> None:
    """事件类型占用 kind；考试类型在 exam_kind（ mid/final 不被 'exam' 吞掉）。"""
    state = apply_event(initial_state(), {"kind": "exam", "exam_kind": "mid", "rank": 1, "score": 10})
    assert state.exams[0].kind == "mid"
    state = apply_event(state, {"kind": "exam", "rank": 1, "score": 10})
    assert state.exams[-1].kind is None  # 缺 exam_kind 按读不到处理
