"""跑局数据管道：每局真机数据增量落盘到 ``data/runs/<episode>.json``。

为什么需要：模拟器 6 个参数只有 3 个评价点当锚，欠定。每局把「每周行动 +
课程得分 + 考试 6 人分数 + 最终结算」边跑边写盘，超时/被 kill 也保住已跑完的周。

落盘格式（``scripts/run_report.py`` 与标定脚本共用）::

    {
      "episode": "ep-xxx",
      "started_at": "2026-11-15 18:47:00",
      "weeks": [{"week": 3, "action": "lesson", "lesson_score": 152,
                 "attrs_after": [210, 90, 95], "stamina": 22}],
      "exams": [{"kind": "mid", "rank": 2, "score": 8421,
                 "others": [9210, 8421, 7003, 5120, 4110, 3980]}],
      "final": {"attrs": [344, 235, 533], "rank": 1, "exam_score": 17300,
                "eval_points": 5577, "grade": "C+"},
      "meta": {"audition_coefficient": 4.11, "lesson_min_stamina": 10}
    }

约定：

- ``weeks`` 每完成一个周行动写一条；``lesson_score`` 只认课程帧/结算屏读到的
  分数，读不到写 ``null`` 并在 ``note`` 里说明，**绝不用属性增量推算冒充**。
- ``exams`` 期中/期末各写一条；``others`` 是从高到低的全员分数（含自己）。
- ``final`` 允许用最后一次采样的三维（结算页通常不再显示三颗属性圆）。
- 每个字段读不到都写 ``null`` 并记 ``note``，不编造数字。

所有写入都是「先写 ``.tmp`` 再 ``os.replace``」的原子写；每个 ``note_*`` 立即
flush，进程被 kill 不会丢已经写下的数据。
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = ROOT / "data" / "runs"
POLICY_PATH = ROOT / "data" / "knowledge" / "policy.json"

#: 周行动只有这四种（模拟器的 ProduceSim 动作集合）。
VALID_ACTIONS = ("lesson", "train", "rest", "outing")
#: 「初」Regular 剧本的期中/期末周（与 sim.produce.ProduceConfig 默认一致）。
MIDTERM_WEEK = 6
FINAL_WEEK = 12
#: 模拟器标定所需配置的默认值（policy.json 缺文件/缺键时兜底；不是实测数据）。
#: 训练体力门新键 ``training_min_stamina`` 优先；旧键 ``lesson_min_stamina`` 保留同步。
DEFAULT_META = {"audition_coefficient": 4.11, "training_min_stamina": 10, "lesson_min_stamina": 10}

_WEEK_RE = re.compile(r"(\d{1,2})\s*周")
_GRADE_RE = re.compile(r"([SABCDE])\s*(\+?)")
_EXAM_RANK_RE = re.compile(r"([1-6])\s*(?:st|nd|rd|th)\b", re.IGNORECASE)
_EXAM_SCORE_RE = re.compile(r"(\d{2,6})\s*(?:pt|point)\b", re.IGNORECASE)


def _norm_text(text: Any) -> str:
    """NFKC + 压空白：全角字母/数字/加号先归一，避免「Ｃ＋」读不出来。"""
    if text is None:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"[\s\u3000]+", " ", value).strip()


def _as_int(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    """转 int；bool/不可转/越界返回 None（不拿 0 顶替读不到的值）。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def _as_attrs(value: Any) -> list[int] | None:
    """三维必须是 3 个 0..2000 的整数，否则整体按读不到处理。"""
    if value is None:
        return None
    try:
        values = [int(item) for item in value]
    except (TypeError, ValueError):
        return None
    if len(values) != 3 or any(item < 0 or item > 2000 for item in values):
        return None
    return values


def _as_scores(value: Any) -> list[int] | None:
    """分数列表：只保留 0..999999 的整数，从高到低排序（others 的口径）。"""
    if value is None:
        return None
    values: list[int] = []
    try:
        iterator = list(value)
    except TypeError:
        return None
    for item in iterator:
        number = _as_int(item, minimum=0, maximum=999999)
        if number is not None:
            values.append(number)
    if not values:
        return None
    return sorted(values, reverse=True)


