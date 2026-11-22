"""UINet 接入：UIObs v1 转换、合法动作、引擎切换与真实模型推理。"""

from __future__ import annotations

import json
import statistics
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest

from gkagent.data.card_table import CardTable
from gkagent.policy.lesson import LessonPolicy, RuleFallbackBlocked
from gkagent.sim import uinet
from gkagent.sim.uiobs import (
    DEFAULT_MAX_STAMINA,
    PLAN_CODES,
    legal_actions,
    resolve_card,
    to_uiobs,
)
from gkagent.vision.lesson import LessonCard, LessonState


class FakeTable:
    """只实现 CardTable 里被策略/转换器用到的两个方法。"""

    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = rows

    def get(self, name: str) -> dict | None:
        return self.rows.get(name) or self.rows.get((name or "").rstrip("+＋"))

    def cost(self, name: str) -> int | None:
        row = self.get(name)
        return int(row["cost"]) if row and row.get("cost") is not None else None


TABLE = FakeTable(
    {
        "大牌": {"id": "p_card-99-act-1_001", "upgrade": 0, "cost": 5},
        "小牌": {"id": "p_card-99-act-1_002", "upgrade": 1, "cost": 1},
        "中牌": {"id": "p_card-99-men-1_003", "upgrade": 0, "cost": 3},
    }
)

#: 真实模型测试用：不读 data/knowledge/policy.json，只用默认参数。
DEFAULT_MISSING_POLICY = Path(__file__).resolve().parent / "_no_such_policy.json"


def _card(index: int, name: str, score: int, cost: int | None) -> LessonCard:
    return LessonCard(
        index=index,
        box=(0, 0, 1, 1),
        point=(100 + index * 30, 900),
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
        "cards": (
            _card(0, "大牌", 40, 5),
            _card(1, "小牌", 5, 1),
            _card(2, "中牌", 20, 3),
        ),
    }
    base.update(kwargs)
    return LessonState(**base)


def _policy(tmp_path: Path, **kwargs) -> LessonPolicy:
    policy = LessonPolicy(params_path=tmp_path / "missing.json", **kwargs)
    policy._table = TABLE
    return policy


def _real_ready() -> bool:
    """真实模型测试要求模型 + 主数据表 + 已生成的 pickle 缓存（否则首次解析 50s）。"""
    return uinet.available() and (uinet.master_dir() / "master.pkl").is_file()


def _real_state() -> tuple[LessonState, CardTable]:
    table = CardTable()
    picked = [
        (name, row)
        for name, row in table._cards.items()
        if row.get("id")
        and row.get("upgrade") == 0
        and 0 < int(row.get("cost") or 99) <= 6
    ][:3]
    assert len(picked) == 3
    cards = tuple(
        _card(index, name, 20 + index * 10, int(row["cost"]))
        for index, (name, row) in enumerate(picked)
    )
    return _state(cards=cards, stamina=20, score=123), table


# ---------------------------------------------------------------- UIObs 转换
def test_hand_maps_card_id_and_upgrade() -> None:
    obs = to_uiobs(_state(), table=TABLE)
    assert obs["v"] == "uiobs.v1"
    assert obs["hand"] == [
        {"id": "p_card-99-act-1_001", "u": 0, "p": 1},
        {"id": "p_card-99-act-1_002", "u": 1, "p": 1},
        {"id": "p_card-99-men-1_003", "u": 0, "p": 1},
    ]


def test_unplayable_card_is_p0_and_not_in_legal() -> None:
    obs = to_uiobs(_state(stamina=3), table=TABLE)
    assert [card["p"] for card in obs["hand"]] == [0, 1, 1]
    assert ["play", 0] not in obs["legal"]
    assert ["play", 1] in obs["legal"]
    assert ["end"] in obs["legal"]


def test_allow_skip_false_has_no_end_action() -> None:
    obs = to_uiobs(_state(), table=TABLE, allow_skip=False)
    assert ["end"] not in obs["legal"]
    assert {"play"} == {action[0] for action in obs["legal"]}


