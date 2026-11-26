"""A4 真机截图回放：六类关键屏（WORKPLAN A4 DoD）+ 一个回放抓出来的生产 bug 回归。

和 ``test_produce_ui*.py`` 的合成 OCR 行不同，这里跑的是**真像素 → 真 OCR → 生产判定**：
fixture 全部是 2026-11-10~22 的真机截图（720x1280，复制自 ``data/``），
OCR 走 ``configs/ocr_jp.example.yaml``（官方 PP-OCRv6 多语言模型，A1）。
模型/配置缺失时整套 skip（干净 checkout 不会红）。

覆盖矩阵（WORKPLAN A4 DoD「至少覆盖」）：

| 屏幕 | fixture | 真机来源 |
|---|---|---|
| 日文剧情二选一（F#41） | ``story_choice_ep_t3_3_step049.png`` | ep-t3-3 step49（11-22 02:13） |
| 课程 buff 场景（F#42） | ``lesson_ep_t3_4_step001.png`` | ep-t3-4 step1（11-22 02:22，A2 已归档） |
| 结果页（F#43 同屏型） | ``result_ep_t3_4_step004.png`` | ep-t3-4 step4（11-22 02:22） |
| 外出事件 | ``outing_choice_ep_full1_step049.png`` | ep-full1 step49（11-19 18:41） |
| 考试浮层（F#17/F#32） | ``exam_card_overlay_20261115.png`` | 11-15 17:17 考试实拍 |
| 回合结束确认框（F#8/F#36） | ⚠️ 无真机帧，见下 | — |

**回合结束确认框的真机帧已经不存在**：``step_NNN.png`` 是轮转覆盖的，含该弹窗的
旧局（ep-cplus11 / ep-finish3/4/5 / ep-exp4）截图已被后续 ep-t3 跑局覆盖。
2026-11-22 A4 用 ``scripts/scan_frames.py`` 扫了 1352 张归档截图
（data/auto step+fail 487、data/manual/arun/bench/video/ssr 511、data 根目录 354）
+ data/bench 26，**0 帧**命中「结束回合 / 尚可使用技能卡」。
所以该分支用「真机课程帧的 OCR 行 + FAILURES #36 记录的真实弹窗文案」回放；
同 UI 组件的真机弹窗（ep-t3-4 step19「快进确认」）另有一条真像素回放。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ocr_jp.example.yaml"
MODEL_DIR = ROOT / "data" / "models" / "ocr_jp"
FIXTURES = ROOT / "tests" / "fixtures"

STORY_FRAME = FIXTURES / "story_choice_ep_t3_3_step049.png"
LESSON_FRAME = FIXTURES / "lesson_ep_t3_4_step001.png"
RESULT_FRAME = FIXTURES / "result_ep_t3_4_step004.png"
OUTING_FRAME = FIXTURES / "outing_choice_ep_full1_step049.png"
EXAM_FRAME = FIXTURES / "exam_card_overlay_20261115.png"
DIALOG_FRAME = FIXTURES / "confirm_dialog_ep_t3_4_step019.png"
DRINK_FRAME = FIXTURES / "drink_limit_20261114.png"

pytestmark = [
    pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml"),
    pytest.mark.skipif(
        not all((MODEL_DIR / name).is_file() for name in ("det.onnx", "rec.onnx", "keys.txt")),
        reason="缺少日文 OCR 模型（先跑 scripts/download_ocr_models.py）",
    ),
]


@dataclass
class FakeDevice:
    clicks: list[tuple[int, int]] = field(default_factory=list)
    swipes: list[tuple[int, int, int, int]] = field(default_factory=list)

    def click_force(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))

    def click(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.swipes.append((int(x1), int(y1), int(x2), int(y2)))


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)


@pytest.fixture(scope="module")
def ocr():
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2  # noqa: F401 - 确认 cv2 可用

    from gkagent.vision.ocr import OcrEngine

    return OcrEngine(config_path=CONFIG)


def _read(ocr, path: Path):
    """真机帧 → 生产快速读屏的 ``(image, lines)``；缺 fixture 时 skip。"""
    import cv2

    if not path.is_file():
        pytest.skip(f"缺少 fixture {path.name}")
    image = cv2.imread(str(path))
    assert image is not None
    driver = _driver(ocr)
    return image, driver.read_fast(image)


def _driver(ocr=None):
    from gkagent.tasks.produce_ui import ProduceDriver

    return ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)


# ---------------------------------------------------------------- 1. 日文剧情二选一
def test_japanese_story_choice_reads_options_and_picks_bubble(ocr) -> None:
    """F#41：日文剧情二选一要读得出两条假名选项，并点**选项气泡**而不是右下「快进」。

    旧中文模型只读得出 ``飲物持``/``？`` 碎片，story 分支永远先点「快进」→ 原地循环。
    """
    image, lines = _read(ocr, STORY_FRAME)
    text = _driver().text_of(lines)
    assert "飲み物を持ってきました" in text, text
    assert "慣れてきましたか" in text, text

    driver = _driver(ocr)
    agent = FakeAgent()
    tick = driver.decide(agent, lines, image)
    assert tick.ok, tick.describe()
    assert (tick.screen, tick.action) == ("story", "choice"), tick.describe()
    assert agent.device.clicks, "故事选项屏没有点任何东西"
    x, y = agent.device.clicks[-1]
    # 第一条气泡（「飲み物を持ってきました」）在屏幕中部；「快进」在右下 y≈1189。
    assert 60 <= x <= 660, (x, y)
    assert 700 <= y <= 950, f"应点选项气泡，实际 ({x},{y})"
    assert abs(y - 1189) > 100, "又点回右下「快进」了（F#41 原地循环）"


def test_japanese_story_choice_never_clicks_fast_forward(ocr) -> None:
    """同一屏连续决策也不能落到「快进」按钮上（旧实现每步都点右下）。"""
    image, lines = _read(ocr, STORY_FRAME)
    driver = _driver(ocr)
    agent = FakeAgent()
    ticks = [driver.decide(agent, lines, image) for _ in range(3)]
    assert all(tick.screen == "story" for tick in ticks), [t.describe() for t in ticks]
    assert all(tick.action == "choice" for tick in ticks), [t.describe() for t in ticks]
    assert all(y < 1100 for _x, y in agent.device.clicks), agent.device.clicks


# ---------------------------------------------------------------- 2. 课程 buff 场景
def test_lesson_buff_frame_defers_to_policy_then_plays_scoring_card(ocr, tmp_path: Path) -> None:
    """F#42：课程帧 → decide 交给出牌策略（不自己点）→ 策略必须打正分牌、不选 buff。"""
    image, lines = _read(ocr, LESSON_FRAME)
    text = _driver().text_of(lines)
    assert "剩余回合数" in text and "CLEAR截止" in text, text

    driver = _driver(ocr)
    agent = FakeAgent()
    tick = driver.decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("lesson", "card-policy"), tick.describe()
    assert agent.device.clicks == [], "课程帧应该交给 LessonPolicy，不应该在 UI 层乱点"

    from gkagent.policy.lesson import LessonPolicy
    from gkagent.vision.lesson import LessonReader

    reader = LessonReader(ocr)
    reader.reset_lesson()
    state = reader.read(image, kind="lesson")
    names = {card.name for card in state.cards}
    assert {"魅力的基础", "表情的基础", "轻快步伐"} <= names, names

    policy = LessonPolicy(params_path=tmp_path / "missing.json", engine="expectimax")
    action = policy.decide(state)
    assert action.kind == "card", action.reason
    assert action.card is not None and action.card.name == "魅力的基础"
    assert action.card.total_score > 0
    assert action.card.name != "表情的基础", "又选了不产生课程分的 buff 牌（F#42）"