def parse_grade(text: Any) -> str | None:
    """评价字母：``C+`` / ``S`` / ``A+``；全角/空格已归一，非纯评级返回 None。"""
    value = _norm_text(text).upper()
    match = _GRADE_RE.fullmatch(value)
    if match is None:
        return None
    return match.group(1) + match.group(2)


def parse_eval_points(text: Any) -> int | None:
    """评价点：4-6 位数字（真机 C+ = 5577）；位数不对/读不到返回 None。"""
    digits = re.sub(r"[^0-9]", "", _norm_text(text))
    if not 4 <= len(digits) <= 6 or int(digits) == 0:
        return None
    return int(digits)


def week_from_countdown(
    text: Any,
    phase: str | None,
    *,
    midterm_week: int = MIDTERM_WEEK,
    final_week: int = FINAL_WEEK,
) -> int | None:
    """把行动页左上角「期中截止 4周 / 最终截止 6周」换算成绝对周数。

    真机实测（data/manual/182343 等）：期中阶段 ``4周`` = 第 2 周，即
    ``midterm_week - 剩周``；期末阶段 ``6周`` = 第 7 周，即
    ``final_week - 剩周 + 1``（期中考试那周不占行动页）。换算不出来返回 None。
    """
    match = _WEEK_RE.search(_norm_text(text))
    if match is None or phase not in ("mid", "final"):
        return None
    left = int(match.group(1))
    week = midterm_week - left if phase == "mid" else final_week - left + 1
    if 1 <= week <= final_week:
        return week
    return None


def parse_exam_result(lines: Iterable[Any]) -> dict[str, Any] | None:
    """解析考试结算屏（``1st 581Pt`` … 6 行）→ rank/score/others。

    行对象只需要 ``text`` 和 ``box=(x, y, w, h)``（:class:`OcrLine` 即可）。
    自己那一行靠「日志」按钮定位（只有玩家行有），并用排名数字兜底；分数行
    按 y 就近匹配。``others`` 始终从高到低排序；第 6 名常被底部按钮遮挡，
    读到的不足 6 人时在 ``note`` 里说明，不补编数字。
    """
    ranks: dict[int, int] = {}
    scores: list[tuple[int, int]] = []
    seen_scores: set[tuple[int, int]] = set()
    log_y: int | None = None
    wei_ys: list[int] = []
    badge_digits: list[tuple[int, int]] = []
    for line in lines or []:
        text = _norm_text(getattr(line, "text", ""))
        if not text:
            continue
        box = getattr(line, "box", (0, 0, 0, 0))
        try:
            _x, y, _width, height = (int(value) for value in box[:4])
        except (TypeError, ValueError):
            continue
        center_y = y + height // 2
        rank_match = _EXAM_RANK_RE.match(text)
        if rank_match is not None:
            ranks.setdefault(int(rank_match.group(1)), center_y)
        score_match = _EXAM_SCORE_RE.search(text)
        if score_match is not None:
            score = int(score_match.group(1))
            key = (score, center_y)
            if 1 <= score <= 999999 and key not in seen_scores:
                seen_scores.add(key)
                scores.append((score, center_y))
            continue
        if rank_match is not None:
            continue
        if "日志" in text:
            log_y = center_y
        elif text == "位":
            wei_ys.append(center_y)
        elif text.isdigit() and len(text) == 1:
            badge_digits.append((int(text), center_y))

    if not scores:
        return None
    others = sorted((score for score, _y in scores), reverse=True)

    own_rank: int | None = None
    own_score: int | None = None
    if log_y is not None:
        if ranks:
            candidate = min(ranks, key=lambda rank: abs(ranks[rank] - log_y))
            if abs(ranks[candidate] - log_y) <= 90:
                own_rank = candidate
        nearest = min(scores, key=lambda item: abs(item[1] - log_y))
        if abs(nearest[1] - log_y) <= 90:
            own_score = nearest[0]
    if own_rank is None:
        # 顶部「3位」大徽章：数字行 + 「位」字挨在一起（日志按钮被裁掉时兜底）
        for digit, digit_y in badge_digits:
            if 1 <= digit <= 6 and any(abs(digit_y - wei_y) <= 90 for wei_y in wei_ys):
                own_rank = digit
                break
    if own_score is None and own_rank is not None and own_rank in ranks:
        rank_y = ranks[own_rank]
        nearest = min(scores, key=lambda item: abs(item[1] - rank_y))
        if abs(nearest[1] - rank_y) <= 90:
            own_score = nearest[0]
    if own_score is not None and own_score not in others:
        others = sorted([*others, own_score], reverse=True)

    notes: list[str] = []
    if len(others) < 6:
        notes.append(f"只读到 {len(others)}/6 人分数（第 6 名常被底部按钮遮挡）")
    if own_rank is None:
        notes.append("rank 未读到")
    if own_score is None:
        notes.append("score 未读到")
    result: dict[str, Any] = {
        "rank": own_rank,
        "score": own_score,
        "others": others,
    }
    if notes:
        result["note"] = "；".join(notes)
    return result


