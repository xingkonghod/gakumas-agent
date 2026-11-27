"""日文客户端读屏修复回归（matto 基准 top 缺口；合成行/桩引擎，不需要数据集）。

修复清单（单变量，F#48 日文别名先例）：
- parse_attr_value：ATTR_MAX 2000→9999（H.I.F 属性上限 3200）+ 5 位图标前导数字拆分；
- LESSON_WORDS += 残りターン（日文考试/课程帧不再误判 result-tap）；
- 商店分支日文标题/「終了」别名（Pポイントと交換するものを選んでください）；
- 行动页闸门「行動」/「を選択して」（OCR 偶读「行助」）；
- LessonReader 属性日文别名（ボーカル→歌唱）、纯假名卡名候选。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from gkagent.tasks import produce_ui
from gkagent.tasks.produce_ui import ProduceDriver, parse_attr_value
from gkagent.vision.lesson import LessonReader
from gkagent.vision.ocr import OcrLine


@dataclass
class _Device:
    clicks: list = field(default_factory=list)

    def click(self, x, y):
        self.clicks.append((int(x), int(y)))

    def click_force(self, x, y):
        self.clicks.append((int(x), int(y)))

    def swipe(self, *args):
        pass


@dataclass
class _Agent:
    device: _Device = field(default_factory=_Device)


def _driver():
    return ProduceDriver(ocr=None, sleep=lambda _s: None)


# ---------------------------------------------------------------- parse_attr_value
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2336", 2336),  # matto 00058：旧 ATTR_MAX=2000 拒读
        ("3200", 3200),
        ("11473", 1473),  # 麦克风图标读成前导 1（matto 00058 vo 框）
        ("312/1000", 312),  # 旧行为不变
        ("312 1000", 312),
        ("1207", 1207),
        ("", None),
        ("9", None),  # 单字符噪声
    ],
)
def test_parse_attr_value_ja_gaps(text: str, expected) -> None:
    assert parse_attr_value(text) == expected


def test_attr_max_covers_matto_caps() -> None:
    assert produce_ui.ATTR_MAX >= 3200


# ---------------------------------------------------------------- 屏幕路由别名
def test_lesson_words_include_ja_turns() -> None:
    assert "残りターン" in produce_ui.LESSON_WORDS


def test_ja_exam_frame_routes_to_card_policy() -> None:
    """matto r3-00074：残りターン + SKIP → lesson/card-policy（旧落 result-tap 空转）。"""
    lines = [
        OcrLine("残りターン", 0.96, (4, 3, 84, 26)),
        OcrLine("9", 0.99, (35, 55, 24, 26)),
        OcrLine("ボーカル", 0.99, (75, 38, 71, 25)),
        OcrLine("2805%", 0.99, (66, 56, 105, 36)),
        OcrLine("SKIP", 0.99, (476, 589, 43, 23)),
    ]
    tick = _driver().decide(_Agent(), lines)
    assert (tick.screen, tick.action) == ("lesson", "card-policy"), tick.describe()


def test_ja_shop_title_and_exit_button() -> None:
    """matto r3-00001：日文商店标题 + 「終了」→ shop/exit（旧中文关键词落空）。"""
    lines = [
        OcrLine("Pポイントと交換するものを選んでください", 0.99, (90, 225, 360, 24)),
        OcrLine("強化", 0.9, (92, 712, 53, 28)),
        OcrLine("削除", 0.97, (330, 711, 55, 32)),
        OcrLine("交換する", 0.99, (239, 799, 91, 29)),
        OcrLine("×終了", 0.92, (438, 795, 90, 38)),
    ]
    agent = _Agent()
    tick = _driver().decide(agent, lines)
    assert (tick.screen, tick.action) == ("shop", "exit"), tick.describe()
    assert agent.device.clicks, "商店退出没有点任何东西"
    x, y = agent.device.clicks[-1]
    assert 430 <= x <= 540 and 780 <= y <= 840, (x, y)  # 「×終了」行中心


def test_cn_shop_still_exits() -> None:
    """对照组：中文商店标题 + 结束仍走 shop/exit（逐位不变）。"""
    lines = [
        OcrLine("用P点数进行兑换", 0.99, (200, 300, 320, 30)),
        OcrLine("结束", 0.99, (600, 1160, 80, 36)),
    ]
    tick = _driver().decide(_Agent(), lines)
    assert (tick.screen, tick.action) == ("shop", "exit"), tick.describe()


@pytest.mark.parametrize(
    "text",
    ["行動を選択してください", "行助を選択してくださ", "请选择行动", "授课"],
)
def test_action_page_gate_accepts_ja(text: str) -> None:
    assert produce_ui._might_show_attributes(text) is True


def test_action_title_words_include_ja() -> None:
    assert "行動" in produce_ui._ATTR_ACTION_TITLE_WORDS
    assert "を選択して" in produce_ui._ATTR_ACTION_TITLE_WORDS


# ---------------------------------------------------------------- LessonReader 别名
class _StubEngine:
    def __init__(self, text: str):
        self._text = text

    def line(self, image, roi, **kwargs):
        return OcrLine(self._text, 0.99, tuple(roi))


def _reader_with(text: str) -> LessonReader:
    reader = LessonReader.__new__(LessonReader)  # 跳过卡表/模型加载，只测读屏别名
    reader.engine = _StubEngine(text)
    return reader


@pytest.mark.parametrize(
    ("ja", "canonical"),
    [("ボーカル", "歌唱"), ("ダンス", "舞蹈"), ("ビジュアル", "视觉"), ("歌唱", "歌唱")],
)
def test_attribute_ja_aliases_normalize_to_cn(ja: str, canonical: str) -> None:
    reader = _reader_with(ja)
    image = np.zeros((1280, 720, 3), dtype=np.uint8)
    assert reader._attribute(image, (98, 50, 82, 36)) == canonical


def test_name_lines_accepts_pure_kana_card_names() -> None:
    """matto 手牌 イメトレ（纯片假名）旧过滤只认汉字 → 整张漏读。"""
    reader = _reader_with("")
    image = np.zeros((1280, 720, 3), dtype=np.uint8)
    lines = [
        OcrLine("イメトレ", 0.98, (239, 1080, 63, 19)),
        OcrLine("気まぐれハート", 0.93, (46, 1075, 122, 24)),
        OcrLine("123", 0.99, (300, 1080, 30, 20)),  # 数字行仍排除
    ]
    found = reader._name_lines(image, lines)
    names = {name for name, _box in found}
    assert "イメトレ" in names, names
    assert "気まぐれハート" in names, names
    assert "123" not in names, names
