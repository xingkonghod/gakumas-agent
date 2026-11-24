"""F#45 回归：v3.6.1 培育开场二选一「白色效果描述气泡」误点（真机 ep-t31-a）。

现象：v3.6.1（2026-11-24 更新）开场剧情选中选项后，顶部多出一层**白色效果描述**
气泡（「选择并获得特定的P饮料」），旧 4.45 分支取「最上气泡」→ 点到描述层 →
画面不动 → 同屏 10 次停机。旧版（11-22 ep-t3-3）只有两个选项气泡，无描述层。

修复（produce_ui 4.45）：① OCR 带 ">" 箭头的选项（已选中、可确认）优先；
② 否则顶部气泡填充近纯白且下方有橙/深灰选项 → 剔除描述层；③ 其余点最上选项。
颜色分类 ``_bubble_fill_kind`` 走 BGR（与 _checkbox_checked 同口径），不依赖 OCR 语言。

真帧回放（缺 OCR 模型/配置自动 skip，同 A4）：
- ``story_choice_v361_ep_t31_a.png``：ep-t31-a step44（2026-11-24 21:19），三气泡
  （白描述 y690 / 橙选中 y790 带 > / 灰 y890）→ 必须点橙选项，不能点描述层。
- ``story_choice_ep_t3_3_step049.png``：旧版两白气泡 → 仍点最上选项（不被误剔除）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrLine

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ocr_jp.example.yaml"
MODEL_DIR = ROOT / "data" / "models" / "ocr_jp"
FIXTURES = ROOT / "tests" / "fixtures"
V361_FRAME = FIXTURES / "story_choice_v361_ep_t31_a.png"
OLD_FRAME = FIXTURES / "story_choice_ep_t3_3_step049.png"


@dataclass
class FakeDevice:
    clicks: list[tuple[int, int]] = field(default_factory=list)

    def click_force(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))

    def click(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)


def _driver() -> ProduceDriver:
    return ProduceDriver(sleep=lambda _seconds: None)


def _dialogue_and_fast() -> list[OcrLine]:
    return [
        OcrLine("おはようございます、プロデューサー。", 0.9, (76, 980, 457, 28)),
        OcrLine("本日もお願いします。", 0.9, (78, 1019, 250, 27)),
        OcrLine("快进", 0.9, (584, 1187, 81, 28)),
    ]


def _bgr_image(bands: list[tuple[int, int, tuple[int, int, int]]]) -> np.ndarray:
    """bands: (top, bottom, BGR)；背景深灰。"""
    img = np.full((1280, 720, 3), 40, dtype=np.uint8)
    for top, bottom, color in bands:
        img[top:bottom, 45:675] = color
    return img


# ---------------------------------------------------------------- 合成场景
def test_three_bubbles_white_description_skipped_for_orange_choice() -> None:
    """白描述 + 橙选中 + 灰选项（无箭头 OCR）→ 颜色规则剔除描述层，点橙选项。"""
    img = _bgr_image(
        [
            (690, 780, (245, 245, 245)),  # 白描述
            (790, 880, (73, 156, 255)),  # 橙选中（BGR）
            (890, 980, (227, 227, 228)),  # 灰选项（BGR）
        ]
    )
    lines = [
        OcrLine("选择并获得特定的P饮料", 0.9, (70, 690, 590, 90)),
        OcrLine("飲み物を持ってきました", 0.9, (70, 790, 590, 90)),
        OcrLine("慣れてきましたか?", 0.9, (70, 890, 590, 90)),
        *_dialogue_and_fast(),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines, img)
    assert (tick.screen, tick.action) == ("story", "choice"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert 790 <= y <= 880, f"应点橙选项气泡，实际 ({x},{y})"
    assert not (650 <= y <= 760), f"点到白色描述层了 ({x},{y})"


def test_two_white_bubbles_old_layout_keeps_top_choice() -> None:
    """旧版两白气泡（未选中态）→ 不能把最上选项当描述层剔除。"""
    img = _bgr_image(
        [
            (700, 790, (250, 250, 250)),
            (810, 900, (250, 250, 250)),
        ]
    )
    lines = [
        OcrLine("飲み物を持ってきました", 0.9, (70, 700, 590, 90)),
        OcrLine("慣れてきましたか?", 0.9, (70, 810, 590, 90)),
        *_dialogue_and_fast(),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines, img)
    assert (tick.screen, tick.action) == ("story", "choice"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert 700 <= y <= 790, f"应点最上选项，实际 ({x},{y})"


def test_arrow_marked_choice_preferred_without_image() -> None:
    """OCR 读到 ">" 箭头（选中态）→ 无图像也优先点它确认。"""
    lines = [
        OcrLine("选择并获得特定的P饮料", 0.9, (70, 690, 590, 90)),
        OcrLine("飲み物を持ってきました>", 0.9, (70, 790, 590, 90)),
        OcrLine("慣れてきましたか?", 0.9, (70, 890, 590, 90)),
        *_dialogue_and_fast(),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines)
    assert (tick.screen, tick.action) == ("story", "choice"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert 790 <= y <= 880, f"应点带箭头的选中项，实际 ({x},{y})"


def test_pink_vivid_selected_no_arrow_clicks_right_side() -> None:
    """F#46 重点练习屏：选中项粉色（vivid）、>> 未被 OCR 读出 → 靠填充色判选中，点右侧箭头。"""
    img = _bgr_image(
        [
            (690, 780, (130, 60, 230)),  # 粉选中（BGR）
            (790, 880, (227, 227, 228)),  # 灰
            (890, 980, (227, 227, 228)),  # 灰
        ]
    )
    lines = [
        OcrLine("重点练习歌唱", 0.9, (70, 690, 590, 90)),
        OcrLine("重点练习舞蹈", 0.9, (70, 790, 590, 90)),
        OcrLine("重点练习视觉效果", 0.9, (70, 890, 590, 90)),
        *_dialogue_and_fast(),
    ]
    agent = FakeAgent()
    tick = _driver().decide(agent, lines, img)
    assert (tick.screen, tick.action) == ("story", "choice"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert 690 <= y <= 780, f"应点粉选中项，实际 ({x},{y})"
    assert x > 500, f"应点右侧 >> 箭头而非中心，实际 ({x},{y})"


def test_bubble_fill_kind_bgr_classification() -> None:
    """颜色分类口径：BGR 存储，vivid/灰/白/背景。"""
    img = _bgr_image(
        [
            (100, 190, (245, 245, 245)),  # 白
            (200, 290, (73, 156, 255)),  # 橙（BGR）
            (300, 390, (227, 227, 228)),  # 灰（BGR）
        ]
    )
    white = OcrLine("x", 0.9, (70, 100, 590, 90))
    orange = OcrLine("x", 0.9, (70, 200, 590, 90))
    gray = OcrLine("x", 0.9, (70, 300, 590, 90))
    bg = OcrLine("x", 0.9, (70, 500, 590, 90))
    kind = ProduceDriver._bubble_fill_kind
    assert kind(img, white) == "white"
    assert kind(img, orange) == "vivid"
    assert kind(img, gray) == "gray"
    assert kind(img, bg) == "other"
    assert kind(None, white) == "other"


# ---------------------------------------------------------------- 真帧回放
@pytest.fixture(scope="module")
def ocr():
    pytest.importorskip("rapidocr_onnxruntime")
    import cv2  # noqa: F401

    from gkagent.vision.ocr import OcrEngine

    return OcrEngine(config_path=CONFIG)


def _read(ocr, path: Path):
    import cv2

    if not path.is_file():
        pytest.skip(f"缺少 fixture {path.name}")
    image = cv2.imread(str(path))
    assert image is not None
    return image, _driver().read_fast(image)


@pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml")
@pytest.mark.skipif(
    not all((MODEL_DIR / n).is_file() for n in ("det.onnx", "rec.onnx", "keys.txt")),
    reason="缺少日文 OCR 模型",
)
def test_v361_frame_clicks_orange_choice_not_description(ocr) -> None:
    """真机 ep-t31-a step44：三气泡屏必须点橙选项（y790-880），不能点白描述（y690）。"""
    image, lines = _read(ocr, V361_FRAME)
    agent = FakeAgent()
    tick = _driver().decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("story", "choice"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert 60 <= x <= 660, (x, y)
    assert 790 <= y <= 880, f"应点橙选项气泡，实际 ({x},{y})"
    assert not (650 <= y <= 760), f"点到白色描述层了 ({x},{y})"


@pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml")
@pytest.mark.skipif(
    not all((MODEL_DIR / n).is_file() for n in ("det.onnx", "rec.onnx", "keys.txt")),
    reason="缺少日文 OCR 模型",
)
def test_old_frame_still_clicks_top_choice(ocr) -> None:
    """旧版（11-22）两白气泡帧：修复后仍点最上选项，不被颜色规则误剔除。"""
    image, lines = _read(ocr, OLD_FRAME)
    agent = FakeAgent()
    tick = _driver().decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("story", "choice"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert 700 <= y <= 950, f"应点选项气泡，实际 ({x},{y})"


@pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml")
@pytest.mark.skipif(
    not all((MODEL_DIR / n).is_file() for n in ("det.onnx", "rec.onnx", "keys.txt")),
    reason="缺少日文 OCR 模型",
)
def test_v361_focus_choice_clicks_arrow_not_center(ocr) -> None:
    """真机 ep-t31-d step123：重点练习三选一（粉选中、无箭头 OCR）→ 点右侧箭头确认。"""
    image, lines = _read(ocr, FIXTURES / "focus_choice_v361_ep_t31_d.png")
    agent = FakeAgent()
    tick = _driver().decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("story", "choice"), tick.describe()
    x, y = agent.device.clicks[-1]
    assert 690 <= y <= 780, f"应点歌唱选中项，实际 ({x},{y})"
    assert x > 500, f"应点右侧 >> 箭头而非中心（中心只重选），实际 ({x},{y})"