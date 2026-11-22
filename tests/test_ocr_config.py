"""OCR 模型配置接线（A1 换日文模型）：config_path / 环境变量 / 本地配置 / 路径解析。

全部用 RapidOCR 替身，不加载真实模型（快、可在 CI 跑）。覆盖：
- 优先级：显式参数 > ``GKAGENT_OCR_CONFIG`` > 本地 ``configs/ocr_jp.yaml`` > 内置中文模型；
- 模型路径解析：相对 YAML 目录、``%VAR%``/``$VAR`` 环境变量、RapidOCR 包内兜底；
- 配置/模型文件缺失必须报错（禁止静默回退中文模型）；
- 两阶段主引擎和单行 ``_line_core`` 引擎拿到同一套模型配置。
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest
import yaml

import gkagent.vision.ocr as ocr_module
from gkagent.vision.ocr import (
    OCR_CONFIG_ENV,
    OcrEngine,
    load_ocr_config_overrides,
    resolve_ocr_config_path,
)


class _FakeRapid:
    """RapidOCR 替身：记录构造参数；带两阶段接口属性，让 OcrEngine 认为可以走快路径。"""

    instances: ClassVar[list[_FakeRapid]] = []

    text_det = object()
    text_rec = object()
    get_crop_img_list = object()
    sorted_boxes = object()

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        _FakeRapid.instances.append(self)

    def __call__(self, _image):
        return [], 0.0


@pytest.fixture(autouse=True)
def _fake_rapid(monkeypatch):
    _FakeRapid.instances = []
    import rapidocr_onnxruntime

    monkeypatch.setattr(rapidocr_onnxruntime, "RapidOCR", _FakeRapid)
    monkeypatch.delenv(OCR_CONFIG_ENV, raising=False)
    # 本机真实存在的 configs/ocr_jp.yaml 不能影响单测（否则会加载真模型）。
    monkeypatch.setattr(ocr_module, "LOCAL_OCR_CONFIG", Path("Z:/no-such-dir/ocr_jp.yaml"))
    return _FakeRapid


def _config_dict(
    *,
    det: str = "det.onnx",
    rec: str = "rec.onnx",
    keys: str | None = "keys.txt",
) -> dict:
    rec_section: dict = {"model_path": rec, "rec_img_shape": [3, 48, 320]}
    if keys is not None:
        rec_section["rec_keys_path"] = keys
    return {
        "Global": {"text_score": 0.5},
        "Det": {"model_path": det},
        "Cls": {"model_path": "models/ch_ppocr_mobile_v2.0_cls_infer.onnx"},
        "Rec": rec_section,
    }


def _write_config(tmp_path: Path, data: dict, name: str = "ocr.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _touch(tmp_path: Path, *names: str) -> None:
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"dummy")


# ---------------------------------------------------------------- 优先级
def test_default_uses_builtin_chinese_model(_fake_rapid) -> None:
    engine = OcrEngine()
    assert engine.config_path is None
    assert "config_path" not in _fake_rapid.instances[0].kwargs
    assert "内置中文模型" in engine.describe_model()


def test_explicit_config_resolves_model_paths(tmp_path, _fake_rapid) -> None:
    _touch(tmp_path, "det.onnx", "rec.onnx", "keys.txt")
    config = _write_config(tmp_path, _config_dict())
    engine = OcrEngine(config_path=config)
    assert engine.config_path == config.resolve()
    kwargs = _fake_rapid.instances[0].kwargs
    assert kwargs["config_path"] == str(config.resolve())
    assert kwargs["det_model_path"] == str((tmp_path / "det.onnx").resolve())
    assert kwargs["rec_model_path"] == str((tmp_path / "rec.onnx").resolve())
    assert kwargs["rec_keys_path"] == str((tmp_path / "keys.txt").resolve())
    # 其它参数仍走我们自己的快路径设置
    assert kwargs["det_limit_type"] == "max"
    assert kwargs["use_cls"] is False


def test_env_config_relative_to_cwd(tmp_path, monkeypatch, _fake_rapid) -> None:
    _touch(tmp_path, "det.onnx", "rec.onnx", "keys.txt")
    config = _write_config(tmp_path, _config_dict())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(OCR_CONFIG_ENV, "ocr.yaml")
    engine = OcrEngine()
    assert engine.config_path == config.resolve()


def test_explicit_config_beats_env(tmp_path, monkeypatch, _fake_rapid) -> None:
    monkeypatch.setenv(OCR_CONFIG_ENV, str(tmp_path / "missing.yaml"))
    _touch(tmp_path, "det.onnx", "rec.onnx", "keys.txt")
    config = _write_config(tmp_path, _config_dict())
    engine = OcrEngine(config_path=config)
    assert engine.config_path == config.resolve()


def test_local_config_auto_discovered(tmp_path, monkeypatch, _fake_rapid) -> None:
    _touch(tmp_path, "det.onnx", "rec.onnx", "keys.txt")
    config = _write_config(tmp_path, _config_dict())
    monkeypatch.setattr(ocr_module, "LOCAL_OCR_CONFIG", config)
    engine = OcrEngine()
    assert engine.config_path == config


def test_explicit_path_beats_local_config(tmp_path, monkeypatch, _fake_rapid) -> None:
    local = tmp_path / "local.yaml"
    local.write_text("Global: {}\nDet: {}\nCls: {}\nRec: {}\n", encoding="utf-8")
    monkeypatch.setattr(ocr_module, "LOCAL_OCR_CONFIG", local)
    _touch(tmp_path, "det.onnx", "rec.onnx", "keys.txt")
    config = _write_config(tmp_path, _config_dict())
    engine = OcrEngine(config_path=config)
    assert engine.config_path == config.resolve()


# ---------------------------------------------------------------- 缺失必须报错
def test_missing_explicit_config_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="OCR 模型配置不存在"):
        OcrEngine(config_path=tmp_path / "nope.yaml")


def test_missing_env_config_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(OCR_CONFIG_ENV, str(tmp_path / "nope.yaml"))
    with pytest.raises(FileNotFoundError, match="OCR 模型配置不存在"):
        OcrEngine()


def test_missing_det_model_raises(tmp_path) -> None:
    _touch(tmp_path, "rec.onnx", "keys.txt")
    config = _write_config(tmp_path, _config_dict())
    with pytest.raises(FileNotFoundError, match="Det.model_path"):
        OcrEngine(config_path=config)


def test_missing_rec_model_raises(tmp_path) -> None:
    _touch(tmp_path, "det.onnx", "keys.txt")
    config = _write_config(tmp_path, _config_dict())
    with pytest.raises(FileNotFoundError, match="Rec.model_path"):
        OcrEngine(config_path=config)


def test_missing_keys_raises(tmp_path) -> None:
    _touch(tmp_path, "det.onnx", "rec.onnx")
    config = _write_config(tmp_path, _config_dict())
    with pytest.raises(FileNotFoundError, match="rec_keys_path"):
        OcrEngine(config_path=config)


def test_incomplete_config_raises(tmp_path) -> None:
    path = _write_config(tmp_path, {"Det": {"model_path": "det.onnx"}})
    with pytest.raises(ValueError, match="缺少"):
        load_ocr_config_overrides(path)


def test_injected_engine_ignores_config(monkeypatch) -> None:
    """测试注入 engine 时不应受本机环境变量影响（单测可复现）。"""
    monkeypatch.setenv(OCR_CONFIG_ENV, "definitely-missing.yaml")
    engine = OcrEngine(engine=_FakeRapid())
    assert engine.config_path is None


# ---------------------------------------------------------------- 路径解析
def test_model_path_env_var_expansion(tmp_path, monkeypatch, _fake_rapid) -> None:
    _touch(tmp_path, "det.onnx", "rec.onnx", "keys.txt")
    monkeypatch.setenv("OCR_TEST_DIR", str(tmp_path))
    data = _config_dict(
        det="$OCR_TEST_DIR/det.onnx",
        rec="$OCR_TEST_DIR/rec.onnx",
        keys="$OCR_TEST_DIR/keys.txt",
    )
    config = _write_config(tmp_path, data)
    OcrEngine(config_path=config)
    kwargs = _fake_rapid.instances[0].kwargs
    assert kwargs["det_model_path"] == str((tmp_path / "det.onnx").resolve())
    assert kwargs["rec_model_path"] == str((tmp_path / "rec.onnx").resolve())
    assert kwargs["rec_keys_path"] == str((tmp_path / "keys.txt").resolve())


def test_det_model_falls_back_to_rapidocr_package(tmp_path, _fake_rapid) -> None:
    """配置只换 Rec、Det 保留包内默认路径时（相对路径解析不到）走 RapidOCR 包内兜底。"""
    _touch(tmp_path, "rec.onnx", "keys.txt")
    config = _write_config(
        tmp_path,
        _config_dict(det="models/ch_PP-OCRv4_det_infer.onnx"),
    )
    engine = OcrEngine(config_path=config)
    kwargs = _fake_rapid.instances[0].kwargs
    assert Path(kwargs["det_model_path"]).is_file()
    assert kwargs["det_model_path"].endswith("ch_PP-OCRv4_det_infer.onnx")
    assert engine.config_path == config.resolve()


def test_resolve_ocr_config_path_returns_none_without_config(monkeypatch) -> None:
    monkeypatch.delenv(OCR_CONFIG_ENV, raising=False)
    monkeypatch.setattr(ocr_module, "LOCAL_OCR_CONFIG", Path("Z:/no-such-dir/ocr_jp.yaml"))
    assert resolve_ocr_config_path() is None


# ---------------------------------------------------------------- 单行引擎
def test_line_engine_gets_same_model_config(tmp_path, _fake_rapid) -> None:
    """单行快路径（分数/体力/回合数）也必须用日文字典，否则数字/汉字读歪。"""
    _touch(tmp_path, "det.onnx", "rec.onnx", "keys.txt")
    config = _write_config(tmp_path, _config_dict())
    engine = OcrEngine(config_path=config)
    assert len(_fake_rapid.instances) == 1  # 主引擎

    image = np.zeros((40, 120, 3), dtype=np.uint8)
    assert engine.line(image, (0, 0, 120, 40)) is None  # 替身返回空

    assert len(_fake_rapid.instances) == 2  # 懒加载的单行引擎
    main, line_engine = _fake_rapid.instances
    assert line_engine.kwargs["use_det"] is False
    assert line_engine.kwargs["config_path"] == main.kwargs["config_path"]
    assert line_engine.kwargs["det_model_path"] == main.kwargs["det_model_path"]
    assert line_engine.kwargs["rec_model_path"] == main.kwargs["rec_model_path"]
    assert line_engine.kwargs["rec_keys_path"] == main.kwargs["rec_keys_path"]
