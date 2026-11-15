"""OCR 提速回归：语义缓存、固定小框探针、full fallback 默认关闭。

这些测试不碰真机：用 stub 引擎控制每个 ROI 返回的文本，验证
1) 单行缓存命中后不再调用识别模型；
2) 三维快路径成功时不跑整图 OCR，默认也不允许整图兜底；
3) 行动页探针能根据固定小框文字正确判定；
4) 语义指纹相同（OCR 文本归一化后相同）时整屏结果复用。
"""

from __future__ import annotations

import numpy as np

from gkagent.tasks import produce_ui
from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrEngine, OcrLine
from gkagent.vision.ocr_cache import (
    LineFingerprintCache,
    SemanticScreenCache,
    normalize_ocr_text,
    semantic_fingerprint,
)


# ---------------------------------------------------------------- stubs
class _FakeMainEngine:
    """只给 OcrEngine 占位；line 缓存测试不会走 read。"""

    def __call__(self, _image):
        return [], 0.0


class _CountingLineEngine:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, _crop):
        self.calls += 1
        return [["154", 0.99]], 0.0


class _StubOcr:
    """按 ROI 返回预置文本；记录 read/line 调用次数，用来断言"没跑整图 OCR"。"""

    def __init__(self, texts: dict[tuple[int, int, int, int], str] | None = None) -> None:
        self.texts = {tuple(roi): text for roi, text in (texts or {}).items()}
        self.line_calls: list[tuple[int, int, int, int]] = []
        self.read_calls = 0
        self.full_lines: list[OcrLine] = [OcrLine("请选择行动", 0.9, (180, 830, 360, 60))]

    def line(self, _image, roi, **_kwargs) -> OcrLine | None:
        self.line_calls.append(tuple(roi))
        text = self.texts.get(tuple(roi))
        return None if not text else OcrLine(text, 0.99, tuple(roi))

    def read(self, _image, _roi=None):
        self.read_calls += 1
        return list(self.full_lines)


def _image() -> np.ndarray:
    return np.zeros((1280, 720, 3), dtype=np.uint8)


def _driver(ocr) -> ProduceDriver:
    return ProduceDriver(ocr=ocr, sleep=lambda _seconds: None)


# ---------------------------------------------------------------- 单行缓存
def test_line_cache_hit_skips_recognizer() -> None:
    line_engine = _CountingLineEngine()
    engine = OcrEngine(
        engine=_FakeMainEngine(),
        line_engine=line_engine,
        line_cache=LineFingerprintCache(),
        use_line_cache=True,
    )
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    roi = (20, 20, 160, 60)
    engine.line(image, roi)
    assert line_engine.calls == 1
    # 同一画面/同一文字：第二次必须命中缓存，不再调用识别模型。
    engine.line(image, roi)
    assert line_engine.calls == 1
    assert engine.line_cache_hits == 1

    # 文字区域被改掉：文字掩码指纹变化，必须重新识别。
    image[20:80, 20:180] = 0
    image[30:70, 40:160] = 255
    engine.line(image, roi)
    assert line_engine.calls == 2


