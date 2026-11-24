"""T7② 纯函数状态重放：同观测序列 → 同状态 → 可逐步比对。

`run_record.RunRecorder` 边跑边写「每周行动 + 课程分 + 考试 + 结算」；本模块把
这些**观测**变成一条有序事件序列，再用纯函数折叠成状态快照序列：

- ``apply_event(state, event) -> RunState``：**无副作用**，返回新状态，绝不改输入；
  不读时钟/文件/随机数，同输入必同输出（``fingerprint`` 可逐位验证）。
- ``replay(events)``：逐事件一个快照；``legacy_events(record)`` 从旧格式
  （只有 weeks/exams/final 汇总、没有 events 日志）确定式重建观测序列。
- ``compare_replays(a, b)``：逐步比对两条快照序列，报告首个分歧步与逐字段差异。
- ``consistency_check(record)``：events 日志重放 vs 汇总重建重放 vs 原始记录三方
  对账，抓记录器/重放器漂移（补写合并导致的 ``missing_fields`` 差异除外，见下）。

事件种类（与 RunRecorder.note_* 一一对应）：

``action``
    周行动观测 ``{week, action, attrs_after, stamina}``（验证后值，读不到为 null）。
``backfill``
    同周补写（课程结束先落分、下一行动页补三维）：只更新 attrs/stamina，
    **不重复计周**——保证与旧格式「一周一条合并行」重建出的状态一致。
``lesson``
    课程分观测 ``{score}``；null = 没读到（绝不用属性增量推算冒充）。
``exam``
    考试结算 ``{exam_kind, rank, score, others}``（事件类型占用 ``kind``，
    考试类型 mid/final 在 ``exam_kind``）；others 从高到低含自己。
``final``
    最终结算 ``{attrs, rank, exam_score, eval_points, grade}``；
    缺失兜底口径与 ``RunRecorder.note_final`` 完全一致（attrs 用最后已知三维、
    rank/exam_score 只从**期末**考试补）。

状态字段里 ``missing_fields`` / ``lesson_unread`` 是**观测级**计数：旧格式重建是
合并视图，补写前的缺失已被抹平、「观测到 null」与「从未观测」也分不清，所以
三方对账只比语义字段（``CONSISTENCY_FIELDS``），这两个计数只作复盘页展示，不当漂移。

本模块不碰任何考试/模拟器规则：只做跑局观测的簿记重放（T7 可靠性工程）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any

from gkagent.data.run_record import (
    MIDTERM_WEEK,
    VALID_ACTIONS,
    _as_attrs,
    _as_int,
    _as_scores,
    parse_eval_points,
    parse_grade,
)

#: 事件种类白名单；未知种类显式报错（不静默跳过，与项目「禁静默回退」同口径）。
EVENT_KINDS = ("action", "backfill", "lesson", "exam", "final")

#: 三方对账比较的语义字段。排除两个**观测级**计数：
#: - missing_fields：补写合并后旧格式看不到补写前的缺失；
#: - lesson_unread：合并汇总分不清「观测到 null」与「从未观测」（note_lesson 没调用），
#:   只有 live 日志知道；lesson_total/lesson_known（非空分数和）两视图可比，保留。
CONSISTENCY_FIELDS = (
    "week",
    "phase",
    "attrs",
    "stamina",
    "weeks_seen",
    "duplicates",
    "action_counts",
    "lesson_total",
    "lesson_known",
    "exams",
    "exam_score_total",
    "final",
)


@dataclass(frozen=True)
class ExamSnapshot:
    """一场考试的不可变快照（others 从高到低含自己；note 是记录器侧标注，不入状态）。"""

    kind: str | None = None
    rank: int | None = None
    score: int | None = None
    others: tuple[int, ...] | None = None


@dataclass(frozen=True)
class FinalSnapshot:
    """最终结算的不可变快照。"""

    attrs: tuple[int, int, int] | None = None
    rank: int | None = None
    exam_score: int | None = None
    eval_points: int | None = None
    grade: str | None = None


@dataclass(frozen=True)
class RunState:
    """观测序列折叠出的簿记状态（深不可变：全部字段可哈希，apply 只返回新对象）。"""

    seq: int = -1
    n_events: int = 0
    week: int | None = None
    phase: str | None = None
    attrs: tuple[int, int, int] | None = None
    stamina: int | None = None
    weeks_seen: int = 0
    duplicates: int = 0
    last_action_key: tuple[int | None, str | None] | None = None
    action_counts: tuple[tuple[str, int], ...] = ()
    lesson_total: int = 0
    lesson_known: int = 0
    lesson_unread: int = 0
    exams: tuple[ExamSnapshot, ...] = ()
    exam_score_total: int = 0
    final: FinalSnapshot | None = None
    missing_fields: int = 0


def initial_state() -> RunState:
    """空观测序列的起点状态。"""
    return RunState()


def _phase_of(week: int | None) -> str | None:
    """周数 → 阶段：期中行动周 1..5 = mid，期末行动周 7..12 = final。

    第 6 周是期中考试周（不占行动页，见 run_record.week_from_countdown），
    没有行动观测阶段，返回 None；None 周保持 None。
    """
    if week is None or week == MIDTERM_WEEK:
        return None
    return "mid" if week < MIDTERM_WEEK else "final"


def _count_missing(*values: Any) -> int:
    return sum(1 for value in values if value is None)


def _bump_counts(counts: tuple[tuple[str, int], ...], action: str | None) -> tuple[tuple[str, int], ...]:
    if action is None:
        return counts
    merged = dict(counts)
    merged[action] = merged.get(action, 0) + 1
    return tuple(sorted(merged.items()))


def _exam_of(event: Mapping[str, Any]) -> ExamSnapshot:
    # 事件类型占用 "kind"（=exam）；考试类型（mid/final）在 "exam_kind"。
    kind = event.get("exam_kind")
    kind_value = kind if kind in ("mid", "final") else None
    others = _as_scores(event.get("others"))
    score = _as_int(event.get("score"), minimum=0, maximum=999999)
    if others is not None and score is not None and score not in others:
        others = sorted([*others, score], reverse=True)
    return ExamSnapshot(
        kind=kind_value,
        rank=_as_int(event.get("rank"), minimum=1, maximum=6),
        score=score,
        others=tuple(others) if others is not None else None,
    )


def _final_of(event: Mapping[str, Any], state: RunState) -> FinalSnapshot:
    """与 RunRecorder.note_final 同口径的兜底合并（纯函数版）。"""
    previous = state.final if state.final is not None else FinalSnapshot()
    attrs_raw = _as_attrs(event.get("attrs"))
    attrs = tuple(attrs_raw) if attrs_raw is not None else state.attrs
    rank = _as_int(event.get("rank"), minimum=1, maximum=6)
    exam_score = _as_int(event.get("exam_score"), minimum=0, maximum=999999)
    final_exam = next(
        (exam for exam in reversed(state.exams) if exam.kind == "final"),
        None,
    )
    if final_exam is not None:
        if rank is None:
            rank = final_exam.rank
        if exam_score is None:
            exam_score = final_exam.score
    points = _as_int(event.get("eval_points"), minimum=1000, maximum=999999)
    if points is None:
        points = parse_eval_points(event.get("eval_points"))
    grade_raw = event.get("grade")
    grade = parse_grade(grade_raw) if isinstance(grade_raw, str) else None
    return FinalSnapshot(
        attrs=attrs if attrs is not None else previous.attrs,
        rank=rank if rank is not None else previous.rank,
        exam_score=exam_score if exam_score is not None else previous.exam_score,
        eval_points=points if points is not None else previous.eval_points,
        grade=grade if grade is not None else previous.grade,
    )


def apply_event(state: RunState, event: Mapping[str, Any]) -> RunState:
    """一条观测 → 新状态（纯函数：不修改 state/event，无 I/O/时钟/随机）。

    未知事件种类抛 ``ValueError``（显式失败，不静默丢观测）。
    attrs/stamina/week 采用「最后已知值优先」：null 观测不抹掉已读到的值，
    与 RunRecorder 的补写语义一致。
    """
    kind = event.get("kind")
    if kind not in EVENT_KINDS:
        raise ValueError(f"未知观测事件种类: {kind!r}（允许 {EVENT_KINDS}）")
    seq = event.get("seq")
    seq_value = seq if isinstance(seq, int) and not isinstance(seq, bool) else state.n_events
    base = replace(state, seq=seq_value, n_events=state.n_events + 1)

    if kind in ("action", "backfill"):
        week = _as_int(event.get("week"), minimum=1, maximum=99)
        action_raw = event.get("action")
        action = action_raw if action_raw in VALID_ACTIONS else None
        attrs = _as_attrs(event.get("attrs_after"))
        stamina = _as_int(event.get("stamina"), minimum=0, maximum=999)
        new_week = week if week is not None else state.week
        updates: dict[str, Any] = {
            "week": new_week,
            "phase": _phase_of(new_week),
            "attrs": tuple(attrs) if attrs is not None else state.attrs,
            "stamina": stamina if stamina is not None else state.stamina,
            "missing_fields": state.missing_fields
            + (_count_missing(week, action, attrs, stamina) if kind == "action" else _count_missing(attrs, stamina)),
        }
        if kind == "action":
            key = (week, action)
            updates["weeks_seen"] = state.weeks_seen + 1
            updates["duplicates"] = state.duplicates + (1 if state.last_action_key == key else 0)
            updates["last_action_key"] = key
            updates["action_counts"] = _bump_counts(state.action_counts, action)
        return replace(base, **updates)

    if kind == "lesson":
        score = _as_int(event.get("score"), minimum=0, maximum=999999)
        if score is None:
            return replace(base, lesson_unread=state.lesson_unread + 1, missing_fields=state.missing_fields + 1)
        return replace(
            base,
            lesson_total=state.lesson_total + score,
            lesson_known=state.lesson_known + 1,
        )

    if kind == "exam":
        exam = _exam_of(event)
        missing = _count_missing(exam.kind, exam.rank, exam.score, exam.others)
        if state.exams and state.exams[-1] == exam:
            # 与 note_exam 同口径：重复结算观测不重复入账
            return replace(base, missing_fields=state.missing_fields + missing)
        total = state.exam_score_total + (exam.score if exam.score is not None else 0)
        return replace(
            base,
            exams=(*state.exams, exam),
            exam_score_total=total,
            missing_fields=state.missing_fields + missing,
        )

    # kind == "final"
    final = _final_of(event, state)
    missing = _count_missing(
        _as_attrs(event.get("attrs")),
        _as_int(event.get("rank"), minimum=1, maximum=6),
        _as_int(event.get("exam_score"), minimum=0, maximum=999999),
        _as_int(event.get("eval_points"), minimum=1000, maximum=999999),
        parse_grade(event.get("grade")) if isinstance(event.get("grade"), str) else None,
    )
    return replace(base, final=final, missing_fields=state.missing_fields + missing)


def replay(events: Iterable[Mapping[str, Any]]) -> tuple[RunState, ...]:
    """逐事件折叠：返回每个事件之后的状态快照（不含初始状态）。"""
    states: list[RunState] = []
    state = initial_state()
    for event in events:
        state = apply_event(state, event)
        states.append(state)
    return tuple(states)


def legacy_events(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """从旧格式汇总（weeks/exams/final）确定式重建观测序列。

    顺序 = 周记录原序（每周一条 action；lesson 周紧跟一条 lesson 观测，
    分数 null 也如实重建）→ 考试原序 → 结算。seq 从 0 连续编号。
    """
    events: list[dict[str, Any]] = []
    for week in record.get("weeks") or []:
        if not isinstance(week, Mapping):
            continue
        events.append(
            {
                "kind": "action",
                "week": week.get("week"),
                "action": week.get("action"),
                "attrs_after": week.get("attrs_after"),
                "stamina": week.get("stamina"),
            }
        )
        if week.get("action") == "lesson":
            events.append({"kind": "lesson", "score": week.get("lesson_score")})
    for exam in record.get("exams") or []:
        if not isinstance(exam, Mapping):
            continue
        events.append(
            {
                "kind": "exam",
                "exam_kind": exam.get("kind"),
                "rank": exam.get("rank"),
                "score": exam.get("score"),
                "others": exam.get("others"),
            }
        )
    final = record.get("final")
    if isinstance(final, Mapping):
        events.append(
            {
                "kind": "final",
                "attrs": final.get("attrs"),
                "rank": final.get("rank"),
                "exam_score": final.get("exam_score"),
                "eval_points": final.get("eval_points"),
                "grade": final.get("grade"),
            }
        )
    for index, event in enumerate(events):
        event["seq"] = index
    return events


def events_of(record: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """取记录的观测序列：有 events 日志用日志（source=events），否则旧格式重建（legacy）。"""
    events = record.get("events")
    if isinstance(events, list) and events:
        return [dict(event) for event in events if isinstance(event, Mapping)], "events"
    return legacy_events(record), "legacy"


def _jsonify(value: Any) -> Any:
    """元组 → 列表（JSON 原生形态）：冻结期望/指纹/比对都走同一表示，round-trip 不漂移。"""
    if isinstance(value, tuple):
        return [_jsonify(item) for item in value]
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    return value


def state_to_dict(state: RunState) -> dict[str, Any]:
    """状态 → 可 JSON 序列化字典（asdict 递归展开 + 元组归一为列表）。"""
    return _jsonify(asdict(state))


def fingerprint(states: Sequence[RunState]) -> str:
    """快照序列的 sha256 指纹：同观测序列 → 同状态 → 同指纹（逐位可验证）。"""
    payload = json.dumps(
        [state_to_dict(state) for state in states],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_states(a: RunState, b: RunState) -> dict[str, list[Any]]:
    """两个状态的逐字段差异：``{字段: [a值, b值]}``（只列不相等字段）。"""
    left, right = state_to_dict(a), state_to_dict(b)
    return {
        key: [left.get(key), right.get(key)]
        for key in sorted(set(left) | set(right))
        if left.get(key) != right.get(key)
    }


def compare_replays(a: Sequence[RunState], b: Sequence[RunState]) -> dict[str, Any]:
    """逐步比对两条快照序列：首个分歧步 + 每步字段差异 + 长度差。

    公共前缀逐步比；长度不同时 ``first_divergence`` 至少是较短长度（序列本身分歧）。
    """
    diffs: list[dict[str, Any]] = []
    common = min(len(a), len(b))
    for index in range(common):
        fields = compare_states(a[index], b[index])
        if fields:
            diffs.append({"step": index, "fields": fields})
    length_mismatch = len(a) != len(b)
    first = diffs[0]["step"] if diffs else (common if length_mismatch else None)
    return {
        "equal": not diffs and not length_mismatch,
        "steps_a": len(a),
        "steps_b": len(b),
        "length_mismatch": length_mismatch,
        "first_divergence": first,
        "diffs": diffs,
    }


def _exam_dict(exam: ExamSnapshot) -> dict[str, Any]:
    return {
        "kind": exam.kind,
        "rank": exam.rank,
        "score": exam.score,
        "others": list(exam.others) if exam.others is not None else None,
    }


def _final_dict(final: FinalSnapshot | None) -> dict[str, Any] | None:
    if final is None:
        return None
    return {
        "attrs": list(final.attrs) if final.attrs is not None else None,
        "rank": final.rank,
        "exam_score": final.exam_score,
        "eval_points": final.eval_points,
        "grade": final.grade,
    }


def consistency_check(record: Mapping[str, Any]) -> dict[str, Any]:
    """三方对账：events 重放 vs 旧格式重建重放 vs 记录汇总。

    返回 ``{source, consistent, steps, fingerprint, discrepancies, record_diffs}``：
    - ``discrepancies``：两条重放路径终态的语义字段差异（记录器/重放器漂移）；
    - ``record_diffs``：重建终态与记录里 weeks/exams/final 汇总的差异。
    ``missing_fields`` 是观测级计数（补写合并不可比），不参与对账。
    """
    events, source = events_of(record)
    states_live = replay(events)
    states_legacy = replay(legacy_events(record))
    live = states_live[-1] if states_live else initial_state()
    legacy = states_legacy[-1] if states_legacy else initial_state()

    discrepancies: list[dict[str, Any]] = []
    live_dict, legacy_dict = state_to_dict(live), state_to_dict(legacy)
    for field in CONSISTENCY_FIELDS:
        if live_dict.get(field) != legacy_dict.get(field):
            discrepancies.append({"field": field, "events": live_dict.get(field), "legacy": legacy_dict.get(field)})

    record_diffs: list[dict[str, Any]] = []
    weeks = [week for week in record.get("weeks") or [] if isinstance(week, Mapping)]
    if len(weeks) != legacy.weeks_seen:
        record_diffs.append({"field": "weeks_seen", "replay": legacy.weeks_seen, "record": len(weeks)})
    lesson_sum = sum(
        score
        for week in weeks
        if week.get("action") == "lesson"
        for score in [_as_int(week.get("lesson_score"), minimum=0, maximum=999999)]
        if score is not None
    )
    if lesson_sum != legacy.lesson_total:
        record_diffs.append({"field": "lesson_total", "replay": legacy.lesson_total, "record": lesson_sum})
    record_exams = [
        {
            "kind": exam.get("kind") if exam.get("kind") in ("mid", "final") else None,
            "rank": _as_int(exam.get("rank"), minimum=1, maximum=6),
            "score": _as_int(exam.get("score"), minimum=0, maximum=999999),
            "others": _as_scores(exam.get("others")),
        }
        for exam in record.get("exams") or []
        if isinstance(exam, Mapping)
    ]
    replay_exams = [_exam_dict(exam) for exam in legacy.exams]
    if record_exams != replay_exams:
        record_diffs.append({"field": "exams", "replay": replay_exams, "record": record_exams})
    final = record.get("final")
    if isinstance(final, Mapping):
        record_final = {
            "attrs": _as_attrs(final.get("attrs")),
            "rank": _as_int(final.get("rank"), minimum=1, maximum=6),
            "exam_score": _as_int(final.get("exam_score"), minimum=0, maximum=999999),
            "eval_points": _as_int(final.get("eval_points"), minimum=1000, maximum=999999),
            "grade": parse_grade(final.get("grade")) if isinstance(final.get("grade"), str) else None,
        }
        replay_final = _final_dict(legacy.final)
        if record_final != replay_final:
            record_diffs.append({"field": "final", "replay": replay_final, "record": record_final})
    elif legacy.final is not None:
        record_diffs.append({"field": "final", "replay": _final_dict(legacy.final), "record": None})

    return {
        "source": source,
        "consistent": not discrepancies and not record_diffs,
        "steps": len(states_live),
        "fingerprint": fingerprint(states_live),
        "discrepancies": discrepancies,
        "record_diffs": record_diffs,
    }
