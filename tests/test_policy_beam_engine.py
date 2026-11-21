"""``lesson.engine = "beam"`` 与「考试牌序计划 → 搜索」接线的策略层测试。

两层：

* beam：``policy.json`` 能开关（``lesson.engine=beam`` + 宽度/预算参数），搜索走
  ``search_beam``；没有 known_draw（没采到牌序）时改用回合内 expectimax；
  搜索异常抛 ``RuleFallbackBlocked``（用户规则：**不许回退 rules**）；
* draw_plan：策略把当前手牌喂给 ``ExamDrawPlan``（begin_turn/observe_hand/end_turn），
  并把计划给的 known_draw / discard_order / 重洗钩子注进 ExpectState。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.policy.lesson import LessonPolicy, RuleFallbackBlocked
from gkagent.sim.expectimax import BeamResult, ExpectimaxResult
from gkagent.vision.lesson import LessonCard, LessonState

SMALL_ID = "p_card-00-act-0_001"
BIG_ID = "p_card-00-act-0_002"


class FakeTable:
    """最小卡表：get(卡名) / name_of(id, upgrade) 都够用。"""

    def __init__(self) -> None:
        self.rows = {
            "大牌": {
                "id": BIG_ID,
                "upgrade": 0,
                "cost": 5,
                "effects": [{"type": "ExamLesson", "values": [40]}],
            },
            "小牌": {
                "id": SMALL_ID,
                "upgrade": 0,
                "cost": 1,
                "effects": [{"type": "ExamLesson", "values": [5]}],
            },
        }
        self.by_id = {
            (row["id"], row["upgrade"]): name for name, row in self.rows.items()
        }

    def get(self, name: str) -> dict | None:
        return self.rows.get(name) or self.rows.get((name or "").rstrip("+＋"))

    def name_of(self, card_id: str, upgrade: int = 0) -> str | None:
        return self.by_id.get((card_id, int(upgrade)))


class FakePlan:
    """``ExamDrawPlan`` 的最小替身：记录调用 + 按需给全知牌序。"""

    def __init__(self, known=(), *, active: bool = True, fail: bool = False) -> None:
        self.known = tuple(known)
        self.active = active
        self.fail = fail
        self.calls: dict[str, list] = {
            "begin_turn": [],
            "observe_hand": [],
            "note_play": [],
            "end_turn": [],
        }

    def begin_turn(self, names, parameter_type=None) -> bool:
        self.calls["begin_turn"].append((tuple(names), parameter_type))
        return self.active

    def observe_hand(self, names) -> bool:
        self.calls["observe_hand"].append(tuple(names))
        return True

    def note_play(self, name) -> None:
        self.calls["note_play"].append(name)

    def end_turn(self, leftover=()) -> None:
        self.calls["end_turn"].append(tuple(leftover))

    def expect_state_kwargs(self, to_specs=None):
        if self.fail:
            raise RuntimeError("plan exploded")
        if not self.active or to_specs is None:
            return {}
        known = tuple(to_specs(self.known))
        return {
            "deck": known,
            "known_draw": known,
            "discard": (),
            "discard_order": (),
        }

    def reshuffle_hook(self):
        return None


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
        "kind": "audition",
        "turns_left": 3,
        "total_turns": 6,
        "score": 50,
        "gauge": 100,
        "stamina": 10,
        "attribute": "歌唱",
        "cards": (_card(0, "大牌", 40, 5), _card(1, "小牌", 5, 1)),
    }
    base.update(kwargs)
    return LessonState(**base)


def _policy(tmp_path: Path, **kwargs) -> LessonPolicy:
    params = kwargs.pop("params", None)
    policy = LessonPolicy(params_path=tmp_path / "missing.json", params=params, **kwargs)
    policy._table = FakeTable()
    return policy


# ---------------------------------------------------------------- beam 引擎开关


def test_policy_json_can_switch_to_beam(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "lesson": {
                    "engine": "beam",
                    "beam_width": 8,
                    "beam_deadline_ms": 120,
                },
            }
        ),
        encoding="utf-8",
    )
    policy = LessonPolicy(params_path=path)
    assert policy.engine == "beam"
    assert policy.params["beam_width"] == 8
    assert policy.params["beam_deadline_ms"] == pytest.approx(120.0)


def test_beam_engine_uses_known_draw_and_labels_reason(tmp_path: Path) -> None:
    plan = FakePlan([(SMALL_ID, 0), (BIG_ID, 0), (SMALL_ID, 0)])
    policy = _policy(
        tmp_path,
        engine="beam",
        draw_plan=plan,
        params={"beam_deadline_ms": 60.0, "beam_width": 2},
    )
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.card is not None
    assert action.reason.startswith("beam:")
    # 计划在第一个回合被调用过（begin_turn 拿到当前手牌）
    assert plan.calls["begin_turn"]


def test_beam_without_known_draw_falls_back_to_expectimax(
    monkeypatch, tmp_path: Path
) -> None:
    captured = {}

    def fake_expectimax(state, *args, **kwargs):
        captured["state"] = state
        return ExpectimaxResult(
            card=state.hand[0],
            utility=0.5,
            skip_utility=0.4,
            actions=(),
            nodes=3,
            elapsed_ms=1.0,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats",
        fake_expectimax,
        raising=True,
    )
    plan = FakePlan([], active=True)  # 计划在，但没有牌序数据
    policy = _policy(tmp_path, engine="beam", draw_plan=plan)
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.reason.startswith("expectimax:")


def test_beam_exception_falls_back_to_rules(monkeypatch, tmp_path: Path) -> None:
    """beam 搜索异常不再回退 rules：抛 RuleFallbackBlocked（真机入口中止本局）。"""

    def boom(*args, **kwargs):
        raise RuntimeError("beam exploded")

    monkeypatch.setattr("gkagent.sim.expectimax.search_beam", boom, raising=True)
    plan = FakePlan([(SMALL_ID, 0)])
    policy = _policy(tmp_path, engine="beam", draw_plan=plan)
    with pytest.raises(RuleFallbackBlocked, match="beam exploded"):
        policy.decide(_state())


def test_beam_skip_intercepted_when_cards_affordable(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_beam(state, *args, **kwargs):
        return BeamResult(
            card=None,
            utility=0.0,
            skip_utility=0.0,
            sequence=(),
            end_state=None,
            width=2,
            depth_reached=1,
            layer_scores=(),
            elapsed_ms=1.0,
            complete=True,
        )

    def fake_expectimax(state, *args, **kwargs):
        return ExpectimaxResult(
            card=state.hand[0],
            utility=0.3,
            skip_utility=0.0,
            actions=(("大牌", 0.3),),
            nodes=2,
            elapsed_ms=0.5,
            complete=True,
        )

    monkeypatch.setattr("gkagent.sim.expectimax.search_beam", fake_beam, raising=True)
    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats",
        fake_expectimax,
        raising=True,
    )
    plan = FakePlan([(SMALL_ID, 0)])
    policy = _policy(tmp_path, engine="beam", draw_plan=plan)
    # 2026-11-21 用户规则：beam 建议 SKIP 不算数，有牌就按搜索硬打（不回退 rules）
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.reason.startswith("expectimax:")
    assert "不回退 rules" in policy.decision_note()
    exam_action = policy.decide(_state(), allow_skip=False)
    assert exam_action.kind in {"card", "wait"}


def test_beam_skip_uses_beam_plan_first_card(monkeypatch, tmp_path: Path) -> None:
    """beam 建议 SKIP 但根回合计划里有首牌：按 beam 自己的计划硬打，不用 rules。"""

    def fake_beam(state, *args, **kwargs):
        return BeamResult(
            card=None,
            utility=0.4,
            skip_utility=0.9,
            sequence=("大牌",),
            end_state=None,
            width=2,
            depth_reached=1,
            layer_scores=(),
            elapsed_ms=1.0,
            complete=True,
        )

    monkeypatch.setattr("gkagent.sim.expectimax.search_beam", fake_beam, raising=True)
    plan = FakePlan([(SMALL_ID, 0)])
    policy = _policy(tmp_path, engine="beam", draw_plan=plan)
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "大牌"
    assert "beam 根回合计划" in action.reason
    assert "不回退 rules" in policy.decision_note()


# ---------------------------------------------------------------- draw_plan 接线


def test_expectimax_engine_gets_known_draw_from_plan(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_expectimax(state, *args, **kwargs):
        captured["state"] = state
        captured["kw"] = kwargs
        return ExpectimaxResult(
            card=state.hand[0],
            utility=0.5,
            skip_utility=0.4,
            actions=(),
            nodes=1,
            elapsed_ms=1.0,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats",
        fake_expectimax,
        raising=True,
    )
    plan = FakePlan([(SMALL_ID, 0), (BIG_ID, 0)])
    policy = _policy(tmp_path, engine="expectimax", draw_plan=plan)
    action = policy.decide(_state())
    assert action.kind == "card"
    state = captured["state"]
    assert len(state.known_draw) == 2
    assert state.known_draw == state.deck
    assert state.discard_order == ()
    assert plan.calls["begin_turn"]
    # FakePlan 没给重洗钩子 → 搜索拿到 None（回退到多重集期望的重洗）
    assert captured["kw"].get("reshuffle") is None


def test_plan_begin_turn_and_end_turn_are_driven_by_turns_left(tmp_path: Path) -> None:
    plan = FakePlan([(SMALL_ID, 0)])
    policy = _policy(tmp_path, engine="rules", draw_plan=plan)
    # 第 2 回合（剩余 2）
    state2 = _state(turns_left=2)
    policy.decide(state2)
    assert plan.calls["begin_turn"][-1] == (
        ("大牌", "小牌"),
        1,  # attribute 歌唱 → ProduceParameterType 1
    )
    policy.note_play(state2.cards[1])  # 打出小牌
    # 第 3 回合（剩余 1）：先把上一回合剩余手牌（大牌）并进弃牌堆
    policy.decide(_state(turns_left=1, cards=(_card(0, "小牌", 5, 1),)))
    assert plan.calls["end_turn"][-1] == ("大牌",)
    assert plan.calls["note_play"] == ["小牌"]
    assert len(plan.calls["begin_turn"]) == 2