def test_num_fields_map_score_stamina_plays() -> None:
    obs = to_uiobs(_state(score=321, stamina=7), table=TABLE, plays=2)
    assert obs["num"] == {
        "score": 321,
        "stamina": 7,
        "max_stamina": DEFAULT_MAX_STAMINA,
        "block": 0,
        # 真机每回合基础 1 张（B3）：本回合已出 2 张 → 可出次数 0
        "playable": 0,
        "plays": 2,
    }
    # 体力读到了上限、比默认值大时，上限不能小于当前体力
    assert to_uiobs(_state(stamina=60), table=TABLE)["num"]["max_stamina"] == 60
    assert to_uiobs(_state(stamina=7), table=TABLE, playable=0)["num"]["playable"] == 0


def test_exam_fields_turn_limit_plan_types() -> None:
    obs = to_uiobs(_state(), table=TABLE, plan="sense")
    exam = obs["exam"]
    assert exam["turn"] == 4  # total 6 - turns_left 3 + 1
    assert exam["limit"] == 6
    assert exam["plan"] == PLAN_CODES["sense"]
    assert len(exam["types"]) == 6 and set(exam["types"]) == {1}
    assert exam["permil"] == [1000, 1000, 1000]
    assert exam["crit"] == [0, 0, 0]
    assert exam["produce"] == "produce-007" and exam["step"] == "AUDITION_MID1"
    assert to_uiobs(_state(), table=TABLE, plan="logic")["exam"]["plan"] == 3
    assert to_uiobs(_state(), table=TABLE, plan="anomaly")["exam"]["plan"] == 4


def test_audition_uses_its_own_defaults() -> None:
    state = _state(kind="audition", turns_left=2, total_turns=None, attribute="舞蹈")
    exam = to_uiobs(state, table=TABLE)["exam"]
    assert exam["limit"] == 2 and exam["turn"] == 1
    assert exam["types"] == [2, 2]
    assert exam["produce"] == "produce-008" and exam["step"] == "AUDITION_FINAL"


def test_missing_fields_do_not_raise() -> None:
    obs = to_uiobs(LessonState())
    assert obs["hand"] == [] and obs["legal"] == [["end"]]
    assert obs["num"]["stamina"] == 0
    assert obs["num"]["max_stamina"] == DEFAULT_MAX_STAMINA
    assert obs["exam"]["limit"] == 1
    # 卡名/费用全读不到：保留序号，乐观标 p=1，不抛异常
    state = _state(
        stamina=None,
        cards=(_card(0, "", None, None), _card(1, "？", None, None)),
    )
    obs = to_uiobs(state, table=FakeTable({}))
    assert len(obs["hand"]) == 2
    assert [card["id"] for card in obs["hand"]] == ["", ""]
    assert obs["legal"] == [["play", 0], ["play", 1], ["end"]]


def test_resolve_card_falls_back_to_upgrade_suffix() -> None:
    card_id, upgrade = resolve_card("小牌++", table=FakeTable({}))
    assert card_id == "" and upgrade == 2


# ---------------------------------------------------------------- 引擎切换
def test_policy_json_accepts_uinet_engine(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"lesson": {"engine": "uinet"}}), encoding="utf-8")
    assert LessonPolicy(params_path=path).engine == "uinet"


def test_uinet_missing_model_blocks_rule_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    """用户规则：UINet 模型缺失时抛 blocked，绝不回退 rules。"""
    monkeypatch.setenv("GKMS_UINET_MODEL", str(tmp_path / "missing.onnx"))
    policy = _policy(tmp_path, engine="uinet")
    with pytest.raises(RuleFallbackBlocked, match="uinet"):
        policy.decide(_state())
    assert policy.forbids_rule_fallback


def test_uinet_missing_master_blocks_rule_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GKMS_UINET_MASTER", str(tmp_path / "no-master"))
    policy = _policy(tmp_path, engine="uinet")
    with pytest.raises(RuleFallbackBlocked, match="uinet"):
        policy.decide(_state())