# ---------------------------------------------------------------- 3. 结果页
def test_result_page_after_three_gains_looks_for_next_button(ocr) -> None:
    """结果页（「上升了 N!」+ 属性条）：先点中央推进，第 3 次起按 A3 找「下一步」按钮。

    该屏在旧日志里被写成「结果页空转」；真机帧真实动作是 result-tap（点中央继续），
    第 3 次起 ``action`` 切成 ``next``（本帧没有按钮文字，所以仍点中央但计数不归零）。
    """
    image, lines = _read(ocr, RESULT_FRAME)
    text = _driver().text_of(lines)
    assert "上升了0" in text, text

    driver = _driver(ocr)
    agent = FakeAgent()
    first = driver.decide(agent, lines, image)
    assert (first.screen, first.action) == ("result-tap", "gain"), first.describe()
    assert agent.device.clicks[-1] == (360, 1000)

    driver.decide(agent, lines, image)
    third = driver.decide(agent, lines, image)
    assert (third.screen, third.action) == ("result-tap", "next"), third.describe()
    assert driver.gain_waits == 3
    assert set(agent.device.clicks) == {(360, 1000)}, agent.device.clicks


# ---------------------------------------------------------------- 4. 外出事件
def test_outing_event_choice_is_not_gain_and_confirms(ocr) -> None:
    """外出三选一：判成 ``event-choice`` 点最后一行并两步确认，负 P 费不能当飘字。"""
    image, lines = _read(ocr, OUTING_FRAME)
    text = _driver().text_of(lines)
    assert "どんな息抜きを提案しますか" in text, text

    driver = _driver(ocr)
    agent = FakeAgent()
    first = driver.decide(agent, lines, image)
    assert (first.screen, first.action) == ("event-choice", "last-row"), first.describe()
    x, y = agent.device.clicks[-1]
    assert x == 360 and 850 <= y <= 1000, f"应点最后一行选项，实际 ({x},{y})"

    second = driver.decide(agent, lines, image)
    assert (second.screen, second.action) == ("event-choice", "confirm"), second.describe()
    assert agent.device.clicks[-1] == agent.device.clicks[-2]