def test_line_cache_tolerates_background_change() -> None:
    """同文字、不同背景（角色呼吸/光照）：掩码指纹不变，应该命中。"""
    line_engine = _CountingLineEngine()
    engine = OcrEngine(
        engine=_FakeMainEngine(),
        line_engine=line_engine,
        line_cache=LineFingerprintCache(),
        use_line_cache=True,
    )
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    roi = (20, 20, 160, 60)
    import cv2

    cv2.putText(image, "154", (35, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
    engine.line(image, roi)
    assert line_engine.calls == 1
    # 只改背景颜色/亮度，不动文字：缓存应命中。
    image[:] = (40, 80, 120)
    cv2.putText(image, "154", (35, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
    engine.line(image, roi)
    assert line_engine.calls == 1


# ---------------------------------------------------------------- 语义指纹
def test_semantic_fingerprint_normalizes_text() -> None:
    assert normalize_ocr_text("　请选择 行动\n") == "请选择 行动"
    assert semantic_fingerprint("请选择行动") == semantic_fingerprint("请选择行动")
    assert semantic_fingerprint("请选择行动") != semantic_fingerprint("请选择授课")
    assert semantic_fingerprint("") == ""


def test_semantic_screen_cache_reuses_by_text_hash() -> None:
    cache = SemanticScreenCache()
    lines = [OcrLine("请选择行动", 0.9, (180, 830, 360, 60))]
    assert cache.get("请选择行动") is None
    cache.put("请选择行动", lines)
    assert cache.hits == 0
    reused = cache.get("请选择行动")
    assert reused is not None and reused[0].text == "请选择行动"
    assert cache.hits == 1
    # 归一化后相同的文本也算同一语义指纹。
    assert cache.get(" 请选择行动 ") is not None


def test_static_screen_cache_skips_second_full_read() -> None:
    """快进按钮文字重复 = 同一剧情屏：第二次不再整屏 OCR（语义指纹命中）。"""
    ocr = _StubOcr(
        {
            produce_ui.FAST_LOADING_EN_BOX: "快进",
            produce_ui.FAST_LOADING_BOX: "",
        }
    )
    driver = _driver(ocr)
    image = _image()
    first = driver.read_fast(image)
    assert ocr.read_calls == 1
    second = driver.read_fast(image)
    assert ocr.read_calls == 1  # 语义缓存命中，没有第二次整屏 OCR
    assert [line.text for line in second] == [line.text for line in first]


# ---------------------------------------------------------------- 三维/行动页
def _attr_texts() -> dict[tuple[int, int, int, int], str]:
    return {
        produce_ui.ATTR_ROIS[0]: "312",
        produce_ui.ATTR_ROIS[1]: "215",
        produce_ui.ATTR_ROIS[2]: "351",
    }


def test_read_attrs_fast_path_never_runs_full_ocr() -> None:
    """三个固定框都读到：即使 caller 打开 allow_full，也不能再跑整图。"""
    ocr = _StubOcr(_attr_texts())
    driver = _driver(ocr)
    assert driver.read_attrs(_image(), allow_full=True) == (312, 215, 351)
    assert ocr.read_calls == 0
    assert ocr.line_calls == list(produce_ui.ATTR_ROIS)


def test_read_attrs_default_disables_full_fallback() -> None:
    """两个框读不到：默认只返回 None，不跑 5-15s 的整图兜底。"""
    texts = {produce_ui.ATTR_ROIS[0]: "312"}
    ocr = _StubOcr(texts)
    driver = _driver(ocr)
    assert driver.read_attrs(_image()) is None
    assert ocr.read_calls == 0
    # 显式允许时才兜底。
    assert driver.read_attrs(_image(), allow_full=True) is None
    assert ocr.read_calls == 1


def test_read_attrs_skips_probes_on_non_action_text() -> None:
    """课程/剧情文本不可能有三维圆：text_hint 直接筛掉，连小框都不读。"""
    ocr = _StubOcr(_attr_texts())
    driver = _driver(ocr)
    assert driver.read_attrs(_image(), text_hint="剩余回合数 3 CLEAR") is None
    assert ocr.line_calls == []
    assert ocr.read_calls == 0


def _action_probe_texts() -> dict[tuple[int, int, int, int], str]:
    texts = _attr_texts()
    texts.update(
        {
            produce_ui.FAST_STATUS_BOX: "期中截止",
            produce_ui.FAST_STAMINA_BOX: "24/35",
            produce_ui.FAST_P_BOX: "41",
            produce_ui.FAST_ACTION_TITLE_BOX: "请选择行动",
            produce_ui.FAST_RECOMMEND_BOX: "推荐歌唱训练",
            produce_ui.FAST_TRAIN_LABEL_BOXES[0]: "Vo.训练",
            produce_ui.FAST_TRAIN_LABEL_BOXES[1]: "Da.训练",
            produce_ui.FAST_TRAIN_LABEL_BOXES[2]: "Vi.训练",
            produce_ui.FAST_LESSON_BOX: "授课",
            produce_ui.FAST_REST_BOX: "休息",
        }
    )
    return texts


def test_action_page_probe_builds_decide_lines() -> None:
    ocr = _StubOcr(_action_probe_texts())
    driver = _driver(ocr)
    image = _image()
    lines = driver._action_probe(image)
    assert lines is not None
    text = driver.text_of(lines)
    for word in ("请选择行动", "授课", "休息", "Vo.训练", "推荐歌唱训练", "24/35"):
        assert word in text
    assert driver._frame_attrs == (312, 215, 351)
    # 同一帧再读三维：直接吃探针结果，不重复 OCR。
    calls = len(ocr.line_calls)
    assert driver.read_attrs(image, text_hint=text) == (312, 215, 351)
    assert len(ocr.line_calls) == calls


def test_action_page_probe_returns_none_when_no_controls() -> None:
    """三维读齐但一个可点行动都没有（事件/结算页）→ 交回整屏 OCR。"""
    ocr = _StubOcr(_attr_texts())
    driver = _driver(ocr)
    assert driver._action_probe(_image()) is None


def test_looks_like_action_page_probe() -> None:
    image = _image()
    assert _driver(
        _StubOcr({produce_ui.ATTR_ACTION_TITLE_BOX: "请选择行动"})
    )._looks_like_action_page(image)
    assert not _driver(
        _StubOcr({produce_ui.ATTR_ACTION_TITLE_BOX: "舞蹈能力值上升"})
    )._looks_like_action_page(image)


def test_read_fast_event_page_uses_option_rows() -> None:
    texts = {
        produce_ui.FAST_LOADING_EN_BOX: "快进",
        produce_ui.FAST_EVENT_ROW_BOXES[0]: "让我们找出共同的问题点吧 -8",
        produce_ui.FAST_EVENT_ROW_BOXES[1]: "仔细地处理一下吧",
        produce_ui.FAST_EVENT_ROW_BOXES[2]: "2A 使用视频网站来学习吧",
    }
    ocr = _StubOcr(texts)
    driver = _driver(ocr)
    lines = driver.read_fast(_image())
    text = driver.text_of(lines)
    assert "快进" in text
    assert ocr.read_calls == 0
    assert sum(1 for line in lines if "问题点" in line.text or "处理" in line.text or "视频" in line.text) == 3


def test_read_fast_loading_page_skips_full_read() -> None:
    ocr = _StubOcr({produce_ui.FAST_LOADING_BOX: "正在下载数据"})
    driver = _driver(ocr)
    lines = driver.read_fast(_image())
    assert [line.text for line in lines] == ["LOADING"]
    assert ocr.read_calls == 0


def test_read_fast_reward_page_skips_full_read() -> None:
    ocr = _StubOcr(
        {
            produce_ui.FAST_REWARD_TITLE_BOX: "请选择要领取的技能卡。",
            produce_ui.FAST_REWARD_RECOMMEND_BOX: "推荐",
            produce_ui.FAST_REWARD_CLAIM_BOX: "领取",
        }
    )
    driver = _driver(ocr)
    lines = driver.read_fast(_image())
    text = driver.text_of(lines)
    assert "请选择要领取" in text and "推荐" in text and "领取" in text
    assert ocr.read_calls == 0
