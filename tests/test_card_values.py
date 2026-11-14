"""card_table.json 的卡牌效果数值回归测试。

真值来源：
- gakumasu-diff 的 ProduceCard.yaml + ProduceExamEffect.yaml（游戏 master 同源）；
- 游戏截图 ``data/live_lesson.png``（聊天时间 84 是吃加成后的预览，卡面基础值 27）、
  ``data/exam_c.png``（表现的基础 元气 4、表现的基础+ 元气 7、最高的星 26x2 是加成后）。

这些测试只读已提交的 card_table.json，不解析 40MB YAML，保证秒级完成。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "data" / "knowledge" / "card_table.json"


def load_cards() -> dict[str, dict]:
    data = json.loads(TABLE.read_text(encoding="utf-8"))
    return data["cards"]


def values_of(cards: dict[str, dict], name: str, effect_type: str) -> list[int]:
    return [
        value
        for effect in cards[name]["effects"]
        if effect["type"] == effect_type
        for value in effect["values"]
    ]


def test_table_keeps_scale_and_schema() -> None:
    cards = load_cards()
    assert len(cards) == 1724
    for name, row in cards.items():
        assert name
        assert isinstance(row["cost"], int) and row["cost"] >= 0
        assert row["id"]
        assert isinstance(row["effects"], list)
        for effect in row["effects"]:
            assert isinstance(effect["type"], str) and effect["type"]
            assert isinstance(effect["values"], list)
            assert all(isinstance(value, int) for value in effect["values"])
            assert isinstance(effect["turn"], int)
            if "count" in effect:
                # 多段效果写 count>1；本身无数值、只靠次数表达的效果（如使用数+1）写 count>=1。
                assert isinstance(effect["count"], int) and effect["count"] >= 1
            if "inner" in effect:
                assert effect["inner"]
                for child in effect["inner"]:
                    assert child["type"] and isinstance(child["values"], list)


def test_known_starter_card_values() -> None:
    cards = load_cards()

    # 魅力的基础：4 费，打分 +9。
    assert cards["魅力的基础"]["cost"] == 4
    assert 9 in values_of(cards, "魅力的基础", "ExamLesson")

    # 聊天时间：6 费，打分 +27；截图里的 84 是吃了好调/倍率后的预览值。
    assert cards["聊天时间"]["cost"] == 6
    assert 27 in values_of(cards, "聊天时间", "ExamLesson")

    # 表现的基础：0 费，元气 +4；+ 版元气 +7（exam_c.png 实测）。
    assert cards["表现的基础"]["cost"] == 0
    assert 4 in values_of(cards, "表现的基础", "ExamBlock")
    assert cards["表现的基础+"]["cost"] == 0
    assert 7 in values_of(cards, "表现的基础+", "ExamBlock")


def test_upgraded_values_are_not_copied_from_base() -> None:
    cards = load_cards()
    # 魅力的基础+ / 聊天时间+ 的数值确实随强化变化，不是把基础值抄一遍。
    assert values_of(cards, "魅力的基础+", "ExamLesson") == [14]
    assert values_of(cards, "聊天时间+", "ExamLesson") == [38]


def test_multi_hit_count_is_preserved() -> None:
    cards = load_cards()
    # 最高的星：卡面基础是打分 +3 x 2 次（截图 26x2 是加成后的数值）。
    lesson = [effect for effect in cards["最高的星"]["effects"] if effect["type"] == "ExamLesson"]
    assert any(effect["values"] == [3] and effect.get("count") == 2 for effect in lesson)


def test_status_enchant_keeps_inner_effect() -> None:
    cards = load_cards()
    # 悠闲地睡个好觉：3 回合内每回合结束集中 +2，数值在内层效果里。
    outer = next(
        effect
        for effect in cards["悠闲地睡个好觉"]["effects"]
        if effect["type"] == "ExamStatusEnchant"
    )
    assert outer["turn"] == 3
    assert outer["enchant"].startswith("enchant-")
    assert any(
        child["type"] == "ExamLessonBuff" and child["values"] == [2]
        for child in outer["inner"]
    )


def test_conditional_card_trigger_is_recorded() -> None:
    cards = load_cards()
    # 聊天时间只能在好调状态使用；条件存在 playProduceExamTriggerId。
    assert cards["聊天时间"]["trigger"] == "e_trigger-exam_start_turn-parameter_buff"


def test_numeric_coverage_above_80_percent() -> None:
    cards = load_cards()
    valued = sum(1 for row in cards.values() if any(e["values"] for e in row["effects"]))
    assert valued / len(cards) > 0.8
    # 状态附魔展开后的内层数值也算覆盖。
    with_inner = sum(
        1
        for row in cards.values()
        if any(e["values"] or e.get("inner") for e in row["effects"])
    )
    assert with_inner / len(cards) > 0.95
