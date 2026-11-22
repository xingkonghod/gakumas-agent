"""课程读屏 + 出牌策略 + buff 知识库的离线单测。

真机帧测试会用 ``data/live_lesson.png`` 等实拍图，文件缺失或没装 rapidocr 时自动跳过。
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

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


def _card(
    index: int, name: str, score, cost, *, buff=False, text="", highlight=False
) -> LessonCard:
    return LessonCard(
        index=index,
        box=(index * 200, 900, 190, 232),
        point=(index * 200 + 95, 1000),
        name=name,
        score=score,
        cost=cost,
        buff=buff,
        text=text,
        highlight=highlight,
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


def test_policy_never_skips_worthless_cards_when_affordable() -> None:
    """2026-11-21 用户规则：读不到/分数低不是跳过理由，还有付得起的牌就硬打一张。"""
    policy = LessonPolicy()
    state = _state(
        [_card(0, "元气", 0, 2), _card(1, "护盾", 0, 3)],
        turns_left=3,
        stamina=20,
    )
    action = policy.decide(state)
    assert action.kind == "card"


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


def test_policy_buffs_early_even_with_high_score_card() -> None:
    """用户打法：前几个回合先攒倍率。150 分的牌在剩余 5 回合时也压不过集中。"""
    policy = LessonPolicy()
    state = _state(
        [
            _card(0, "集中", 0, 3, buff=True, text="集中+3"),
            _card(1, "高分牌", 150, 5, text="打分+15"),
        ],
        turns_left=5,
        stamina=25,
    )
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "集中"


def test_policy_last_turn_takes_score_over_buff() -> None:
    """最后一回合铺 buff 没用，必须打分数牌。"""
    policy = LessonPolicy()
    state = _state(
        [
            _card(0, "集中", 0, 2, buff=True, text="集中+3"),
            _card(1, "高分牌", 25, 3, text="打分+25"),
        ],
        turns_left=1,
        stamina=20,
    )
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "高分牌"


def test_policy_highlighted_card_wins_over_higher_score() -> None:
    """游戏金框/推荐 = 先铺倍率的提示：高亮牌无条件优先。"""
    policy = LessonPolicy()
    state = _state(
        [
            _card(0, "普通高分", 80, 4, text="打分+8"),
            _card(1, "高亮牌", 25, 4, text="好调+2", highlight=True),
        ],
        turns_left=5,
        stamina=20,
    )
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "高亮牌"


def test_policy_buff_yields_when_unaffordable() -> None:
    """没体力铺 buff 时让位给付得起的分数牌（不能因为 buff 优先就不出牌）。"""
    policy = LessonPolicy()
    state = _state(
        [
            _card(0, "贵集中", 0, 8, buff=True, text="集中+3"),
            _card(1, "分数牌", 25, 3, text="打分+25"),
        ],
        turns_left=5,
        stamina=5,
    )
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "分数牌"


def test_gold_frame_detects_highlighted_hand_card() -> None:
    """手牌金框检测：金色竖边 → 高亮；纯色卡面 → 不高亮。"""
    import numpy as np

    from gkagent.vision.lesson import _gold_frame

    image = np.full((1280, 720, 3), 40, dtype=np.uint8)
    rect = (100, 900, 190, 232)
    assert _gold_frame(image, rect) is False
    image[900:1132, 96:102] = (20, 170, 240)  # BGR 金色（左描边）
    image[900:1132, 288:294] = (20, 170, 240)  # 右描边
    assert _gold_frame(image, rect) is True


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
    """课程帧：右上角是**培育属性值**，课程分按开课基线换算；圆环是"还差分"。

    F#42 的根因之一：旧读法把右上属性值当课程分、把圆环"还差 30 分"当 CLEAR 线，
    于是"分数 90 ≥ CLEAR 30"被判断成已经 PERFECT，搜索一路建议 SKIP。
    """
    cv2, reader = _reader()
    image = cv2.imread(str(FRAMES / "lesson_now.png"))
    state = reader.read(image, kind="lesson")
    assert state.turns_left == 1
    assert state.stamina == 25
    # 右上角读到的原始属性值 124；这是本课第一帧 → 课程分 0。
    assert state.attr == 124
    assert state.score == 0
    # 正中圆环「PERFECT截止 21」= 还差 21 分到满分线 → 满分线 = 已得分(0) + 21。
    assert state.goal == "perfect"
    assert state.perfect == 21
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


def test_policy_plays_cheapest_when_scores_unreadable() -> None:
    """分数没读到 ≠ 牌没用：跳课不涨属性，打最便宜的保成长。"""
    policy = LessonPolicy()
    state = _state(
        [_card(0, "聊天时间", None, 6), _card(1, "表现的基础", None, 0)],
        turns_left=3,
        stamina=20,
    )
    action = policy.decide(state)
    assert action.kind == "card"
    assert action.card is not None and action.card.name == "表现的基础"


def test_policy_only_skips_when_truly_no_affordable_card() -> None:
    """只有真没体力（所有牌都付不起）才允许 SKIP；分数为 0 也要打。"""
    policy = LessonPolicy()
    # 还有体力：硬打
    assert policy.decide(
        _state([_card(0, "元气", 0, 2)], turns_left=3, stamina=20)
    ).kind == "card"
    # 真付不起：SKIP
    action = policy.decide(_state([_card(0, "元气", 0, 2)], turns_left=3, stamina=1))
    assert action.kind == "skip"


def test_card_table_gives_exact_cost() -> None:
    """费用来自 gakumasu-diff 属性表（按 ID 对齐），不再靠 OCR。"""
    from gkagent.data.card_table import CardTable

    table = CardTable()
    if not len(table):
        import pytest

        pytest.skip("缺少 data/knowledge/card_table.json")
    assert table.cost("魅力的基础") == 4
    assert table.cost("聊天时间") == 6
    assert table.cost("表现的基础") == 0
    meta = table.meta("元气的问候")
    # 卡面写「体力消耗 4」；YAML 的 stamina=0、forceStamina=4，费用取两者较大值。
    assert meta is not None and meta.cost == 4
    assert CardTable.looks_conditional("好调状态的时候，可以使用")
    assert not CardTable.looks_conditional("打分+9")


def test_reader_cost_comes_from_table() -> None:
    cv2, reader = _reader()
    from gkagent.data.card_table import CardTable

    table = CardTable()
    if not len(table):
        import pytest

        pytest.skip("缺少 card_table.json")
    reader.table = table
    image = cv2.imread(str(FRAMES / "exam_c.png"))
    cards = {card.name: card for card in reader.read(image, kind="audition").cards}
    assert cards["猛烈地"].cost == table.cost("猛烈地")


# --------------------------------------------------------------------- 课程 HUD 换算（F#42）
class _FakeHudOcr:
    """只回答课程 HUD 固定框的假 OCR：回合/属性值/体力/圆环还差分/圆环档位。

    手牌区一律空（``read`` 返回 []），这样不用真图也能测 ``LessonReader.read``
    的课程分换算（真图回归在 ``tests/test_lesson_play_f42.py``）。
    """

    _CENTERS: ClassVar[dict[tuple[int, int], str]] = {
        (370, 108): "goal",  # 圆环标签 (295, 96, 150, 24)
        (104, 85): "turns",  # (58, 56, 92, 58)
        (646, 61): "attr",  # 右上属性值 (588, 34, 116, 54)
        (602, 183): "stamina",  # (556, 156, 92, 54)
        (360, 140): "gauge",  # 圆环数字 (300, 105, 120, 70)
    }

    def __init__(self, **values: str) -> None:
        self.values = dict(values)

    def read(self, image, roi=None):  # 手牌名整块 OCR：不需要
        return []

    def line(self, image, roi, *, digits_only: bool = False):
        from gkagent.vision.ocr import OcrLine

        x, y, w, h = (int(value) for value in roi)
        cx, cy = x + w // 2, y + h // 2
        key = next(
            (
                name
                for (ex, ey), name in self._CENTERS.items()
                if abs(cx - ex) <= 6 and abs(cy - ey) <= 6
            ),
            None,
        )
        return OcrLine(self.values.get(key, "") if key else "", 0.9, roi)


def _hud_reader(**values: str):
    from gkagent.vision.lesson import LessonReader

    return LessonReader(_FakeHudOcr(**values))


def _read_hud(reader, **values: str):
    import numpy as np

    reader.engine.values.update(values)
    return reader.read(np.zeros((1280, 720, 3), dtype=np.uint8), kind="lesson")


def test_lesson_hud_maps_attr_to_relative_score_and_clear_line() -> None:
    """课程分 = 右上属性值 − 开课属性值；CLEAR 线 = 已得分 + 圆环"还差"分。"""
    reader = _hud_reader(
        turns="5", attr="162", gauge="30", stamina="36", goal="CLEAR截止"
    )
    state = _read_hud(reader)
    assert (state.goal, state.attr, state.score) == ("clear", 162, 0)
    assert (state.gauge, state.perfect) == (30, 60)

    # 打出一刀 +28 分：属性 190、还差 2 分 → 课程分 28，过关线还是 30。
    state = _read_hud(reader, turns="4", attr="190", gauge="2")
    assert (state.score, state.gauge, state.perfect) == (28, 30, 60)

    # 过关后圆环换成 PERFECT：属性 214、还差 8 分 → 满分线 = 52 + 8 = 60。
    state = _read_hud(reader, turns="3", attr="214", gauge="8", goal="PERFECT截止")
    assert state.goal == "perfect"
    assert (state.score, state.perfect) == (52, 60)
    assert state.gauge == 30  # 满分线的一半（普通/SP 课 CLEAR = 满分/2）


def test_lesson_hud_rebases_score_on_new_lesson() -> None:
    """新开一节课：reset_lesson() 后课程分从 0 重新算（属性基线跟着换）。"""
    reader = _hud_reader(
        turns="5", attr="162", gauge="30", stamina="36", goal="CLEAR截止"
    )
    assert _read_hud(reader).score == 0
    assert _read_hud(reader, attr="190", gauge="2").score == 28
    reader.reset_lesson()
    state = _read_hud(reader, turns="6", attr="500", gauge="40", goal="CLEAR截止")
    assert (state.attr, state.score, state.gauge) == (500, 0, 40)


def test_lesson_hud_keeps_last_goal_when_label_unreadable() -> None:
    """档位标签在动画帧读不到：沿用本课最近一次读到的档位，不瞎猜。"""
    reader = _hud_reader(
        turns="3", attr="162", gauge="30", stamina="36", goal="CLEAR截止"
    )
    assert _read_hud(reader).goal == "clear"
    state = _read_hud(reader, attr="170", gauge="22", goal="")
    assert (state.goal, state.score, state.gauge) == ("clear", 8, 30)
    state = _read_hud(reader, attr="200", gauge="10", goal="PERFECT截止")
    assert (state.goal, state.score, state.perfect) == ("perfect", 38, 48)


def test_perfect_line_table_covers_oikomi_tiers() -> None:
    """满分线查档位表：普通/SP 课 = 2×过关线；追い込み 90→360、165→600。"""
    from gkagent.vision.lesson import _perfect_line

    assert _perfect_line(30) == 60
    assert _perfect_line(40) == 80
    assert _perfect_line(90) == 360
    assert _perfect_line(165) == 600