def test_uinet_exception_blocks_rule_fallback(monkeypatch, tmp_path: Path) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("onnx exploded")

    monkeypatch.setattr(uinet, "predict", boom)
    policy = _policy(tmp_path, engine="uinet")
    with pytest.raises(RuleFallbackBlocked, match="onnx exploded"):
        policy.decide(_state())


def test_uinet_play_action_maps_back_to_lesson_card(
    monkeypatch, tmp_path: Path
) -> None:
    def fake(obs, **kwargs):
        return uinet.UinetOutput(
            action=("play", 1),
            probs=(0.1, 0.9, 0.0, 0.0),
            score_quantiles={},
            elapsed_ms=1.5,
        )

    monkeypatch.setattr(uinet, "predict", fake)
    action = _policy(tmp_path, engine="uinet").decide(_state())
    assert action.kind == "card"
    assert action.index == 1
    assert action.card is not None and action.card.name == "小牌"
    assert action.point == (130, 900)
    assert "uinet" in action.reason


def test_uinet_end_action_intercepted_to_card(monkeypatch, tmp_path: Path) -> None:
    def fake(obs, **kwargs):
        return uinet.UinetOutput(
            action=("end",), probs=(1.0,), score_quantiles={}, elapsed_ms=1.0
        )

    monkeypatch.setattr(uinet, "predict", fake)
    policy = _policy(tmp_path, engine="uinet")
    # 2026-11-21 用户规则：UINet 说 end 也不算数——还有付得起的牌就按它的概率硬打
    action = policy.decide(_state())
    assert action.kind == "card"
    assert "不回退 rules" in policy.decision_note()
    # 考试模式不允许 SKIP：同样只能出牌/等待
    exam_action = policy.decide(_state(), allow_skip=False)
    assert exam_action.kind in {"card", "wait"}


def test_uinet_no_affordable_cards_skips_only_when_allowed(
    tmp_path: Path,
) -> None:
    """只有所有牌都付不起（真没体力）才 SKIP；考试返回 wait。"""
    state = _state(stamina=0)
    policy = _policy(tmp_path, engine="uinet")
    action = policy.decide(state)
    assert action.kind == "skip"
    exam_action = policy.decide(state, allow_skip=False)
    assert exam_action.kind == "wait"


def test_uinet_drink_action_forces_probability_pick(
    monkeypatch, tmp_path: Path
) -> None:
    """UINet 建议喝饮料（真机没有对应动作）：按其概率硬打一张，不回退 rules。"""

    def fake(obs, **kwargs):
        return uinet.UinetOutput(
            action=("drink", 0), probs=(0.9, 0.1, 0.0, 0.0), score_quantiles={}, elapsed_ms=1.0
        )

    monkeypatch.setattr(uinet, "predict", fake)
    policy = _policy(tmp_path, engine="uinet")
    action = policy.decide(_state())
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "大牌"
    assert "不回退 rules" in policy.decision_note()


# ---------------------------------------------------------------- 真实 ONNX
@pytest.mark.skipif(not _real_ready(), reason="UINet 模型/主数据/pickle 未就绪")
def test_real_model_top_action_is_legal_and_fast() -> None:
    state, table = _real_state()
    policy = _policy_for_real(table)
    obs = to_uiobs(state, table=table, plan="sense")
    out = uinet.predict(obs)
    assert list(out.action) in obs["legal"]
    assert len(out.probs) == len(obs["legal"])
    assert 0.0 <= max(out.probs) <= 1.0
    policy.decide(state)  # 预热 ONNX 会话
    samples = []
    decisions = []
    for _ in range(5):
        started = time.perf_counter()
        decisions.append(policy.decide(state))
        samples.append((time.perf_counter() - started) * 1000.0)
    for decision in decisions:
        assert decision.kind in {"card", "skip", "wait"}
        if decision.kind == "card":
            assert decision.index is not None and 0 <= decision.index < len(state.cards)
    assert statistics.median(samples) < 100.0


