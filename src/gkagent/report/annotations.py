"""T7③ 人工标注 → 回归用例（纯函数转换，闭环的离线 half）。

复盘页（review_page）导出标注 JSON（schema ``gkagent-review-annotations/1``）：
人在逐回合/逐步行上给 ``verdict``（ok/bad/unsure）+ ``comment`` + ``expected``
（``k=v;k=v`` 观测修正值）。本模块把 **verdict=bad 且带 expected** 的标注转成
可执行回归用例，冻结进 ``tests/fixtures/review_regressions.json``：

- ``target=week/exam/final``：把人工修正值作为**新观测事件**追加到该局观测序列
  末尾，用 ``run_replay.replay`` 算出终态并**整态冻结**为期望——以后重放语义
  变了（同观测不再同状态）回归立刻红。
- ``target=step``：把人工修正（如 ``outcome=moved``）应用到该步轨迹行，冻结
  ``summarize_traces`` 的分类结论（是否异常/outcome 计数）——钉住互验复盘口径。

用例在**转换时**（人工复核过的代码版本）计算期望并写死进 JSON；测试只负责
重算比对，不重新推导期望，避免「被测代码给自己出题」。

约定：expected 的值先按 JSON 解析（数字/列表/布尔），解析不了按字符串；
``attrs_after=210,90,95`` 这类逗号列表不是合法 JSON，按字符串保留，
转换时再按观测字段口径解析（见 ``_observation_value``）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from gkagent.data.run_replay import legacy_events, replay, state_to_dict
from gkagent.runtime.trace import summarize_traces

SCHEMA = "gkagent-review-annotations/1"
FIXTURE_SCHEMA = "gkagent-review-regressions/1"
VERDICTS = ("ok", "bad", "unsure")


def parse_expected(text: Any) -> dict[str, Any]:
    """``k=v;k=v`` → dict；值先试 JSON 解析，失败按字符串；空文本 → {}。"""
    if not isinstance(text, str) or not text.strip():
        return {}
    result: dict[str, Any] = {}
    for part in text.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, _, raw = part.partition("=")
        key, raw = key.strip(), raw.strip()
        if not key:
            continue
        try:
            result[key] = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            result[key] = raw
    return result


def _observation_value(key: str, value: Any) -> Any:
    """观测字段口径：attrs_after/others 允许 ``210,90,95`` 逗号列表写法。"""
    if key in ("attrs_after", "others") and isinstance(value, str):
        parts = [item.strip() for item in value.split(",") if item.strip()]
        try:
            return [int(item) for item in parts]
        except ValueError:
            return value
    return value


def normalize_annotations(payload: Mapping[str, Any]) -> dict[str, Any]:
    """校验标注导出 JSON；坏 schema/缺 episode 显式抛 ``ValueError``（不静默吞）。"""
    if not isinstance(payload, Mapping):
        raise ValueError("标注顶层必须是对象")  # noqa: TRY004 - 坏数据统一 ValueError，CLI 按此退出
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"标注 schema 必须是 {SCHEMA!r}，收到 {payload.get('schema')!r}")
    episode = payload.get("episode")
    if not isinstance(episode, str) or not episode.strip():
        raise ValueError("标注缺 episode")
    raw = payload.get("annotations")
    if not isinstance(raw, list):
        raise ValueError("标注 annotations 必须是列表")  # noqa: TRY004 - 同上
    annotations: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            continue
        ann_id = item.get("id")
        target = item.get("target")
        if not isinstance(ann_id, str) or target not in ("week", "exam", "final", "step"):
            continue
        expected = item.get("expected")
        annotations.append(
            {
                "id": ann_id,
                "target": target,
                "key": item.get("key"),
                "verdict": verdict,
                "comment": str(item.get("comment") or ""),
                "expected": expected if isinstance(expected, dict) else parse_expected(expected),
            }
        )
    return {
        "episode": episode.strip(),
        "fingerprint": str(payload.get("fingerprint") or ""),
        "provenance": str(payload.get("provenance") or "human-annotation"),
        "annotations": annotations,
    }


def _correction_events(target: str, key: Any, expected: Mapping[str, Any], record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """人工修正 → 追加观测事件（不改原观测，修正作为新观测追加，重放最后已知值优先）。"""
    expected = {name: _observation_value(name, value) for name, value in expected.items()}
    if target == "week":
        weeks = record.get("weeks") or []
        row = weeks[int(key)] if isinstance(key, int) and 0 <= int(key) < len(weeks) else {}
        events: list[dict[str, Any]] = []
        if "lesson_score" in expected:
            events.append({"kind": "lesson", "score": expected["lesson_score"]})
        obs = {name: expected[name] for name in ("week", "action", "attrs_after", "stamina") if name in expected}
        if obs:
            kind = "action" if "action" in obs else "backfill"
            events.append(
                {
                    "kind": kind,
                    "week": obs.get("week", row.get("week") if isinstance(row, Mapping) else None),
                    "action": obs.get("action", row.get("action") if isinstance(row, Mapping) else None),
                    "attrs_after": obs.get("attrs_after"),
                    "stamina": obs.get("stamina"),
                }
            )
        return events
    if target == "exam":
        exams = record.get("exams") or []
        row = exams[int(key)] if isinstance(key, int) and 0 <= int(key) < len(exams) else {}
        row = row if isinstance(row, Mapping) else {}
        return [
            {
                "kind": "exam",
                "exam_kind": expected.get("exam_kind", row.get("kind")),
                "rank": expected.get("rank", row.get("rank")),
                "score": expected.get("score", row.get("score")),
                "others": expected.get("others", row.get("others")),
            }
        ]
    if target == "final":
        return [
            {
                "kind": "final",
                "attrs": expected.get("attrs"),
                "rank": expected.get("rank"),
                "exam_score": expected.get("exam_score"),
                "eval_points": expected.get("eval_points"),
                "grade": expected.get("grade"),
            }
        ]
    return []


def cases_from_annotations(
    payload: Mapping[str, Any],
    record: Mapping[str, Any],
    trace_rows: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """标注 → 回归用例列表（只转 verdict=bad 且带 expected 的；其余留作页面历史）。"""
    norm = normalize_annotations(payload)
    episode = norm["episode"]
    base = legacy_events(record)
    cases: list[dict[str, Any]] = []
    for ann in norm["annotations"]:
        if ann["verdict"] != "bad" or not ann["expected"]:
            continue
        target, key = ann["target"], ann["key"]
        if target == "step":
            row = next((dict(r) for r in trace_rows if r.get("step") == key), None)
            if row is None:
                continue
            row.update(ann["expected"])
            summary = summarize_traces([row])
            cases.append(
                {
                    "id": f"{episode}:step:{key}",
                    "kind": "trace",
                    "episode": episode,
                    "target": target,
                    "key": key,
                    "comment": ann["comment"],
                    "provenance": norm["provenance"],
                    "rows": [row],
                    "expect": {
                        "anomaly": bool(summary["anomalies"]),
                        "outcomes": summary["outcomes"],
                        "retaps": summary["retaps"],
                        "lost": summary["lost"],
                    },
                }
            )
            continue
        events = base + _correction_events(target, key, ann["expected"], record)
        for index, event in enumerate(events):
            event["seq"] = index
        states = replay(events)
        if not states:
            continue
        cases.append(
            {
                "id": f"{episode}:{target}:{key}",
                "kind": "replay",
                "episode": episode,
                "target": target,
                "key": key,
                "comment": ann["comment"],
                "provenance": norm["provenance"],
                "events": events,
                "expect": state_to_dict(states[-1]),
            }
        )
    return cases


def merge_cases(fixture: Mapping[str, Any] | None, new_cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """合并进夹具：按 case id 去重，新用例覆盖同 id 旧用例（人工复核更新）。"""
    merged: dict[str, dict[str, Any]] = {}
    if isinstance(fixture, Mapping):
        for case in fixture.get("cases") or []:
            if isinstance(case, Mapping) and isinstance(case.get("id"), str):
                merged[case["id"]] = dict(case)
    for case in new_cases:
        if isinstance(case, Mapping) and isinstance(case.get("id"), str):
            merged[case["id"]] = dict(case)
    return {"schema": FIXTURE_SCHEMA, "cases": [merged[key] for key in sorted(merged)]}
