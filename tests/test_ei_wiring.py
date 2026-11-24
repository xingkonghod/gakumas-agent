"""B11 v6 学生网生产接线（engine=net）：硬规矩 / 禁回退 / 默认逐位不变。

接线口径（2026-11-23，见 docs/EXPECTIMAX.md「B11 v6 生产接线」）：

* ``LessonPolicy(engine="net", net_model=…)`` 在**可观测状态**的可出牌里 argmax
  优势分（无搜索、不用 known_draw/牌序，public-safe 口径）；
* 用户硬规矩：有可出牌绝不 SKIP；只有所有牌都付不起（真没体力）才允许 SKIP；
* 模型缺失/推理异常/结果失配 → ``RuleFallbackBlocked``（真机入口记
  ``[engine][BLOCKED]`` 中止本局），**绝不静默回退 rules**；状态没读全 → wait；
* 其它引擎不读 ``net_model``，默认行为逐位不变；
* ``auto_produce`` 入口：``--net-model`` > ``policy.json produce.net_model`` >
  默认入库 v6（``data/knowledge/ei_policy_v6.json``）；缺模型起跑前 return 2。

scripts/ 的接线用源码静态检查兜底（与 test_c1_wiring.py 同约定）。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from gkagent.policy.lesson import LessonPolicy, RuleFallbackBlocked
from gkagent.sim.expectimax import ExpectimaxResult
from gkagent.sim.leaf_mlp import DIM as LEAF_DIM
from gkagent.sim.lesson import CardSpec
from gkagent.sim.policy_mlp import (
    ACTION_FEATURE_NAMES,
    INPUT_DIM,
    PolicyMLP,
)
from gkagent.vision.lesson import LessonCard, LessonState

ROOT = Path(__file__).resolve().parents[1]
TRACKED_V6 = ROOT / "data" / "knowledge" / "ei_policy_v6.json"


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


def _score_net() -> PolicyMLP:
    """合成网：优势分 = max(候选牌面分, 0)（单调挑高分牌，确定性可断言）。"""
    column = LEAF_DIM + ACTION_FEATURE_NAMES.index("card_score")
    w1 = np.zeros((INPUT_DIM, 1))
    w1[column, 0] = 1.0
    return PolicyMLP(
        mean=np.zeros(INPUT_DIM),
        scale=np.ones(INPUT_DIM),
        w1=w1,
        b1=np.zeros(1),
        w2=np.ones((1, 1)),
        b2=np.zeros(1),
        out_w=np.ones((1, 1)),
        out_b=np.zeros(1),
        meta={"test": "score=card_score"},
    )


def _zero_net() -> PolicyMLP:
    """全零网：所有候选优势分 0（平手），用来验证「有牌绝不 SKIP」。"""
    return PolicyMLP(
        mean=np.zeros(INPUT_DIM),
        scale=np.ones(INPUT_DIM),
        w1=np.zeros((INPUT_DIM, 1)),
        b1=np.zeros(1),
        w2=np.zeros((1, 1)),
        b2=np.zeros(1),
        out_w=np.zeros((1, 1)),
        out_b=np.zeros(1),
        meta={"test": "zero"},
    )


def _saved(tmp_path: Path, model: PolicyMLP | None = None) -> str:
    path = tmp_path / "net.json"
    (model or _score_net()).save(path)
    return str(path)


class FakePlan:
    """激活的考试牌序计划：注入全知 deck/discard（net 必须无视它）。"""

    active = True

    def start(self) -> None:
        pass

    def begin_turn(self, names, parameter=None) -> None:
        pass

    def end_turn(self, names) -> None:
        pass

    def observe_hand(self, names) -> None:
        pass

    def expect_state_kwargs(self, to_specs=None) -> dict:
        spec = CardSpec(name="大牌", cost=5, score=40)
        return {
            "deck": (spec,),
            "known_draw": (spec,),
            "discard": (spec,),
            "discard_order": (spec,),
        }


# ------------------------------------------------------------------ 引擎开关
def test_net_engine_accepted_and_default_unchanged(tmp_path: Path) -> None:
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    assert policy.engine == "net"
    assert policy.forbids_rule_fallback is True
    # 默认引擎仍是 rules（LessonPolicy 口径），net_model 默认 None
    assert LessonPolicy(params_path=tmp_path / "missing.json").engine == "rules"
    assert LessonPolicy.DEFAULT_PARAMS["net_model"] is None
    with pytest.raises(ValueError, match="未知出牌引擎"):
        _policy(tmp_path, engine="magic")


def test_net_model_params_path_and_kwarg_priority(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    model_path = _saved(tmp_path)
    path.write_text(
        json.dumps({"version": 1, "lesson": {"engine": "net", "net_model": model_path}}),
        encoding="utf-8",
    )
    policy = LessonPolicy(params_path=path)
    assert policy.engine == "net"
    assert policy.params["net_model"] == model_path
    # 显式关键字优先级最高
    other = _saved(tmp_path, _zero_net())
    override = LessonPolicy(params_path=path, net_model=other)
    assert override.params["net_model"] == other


# ------------------------------------------------------------------ 决策口径
def test_net_picks_argmax_advantage_card(tmp_path: Path) -> None:
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.index == 0
    assert action.card is not None and action.card.name == "大牌"
    assert action.expected == pytest.approx(40.0)
    assert "net:" in action.reason and "优势" in action.reason and "ms" in action.reason
    assert policy.last_decision["engine"] == "net"
    assert policy.decision_note().startswith("eng=net")


def test_net_only_affordable_candidates(tmp_path: Path) -> None:
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    action = policy.decide(_state(stamina=4))  # 大牌 5 费付不起
    assert action.kind == "card"
    assert action.index == 1
    assert action.card is not None and action.card.name == "小牌"
    assert action.expected == pytest.approx(5.0)


def test_net_skip_only_when_all_unaffordable(tmp_path: Path) -> None:
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    action = policy.decide(_state(stamina=0))
    assert action.kind == "skip"
    assert "所有牌都付不起" in action.reason
    assert "真没体力" in policy.last_fallback_reason


def test_net_exam_mode_waits_when_no_affordable(tmp_path: Path) -> None:
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    action = policy.decide(_state(stamina=0), allow_skip=False)
    assert action.kind == "wait"


def test_net_never_skips_with_playable_cards(tmp_path: Path) -> None:
    """全零网（所有优势分平手 0）也绝不 SKIP——硬规矩：有可出牌就打。"""
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path, _zero_net()))
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.index in (0, 1)


def test_net_deterministic(tmp_path: Path) -> None:
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    state = _state()
    first = policy.decide(state)
    second = policy.decide(state)
    assert (first.kind, first.index, first.expected) == (
        second.kind,
        second.index,
        second.expected,
    )


def test_net_missing_state_waits(tmp_path: Path) -> None:
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    assert policy.decide(_state(stamina=None)).kind == "wait"
    assert policy.decide(_state(cards=())).kind == "wait"


# ------------------------------------------------------------------ 禁回退红线
def test_net_missing_model_blocks(tmp_path: Path) -> None:
    policy = _policy(tmp_path, engine="net")
    with pytest.raises(RuleFallbackBlocked, match="net_model"):
        policy.decide(_state())


def test_net_bad_model_blocks(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    policy = _policy(tmp_path, engine="net", net_model=str(missing))
    with pytest.raises(RuleFallbackBlocked):
        policy.decide(_state())
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    policy = _policy(tmp_path, engine="net", net_model=str(bad))
    with pytest.raises(RuleFallbackBlocked):
        policy.decide(_state())
    wrong_format = tmp_path / "wrong.json"
    wrong_format.write_text(json.dumps({"format": "nope"}), encoding="utf-8")
    policy = _policy(tmp_path, engine="net", net_model=str(wrong_format))
    with pytest.raises(RuleFallbackBlocked):
        policy.decide(_state())


def test_net_inference_exception_blocks(monkeypatch, tmp_path: Path) -> None:
    def boom(self, state, cards):
        raise RuntimeError("net exploded")

    monkeypatch.setattr(PolicyMLP, "score", boom)
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    with pytest.raises(RuleFallbackBlocked, match="net exploded"):
        policy.decide(_state())


def test_net_cardspec_mismatch_blocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        LessonPolicy, "_search_action", staticmethod(lambda *a, **k: None)
    )
    policy = _policy(tmp_path, engine="net", net_model=_saved(tmp_path))
    with pytest.raises(RuleFallbackBlocked, match="CardSpec 失配"):
        policy.decide(_state())


def test_net_allow_rule_fallback_debug_switch(tmp_path: Path) -> None:
    """仅调试/旧评测显式打开才允许旧回退（真机入口永远不传 True）。"""
    policy = _policy(tmp_path, engine="net", allow_rule_fallback=True)
    action = policy.decide(_state())
    assert action.kind == "card"  # rules 在体力 10 时正常出牌
    assert "allow_rule_fallback" in policy.last_fallback_reason


# ------------------------------------------------------------------ 默认不变
def test_net_model_ignored_by_rules_engine(tmp_path: Path) -> None:
    state = _state()
    without = _policy(tmp_path, engine="rules").decide(state)
    with_model = _policy(tmp_path, engine="rules", net_model=_saved(tmp_path)).decide(state)
    assert (without.kind, without.index, without.expected) == (
        with_model.kind,
        with_model.index,
        with_model.expected,
    )


def test_net_model_ignored_by_expectimax(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake(state, *args, **kwargs):
        captured["state"] = state
        return ExpectimaxResult(
            card=state.hand[0],
            utility=0.5,
            skip_utility=0.1,
            actions=(("大牌", 0.5),),
            nodes=3,
            elapsed_ms=1.0,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", fake, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax", net_model=_saved(tmp_path))
    action = policy.decide(_state())
    assert captured, "expectimax 路径不受 net_model 影响"
    assert action.kind == "card" and action.index == 0


def test_net_ignores_draw_plan(monkeypatch, tmp_path: Path) -> None:
    """net 只看可观测状态：激活的 draw_plan 也不注入 deck/known_draw/discard。"""
    captured = {}

    def fake_score(self, state, cards):
        captured["state"] = state
        return np.zeros(len(cards))

    monkeypatch.setattr(PolicyMLP, "score", fake_score)
    policy = _policy(
        tmp_path, engine="net", net_model=_saved(tmp_path), draw_plan=FakePlan()
    )
    action = policy.decide(_state())
    assert action.kind == "card"
    state = captured["state"]
    assert state.deck == ()
    assert state.known_draw == ()
    assert state.discard == ()
    assert not state.discard_order  # 默认 None（未注入）


def test_expectimax_still_uses_draw_plan(monkeypatch, tmp_path: Path) -> None:
    """with_plan 重构回归：expectimax 的全知注入逐位不变。"""
    captured = {}

    def fake(state, *args, **kwargs):
        captured["state"] = state
        return ExpectimaxResult(
            card=state.hand[0],
            utility=0.5,
            skip_utility=0.1,
            actions=(("大牌", 0.5),),
            nodes=3,
            elapsed_ms=1.0,
            complete=True,
        )

    monkeypatch.setattr(
        "gkagent.sim.expectimax.expectimax_with_stats", fake, raising=True
    )
    policy = _policy(tmp_path, engine="expectimax", draw_plan=FakePlan())
    policy.decide(_state())
    state = captured["state"]
    assert len(state.deck) == 1
    assert len(state.known_draw) == 1
    assert len(state.discard) == 1


# ------------------------------------------------------------------ 入库模型
def test_tracked_v6_model_loads() -> None:
    model = PolicyMLP.load(TRACKED_V6)
    assert model.w1.shape == (INPUT_DIM, 192)
    assert model.w2.shape == (192, 96)
    # 2026-11-24 r13 完整渐退迭代入库（教师←r11，占比渐退 0.15→0.075，复合门基线=r11）：
    # 入库位 ei_policy_v6.json 现为 r13 权重（large500 r13−r11 +2.882 CI[+1.309,+4.455] 主门 PASS /
    # small500 r13−r11 −0.028 不回退 / vs v1 +0.558 保持），替换 r11。
    assert model.meta.get("task") == "B11 expert-iteration round13"
    assert "PASS" in model.meta["production"]["gate"]
    assert model.meta["production"]["revision"].startswith("r13")


def test_tracked_v6_decides_on_synthetic_state(tmp_path: Path) -> None:
    """入库 v6 真模型走一遍生产链路：出牌/不 SKIP/可观测性（不断言具体哪张）。"""
    policy = _policy(tmp_path, engine="net", net_model=str(TRACKED_V6))
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.index in (0, 1)
    assert policy.last_decision["engine"] == "net"


# ------------------------------------------------------------------ 入口静态接线
def _auto_produce_source() -> str:
    return (ROOT / "scripts" / "auto_produce.py").read_text(encoding="utf-8")


def test_auto_produce_net_engine_wired() -> None:
    source = _auto_produce_source()
    assert 'allowed_engines = ("rules", "expectimax", "beam", "uinet", "net")' in source
    assert 'arg_value("--net-model")' in source
    assert '.get("net_model")' in source
    assert '"ei_policy_v6.json"' in source
    assert "net model missing" in source
    assert 'net_model=net_model_path if lesson_engine == "net" else None' in source
    assert "[engine] net 模型 =" in source
    # 缺模型检查在起跑循环之前（return 2，不带空模型进局）
    assert source.index("net model missing") < source.index("for step in range(1, steps + 1)")