@pytest.mark.skipif(not _real_ready(), reason="UINet 模型/主数据/pickle 未就绪")
def test_real_model_is_deterministic() -> None:
    state, table = _real_state()
    obs = to_uiobs(state, table=table, plan="sense")
    first = uinet.predict(obs)
    second = uinet.predict(obs)
    assert first.action == second.action
    assert first.probs == pytest.approx(second.probs, abs=1e-9)


def _policy_for_real(table: CardTable) -> LessonPolicy:
    policy = LessonPolicy(
        params_path=DEFAULT_MISSING_POLICY,
        engine="uinet",
    )
    policy._table = table
    return policy


# ---------------------------------------------------------------- 2026-11-19 审查补测
def test_legal_actions_indices_align_with_hand_positions() -> None:
    """legal 的下标必须与 hand 列表位置一致，p=0 的牌不能混进去。"""
    hand = [
        {"id": "a", "u": 0, "p": 1},
        {"id": "b", "u": 0, "p": 0},
        {"id": "c", "u": 0, "p": 1},
    ]
    assert legal_actions(hand, allow_skip=False) == [["play", 0], ["play", 2]]
    assert legal_actions(hand, allow_skip=True) == [
        ["play", 0],
        ["play", 2],
        ["end"],
    ]


def test_uiobs_missing_fields_are_encodable_by_uinet() -> None:
    """缺字段的观测（空 LessonState / 普通读数）喂给 UINet 编码器不能抛/出 NaN。"""
    pytest.importorskip("gkms_uinet.encode")
    from gkms_uinet.encode import encode
    from gkms_uinet.feat import Featurizer

    class FakeMaster:
        """只有空表的 Master；让卡表查不到时走 UINet 的 unknown-card 分支。"""

        def __init__(self) -> None:
            self.cards: dict = {}
            self.customizes: dict = {}
            self.grow_effects: dict = {}
            self.searches: dict = {}
            self.effects: dict = {}
            self.triggers: dict = {}
            self.enchants: dict = {}
            self.drinks: dict = {}
            self.drink_effects: dict = {}

    featurizer = Featurizer(FakeMaster())
    for state in (LessonState(), _state()):
        obs = to_uiobs(state, table=TABLE)
        arrays = encode(obs, featurizer)
        for name, array in arrays.items():
            assert np.isfinite(array).all(), name
        for action in obs["legal"]:
            if action[0] == "play":
                assert 0 <= action[1] < len(obs["hand"])


def test_uinet_policy_session_is_reused_until_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ONNX Policy（含会话）必须按模型/主数据/线程数缓存，不能每次 decide 重建。"""
    model = tmp_path / "fake.onnx"
    model.write_bytes(b"onnx")
    master = tmp_path / "master"
    master.mkdir()
    created: list[str] = []

    class FakePolicy:
        def __init__(self, model, master, threads=1):
            created.append("init")

        def decide(self, obs):
            created.append("decide")
            return {
                "action": ["end"],
                "probs": [1.0],
                "score_quantiles": {"50%": 12},
            }

    fake_module = types.ModuleType("gkms_uinet")
    fake_module.Policy = FakePolicy
    monkeypatch.setitem(sys.modules, "gkms_uinet", fake_module)
    monkeypatch.setattr(uinet, "_load_master", lambda directory: object())
    uinet.reset_cache()
    try:
        first = uinet.predict({}, model=model, master=master, threads=1)
        second = uinet.predict({}, model=model, master=master, threads=1)
        assert created.count("init") == 1
        assert created.count("decide") == 2
        assert first.action == second.action == ("end",)
        assert second.score_quantiles == {"50%": 12}

        uinet.reset_cache()
        uinet.predict({}, model=model, master=master, threads=1)
        assert created.count("init") == 2
    finally:
        uinet.reset_cache()