def load_meta(policy_path: Path | str | None = None) -> dict[str, Any]:
    """从 ``data/knowledge/policy.json`` 的 produce 段取标定配置（缺就回默认）。

    训练体力门新旧键都认：``training_min_stamina`` 优先，缺失时读
    ``lesson_min_stamina``；返回的 meta 同时写新旧两个键，旧脚本继续可读。
    """
    meta: dict[str, Any] = dict(DEFAULT_META)
    path = Path(policy_path) if policy_path is not None else POLICY_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return meta
    produce = payload.get("produce") if isinstance(payload, Mapping) else None
    if not isinstance(produce, Mapping):
        return meta
    for key in meta:
        value = produce.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            meta[key] = value
    threshold = produce.get("training_min_stamina")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        threshold = produce.get("lesson_min_stamina")
    if isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
        meta["training_min_stamina"] = threshold
        meta["lesson_min_stamina"] = threshold
    return meta


def action_of(tick_action: Any) -> str | None:
    """把 ``ProduceDriver`` 的 tick.action 映射成四类周行动之一。

    ``sim-lesson`` / ``sim-rest`` / ``sim-outing`` / ``sim-train-Da`` 是模拟器
    选行动分支，去前缀后同样归并；``lesson-skip`` / ``stamina-wait`` 不是行动
    开始，返回 None（调用方不得据此新建周记录）。
    """
    raw = _norm_text(tick_action).lower()
    raw = raw.removeprefix("sim-")
    if raw == "lesson":
        return "lesson"
    if raw == "rest":
        return "rest"
    if raw in ("outing", "go-out", "consult"):
        return "outing"
    if raw.startswith("train"):
        return "train"
    return None


def _refresh_note(record: dict[str, Any], extra: Iterable[str] = ()) -> None:
    """按当前字段重新生成 ``note``：补写成功后旧缺失说明会自动消失。"""
    notes = [str(item) for item in extra if str(item).strip()]
    if record.get("week") is None and "week" in record:
        notes.append("week 未读到")
    if "action" in record and record.get("action") is None:
        notes.append("action 未识别")
    if "attrs_after" in record and record.get("attrs_after") is None:
        notes.append("attrs_after 未读到")
    if "stamina" in record and record.get("stamina") is None:
        notes.append("stamina 未读到")
    if (
        record.get("action") == "lesson"
        and "lesson_score" in record
        and record.get("lesson_score") is None
    ):
        notes.append("lesson_score 未读到（未用属性增量推算）")
    if record.get("kind") is None and "kind" in record:
        notes.append("kind 未识别")
    if record.get("rank") is None and "rank" in record:
        notes.append("rank 未读到")
    if record.get("score") is None and "score" in record:
        notes.append("score 未读到")
    if record.get("others") is None and "others" in record:
        notes.append("others 未读到")
    if record.get("attrs") is None and "attrs" in record:
        notes.append("attrs 未读到")
    if record.get("exam_score") is None and "exam_score" in record:
        notes.append("exam_score 未读到")
    if record.get("eval_points") is None and "eval_points" in record:
        notes.append("eval_points 未读到")
    if record.get("grade") is None and "grade" in record:
        notes.append("grade 未读到")
    deduped = list(dict.fromkeys(notes))
    if deduped:
        record["note"] = "；".join(deduped)
    else:
        record.pop("note", None)


