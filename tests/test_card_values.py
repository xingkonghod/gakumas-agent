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


# ---- 奖励选卡分档估值（效果定档 / 稀有度加成） -----------------------------
def _fake_card(
    *,
    cost: int,
    rarity: str,
    score: int | None = None,
    effects: tuple[str, ...] = (),
) -> dict:
    """构造最小卡表行：score>0 时插入 ExamLesson，effects 为效果类型。"""
    rows = [{"type": effect, "values": [1], "turn": 0} for effect in effects]
    if score is not None:
        rows.insert(0, {"type": "ExamLesson", "values": [score], "turn": 0})
    return {
        "cost": cost,
        "rarity": rarity,
        "plan": "Common",
        "category": "ActiveSkill",
        "effects": rows,
    }


def _write_table(tmp_path: Path, cards: dict[str, dict]):
    from gkagent.data.card_table import CardTable

    path = tmp_path / "card_table.json"
    path.write_text(json.dumps({"cards": cards}, ensure_ascii=False), encoding="utf-8")
    return CardTable(path)


def test_pure_buff_card_outvalues_low_score_white_card() -> None:
    """score=0 的纯 buff 牌不再恒为 0：按效果类型给 8-15 的等效值。"""
    from gkagent.data.card_table import CardTable

    table = CardTable()
    buff = table.value("一决胜负+")  # ExamLessonBuff，score=0
    white = table.value("聊天时间")  # ExamLesson 27 / cost 6 = 4.5，纯白值
    assert buff is not None and white is not None
    assert buff >= 8.0  # 纯 buff 8-15 档
    assert buff > white


def test_ssr_skill_card_is_not_undervalued() -> None:
    """再进一步+（SSR 9 分/3 费）≥ 9.0：3.0 白值 + 5 SSR + 1.0 多段打点。"""
    from gkagent.data.card_table import CardTable

    table = CardTable()
    assert table.score_of("再进一步+") == 9
    assert table.cost("再进一步+") == 3
    value = table.value("再进一步+")
    assert value is not None
    assert value >= 9.0


def test_sr_buff_card_value_is_not_reduced() -> None:
    """一决胜负+（SR 纯 buff）改档后不降：旧值 14.5，目标 ≥ 14。"""
    from gkagent.data.card_table import CardTable

    table = CardTable()
    value = table.value("一决胜负+")
    assert value is not None
    assert value >= 14.5


def test_nt_concentration_card_keeps_high_value() -> None:
    """打招呼的基础（N，集中）仍应留在 ≥ 14 的高档。"""
    from gkagent.data.card_table import CardTable

    table = CardTable()
    value = table.value("打招呼的基础")
    assert value is not None
    assert value >= 14.0


def test_ssr_buff_card_gets_effect_tier_and_rarity_premium(tmp_path: Path) -> None:
    """假想「SSR + buff」：效果档 12-15 再加 SSR +5，必须 ≥ 16。"""
    table = _write_table(
        tmp_path,
        {
            "假SSR好调": _fake_card(cost=1, rarity="Ssr", effects=("ExamLessonBuff",)),
            "假SR好调": _fake_card(cost=1, rarity="Sr", effects=("ExamLessonBuff",)),
        },
    )
    ssr = table.value("假SSR好调")
    sr = table.value("假SR好调")
    assert ssr is not None and sr is not None
    assert ssr >= 16.0
    assert ssr > sr


def test_ssr_pure_white_low_score_not_below_sr(tmp_path: Path) -> None:
    """假想「SSR 纯白值低分」：同白值下不能低于 SR。"""
    table = _write_table(
        tmp_path,
        {
            "假SSR白值": _fake_card(cost=6, rarity="Ssr", score=6),
            "假SR白值": _fake_card(cost=6, rarity="Sr", score=6),
        },
    )
    ssr = table.value("假SSR白值")
    sr = table.value("假SR白值")
    assert ssr is not None and sr is not None
    assert ssr > sr
    assert ssr - sr == 3.0  # 稀有度 +5 vs +2


def test_rarity_bonus_is_tiered(tmp_path: Path) -> None:
    """稀有度加成：SSR/Legend +5、SR +2、R/N 0（同白值 3 分/3 费）。"""
    cards = {
        "假N": _fake_card(cost=3, rarity="N", score=3),
        "假R": _fake_card(cost=3, rarity="R", score=3),
        "假SR": _fake_card(cost=3, rarity="Sr", score=3),
        "假SSR": _fake_card(cost=3, rarity="Ssr", score=3),
        "假Legend": _fake_card(cost=3, rarity="Legend", score=3),
    }
    table = _write_table(tmp_path, cards)
    n = table.value("假N")
    r = table.value("假R")
    sr = table.value("假SR")
    ssr = table.value("假SSR")
    legend = table.value("假Legend")
    assert n is not None and r is not None and sr is not None
    assert ssr is not None and legend is not None
    assert n == r == 1.0
    assert sr - r == 2.0
    assert ssr - r == 5.0
    assert legend - r == 5.0


def test_effect_tiers_rank_stack_above_function_above_sustain(tmp_path: Path) -> None:
    """效果定档：层数类 12-15 > 功能类 10-13 > 生存类 8-10。"""
    table = _write_table(
        tmp_path,
        {
            "假集中": _fake_card(cost=1, rarity="N", effects=("ExamConcentration",)),
            "假抽牌": _fake_card(cost=1, rarity="N", effects=("ExamCardDraw",)),
            "假元气": _fake_card(cost=1, rarity="N", effects=("ExamBlock",)),
        },
    )
    stack = table.value("假集中")
    function = table.value("假抽牌")
    sustain = table.value("假元气")
    assert stack is not None and function is not None and sustain is not None
    assert stack >= 12.0
    assert function >= 10.0
    assert sustain >= 8.0
    assert stack > function > sustain


def test_buff_effect_tiers_rank_concentration_above_vitality() -> None:
    """纯 buff 按效果类型分档：集中/温存 > 纯元气。"""
    from gkagent.data.card_table import CardTable

    table = CardTable()
    vitality = table.value("表现的基础+")  # ExamBlock 纯元气 = 9
    concentration = table.value("打招呼的基础")  # ExamConcentration 集中
    preservation = table.value("临场应对的基础++")  # ExamPreservation 温存
    assert vitality is not None and concentration is not None and preservation is not None
    assert concentration > vitality
    assert preservation > vitality