# ---------------------------------------------------------------- 5. 考试浮层
def test_exam_card_overlay_is_exam_mode_and_detail_open(ocr) -> None:
    """考试浮层：识别成考试（F#17 禁跳）+ 卡片详情浮层（F#32 考试文案）+ 手牌可读。"""
    image, lines = _read(ocr, EXAM_FRAME)
    text = _driver().text_of(lines)
    assert "考试·舞台中仅限1次" in text, text
    assert "1st" in text and "2nd" in text, text

    driver = _driver(ocr)
    assert driver.exam_mode(image, lines) is True
    assert driver.card_detail_open(image) is True
    # 浮层顶部卡名（F#32：考试浮层文案是「得分+/仅限1次」，旧规则判不出来）
    assert driver.card_detail_name(image) == "在我发现的世界"

    agent = FakeAgent()
    tick = driver.decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("lesson", "card-policy"), tick.describe()
    assert agent.device.clicks == []

    from gkagent.tasks.produce_ui import lesson_stamina_gate
    from gkagent.vision.lesson import LessonReader

    state = LessonReader(ocr).read(image, kind="audition")
    assert state.kind == "audition"
    assert "在我发现的世界" in {card.name for card in state.cards}, [c.name for c in state.cards]
    # F#17：考试里体力 0 也**永远不 SKIP**（课程侧同一状态下会 SKIP）。
    zero_stamina = replace(state, stamina=0)
    assert lesson_stamina_gate(zero_stamina, stamina=0, exam=True) is None
    lesson_gate = lesson_stamina_gate(zero_stamina, stamina=0, exam=False)
    assert lesson_gate is not None, "对照组：课程侧体力 0 必须 SKIP"


# ---------------------------------------------------------------- 6. 回合结束确认框
def test_turn_end_confirm_dialog_on_real_lesson_frame_clicks_yes(ocr) -> None:
    """F#8/F#36 回合结束确认框：必须在「确定」通用匹配 / 课程分支之前点固定「是」。

    ⚠️ 真机帧已在跑局轮转里被覆盖（见模块 docstring 的扫描证据）。这里用真机课程帧
    的 OCR 行（真背景+真课程文字）加上 FAILURES #36 记录的真实弹窗文案回放：
    弹窗出现时课程文字（SKIP/剩余回合数）还在，必须优先点「是」而不是点心 SKIP/课程卡。
    """
    from gkagent.tasks.produce_ui import TURN_END_YES
    from gkagent.vision.ocr import OcrLine

    image, lesson_lines = _read(ocr, LESSON_FRAME)
    dialog_lines = [
        OcrLine("回合结束", 0.95, (250, 470, 220, 44)),
        OcrLine("尚可使用技能卡", 0.95, (200, 540, 320, 36)),
        OcrLine("确定要结束回合吗？", 0.95, (180, 600, 360, 36)),
        OcrLine("下次起不再显示", 0.95, (250, 680, 220, 28)),
        OcrLine("否", 0.95, (170, 1170, 60, 40)),
        OcrLine("是", 0.95, (490, 1170, 60, 40)),
    ]
    driver = _driver(ocr)
    agent = FakeAgent()
    tick = driver.decide(agent, [*lesson_lines, *dialog_lines], image)
    assert (tick.screen, tick.action) == ("dialog", "end-turn-yes"), tick.describe()
    assert agent.device.clicks[-1] == TURN_END_YES


