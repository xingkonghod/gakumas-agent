"""分数宝石 OCR 失败时的卡表兜底 / 降权 / 下回合重读。

真机问题：手牌左上角分数宝石没读到时 ``LessonCard.score`` 变 0/None，
老策略把这张牌当"0 分填充牌"跳过，而 ``card_table.json`` 其实知道它的分值。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from gkagent.data.card_table import CardTable
from gkagent.policy.lesson import LessonPolicy
from gkagent.vision.lesson import (
    CARD_HEIGHT,
    CARD_TOP,
    CARD_WIDTH,
    LessonCard,
    LessonReader,
    LessonState,
    card_value,
)
from gkagent.vision.ocr import OcrLine

CARD_RECT = (55, CARD_TOP, CARD_WIDTH, CARD_HEIGHT)
IMAGE = np.zeros((1280, 720, 3), dtype=np.uint8)

# 卡表里已知有分的牌（屏幕宝石没读到时用来兜底）
KNOWN_NAME = "聊天时间"
KNOWN_SCORE = 27
# 卡表里确实没分的牌（ExamLesson 白值为 0）
ZERO_NAME = "表现的基础"


@pytest.fixture
def table() -> CardTable:
    loaded = CardTable()
    if not len(loaded):
        pytest.skip("缺少 data/knowledge/card_table.json")
    return loaded


def _card(index: int, name: str, score: int | None, cost: int | None, **kwargs) -> LessonCard:
    return LessonCard(
        index=index,
        box=(index * 200, 900, 190, 232),
        point=(index * 200 + 95, 1000),
        name=name,
        score=score,
        cost=cost,
        **kwargs,
    )


def _policy(tmp_path: Path) -> LessonPolicy:
    """走代码默认值，避免仓库 policy.json 的后续调参影响断言。"""
    return LessonPolicy(params_path=tmp_path / "missing.json")


class FakeLineOcr:
    """只回答分数宝石和卡名框；费用框一律"没读到"。"""

    def __init__(self, score_texts: list[str], name_text: str = "") -> None:
        self.score_texts = list(score_texts)
        self.name_text = name_text
        self.score_calls = 0

    def line(self, image, roi, *, digits_only=False):
        _x, y, _w, _h = roi
        if y < 950:  # 分数宝石（含重读时放宽的框）
            index = min(self.score_calls, len(self.score_texts) - 1)
            self.score_calls += 1
            return OcrLine(self.score_texts[index], 0.9, roi)
        if y >= 1070:  # 卡名框
            return OcrLine(self.name_text, 0.9, roi)
        return OcrLine("", 0.9, roi)


def _reader(
    table: CardTable, score_texts: list[str], *, name_text: str = ""
) -> tuple[LessonReader, FakeLineOcr]:
    engine = FakeLineOcr(score_texts, name_text=name_text)
    return LessonReader(engine, table=table), engine


# --------------------------------------------------------------------- 卡表兜底
@pytest.mark.parametrize("score_text", ["", "0", "看不清"])
def test_gem_missing_uses_card_table_score(table: CardTable, score_text: str) -> None:
    """屏幕分数缺失 + 卡表 27 分 → reader 返回 27，并标记成"估"。"""
    assert table.score_of(KNOWN_NAME) == KNOWN_SCORE
    reader, _engine = _reader(table, [score_text])
    card = reader.read_card(IMAGE, 0, CARD_RECT, name=KNOWN_NAME)
    assert card.score == KNOWN_SCORE
    assert card.score_estimated is True
    assert card.recheck is True
    assert card.score_unread is False
    assert card_value(card) == KNOWN_SCORE


def test_recheck_rereads_gem_on_next_hand(table: CardTable) -> None:
    """上一回合没读到的宝石：下一回合进手牌时优先重读，读到就用屏幕真值。"""
    reader, engine = _reader(table, ["", "84"])
    first = reader.read_card(IMAGE, 0, CARD_RECT, name=KNOWN_NAME)
    assert first.score == KNOWN_SCORE
    assert first.score_estimated is True
    assert first.recheck is True
    assert reader.pending_recheck == (KNOWN_NAME,)

    second = reader.read_card(IMAGE, 0, CARD_RECT, name=KNOWN_NAME)
    assert second.score == 84
    assert second.score_estimated is False
    assert second.recheck is False
    assert reader.pending_recheck == ()
    assert engine.score_calls == 2  # 重读一次就成功，不用放宽框


def test_missing_gem_and_unknown_table_keeps_zero(table: CardTable) -> None:
    """屏幕分数缺失 + 卡表也查不到 → 保持 0，不会被当成高分。"""
    assert table.score_of("查无此卡") is None
    reader, _engine = _reader(table, [""])
    card = reader.read_card(IMAGE, 0, CARD_RECT, name="查无此卡")
    assert card.score == 0
    assert card.score_unread is True
    assert card.score_estimated is False
    assert card.recheck is False
    assert card_value(card) == 0


def test_table_zero_score_is_not_treated_as_estimated(table: CardTable) -> None:
    """卡表确认这张牌本身 0 分（纯防御/功能牌）：0 是真值，不标估。"""
    assert table.score_of(ZERO_NAME) == 0
    reader, _engine = _reader(table, [""])
    card = reader.read_card(IMAGE, 0, CARD_RECT, name=ZERO_NAME)
    assert card.score == 0
    assert card.score_estimated is False
    assert card.score_unread is False
    assert card.recheck is False


def test_card_name_with_select_label_still_hits_table(table: CardTable) -> None:
    """卡名含 SELECT 标签时先清洗再查表；LessonCard.name 保留原文供选中态检测。"""
    raw_name = "SELECT" + KNOWN_NAME
    reader, _engine = _reader(table, [""], name_text=raw_name)
    card = reader.read_card(IMAGE, 0, CARD_RECT)
    assert card.name == raw_name
    assert card.score == KNOWN_SCORE
    assert card.score_estimated is True
    assert card.cost == table.cost(KNOWN_NAME)  # 费用查表同样用清洗后的卡名


# --------------------------------------------------------------------- 策略降权
def test_policy_does_not_pick_unread_zero_over_real_six(tmp_path: Path) -> None:
    """0 分缺失卡 vs 真实 6 分卡：选真实 6 分，不选缺失卡。"""
    missing = _card(0, "缺分卡", 0, 0, score_unread=True)
    real_six = _card(1, "真实六分", 6, 3)
    state = LessonState(cards=(missing, real_six), turns_left=3, stamina=20)
    action = _policy(tmp_path).decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.index == 1


def test_policy_plays_estimated_card_instead_of_skipping(tmp_path: Path) -> None:
    """兜底过的牌绝不能再当 0 分卡跳过：27 分估 → 24.3，仍远高于 6 分牌。"""
    estimated = _card(0, KNOWN_NAME, KNOWN_SCORE, 2, score_estimated=True)
    weak = _card(1, "弱卡", 6, 3)
    state = LessonState(cards=(estimated, weak), turns_left=3, stamina=20)
    action = _policy(tmp_path).decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.index == 0
    assert action.expected == pytest.approx(KNOWN_SCORE * 0.9)


def test_low_estimated_score_is_not_pushed_below_min_gain(tmp_path: Path) -> None:
    """1 分兜底牌降权后是 0.9：不能因此掉到 min_gain 门槛下被跳过。"""
    estimated = _card(0, "一分卡", 1, 2, score_estimated=True)
    state = LessonState(cards=(estimated,), turns_left=3, stamina=20)
    action = _policy(tmp_path).decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.index == 0


def test_policy_slightly_downweights_estimated_score(tmp_path: Path) -> None:
    """兜底值只轻微降权（×0.9）：27 估 → 24.3，略输真实 25 分；不降权会误选。"""
    estimated = _card(0, KNOWN_NAME, KNOWN_SCORE, 2, score_estimated=True)
    real = _card(1, "真实二十五分", 25, 2)
    state = LessonState(cards=(estimated, real), turns_left=3, stamina=20)
    action = _policy(tmp_path).decide(state)
    assert action.card is not None and action.card.index == 1
    assert _policy(tmp_path).describe()["estimated_score_weight"] == 0.9
