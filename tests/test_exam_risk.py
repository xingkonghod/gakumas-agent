"""known_draw 事前检测（exam_risk）回归测试。

覆盖：
- 卡表扫描：命中额外 RNG 机制卡的 id/effects 正确；
- 牌组扫描：只标记含机制卡的条目，纯牌组返回空；
- ExamSetup：``rng_risk`` 序列化/反序列化 + ``known_info_ok``；
- ExamDrawPlan：含机制卡的 setup 直接停用（不建 oracle、不给 known_draw）；
- 摘要格式化。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gkagent.sim.exam_plan import STATUS_MISMATCH, ExamDrawPlan, ExamSetup
from gkagent.sim.exam_risk import (
    EXTRA_RNG_EFFECT_TYPES,
    deck_rng_risks,
    format_rng_risks,
    known_info_ok,
    load_extra_rng_index,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "knowledge" / "card_table.json"


def _clean_and_risky_ids() -> tuple[str, str]:
    """从真实卡表里挑一个机制卡 id 和一个纯效果 id（没有数据就 skip）。"""
    if not DATA.exists():
        pytest.skip("缺少 card_table.json")
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    cards = raw.get("cards", raw)
    items = cards.values() if isinstance(cards, dict) else cards
    risky = clean = None
    for row in items:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        types = {
            str(effect.get("type"))
            for effect in (row.get("effects") or ())
            if isinstance(effect, dict)
        }
        if types & EXTRA_RNG_EFFECT_TYPES and risky is None:
            risky = str(row["id"])
        if not types & EXTRA_RNG_EFFECT_TYPES and clean is None:
            clean = str(row["id"])
        if risky and clean:
            break
    if not risky or not clean:
        pytest.skip("card_table 里找不到机制卡/纯效果卡样例")
    return clean, risky


def test_load_extra_rng_index_hits_expected_types() -> None:
    index = load_extra_rng_index(DATA)
    assert index, "卡表里应有额外 RNG 机制卡"
    for effects in index.values():
        assert effects <= EXTRA_RNG_EFFECT_TYPES


def test_deck_rng_risks_only_marks_risky_cards() -> None:
    clean, risky = _clean_and_risky_ids()
    risks = deck_rng_risks([[clean, 0], [risky, 1]])
    assert len(risks) == 1
    assert risks[0]["card_id"] == risky
    assert risks[0]["effects"]
    assert known_info_ok([[clean, 0]])
    assert not known_info_ok([[clean, 0], [risky, 0]])


def test_deck_rng_risks_accepts_plain_id_and_skips_unknown() -> None:
    _clean, risky = _clean_and_risky_ids()
    assert deck_rng_risks([risky])[0]["card_id"] == risky
    assert deck_rng_risks(["no-such-card-id"]) == []


def test_format_rng_risks() -> None:
    assert format_rng_risks([]) == "无"
    text = format_rng_risks(
        [
            {"card_id": "a", "effects": ["ExamCardCreateSearch"]},
            {"card_id": "b", "effects": ["ExamCardMove"]},
        ]
    )
    assert "a(ExamCardCreateSearch)" in text and "b(" in text


def _setup_dict(**overrides) -> dict:
    raw = {
        "index": 0,
        "ts": "2026-11-22T00:00:00+08:00",
        "seed": 0x504C4509,
        "config_turns": 9,
        "deck": [["p_card-00-act-0_001", 0]],
        "card_variants": {"p_card-00-act-0_001": 1},
        "npc_count": 5,
        "turn_start_distribute": 10,
        "hand_limit": 3,
        "truth": [],
    }
    raw.update(overrides)
    return raw


def test_exam_setup_known_info_ok_default_true() -> None:
    setup = ExamSetup.from_dict(_setup_dict())
    assert setup.known_info_ok is True
    assert setup.rng_risk == ()


def test_exam_setup_parses_rng_risk_and_roundtrips() -> None:
    risk = [{"card_id": "p_card-01-men-2_099", "effects": ["ExamCardCreateId"]}]
    setup = ExamSetup.from_dict(_setup_dict(rng_risk=risk))
    assert setup.known_info_ok is False
    assert setup.rng_risk[0]["card_id"] == "p_card-01-men-2_099"
    assert setup.to_dict()["rng_risk"] == risk


def test_exam_plan_refuses_unverifiable_setup() -> None:
    risk = [{"card_id": "p_card-01-men-2_099", "effects": ["ExamCardCreateId"]}]
    setup = ExamSetup.from_dict(_setup_dict(rng_risk=risk))
    plan = ExamDrawPlan(setup)
    plan.start()
    assert plan.active is False
    assert plan.status == STATUS_MISMATCH
    assert "不可验" in plan.reason
    assert plan.begin_turn([("p_card-00-act-0_001", 0)]) is False
    assert plan.known_draw == ()
    assert plan.expect_state_kwargs(to_specs=list) == {}