# ---------------------------------------------------------------- 7. 确认弹窗（同 UI 组件真机帧）
def test_real_confirm_dialog_frame_clicks_ok_button(ocr) -> None:
    """真机确认弹窗（ep-t3-4 step19「快进确认」）：点 OCR 读到的「确定」按钮中心。"""
    image, lines = _read(ocr, DIALOG_FRAME)
    text = _driver().text_of(lines)
    assert "快进确认" in text and "是否快进" in text, text

    driver = _driver(ocr)
    agent = FakeAgent()
    tick = driver.decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("dialog", "confirm"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert 400 <= x <= 660 and 1100 <= y <= 1230, f"应点右侧「确定」按钮，实际 ({x},{y})"


# ---------------------------------------------------------------- 8. 回放抓出的生产 bug
def test_drink_limit_dialog_checks_checkbox_row(ocr) -> None:
    """持有上限「请选择保留的 3 瓶饮料」：按勾选框列找到未勾选行并补勾。

    这条是 A4 回放**抓出来的生产 bug**：``_checkbox_bands`` 漏了 ``@staticmethod``，
    真机带上 image 走到这个分支会 ``TypeError: takes 1 positional argument but 2
    were given``（合成单测不传 image，所以一直没红）。修复后本帧必须点勾选框列 x=632。
    """
    image, lines = _read(ocr, DRINK_FRAME)
    text = _driver().text_of(lines)
    assert "持有数量已达上限" in text and "还可选择2个" in text, text

    driver = _driver(ocr)
    bands = driver._checkbox_bands(image)
    assert bands, "勾选框列没扫出任何行"

    agent = FakeAgent()
    tick = driver.decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("drink-keep", "check-row"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert x == 632, f"应点勾选框列，实际 ({x},{y})"
    assert any(top <= y <= bottom for top, bottom in bands), (y, bands)
    assert agent.device.swipes == [], "勾完一行就应返回，不该先滚动"


def test_drink_limit_ocr_misses_need_still_checks_row(ocr) -> None:
    """F#48（真机 ep-t31-i）：OCR 漏读「还可选择N」/「保留」时仍按勾选框补勾。

    旧逻辑 ``need`` 只信 OCR「还可选择N」：漏读 → need=0 → 跳过补勾直接点禁用态
    「保留」(360,1166) → 空转 tap-lost 停局。修复：有图且读到「手持的饮料」标题就扫描
    补勾。这里用真夹具图 + 模拟 OCR 漏读（删掉「还可选择」「保留」行）验证。
    """
    image, lines = _read(ocr, DRINK_FRAME)
    filtered = [
        ln for ln in lines
        if "还可选择" not in ln.text and ln.text.strip() != "保留"
    ]
    text = _driver().text_of(filtered)
    assert "持有上限" in text, text
    assert "还可选择" not in text, text
    assert "手持的饮料" in text, text

    driver = _driver(ocr)
    agent = FakeAgent()
    tick = driver.decide(agent, filtered, image)
    assert (tick.screen, tick.action) == ("drink-keep", "check-row"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert x == 632, f"应点勾选框列补勾，实际 ({x},{y})"
    # F#51：获得段灰勾行可点且计入保留数 → 扫描起点取两段标题较上者，
    # 补勾可能落在获得段（y≈525）或手持段；只要落在勾选框 band 内即正确。
    assert y > 440, f"应点获得/手持段未计入行（获得标题+20 起），实际 y={y}"
    assert agent.device.swipes == []
