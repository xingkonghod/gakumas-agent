"""课程读屏 + 出牌策略 + buff 知识库的离线单测。

真机帧测试会用 ``data/live_lesson.png`` 等实拍图，文件缺失或没装 rapidocr 时自动跳过。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gkagent.data.buffs import BuffLibrary
from gkagent.data.card_costs import CardCosts
from gkagent.data.card_effects import estimate_value, is_buff_text, parse_effects
from gkagent.policy.lesson import LessonPolicy
from gkagent.vision.lesson import LessonCard, LessonState, _parse_int, _parse_score, card_value

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "data"


# --------------------------------------------------------------------- 文本解析
def test_parse_score_variants() -> None:
    assert _parse_score("84") == (84, 1)
    assert _parse_score("26x2") == (26, 2)
    assert _parse_score("26 x2") == (26, 2)
    assert _parse_score("") == (None, None)
    assert _parse_int("-6") == 6
    assert _parse_int("体力") is None


def test_parse_effects_master_text() -> None:
    effects = {effect.kind: effect.amount for effect in parse_effects("打分 / + / 9")}
    assert effects["score"] == 9
    effects = {effect.kind: effect.amount for effect in parse_effects("打分 / + / 2 / 元气 / + / 2")}
    assert effects == {"score": 2.0, "vitality": 2.0}


def test_estimate_value_prefers_score_over_vitality() -> None:
    score_card = estimate_value("打分 / + / 9")
    defense_card = estimate_value("元气 / + / 6")
    assert score_card.score > defense_card.score
    assert score_card.is_score_card
    assert not is_buff_text("打分 / + / 9")


def test_buff_text_detection() -> None:
    # 带打分的牌不算纯 buff（哪怕它有"好调状态才可使用"的条件）
    assert not is_buff_text("好调状态的时候，可以使用 / 打分+27")
    assert is_buff_text("集中+2") is True
    assert is_buff_text("打分+3 好调+2") is False


def test_buff_library_loads_known_buffs() -> None:
    lib = BuffLibrary.load()
    assert lib.buffs  # 能加载出 buff 表
    hits = lib.find("好调状态的时候，可以使用")
    assert any(buff.id == "condition" for buff in hits)
    assert lib.play_order("集中+2") < lib.play_order("元气+5")


# --------------------------------------------------------------------- 策略
def _state(cards, **kwargs) -> LessonState:
    return LessonState(cards=tuple(cards), **kwargs)


def _card(index: int, name: str, score, cost, *, buff=False, text="") -> LessonCard:
    return LessonCard(
        index=index,
        box=(index * 200, 900, 190, 232),
        point=(index * 200 + 95, 1000),
        name=name,
        score=score,
        cost=cost,
        buff=buff,
        text=text,
    )


def test_policy_picks_high_score_card_even_when_costly() -> None:
    """回归：老代码把分数预览当费用，84 分的牌被判"付不起"。"""
    policy = LessonPolicy()
    state = _state(
        [_card(0, "平衡感", 2, 2), _card(1, "聊天时间", 84, 6), _card(2, "表现的基础", 4, 0)],
        turns_left=9,
        stamina=28,
    )
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "聊天时间"


def test_policy_skips_unaffordable_cards() -> None:
    policy = LessonPolicy()
    state = _state([_card(0, "聊天时间", 84, 30)], turns_left=4, stamina=5)
    action = policy.decide(state)
    assert action.kind == "skip"


def test_policy_skips_worthless_cards() -> None:
    policy = LessonPolicy()
    state = _state(
        [_card(0, "元气", 0, 2), _card(1, "护盾", 0, 3)],
        turns_left=3,
        stamina=20,
    )
    action = policy.decide(state)
    assert action.kind == "skip"


def test_policy_last_turn_maximises_total_score() -> None:
    """最后一回合体力不用就浪费：30 分 / 6 体力 优于 22 分 / 4 体力。"""
    policy = LessonPolicy()
    state = _state(
        [_card(0, "聊天时间", 30, 6), _card(1, "击掌", 22, 4)],
        turns_left=1,
        stamina=25,
    )
    action = policy.decide(state)
    assert action.card is not None and action.card.name == "聊天时间"


def test_policy_plays_cheap_buff_first() -> None:
    policy = LessonPolicy()
    state = _state(
        [
            _card(0, "好调", 0, 2, buff=True, text="好调+2"),
            _card(1, "魅力的基础", 9, 5, text="打分+9"),
        ],
        turns_left=4,
        stamina=20,
    )
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "好调"
    # 同一回合只铺一次 buff
    policy.note_play(action.card)
    again = policy.decide(state)
    assert again.card is not None and again.card.name == "魅力的基础"


# --------------------------------------------------------------------- 费用缓存
def test_card_costs_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "card_costs.json"
    costs = CardCosts(path)
    assert costs.get("聊天时间") is None
    assert costs.record("聊天时间", 6) is True
    assert costs.record("聊天时间", 6) is False
    again = CardCosts(path)
    assert again.get("聊天时间") == 6


# --------------------------------------------------------------------- 真机帧
needs_frames = pytest.mark.skipif(
    not (FRAMES / "live_lesson.png").exists(),
    reason="缺少实拍帧 data/live_lesson.png",
)


def _reader():
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2

    from gkagent.vision.lesson import LessonReader
    from gkagent.vision.ocr import OcrEngine

    return cv2, LessonReader(OcrEngine())


@needs_frames
def test_reader_reads_audition_frame() -> None:
    cv2, reader = _reader()
    image = cv2.imread(str(FRAMES / "live_lesson.png"))
    state = reader.read(image, kind="audition")
    assert state.turns_left == 9
    assert state.stamina == 28
    assert state.attribute == "歌唱"
    assert state.multiplier == 310
    names = {card.name: card for card in state.cards}
    assert "聊天时间" in names
    assert names["聊天时间"].score == 84
    assert names["聊天时间"].cost == 6


@needs_frames
def test_reader_reads_lesson_frame() -> None:
    cv2, reader = _reader()
    image = cv2.imread(str(FRAMES / "lesson_now.png"))
    state = reader.read(image, kind="lesson")
    assert state.turns_left == 1
    assert state.stamina == 25
    assert state.score == 124
    assert any(card.score for card in state.cards)


@needs_frames
def test_reader_policy_beats_old_name_pick_on_audition() -> None:
    """同一帧：老逻辑会把 84 分牌判无用，新策略必须选中它。"""
    cv2, reader = _reader()
    image = cv2.imread(str(FRAMES / "live_lesson.png"))
    state = reader.read(image, kind="audition")
    action = LessonPolicy(buffs=reader.buffs).decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "聊天时间"
    assert card_value(action.card, turns_left=state.turns_left) == 84
