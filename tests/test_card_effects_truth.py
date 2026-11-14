"""高频卡真值测试：直接断言 data/knowledge/card_table.json 的硬数值。

覆盖 8 张高频卡：

- 截图核对真值（用户给定）：魅力的基础 4 费/9 分、聊天时间 6 费/27 分、
  表现的基础 0 费/元气 4、最高的星 3 分 × 2 段、准备运动 6 分 + 好调 2；
- 强化版沿用 ``tests/test_card_values.py`` 已锁定的同源 master 值：
  魅力的基础+ 14 分、聊天时间+ 38 分、表现的基础+ 元气 7。

注意：这是"抓数据错"的测试，不是宽松的冒烟测试——
如果数值与真值不符，断言失败并把卡表实际值打进消息；
如果卡表缺卡/缺字段导致无法断言，则 skip 并说明原因，避免把"没数据"误判成"数据错"。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CARD_TABLE = ROOT / "data" / "knowledge" / "card_table.json"

# 8 张高频卡：3 张基础卡 + 3 张强化版 + 多段卡 + 带 buff 卡
HIGH_FREQUENCY_CARDS = (
    "魅力的基础",
    "魅力的基础+",
    "聊天时间",
    "聊天时间+",
    "表现的基础",
    "表现的基础+",
    "最高的星",
    "准备运动",
)

# 费用真值（强化版费用表未在截图里核对，故只断言基础卡）
COST_TRUTHS = (
    ("魅力的基础", 4),
    ("聊天时间", 6),
    ("表现的基础", 0),
)

# 打分真值：基础卡来自截图，强化版来自同源 master（test_card_values.py 已锁定）
SCORE_TRUTHS = (
    ("魅力的基础", 9),
    ("魅力的基础+", 14),
    ("聊天时间", 27),
    ("聊天时间+", 38),
)

# 元气在卡表里是 ExamBlock
VITALITY_TRUTHS = (
    ("表现的基础", 4),
    ("表现的基础+", 7),
)


# ---------------------------------------------------------------------- 读表/防御
def load_cards() -> dict[str, dict]:
    data = json.loads(CARD_TABLE.read_text(encoding="utf-8"))
    return data["cards"]


def require_card(cards: dict[str, dict], name: str) -> dict:
    row = cards.get(name)
    if row is None:
        pytest.fail(
            f"卡表缺少高频卡 {name}；应包含 8 张真值卡: {', '.join(HIGH_FREQUENCY_CARDS)}",
            pytrace=False,
        )
    return row


def require_field(row: dict, name: str, field: str):
    if field not in row or row[field] is None:
        pytest.skip(f"{name} 卡表缺 {field} 字段，无法断言（实际字段={sorted(row)}）")
    return row[field]


def require_effects(row: dict, name: str) -> list[dict]:
    effects = row.get("effects")
    if not isinstance(effects, list) or not effects:
        pytest.skip(f"{name} 卡表缺 effects 字段或为空，无法断言（实际={effects!r}）")
    return effects


def require_effect(row: dict, name: str, effect_type: str) -> dict:
    effects = require_effects(row, name)
    for effect in effects:
        if isinstance(effect, dict) and effect.get("type") == effect_type:
            return effect
    actual = [effect.get("type") if isinstance(effect, dict) else effect for effect in effects]
    pytest.skip(f"{name} 卡表没有 {effect_type} 效果，无法断言（实际效果={actual}）")


def require_values(effect: dict, label: str) -> list[int]:
    values = effect.get("values")
    if not isinstance(values, list) or not values:
        pytest.skip(f"{label} 缺 values 字段/为空，无法断言（实际={effect!r}）")
    return values


# ---------------------------------------------------------------------- 费用
@pytest.mark.parametrize(
    ("name", "expected"),
    COST_TRUTHS,
    ids=[name for name, _ in COST_TRUTHS],
)
def test_cost_matches_truth(name: str, expected: int) -> None:
    row = require_card(load_cards(), name)
    actual = require_field(row, name, "cost")
    assert actual == expected, (
        f"{name} cost 与真值不符：期望 {expected}，卡表实际 {actual!r}（{CARD_TABLE}）"
    )


# ---------------------------------------------------------------------- 打分
@pytest.mark.parametrize(
    ("name", "expected"),
    SCORE_TRUTHS,
    ids=[name for name, _ in SCORE_TRUTHS],
)
def test_score_matches_truth(name: str, expected: int) -> None:
    row = require_card(load_cards(), name)
    effect = require_effect(row, name, "ExamLesson")
    values = require_values(effect, f"{name} 的 ExamLesson")
    assert values == [expected], (
        f"{name} 打分与真值不符：期望 [{expected}]，卡表实际 {values!r}；"
        f"完整 effect={effect!r}"
    )


# ---------------------------------------------------------------------- 元气（ExamBlock）
@pytest.mark.parametrize(
    ("name", "expected"),
    VITALITY_TRUTHS,
    ids=[name for name, _ in VITALITY_TRUTHS],
)
def test_vitality_matches_truth(name: str, expected: int) -> None:
    row = require_card(load_cards(), name)
    effect = require_effect(row, name, "ExamBlock")
    values = require_values(effect, f"{name} 的 ExamBlock（元气）")
    assert values == [expected], (
        f"{name} 元气与真值不符：期望 [{expected}]，卡表实际 {values!r}；"
        f"完整 effect={effect!r}"
    )


# ---------------------------------------------------------------------- 多段
def test_highest_star_is_two_hits_of_three() -> None:
    name = "最高的星"
    row = require_card(load_cards(), name)
    effect = require_effect(row, name, "ExamLesson")
    values = require_values(effect, f"{name} 的 ExamLesson")
    assert values == [3], (
        f"{name} 打分与真值不符：期望 [3]（3 分 × 2 段），卡表实际 {values!r}；"
        f"完整 effect={effect!r}"
    )
    if "count" not in effect:
        pytest.skip(f"{name} 的 ExamLesson 缺 count 字段，无法确认多段；实际 effect={effect!r}")
    assert effect["count"] == 2, (
        f"{name} 多段 count 与真值不符：期望 2，卡表实际 {effect['count']!r}；"
        f"完整 effect={effect!r}"
    )


# ---------------------------------------------------------------------- 准备运动：打分 + 好调 buff
def test_warmup_score_is_six() -> None:
    name = "准备运动"
    row = require_card(load_cards(), name)
    effect = require_effect(row, name, "ExamLesson")
    values = require_values(effect, f"{name} 的 ExamLesson")
    assert values == [6], (
        f"{name} 打分与真值不符：期望 [6]，卡表实际 {values!r}；完整 effect={effect!r}"
    )


def test_warmup_condition_buff_is_two() -> None:
    name = "准备运动"
    row = require_card(load_cards(), name)
    effect = require_effect(row, name, "ExamLessonBuff")
    values = require_values(effect, f"{name} 的 ExamLessonBuff（好调）")
    assert values == [2], (
        f"{name} 好调 buff 与真值不符：期望 [2]，卡表实际 {values!r}；"
        f"完整 effect={effect!r}"
    )
