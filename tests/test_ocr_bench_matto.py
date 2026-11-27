"""matto OCR 测试集真帧回放（49 帧基准的回归子集；**数据集未跟踪，缺失即 skip**）。

数据来源 https://hiro.matto.top/ocr-dataset/check.html（无许可声明 → 只本地参考
不入库，hiro 先例 docs/PROVENANCE.md）：``data/_ocr_dataset/``（gitignore）。
干净 checkout 没有数据/模型时整套 skip，不会红。

口径与 scripts/ocr_bench.py 一致：engine 层原生 540x960，prod 层放大 720x1280。
这里挑基准抓出的 top 缺口帧做逐位回归（修复清单见 docs/OCR_BENCH_MATTO.md）。
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "_ocr_dataset"
CONFIG = ROOT / "configs" / "ocr_jp.example.yaml"
if not CONFIG.is_file():
    CONFIG = ROOT / "configs" / "ocr_jp.yaml"
MODEL_DIR = ROOT / "data" / "models" / "ocr_jp"

EXAM_FRAME = "dmm-maindmm1m-20261110-205150-r3-00074"
ACTION_FRAME = "dmm-maindmm1m-20261110-205150-00058"
SHOP_FRAME = "dmm-maindmm1m-20261110-205150-r3-00001"

pytestmark = [
    pytest.mark.skipif(not (DATASET / "truth.json").is_file(), reason="matto 数据集未下载（本地参考不入库）"),
    pytest.mark.skipif(not CONFIG.is_file(), reason="缺少 configs/ocr_jp*.yaml"),
    pytest.mark.skipif(
        not all((MODEL_DIR / name).is_file() for name in ("det.onnx", "rec.onnx", "keys.txt")),
        reason="缺少日文 OCR 模型（先跑 scripts/download_ocr_models.py）",
    ),
]


def _load_harness():
    spec = importlib.util.spec_from_file_location("ocr_bench", ROOT / "scripts" / "ocr_bench.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("rapidocr_onnxruntime")
    return _load_harness()


@pytest.fixture(scope="module")
def engine(harness):
    eng = harness.make_engine(threads=4)
    if eng is None:
        pytest.skip("OCR 引擎不可用")
    return eng


@pytest.fixture(scope="module")
def frames(harness):
    doc = harness.load_dataset()
    if doc is None:
        pytest.skip("matto 帧图片缺失")
    return {f["id"]: f for f in doc["frames"]}


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


def _image(harness, frame_id):
    import cv2

    path = DATASET / "img" / (frame_id + ".jpg")
    if not path.is_file():
        pytest.skip(f"缺少帧 {path.name}")
    native = cv2.imread(str(path))
    assert native is not None
    return native, cv2.resize(native, (720, 1280), interpolation=cv2.INTER_CUBIC)


# ---------------------------------------------------------------- 考试帧（multiplier/turns/假名卡名）
def test_exam_frame_prod_reads_turns_attr_multiplier(harness, engine, frames) -> None:
    """r3-00074：旧缺口 turns 读成 912 拒读 / 属性只认中文 / multiplier 上限 999。"""
    from gkagent.vision.lesson import LessonReader

    _native, image = _image(harness, EXAM_FRAME)
    state = LessonReader(engine).read(image, kind="audition")
    assert state.turns_left == 9, state.summary()
    assert state.stamina == 27, state.summary()
    assert state.attribute == "歌唱", state.attribute  # ボーカル 归一
    assert state.multiplier == 2805.0, state.multiplier  # 旧上限 999 拒读
    names = {c.name for c in state.cards}
    assert any("イメトレ" in n for n in names), names  # 纯假名卡名


def test_exam_frame_decide_routes_to_card_policy(harness, engine, frames) -> None:
    from gkagent.tasks.produce_ui import ProduceDriver

    _native, image = _image(harness, EXAM_FRAME)
    driver = ProduceDriver(ocr=engine, sleep=lambda _s: None)
    lines = driver.read_fast(image)
    tick = driver.decide(_Agent(), lines, image)
    assert (tick.screen, tick.action) == ("lesson", "card-policy"), tick.describe()


# ---------------------------------------------------------------- 行动页（params 上限/图标合并）
def test_action_frame_attrs_reads_matto_params(harness, engine, frames) -> None:
    """00058：1473/2336/1207（旧 ATTR_MAX=2000 拒 2336；vo 图标合并 11473）。"""
    from gkagent.tasks.produce_ui import ProduceDriver

    _native, image = _image(harness, ACTION_FRAME)
    driver = ProduceDriver(ocr=engine, sleep=lambda _s: None)
    attrs = driver.read_attrs(image, text_hint=None)
    assert attrs == (1473, 2336, 1207), attrs


# ---------------------------------------------------------------- 商店（日文标题/終了）
def test_shop_frame_decide_exits(harness, engine, frames) -> None:
    from gkagent.tasks.produce_ui import ProduceDriver

    _native, image = _image(harness, SHOP_FRAME)
    driver = ProduceDriver(ocr=engine, sleep=lambda _s: None)
    lines = driver.read_fast(image)
    agent = _Agent()
    tick = driver.decide(agent, lines, image)
    assert (tick.screen, tick.action) == ("shop", "exit"), tick.describe()
    assert agent.device.clicks


# ---------------------------------------------------------------- harness 逐字段口径
def test_bench_frame_engine_layer_closes_top_gaps(harness, engine, frames) -> None:
    """engine 层：考试 turns/multiplier/top_scores、行动 params、商店划线价都判对。"""
    expectations = {
        EXAM_FRAME: {
            "turns_left": "对",
            "multiplier_pct": "对",
            "exam_attr": "对",
            "top_scores[0]": "对",
            "top_scores[2]": "对",
            "hand[1].name": "对",
            "deck_left": "对",
        },
        ACTION_FRAME: {
            "params[0]": "对",
            "params[1]": "对",
            "params[2]": "对",
            "param_caps[0]": "对",
            "growth_pct[0]": "对",
            "star": "对",
            "days_left": "对",
        },
        SHOP_FRAME: {
            "shelf[0].price": "对",
            "shelf[0].sale_from": "对",
            "shelf[4].price": "对",
            "delete_price": "对",
            "delete_used": "对",
            "upgrade_price": "对",
            "button:終了": "对",
            "button:交換する": "对",
        },
    }
    for frame_id, wants in expectations.items():
        res = harness.bench_frame(engine, frames[frame_id], decide=False)
        rows = {r["field"]: r for r in res["rows"]}
        for field_name, want in wants.items():
            assert field_name in rows, (frame_id, field_name)
            assert rows[field_name]["engine"] == want, (
                frame_id, field_name, rows[field_name]["engine"], rows[field_name]["engine_value"],
            )


def test_bench_completion_opt_in_on_real_exam_fields(harness, engine, frames) -> None:
    """deck_left/card_effect/multiplier 的 opt-in 补全：默认关逐位不变，开了才填。"""
    from gkagent.vision.ocr_complete import CompletionSources, complete_fields

    res = harness.bench_frame(engine, frames[EXAM_FRAME], decide=False)
    rows = {r["field"]: r for r in res["rows"]}
    fields = {
        "deck_left": rows["deck_left"]["engine_value"],
        "multiplier_pct": rows["multiplier_pct"]["engine_value"],
        "statuses": [
            {"kind": rows["statuses[0].kind"]["engine_value"], "name": None, "value": rows["statuses[0].value"]["engine_value"]},
        ],
    }
    sources = CompletionSources(deck_count=5, card_effects=({"kind": "card_effect", "name": None, "value": 1},))
    assert complete_fields(fields, sources) == fields  # 默认关
    out = complete_fields(fields, sources, enable=True)
    assert out["deck_left"] == 5
    assert out["statuses"][-1]["kind"] == "card_effect"