class RunRecorder:
    """一局的跑局记录器：每个 ``note_*`` 立即原子写盘。

    ``note_action`` 支持补写：课程结束时可以先落一条 ``attrs_after=null`` 的
    周记录（保住 lesson_score），下一周行动页读到三维后再用同一
    ``(week, action)`` 调用一次，把缺失字段补上而不是追加第二条。
    """

    def __init__(
        self,
        episode: str,
        *,
        runs_dir: Path | str | None = None,
        meta: Mapping[str, Any] | None = None,
        started_at: str | None = None,
        clock: Any = None,
    ) -> None:
        self.episode = str(episode).strip() or "ep-unknown"
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.episode).strip("._-") or "ep-unknown"
        self.runs_dir = Path(runs_dir) if runs_dir is not None else RUNS_DIR
        self.path = self.runs_dir / f"{safe}.json"
        self.clock = clock if clock is not None else time.time
        self.writes = 0
        self._pending_lesson: int | None = None
        self._has_pending_lesson = False
        self._meta_override = dict(meta) if meta is not None else None
        self.data = self._load_existing()
        if self.data is None:
            self.data = self._new_data(started_at)
        self.last_attrs = self._last_attrs_from_weeks()
        self.flush()

    # ------------------------------------------------------------------ 初始化
    def _new_data(self, started_at: str | None) -> dict[str, Any]:
        if started_at is None:
            started_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(self.clock())))
        meta = load_meta()
        if self._meta_override is not None:
            meta.update(self._meta_override)
        return {
            "episode": self.episode,
            "started_at": started_at,
            "weeks": [],
            "exams": [],
            "final": None,
            "meta": meta,
        }

    def _load_existing(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("episode") != self.episode:
            return None
        payload.setdefault("started_at", "")
        payload.setdefault("weeks", [])
        payload.setdefault("exams", [])
        payload.setdefault("final", None)
        meta = payload.get("meta")
        payload["meta"] = dict(meta) if isinstance(meta, Mapping) else load_meta()
        return payload

    def _last_attrs_from_weeks(self) -> list[int] | None:
        for week in reversed(self.data.get("weeks") or []):
            attrs = _as_attrs(week.get("attrs_after"))
            if attrs is not None:
                return attrs
        return None

    # ------------------------------------------------------------------ 周行动
    def note_action(
        self,
        week: Any,
        action: Any,
        attrs: Any,
        stamina: Any,
    ) -> dict[str, Any]:
        """记录一个周行动（行动页读到「行动后的三维/体力」时调用）。

        读不到的 ``attrs_after`` / ``stamina`` / ``lesson_score`` 写 ``null``
        并记 ``note``，不用上一帧或属性增量顶替。
        """
        week_value = _as_int(week, minimum=1, maximum=99)
        action_value = action if action in VALID_ACTIONS else None
        attrs_value = _as_attrs(attrs)
        stamina_value = _as_int(stamina, minimum=0, maximum=999)
        record: dict[str, Any] = {
            "week": week_value,
            "action": action_value,
            "lesson_score": None,
            "attrs_after": attrs_value,
            "stamina": stamina_value,
        }
        last = self.data["weeks"][-1] if self.data["weeks"] else None
        if (
            isinstance(last, dict)
            and week_value is not None
            and last.get("week") == week_value
            and last.get("action") == action_value
            and (last.get("attrs_after") is None or last.get("stamina") is None)
        ):
            # 补写：课程结束时先落的记录（attrs/stamina 还没读到）现在补上
            if attrs_value is not None:
                last["attrs_after"] = attrs_value
            if stamina_value is not None:
                last["stamina"] = stamina_value
            record = last
        else:
            if action_value != "lesson":
                record["lesson_score"] = None
            self.data["weeks"].append(record)

        if (
            record.get("action") == "lesson"
            and record.get("lesson_score") is None
            and self._has_pending_lesson
        ):
            record["lesson_score"] = self._pending_lesson
            self._pending_lesson = None
            self._has_pending_lesson = False
        if attrs_value is not None:
            self.last_attrs = attrs_value
        _refresh_note(record)
        self.flush()
        return record

    def note_lesson(self, score: Any) -> dict[str, Any] | None:
        """记录本局课程得分；刚追加的 lesson 周记录直接补上，否则暂存给下一条。

        只认**最后一条**周记录：不能往回找「上一条缺分的 lesson」，否则上一节
        没读到分时，这一节的分数会错误填到上一周。
        """
        value = _as_int(score, minimum=0, maximum=999999)
        last = self.data["weeks"][-1] if self.data["weeks"] else None
        if (
            isinstance(last, dict)
            and last.get("action") == "lesson"
            and last.get("lesson_score") is None
        ):
            last["lesson_score"] = value
            self._pending_lesson = None
            self._has_pending_lesson = False
            _refresh_note(last)
            self.flush()
            return last
        self._pending_lesson = value
        self._has_pending_lesson = True
        return None

    # ------------------------------------------------------------------ 考试
    def note_exam(self, kind: Any, rank: Any, score: Any, others: Any) -> dict[str, Any]:
        """记录一场考试；``others`` 从高到低（含自己），读不全时记 note。"""
        kind_value = kind if kind in ("mid", "final") else None
        rank_value = _as_int(rank, minimum=1, maximum=6)
        score_value = _as_int(score, minimum=0, maximum=999999)
        others_value = _as_scores(others)
        if others_value is not None and score_value is not None and score_value not in others_value:
            others_value = sorted([*others_value, score_value], reverse=True)
        record: dict[str, Any] = {
            "kind": kind_value,
            "rank": rank_value,
            "score": score_value,
            "others": others_value,
        }
        extra: list[str] = []
        if others_value is not None and len(others_value) < 6:
            extra.append(f"只读到 {len(others_value)}/6 人分数")
        _refresh_note(record, extra=extra)
        if self.data["exams"] and self.data["exams"][-1] == record:
            return self.data["exams"][-1]
        self.data["exams"].append(record)
        self.flush()
        return record

    # ------------------------------------------------------------------ 结算
    def note_final(
        self,
        attrs: Any,
        rank: Any,
        exam_score: Any,
        eval_points: Any,
        grade: Any,
    ) -> dict[str, Any]:
        """记录最终结算；缺失字段按「最后一次采样」兜底，仍读不到写 null。

        - ``attrs`` 缺省时用最后一次周行动采到的三维（结算页常不再显示三维圆）；
        - ``rank`` / ``exam_score`` 缺省时用最后一场**期末**考试记录（期中不冒充）；
        - 其余字段只接受读到的值，不编造。
        """
        final = self.data.get("final")
        if not isinstance(final, dict):
            final = {
                "attrs": None,
                "rank": None,
                "exam_score": None,
                "eval_points": None,
                "grade": None,
            }
            self.data["final"] = final
        attrs_value = _as_attrs(attrs) or self.last_attrs or self._last_attrs_from_weeks()
        if attrs_value is not None:
            final["attrs"] = attrs_value
            self.last_attrs = attrs_value
        rank_value = _as_int(rank, minimum=1, maximum=6)
        exam_value = _as_int(exam_score, minimum=0, maximum=999999)
        # 只从**期末**考试补 rank/exam_score：拿期中名次冒充期末会把对账带偏
        final_exam = next(
            (exam for exam in reversed(self.data["exams"]) if exam.get("kind") == "final"),
            None,
        )
        if final_exam is not None:
            if rank_value is None:
                rank_value = _as_int(final_exam.get("rank"), minimum=1, maximum=6)
            if exam_value is None:
                exam_value = _as_int(final_exam.get("score"), minimum=0, maximum=999999)
        if rank_value is not None:
            final["rank"] = rank_value
        if exam_value is not None:
            final["exam_score"] = exam_value
        points_value = _as_int(eval_points, minimum=1000, maximum=999999)
        if points_value is None:
            points_value = parse_eval_points(eval_points)
        if points_value is not None:
            final["eval_points"] = points_value
        grade_value = parse_grade(grade) if isinstance(grade, str) else None
        if grade_value is not None:
            final["grade"] = grade_value
        _refresh_note(final)
        self.flush()
        return final

    # ------------------------------------------------------------------ 落盘
    def flush(self) -> bool:
        """原子写：先写 ``<name>.json.tmp``，fsync 后再 ``os.replace`` 覆盖正式文件。"""
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.runs_dir.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.data, ensure_ascii=False, indent=2)
            with tmp.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        self.writes += 1
        return True

    def meta_for(self, key: str, default: Any = None) -> Any:
        """取 meta 里的一项配置（auto_produce 日志/对账用）。"""
        meta = self.data.get("meta")
        return meta.get(key, default) if isinstance(meta, Mapping) else default

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"RunRecorder({self.episode!r}, path={str(self.path)!r}, writes={self.writes})"
