"""LessonPolicy 的 engine 开关与「禁止回退 rules」规则。

用户规则（2026-11-21）：bot 不许回退 rules——搜索引擎搜索异常/结果失配时抛
``RuleFallbackBlocked``，不再静默用规则引擎打；搜索建议 SKIP 时按搜索结果自己的
动作价值硬打；状态没读全返回 ``wait`` 等下一帧重读。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.policy.lesson import LessonPolicy, RuleFallbackBlocked
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


def _card(index: int, name: str, score: int, cost: int, *, buff: bool = False) -> LessonCard:
    return LessonCard(
        index=index,
        box=(0, 0, 1, 1),
        point=(100 + index, 200),
        name=name,
        score=score,
        cost=cost,
        buff=buff,
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
    # 未知取值不能把 engine 变成非法状态：配置文件里的坏值仍按默认 rules 解析
    # （这是构造期配置默认，不是运行期静默回退；显式 engine= 写错会直接抛错）。
    path.write_text(
        json.dumps({"version": 1, "lesson": {"engine": "magic"}}), encoding="utf-8"
    )
    assert LessonPolicy(params_path=path).engine == "rules"


def test_unknown_explicit_engine_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="未知出牌引擎"):
        _policy(tmp_path, engine="rulse")


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
    # 真机出牌链路没有喝饮料动作：搜索必须关掉饮料，否则 card=None 会被当成 SKIP。
    assert captured["kwargs"]["allow_drinks"] is False


def test_expectimax_exception_blocks_rule_fallback(monkeypatch, tmp_path: Path) -> None:
    """搜索异常不再退回 rules：必须抛 RuleFallbackBlocked（由真机入口中止本局）。"""

    def boom(*args, **kwargs):
        raise RuntimeError("sim exploded")

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", boom, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax")
    with pytest.raises(RuleFallbackBlocked, match="sim exploded"):
        policy.decide(_state())
    assert "异常" in policy.last_fallback_reason


def test_allow_rule_fallback_debug_switch(monkeypatch, tmp_path: Path) -> None:
    """只有显式调试开关才保留旧回退行为（真机入口永远不传 True）。"""

    def boom(*args, **kwargs):
        raise RuntimeError("sim exploded")

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", boom, raising=True
    )
    state = _state()
    rules = _policy(tmp_path).decide(state)
    fallback = _policy(
        tmp_path, engine="expectimax", allow_rule_fallback=True
    ).decide(state)
    assert (fallback.kind, fallback.index) == (rules.kind, rules.index)


def test_expectimax_skip_intercepted_by_search_ranking(
    monkeypatch, tmp_path: Path
) -> None:
    """搜索建议 SKIP 不算数：还有付得起的牌就按搜索结果自己的动作价值硬打。"""

    def fake(state, *args, **kwargs):
        return ExpectimaxResult(
            card=None,
            utility=0.2,
            skip_utility=0.9,
            actions=(("小牌", 0.2), ("大牌", 0.1)),
            nodes=5,
            elapsed_ms=0.5,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", fake, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax")
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "小牌"
    assert "SKIP" in action.reason and "硬打" in action.reason
    assert "不回退 rules" in policy.decision_note()


def test_expectimax_skip_without_alternative_blocks(monkeypatch, tmp_path: Path) -> None:
    """搜索说 SKIP 但又拿不出任何动作：宁可 blocked，也不许回退 rules。"""

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
    with pytest.raises(RuleFallbackBlocked, match="SKIP"):
        policy.decide(_state())


def test_hardplay_prefers_scoring_card_on_flat_tie(monkeypatch, tmp_path: Path) -> None:
    """F#42：动作全平手（反正到不了 CLEAR）时，硬打必须先打正分牌，不能打 buff。

    真机 ep-t3-4：最后一回合 0 分、还差 30 分，搜索把所有动作打成 0.00，
    旧排序挑中 buff 牌「表情的基础」→ 本课 0 分 FAILED。硬打必须保证得分。
    """

    def fake(state, *args, **kwargs):
        return ExpectimaxResult(
            card=None,
            utility=0.0,
            skip_utility=0.0,
            actions=(("表情的基础", 0.0), ("魅力的基础", 0.0), ("轻快步伐", 0.0)),
            nodes=3,
            elapsed_ms=0.2,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", fake, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax")
    state = _state(
        turns_left=1,
        score=0,
        gauge=30,
        cards=(
            _card(0, "魅力的基础", 29, 4),
            _card(1, "表情的基础", 1, 1, buff=True),
            _card(2, "轻快步伐", 23, 4),
        ),
    )
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "魅力的基础"
    assert "SKIP" in action.reason and "硬打" in action.reason


def test_expectimax_skip_allowed_when_no_card_affordable(
    monkeypatch, tmp_path: Path
) -> None:
    """只有所有牌都付不起（真没体力）才允许 SKIP。"""

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
    state = _state(
        stamina=1, cards=(_card(0, "大牌", 40, 5), _card(1, "小牌", 5, 2))
    )
    action = policy.decide(state)
    assert action.kind == "skip"
    assert "付不起" in action.reason


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


def test_decision_note_reports_missing_state(tmp_path: Path) -> None:
    """体力读不到 → 搜索用不了，返回 wait 等下一帧，且写明不回退 rules。"""
    policy = _policy(tmp_path, engine="expectimax")
    action = policy.decide(_state(stamina=None))
    assert action.kind == "wait"
    note = policy.decision_note()
    assert "等待重读" in note
    assert "不回退 rules" in note


def test_decision_note_rules_engine(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    policy.decide(_state())
    assert policy.decision_note() == "eng=rules"
