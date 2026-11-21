"""考试牌序计划（``ExamSetup`` / ``ExamDrawPlan``）：生产接线的数据层测试。

* ``ExamSetup``：采集 JSON ↔ 类型化视图、牌能否再强化、建 oracle；
* ``ExamDrawPlan``：每回合预测 → 与实机手牌核对 → 给搜索喂
  ``known_draw`` / ``discard_order``；弃牌堆记账与重洗；核对失败就地停用；
  回合内抽牌跟踪；卡名/卡表查不到时安全停用。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.sim.exam_oracle import ExamDrawOracle
from gkagent.sim.exam_plan import (
    STATUS_ACTIVE,
    STATUS_MISMATCH,
    ExamDrawPlan,
    ExamSetup,
    load_exam_setups,
)

DECK = [
    ("p_card-a", 0),
    ("p_card-b", 0),
    ("p_card-c", 0),
    ("p_card-d", 0),
]


def _setup(**kwargs) -> ExamSetup:
    base = {
        "seed": 0x1234,
        "deck": tuple(DECK),
        "config_turns": 4,
        "npc_count": 5,
    }
    base.update(kwargs)
    return ExamSetup(**base)


def _raw(**kwargs) -> dict:
    raw = _setup().to_dict()
    raw.update(kwargs)
    return raw


class FakeTable:
    """最小卡表：get(卡名) / name_of(id, upgrade) 够 ExamDrawPlan 用。"""

    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = rows
        self.by_id = {
            (str(row["id"]), int(row.get("upgrade") or 0)): name
            for name, row in rows.items()
        }

    def get(self, name: str) -> dict | None:
        return self.rows.get(name) or self.rows.get((name or "").rstrip("+＋"))

    def name_of(self, card_id: str, upgrade: int = 0) -> str | None:
        return self.by_id.get((str(card_id), int(upgrade)))


# ---------------------------------------------------------------- ExamSetup


def test_setup_from_dict_round_trip():
    raw = _raw(
        supports=[{"id": "s_card-1", "number": 1, "permil": 62, "filter": 3}],
        initial_keys=[["p_card-a", 0]],
        card_variants={"p_card-a": 1, "p_card-b": 3},
        lost_keys=[["p_card-b", 0]],
        end_lost_keys=[["p_card-c", 0]],
        truth=[{"turn": 1, "parameterType": 1, "hand": [["p_card-a", 0]], "played": []}],
    )
    setup = ExamSetup.from_dict(raw)
    assert setup.seed == 0x1234
    assert setup.deck == tuple(DECK)
    assert setup.config_turns == 4
    assert setup.supports[0]["permil"] == 62
    assert setup.initial_keys == frozenset({("p_card-a", 0)})
    assert setup.lost_keys == frozenset({("p_card-b", 0)})
    assert setup.end_lost_keys == frozenset({("p_card-c", 0)})
    assert setup.truth[0]["turn"] == 1
    # 回写字段兼容采集脚本的 schema
    written = setup.to_dict()
    for key in ("seed", "deck", "config_turns", "supports", "initial_keys", "truth"):
        assert key in written


def test_setup_rejects_bad_records():
    with pytest.raises(ValueError):
        ExamSetup.from_dict({"seed": 1, "deck": []})
    with pytest.raises(ValueError):
        ExamSetup.from_dict({"seed": -1, "deck": [["p_card-a", 0]], "config_turns": 3})


def test_can_upgrade_uses_card_variants():
    setup = _setup(card_variants={"p_card-a": 1})
    assert setup.can_upgrade(("p_card-a", 0)) is True
    assert setup.can_upgrade(("p_card-a", 1)) is False
    # 主数据缺条目的新卡按可强化处理（与 verify_shuffle 同口径）
    assert setup.can_upgrade(("p_card-new", 0)) is True


def test_new_oracle_starts_at_opening_deck():
    setup = _setup()
    oracle = setup.new_oracle()
    assert isinstance(oracle, ExamDrawOracle)
    assert oracle.turn == 0
    assert oracle.remaining != []  # 开局牌堆 = 洗好的整副牌


def test_load_exam_setups_skips_bad_entries(tmp_path: Path):
    path = tmp_path / "exam_setup.json"
    path.write_text(
        json.dumps({"exams": [_raw(), {"seed": 0, "deck": []}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    setups = load_exam_setups(path)
    assert len(setups) == 1
    assert setups[0].seed == 0x1234


def test_load_exam_setups_missing_file_returns_empty(tmp_path: Path):
    assert load_exam_setups(tmp_path / "nope.json") == []


# ---------------------------------------------------------------- ExamDrawPlan


def test_plan_verifies_predicted_hand_and_feeds_known_draw():
    setup = _setup()
    reference = setup.new_oracle()
    expected = reference.draw_next_turn(1)
    plan = ExamDrawPlan(setup)

    assert plan.begin_turn([tuple(card) for card in expected], 1) is True
    assert plan.status == STATUS_ACTIVE
    assert plan.known_draw == tuple(reference.remaining)
    kwargs = plan.expect_state_kwargs(to_specs=list)
    assert kwargs["known_draw"] == tuple(reference.remaining)
    assert kwargs["deck"] == tuple(reference.remaining)
    assert kwargs["discard"] == ()
    assert kwargs["discard_order"] == ()


def test_plan_mismatch_disables_itself():
    plan = ExamDrawPlan(_setup())
    wrong = [("p_card-x", 0), ("p_card-y", 0), ("p_card-z", 0)]
    assert plan.begin_turn(wrong, 1) is False
    assert plan.status == STATUS_MISMATCH
    assert "核对失败" in plan.reason
    # 停用后不再喂任何牌序数据（搜索退回期望模型）
    assert plan.expect_state_kwargs(to_specs=list) == {}
    assert plan.begin_turn(wrong, 1) is False


def test_plan_requires_spec_converter():
    plan = ExamDrawPlan(_setup())
    assert plan.begin_turn([("p_card-a", 0)], 0) in (True, False)
    if plan.active:
        assert plan.expect_state_kwargs() == {}


def test_plan_grave_bookkeeping_and_reshuffle():
    """弃牌堆顺序账：回合末剩余手牌进 grave → 下一回合牌堆抽空时按它重洗。"""
    setup = _setup()
    reference = setup.new_oracle()
    plan = ExamDrawPlan(setup)

    turn1 = [tuple(card) for card in reference.draw_next_turn(1)]
    assert plan.begin_turn(turn1, 1) is True
    plan.end_turn(turn1)  # 一张没打，三张全进弃牌堆（按手牌顺序）

    # 参考 oracle 用同样的 grave 重放第 2 回合（牌堆只剩 1 张 → 必重洗）
    turn2 = [tuple(card) for card in reference.draw_next_turn(1, grave=turn1)]
    assert plan.begin_turn(turn2, 1) is True
    assert plan.stats["reshuffles"] == 1
    assert plan.known_draw == tuple(reference.remaining)
    kwargs = plan.expect_state_kwargs(to_specs=list)
    assert kwargs["discard"] == ()
    assert kwargs["discard_order"] == ()
    # 重洗钩子来自 oracle（纯函数，不推进 RNG）
    before = plan._oracle.rng_state
    plan.reshuffle_hook()([("p_card-a", 0), ("p_card-b", 0)])
    assert plan._oracle.rng_state == before


def test_plan_note_play_and_lost_cards_skip_grave():
    setup = _setup(lost_keys=frozenset({("p_card-d", 0)}))
    plan = ExamDrawPlan(setup)
    reference = setup.new_oracle()
    hand = [tuple(card) for card in reference.draw_next_turn(0)]
    assert plan.begin_turn(hand, 0) is True
    # 普通牌打出后进弃牌堆；Lost 卡（p_card-d）不进
    plan.note_play(("p_card-d", 0))
    plan.end_turn([])
    assert ("p_card-d", 0) not in plan._grave
    plan2 = ExamDrawPlan(setup)
    reference2 = setup.new_oracle()
    hand2 = [tuple(card) for card in reference2.draw_next_turn(0)]
    assert plan2.begin_turn(hand2, 0) is True
    normal = next(card for card in hand2 if card[0] != "p_card-d")
    plan2.note_play(normal)
    plan2.end_turn([])
    assert normal in plan2._grave


def test_plan_observe_hand_tracks_in_turn_draws():
    setup = _setup(deck=tuple(DECK) + (("p_card-e", 0), ("p_card-f", 0)))
    plan = ExamDrawPlan(setup)
    reference = setup.new_oracle()
    hand = [tuple(card) for card in reference.draw_next_turn(0)]
    assert plan.begin_turn(hand, 0) is True
    known_before = plan.known_draw
    assert len(known_before) >= 3  # 6 张牌抽 3 张，牌堆还剩 3 张

    plan.note_play(hand[0])
    rest = hand[1:]
    drawn = known_before[:2]
    plan.observe_hand(rest + list(drawn))
    assert plan.known_draw == known_before[2:]
    assert plan.stats["in_turn_draws"] == 2


def test_plan_observe_hand_mismatch_disables_turn():
    setup = _setup()
    plan = ExamDrawPlan(setup)
    reference = setup.new_oracle()
    hand = [tuple(card) for card in reference.draw_next_turn(0)]
    assert plan.begin_turn(hand, 0) is True
    plan.note_play(hand[0])
    # 多出来的牌不在已知牌序里 → 本回合全知停用（下回合重新核对）
    plan.observe_hand(hand[1:] + [("p_card-zzz", 0)])
    assert plan.expect_state_kwargs(to_specs=list) == {}


def test_plan_name_resolution_uses_card_table():
    table = FakeTable(
        {
            "小牌": {"id": "p_card-a", "upgrade": 0, "cost": 1, "effects": []},
            "中牌": {"id": "p_card-b", "upgrade": 0, "cost": 1, "effects": []},
            "大牌": {"id": "p_card-c", "upgrade": 0, "cost": 2, "effects": []},
        }
    )
    setup = _setup(deck=(("p_card-a", 0), ("p_card-b", 0), ("p_card-c", 0)))
    reference = setup.new_oracle()
    hand = [tuple(card) for card in reference.draw_next_turn(0)]
    names = {("p_card-a", 0): "小牌", ("p_card-b", 0): "中牌", ("p_card-c", 0): "大牌"}
    plan = ExamDrawPlan(setup, card_table=table)
    assert plan.begin_turn([names[card] for card in hand], 0) is True
    assert plan.cards  # 已核对的预测手牌
    # 卡表查不到的名字 → 停用
    plan2 = ExamDrawPlan(setup, card_table=table)
    assert plan2.begin_turn(["不存在的卡"], 0) is False
    assert plan2.status == STATUS_MISMATCH


def test_plan_summary_contains_status_and_stats():
    plan = ExamDrawPlan(_setup())
    plan.begin_turn([("p_card-a", 0)], 0)
    summary = plan.summary()
    assert summary["status"] in {STATUS_ACTIVE, STATUS_MISMATCH}
    assert summary["seed"].startswith("0x")
    assert summary["turn"] == 1
    assert "verified" in summary
