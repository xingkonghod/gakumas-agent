"""LessonPolicy 的 engine 开关：默认 rules，expectimax 可选，异常退回 rules。"""

from __future__ import annotations

import json
from pathlib import Path

from gkagent.policy.lesson import LessonPolicy
from gkagent.sim.expectimax import ExpectimaxResult
from gkagent.vision.lesson import LessonCard, LessonState


class FakeTable:
    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = rows

    def get(self, name: str) -> dict | None:
        return self.rows.get(name) or self.rows.get((name or "").rstrip("+＋"))


TABLE = FakeTable(
    {
        "大牌": {"cost": 5, "effects": [{"type": "ExamLesson", "values": [40]}]},
        "小牌": {"cost": 1, "effects": [{"type": "ExamLesson", "values": [5]}]},
    }
)


def _card(index: int, name: str, score: int, cost: int) -> LessonCard:
    return LessonCard(
        index=index,
        box=(0, 0, 1, 1),
        point=(100 + index, 200),
        name=name,
        score=score,
        cost=cost,
    )


def _state(**kwargs) -> LessonState:
    base = {
        "kind": "lesson",
        "turns_left": 3,
        "total_turns": 6,
        "score": 50,
        "gauge": 100,
        "stamina": 10,
        "cards": (_card(0, "大牌", 40, 5), _card(1, "小牌", 5, 1)),
    }
    base.update(kwargs)
    return LessonState(**base)


def _policy(tmp_path: Path, **kwargs) -> LessonPolicy:
    policy = LessonPolicy(params_path=tmp_path / "missing.json", **kwargs)
    policy._table = TABLE
    return policy


def test_default_engine_is_rules(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    assert policy.engine == "rules"
    state = _state()
    rules = policy.decide(state)
    explicit = _policy(tmp_path, engine="rules").decide(state)
    assert (rules.kind, rules.index) == (explicit.kind, explicit.index)


def test_policy_json_can_switch_engine(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps({"version": 1, "lesson": {"engine": "expectimax"}}),
        encoding="utf-8",
    )
    policy = LessonPolicy(params_path=path)
    policy._table = TABLE
    assert policy.engine == "expectimax"
    # 未知取值不能把 engine 变成非法状态 → 退回 rules
    path.write_text(
        json.dumps({"version": 1, "lesson": {"engine": "magic"}}), encoding="utf-8"
    )
    assert LessonPolicy(params_path=path).engine == "rules"


def test_expectimax_engine_maps_lesson_state(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake(state, *args, **kwargs):
        captured["state"] = state
        captured["kwargs"] = kwargs
        return ExpectimaxResult(
            card=state.hand[0],
            utility=0.875,
            skip_utility=0.5,
            actions=(("大牌", 0.875),),
            nodes=7,
            elapsed_ms=1.5,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", fake, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax")
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.index == 0
    assert action.card is not None and action.card.name == "大牌"
    assert action.expected == 0.875
    assert "expectimax" in action.reason
    mapped = captured["state"]
    assert mapped.stamina == 10
    assert mapped.score == 50
    assert mapped.turns_left == 3
    assert mapped.total_turns == 6
    assert mapped.clear == 100
    assert mapped.perfect == 200
    assert mapped.plays_used == 0


def test_expectimax_exception_falls_back_to_rules(monkeypatch, tmp_path: Path) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("sim exploded")

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", boom, raising=True
    )
    state = _state()
    rules = _policy(tmp_path).decide(state)
    fallback = _policy(tmp_path, engine="expectimax").decide(state)
    assert (fallback.kind, fallback.index) == (rules.kind, rules.index)


def test_expectimax_skip_intercepted_when_cards_affordable(
    monkeypatch, tmp_path: Path
) -> None:
    """2026-11-21 用户规则：搜索建议 SKIP 不算数——还有付得起的牌就硬打一张。"""

    def fake(state, *args, **kwargs):
        return ExpectimaxResult(
            card=None,
            utility=0.0,
            skip_utility=0.0,
            actions=(),
            nodes=1,
            elapsed_ms=0.1,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", fake, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax")
    state = _state()
    # allow_skip=True 也不许跳过（有付得起的牌）
    action = policy.decide(state)
    assert action.kind == "card"
    assert "SKIP" in policy.decision_note() or "fallback=" in policy.decision_note()
    # 考试模式（allow_skip=False）：更不能 SKIP
    action = policy.decide(state, allow_skip=False)
    assert action.kind in {"card", "wait"}


# ---------------------------------------------------------------- 决策可观测性


def test_decision_note_reports_engine(monkeypatch, tmp_path: Path) -> None:
    def fake(state, *args, **kwargs):
        return ExpectimaxResult(
            card=state.hand[0],
            utility=0.9,
            skip_utility=0.5,
            actions=(),
            nodes=3,
            elapsed_ms=1.0,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", fake, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax")
    policy.decide(_state())
    note = policy.decision_note()
    assert "eng=expectimax" in note
    assert "fallback=" not in note
    assert policy.last_decision["engine"] == "expectimax"


def test_decision_note_reports_search_failure(monkeypatch, tmp_path: Path) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("sim exploded")

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", boom, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax")
    action = policy.decide(_state())
    # 搜索异常不能影响出牌，但要能看出「这手其实是规则打的」
    assert action.kind == "card"
    note = policy.decision_note()
    assert "eng=expectimax" in note
    assert "fallback=" in note and "异常" in note


def test_decision_note_reports_missing_state(tmp_path: Path) -> None:
    """体力读不到 → 搜索用不了，decision_note 里必须写明原因。"""
    policy = _policy(tmp_path, engine="expectimax")
    action = policy.decide(_state(stamina=None))
    assert action.kind in {"card", "wait"}
    note = policy.decision_note()
    assert "fallback=体力未知" in note


def test_decision_note_rules_engine(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    policy.decide(_state())
    assert policy.decision_note() == "eng=rules"
