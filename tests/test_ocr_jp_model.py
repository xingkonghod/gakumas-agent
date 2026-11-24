"""日文 OCR 模型真图回归（A1：OCR 换日文模型）。

模型由 ``scripts/download_ocr_models.py`` 下载到 ``data/models/ocr_jp/``（gitignore），
配置模板 ``configs/ocr_jp.example.yaml``；截图用**稳定归档 fixture**
``tests/fixtures/event_ep_t3_4_drink_choice.png``（2026-11-22 真机 ep-t3-4 的日文外出
饮料选项帧，中文模型只能读出 飲物持/？/、。 碎片）。

2026-11-24 修复：原用 ``data/auto/step_025.png`` 是**真机跑局轮转覆写**的活帧，跑局后
被别的屏覆盖 → 4 条测试假红（与 step_047 已知 skip 同类）。改指归档 fixture 后不再受跑局影响。

模型或截图缺失时整套 skip（干净 checkout / CI 不会因为没下模型而红）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ocr_jp.example.yaml"
MODEL_DIR = ROOT / "data" / "models" / "ocr_jp"
FRAME = ROOT / "tests" / "fixtures" / "event_ep_t3_4_drink_choice.png"

pytestmark = [
    pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp.example.yaml"),
    pytest.mark.skipif(
        not all((MODEL_DIR / name).is_file() for name in ("det.onnx", "rec.onnx", "keys.txt")),
        reason="缺少日文 OCR 模型（先跑 scripts/download_ocr_models.py）",
    ),
    pytest.mark.skipif(not FRAME.is_file(), reason="缺少归档帧 event_ep_t3_4_drink_choice.png"),
]


@pytest.fixture(scope="module")
def engine():
    pytest.importorskip("rapidocr_onnxruntime")
    from gkagent.vision.ocr import OcrEngine

    return OcrEngine(config_path=CONFIG)


@pytest.fixture(scope="module")
def frame_text(engine) -> str:
    import cv2

    image = cv2.imread(str(FRAME))
    assert image is not None
    lines = engine.read(image)
    return " ".join(line.text for line in lines)


def test_step_025_reads_complete_japanese(frame_text: str) -> None:
    """DoD：同一张 step_025.png 能读出三个饮料名与完整对白。"""
    for word in ("ヨーグルトパフェ", "つくねハンバーグ", "ドリンクバー"):
        assert word in frame_text, f"缺 {word}；OCR 全文：{frame_text}"


def test_step_025_reads_full_dialogue(frame_text: str) -> None:
    """中文模型只读得出「、。」这类碎片；日文模型要读出整句对白。"""
    assert "そこまで真剣だと慰労を超えますが" in frame_text
    assert "倉本さんのお気に入りは" in frame_text


def test_step_025_still_reads_chinese_ui(frame_text: str) -> None:
    """多语言模型不能为了日文把中文 UI 读崩（行动页/课程/考试分支靠中文关键词）。"""
    for word in ("外出", "审查基准", "快进"):
        assert word in frame_text, f"缺中文 UI 文本 {word}；OCR 全文：{frame_text}"


def test_step_025_event_choice_not_fast_forward(engine) -> None:
    """真实帧走 ProduceDriver：日文恢复后必须选事件选项，不能拿去点「快进」。

    这就是 F#41/#42 类"日文读不到 → 只能点快进 → 剧情/事件原地循环"的回归：
    中文模型下这帧不会有 3 条可读选项，decide 会退回"快进"；日文模型下应点选项行。
    """
    import cv2

    from gkagent.tasks.produce_ui import ProduceDriver

    class _FakeDevice:
        def __init__(self) -> None:
            self.clicks: list[tuple[int, int]] = []

        def click(self, x: int, y: int) -> None:
            self.clicks.append((x, y))

        def swipe(self, *_args) -> None:
            return None

    class _FakeAgent:
        def __init__(self) -> None:
            self.device = _FakeDevice()

    image = cv2.imread(str(FRAME))
    assert image is not None
    driver = ProduceDriver(ocr=engine, sleep=lambda _seconds: None)
    lines = driver.read_fast(image)
    agent = _FakeAgent()
    result = driver.decide(agent, lines)

    assert result.ok, result
    assert result.screen in ("event-choice", "story"), result
    assert result.action in ("last-row", "choice", "confirm"), result
    assert agent.device.clicks, "decide 没有点任何选项"
    x, y = agent.device.clicks[-1]
    assert x == 360
    # 选项区在屏幕中部（650–1000）；「快进」在 y≈1189，点它就说明又退回旧行为了。
    assert 650 <= y <= 1000, f"点到了 ({x},{y})，不是选项行；result={result}"
