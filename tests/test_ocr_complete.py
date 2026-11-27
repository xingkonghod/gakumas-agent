"""opt-in 引擎补全（gkagent.vision.ocr_complete）单测：默认关逐位不变。

matto 基准缺口 B：deck_left / card_effect statuses / multiplier_pct 屏幕读不到
（5 后端全没读），用引擎状态补；**默认 enable=False 必须原样返回**。
"""

from __future__ import annotations

import pytest

from gkagent.sim.exam_multiplier import ExamBonus
from gkagent.vision.ocr_complete import (
    CompletionSources,
    complete_fields,
    sources_from_sim,
)


def _bonus(vocal_permil: int = 28050) -> ExamBonus:
    return ExamBonus(
        permil={"vocal": vocal_permil, "dance": 4110, "visual": 4110},
        components={"vocal": 0, "dance": 0, "visual": 0},
        penalties={"vocal": 0, "dance": 0, "visual": 0},
        common_permil=1000,
    )


class _Sim:
    def __init__(self, deck):
        self.deck = deck


def test_default_off_returns_fields_unchanged() -> None:
    fields = {"deck_left": None, "multiplier_pct": None, "statuses": [{"kind": "status", "name": "やる気", "value": 6}]}
    sources = CompletionSources(deck_count=5, bonus=_bonus(), exam_attr="vocal")
    assert complete_fields(fields, sources) == fields
    assert complete_fields(fields, sources, enable=False) == fields
    assert complete_fields(fields, None, enable=True) == fields


def test_enable_fills_deck_left_only_when_missing() -> None:
    sources = CompletionSources(deck_count=5)
    assert complete_fields({"deck_left": None}, sources, enable=True)["deck_left"] == 5
    # OCR 已读到的值一律不动
    assert complete_fields({"deck_left": 3}, sources, enable=True)["deck_left"] == 3
    # 没有源就不补（绝不编造）
    assert complete_fields({"deck_left": None}, CompletionSources(), enable=True)["deck_left"] is None


def test_card_effects_appended_and_deduped() -> None:
    fields = {"statuses": [{"kind": "status", "name": "好印象", "value": 6}]}
    effects = (
        {"kind": "card_effect", "name": None, "value": 1},
        {"kind": "card_effect", "name": None, "value": 1},  # 重复
        {"kind": "status", "name": "やる気", "value": 6},  # 非 card_effect 不收
    )
    out = complete_fields(fields, CompletionSources(card_effects=effects), enable=True)
    assert out["statuses"] == [
        {"kind": "status", "name": "好印象", "value": 6},
        {"kind": "card_effect", "name": None, "value": 1},
    ]
    # 输入不被修改
    assert fields["statuses"] == [{"kind": "status", "name": "好印象", "value": 6}]


def test_multiplier_from_bonus_permil() -> None:
    sources = CompletionSources(bonus=_bonus(28050), exam_attr="vocal")
    out = complete_fields({"multiplier_pct": None}, sources, enable=True)
    assert out["multiplier_pct"] == 2805  # 28050 permil = 屏幕 2805%
    # OCR 读到了就不动
    assert complete_fields({"multiplier_pct": 411}, sources, enable=True)["multiplier_pct"] == 411
    # 属性未知 / 无 bonus 不补
    assert complete_fields({"multiplier_pct": None}, CompletionSources(bonus=_bonus()), enable=True)["multiplier_pct"] is None
    assert complete_fields({"multiplier_pct": None}, CompletionSources(exam_attr="vocal"), enable=True)["multiplier_pct"] is None


def test_sources_from_sim_deck_count() -> None:
    sources = sources_from_sim(_Sim([1, 2, 3, 4, 5]), bonus=_bonus(), exam_attr="vocal")
    assert sources.deck_count == 5
    assert sources_from_sim(object()).deck_count is None
    out = complete_fields({"deck_left": None, "multiplier_pct": None}, sources, enable=True)
    assert (out["deck_left"], out["multiplier_pct"]) == (5, 2805)


def test_combined_completion_matches_matto_gap_fields() -> None:
    """matto r3-00074 口径：deck_left=5 / card_effect value=1 / multiplier 2805。"""
    fields = {
        "turns_left": 9,
        "deck_left": None,
        "multiplier_pct": None,
        "statuses": [
            {"kind": "status", "name": "やる気", "value": 6},
            {"kind": "status", "name": "好印象", "value": 6},
        ],
    }
    sources = CompletionSources(
        deck_count=5,
        card_effects=({"kind": "card_effect", "name": None, "value": 1},),
        bonus=_bonus(28050),
        exam_attr="vocal",
    )
    out = complete_fields(fields, sources, enable=True)
    assert out["deck_left"] == 5
    assert out["multiplier_pct"] == 2805
    assert out["statuses"][2] == {"kind": "card_effect", "name": None, "value": 1}
    assert out["turns_left"] == 9  # 既有字段不动


@pytest.mark.parametrize("enable", [False, True])
def test_no_sources_never_changes(enable: bool) -> None:
    fields = {"deck_left": None, "statuses": [], "multiplier_pct": None}
    assert complete_fields(fields, None, enable=enable) == fields
