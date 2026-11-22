"""OCR 封装（RapidOCR）：读 720x1280 游戏截图里的中文/日文。

识别逻辑（快速路径，默认）：
1. **检测在原生分辨率**跑（自动限制最长边 ``det_limit_side_len``），不再把整屏
   放大 2 倍送进检测模型——检测耗时与像素数成正比，原图检测便宜 2-4 倍；
2. **识别仍用 2 倍放大的裁剪块**（小字更准）：把检测框坐标 ×2 后从放大图裁；
3. 丢弃低置信度行，坐标按倍率还原到原图，合并重叠的重复行；
4. 传入自定义 ``engine``（如单测的 FakeRapid）时走原来的单阶段路径，行为不变。

``read(..., scale=...)`` 可显式覆盖放大倍率（基准脚本用来复现改前行为）。

**OCR 模型（2026-11-22 A1：换日文模型）**

RapidOCR 内置的是中文模型 ``ch_PP-OCRv4``（字典没有假名），日文剧情只能读出
汉字碎片（``飲物持``/``？``/``、。``）。换成官方 **PP-OCRv6 small det+rec**
（Apache-2.0，多语言：中日英+46 拉丁语系）后，同一张截图能读完整句子
（``ヨーグルトパフェ``/``つくねハンバーグ``/``ドリンクバー``）。

模型配置优先级（都存在时从高到低）：

1. ``OcrEngine(config_path=...)`` 显式参数；
2. 环境变量 ``GKAGENT_OCR_CONFIG``；
3. 本地 ``configs/ocr_jp.yaml``（``scripts/download_ocr_models.py`` 生成，gitignore）；
4. 都没有 → 内置中文模型（默认行为不变）。

配置文件是 RapidOCR ``config.yaml`` 的完整拷贝（``configs/ocr_jp.example.yaml``）；
``Det.model_path`` / ``Rec.model_path`` / ``Rec.rec_keys_path`` 支持 ``%VAR%``/``$VAR``
环境变量，相对路径按 YAML 文件所在目录解析（解析不到再按 RapidOCR 包内路径兜底）。
**配置存在但模型文件缺失时直接报错**，不静默换回中文模型（用户规则：禁止静默回退）。
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from gkagent.vision.ocr_cache import LineFingerprintCache

# 原生分辨率检测：720x1280 的整屏检测输入被压到最长边 1120（原图 0.7MP，
# 旧路径把 2 倍图再压到 2000 长边 ≈ 2.25MP）。识别裁剪仍从 2 倍图取，准确率不变。
DEFAULT_DET_LIMIT_SIDE = 1120
# 很小的 ROI（如左上角状态条）检测前先放大，否则检测模型看不到细笔画。
DET_MIN_SIDE = 240
# 识别批大小：RapidOCR 一次 session 调用最多识别多少行，减少 Python/session 往返。
DEFAULT_REC_BATCH = 12
# onnxruntime 线程数：真机通常同时有别的 OCR 进程（录制器/另一个 bot），
# 默认的"用满 24 核"会互相抢线程，实测反而慢 3-5 倍。8 线程在"单 bot"和
# "bot + 录制器"两种场景都比较稳（720x1280 的 PP-OCR 模型也用不满 24 核）。
DEFAULT_THREADS = 8

# 日文/多语言 OCR 模型配置（见模块文档）。configs/ocr_jp.yaml 由下载脚本生成。
OCR_CONFIG_ENV = "GKAGENT_OCR_CONFIG"
REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_OCR_CONFIG = REPO_ROOT / "configs" / "ocr_jp.yaml"


def resolve_ocr_config_path(
    config_path: str | os.PathLike[str] | None = None,
) -> Path | None:
    """解析 OCR 模型 YAML 的绝对路径；返回 ``None`` 表示用 RapidOCR 内置模型。

    优先级：显式参数 > 环境变量 ``GKAGENT_OCR_CONFIG`` > 本地 ``configs/ocr_jp.yaml``。
    显式参数/环境变量指向的文件不存在时报 ``FileNotFoundError``（禁止静默回退）；
    只有第 3 档（自动发现）不存在时安静返回 ``None``。
    """
    source = "config_path"
    raw: str | os.PathLike[str] | None = config_path
    if raw is None:
        raw = os.environ.get(OCR_CONFIG_ENV)
        source = f"环境变量 {OCR_CONFIG_ENV}"
    if raw is None:
        return LOCAL_OCR_CONFIG if LOCAL_OCR_CONFIG.is_file() else None

    path = Path(os.path.expandvars(str(raw))).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"OCR 模型配置不存在：{path}（来自 {source}）。"
            "日文模型见 scripts/download_ocr_models.py 或 configs/ocr_jp.example.yaml；"
            "不配置则用内置中文模型。"
        )
    return path


def _rapidocr_package_root() -> Path | None:
    try:
        import rapidocr_onnxruntime  # type: ignore[import-untyped]
    except Exception:  # noqa: BLE001 - 未安装时交给调用方的导入错误处理
        return None
    return Path(rapidocr_onnxruntime.__file__).resolve().parent


def _resolve_model_file(
    raw: object,
    base_dir: Path,
    *,
    package_fallback: bool = False,
) -> Path | None:
    """把配置里的模型路径解析成绝对路径：展开环境变量 → YAML 目录 → RapidOCR 包内兜底。"""
    value = os.path.expandvars(str(raw or "")).strip()
    if not value:
        return None
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve() if candidate.is_file() else None
    local = (base_dir / candidate).resolve()
    if local.is_file():
        return local
    if package_fallback:
        package = _rapidocr_package_root()
        if package is not None:
            bundled = (package / candidate).resolve()
            if bundled.is_file():
                return bundled
    return None


def load_ocr_config_overrides(config_path: str | os.PathLike[str]) -> dict[str, str]:
    """读 OCR 模型 YAML，返回传给 RapidOCR 的模型路径覆盖项（绝对路径）。

    只解析我们关心的三个路径键，其它参数（检测预处理/阈值等）由 RapidOCR 自己读 YAML；
    这样 YAML 仍是 RapidOCR 的完整 ``config.yaml``，不需要在代码里维护一份参数表。
    """
    import yaml  # type: ignore[import-untyped]

    path = Path(config_path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"OCR 模型配置不是合法 YAML：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise TypeError(f"OCR 模型配置格式不对（应为 YAML 字典）：{path}")
    for section in ("Global", "Det", "Cls", "Rec"):
        if section not in data:
            raise ValueError(
                f"OCR 模型配置缺少 {section} 段：{path}。"
                "请用 RapidOCR 内置 config.yaml 的完整拷贝（参考 configs/ocr_jp.example.yaml）。"
            )
        if not isinstance(data[section], dict):
            raise TypeError(f"OCR 模型配置的 {section} 段应为字典：{path}")

    base = path.parent
    overrides: dict[str, str] = {}
    fields = (
        # (RapidOCR kwargs 键, YAML 段, 字段, 是否允许 RapidOCR 包内路径兜底, 是否必填)
        ("det_model_path", "Det", "model_path", True, True),
        ("rec_model_path", "Rec", "model_path", True, True),
        ("rec_keys_path", "Rec", "rec_keys_path", False, False),
    )
    for key, section, field, package_fallback, required in fields:
        raw = data[section].get(field)
        if raw is None or str(raw).strip() == "":
            if required:
                raise ValueError(f"OCR 模型配置 {section}.{field} 为空：{path}")
            continue
        resolved = _resolve_model_file(raw, base, package_fallback=package_fallback)
        if resolved is None:
            raise FileNotFoundError(
                f"OCR 模型配置 {section}.{field} 指向的文件不存在：{raw}（配置：{path}）。"
                "相对路径按 YAML 所在目录解析，也可以写绝对路径或 %VAR%/$VAR 环境变量。"
            )
        overrides[key] = str(resolved)
    return overrides


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    box: tuple[int, int, int, int]


class OcrEngine:
    def __init__(
        self,
        engine=None,
        scale: float = 2.0,
        min_score: float = 0.4,
        line_engine=None,
        *,
        config_path: str | os.PathLike[str] | None = None,
        fast: bool = True,
        det_limit_side_len: int = DEFAULT_DET_LIMIT_SIDE,
        rec_batch_num: int = DEFAULT_REC_BATCH,
        line_cache: LineFingerprintCache | None = None,
        use_line_cache: bool = True,
        threads: int | None = DEFAULT_THREADS,
    ) -> None:
        created = engine is None
        # 自定义模型配置只对内部创建的 RapidOCR 生效；测试注入 engine 时忽略
        # （单测不应因为本机环境变量/模型文件而改变行为）。
        self._config_path: Path | None = None
        self._config_overrides: dict[str, str] = {}
        if created:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]

            self._config_path = resolve_ocr_config_path(config_path)
            if self._config_path is not None:
                self._config_overrides = load_ocr_config_overrides(self._config_path)
            # 两阶段路径自己控制"检测原图 + 识别 2 倍裁剪"，所以这里关掉内置检测缩放的
            # min 策略（改成 max），并去掉方向分类（游戏 UI 全是横排文字）。
            options: dict = {
                "det_limit_side_len": int(det_limit_side_len),
                "det_limit_type": "max",
                "use_cls": False,
                "rec_batch_num": int(rec_batch_num),
            }
            if threads is not None and int(threads) > 0:
                options["intra_op_num_threads"] = int(threads)
                options["inter_op_num_threads"] = 1
            if self._config_path is not None:
                options["config_path"] = str(self._config_path)
                options.update(self._config_overrides)
            engine = RapidOCR(**options)
        self._engine = engine
        self._line_engine = line_engine
        self._threads = threads if threads is None or int(threads) > 0 else None
        self.scale = scale
        self.min_score = min_score
        # 只有自己创建的 RapidOCR 才走两阶段快路径；外部注入的 engine 可能没有
        # text_det/text_rec/get_crop_img_list 这些内部接口（单测的 FakeRapid 就没有）。
        self._fast = bool(created and fast and self._supports_two_stage())
        self.det_limit_side_len = int(det_limit_side_len)
        self.rec_batch_num = int(rec_batch_num)
        # 统计：两阶段路径的检测/识别耗时（基准脚本/日志用）
        self.last_det_ms = 0.0
        self.last_rec_ms = 0.0
        # 单行缓存：按 ROI 内"文字掩码"的感知指纹命中，角色呼吸不影响。
        # 只有真实引擎才启用（FakeRapid/单测 stub 直接走原路径，不能影响调用次数断言）。
        self.line_cache = (
            line_cache
            if line_cache is not None
            else (LineFingerprintCache() if (created and use_line_cache) else None)
        )
        self.line_cache_hits = 0
        self.line_cache_misses = 0

    def _supports_two_stage(self) -> bool:
        return all(
            hasattr(self._engine, name)
            for name in ("text_det", "text_rec", "get_crop_img_list", "sorted_boxes")
        )

    @property
    def config_path(self) -> Path | None:
        """当前 OCR 模型配置；``None`` = RapidOCR 内置中文模型。"""
        return self._config_path

    def describe_model(self) -> str:
        """一句话说明当前 OCR 模型（日志/复盘用）。"""
        if self._config_path is None:
            return "RapidOCR 内置中文模型（ch_PP-OCRv4，字典无假名）"
        return f"{self._config_path}"

    def read(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
        *,
        scale: float | None = None,
    ) -> list[OcrLine]:
        target = image
        off_x = off_y = 0
        if roi is not None:
            x, y, w, h = roi
            target = image[y : y + h, x : x + w]
            off_x, off_y = x, y
        if self._fast and scale is None:
            return self._read_two_stage(target, off_x, off_y)
        return self._read_single_stage(target, off_x, off_y, self.scale if scale is None else scale)

    def _read_single_stage(
        self,
        target: np.ndarray,
        off_x: int,
        off_y: int,
        scale: float,
    ) -> list[OcrLine]:
        """原路径：整块放大后交给 RapidOCR（检测+识别一起）。保留给外部 engine/基准对照。"""
        if scale and scale != 1.0:
            target = cv2.resize(
                target,
                None,
                fx=float(scale),
                fy=float(scale),
                interpolation=cv2.INTER_CUBIC,
            )
        result, _ = self._engine(target)
        lines: list[OcrLine] = []
        for box, text, score in result or []:
            confidence = float(score)
            if confidence < self.min_score:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x0 = int(min(xs) / scale) + off_x
            y0 = int(min(ys) / scale) + off_y
            x1 = int(max(xs) / scale) + off_x
            y1 = int(max(ys) / scale) + off_y
            lines.append(OcrLine(str(text).strip(), confidence, (x0, y0, x1 - x0, y1 - y0)))
        return self._dedupe(lines)

    def _read_two_stage(
        self,
        target: np.ndarray,
        off_x: int,
        off_y: int,
    ) -> list[OcrLine]:
        """检测在原生图（小 ROI 先放大），识别在 2 倍裁剪块——小字准，检测便宜。

        检测框只用来定位文字行；识别输入仍按 ``self.scale`` 从原图放大裁剪，
        所以和旧路径的识别清晰度一致，只是检测分辨率降下来了。检测框坐标始终
        保持在**原图坐标系**（小 ROI 检测前的放大倍数会先还原）。
        """
        height, width = target.shape[:2]
        if height < 8 or width < 8:
            return []
        scale = float(self.scale or 1.0)
        det_input = target
        det_ratio = 1.0
        min_side = min(height, width)
        if min_side < DET_MIN_SIDE:
            det_ratio = min(3.0, DET_MIN_SIDE / float(max(min_side, 1)))
            det_input = cv2.resize(
                target,
                None,
                fx=det_ratio,
                fy=det_ratio,
                interpolation=cv2.INTER_CUBIC,
            )
        try:
            started = time.perf_counter()
            boxes, _ = self._engine.text_det(det_input)
            self.last_det_ms = (time.perf_counter() - started) * 1000.0
        except Exception:  # noqa: BLE001 - 两阶段失败就退回旧路径，不让整步崩掉
            return self._read_single_stage(target, off_x, off_y, scale)
        if boxes is None or len(boxes) == 0:
            self.last_rec_ms = 0.0
            return []
        ordered = self._engine.sorted_boxes(boxes)
        if det_ratio != 1.0:
            ordered = [np.asarray(box, dtype=np.float32) / det_ratio for box in ordered]

        big = target
        if scale != 1.0:
            big = cv2.resize(target, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        crop_boxes: list[np.ndarray] = []
        kept: list[tuple[float, float, float, float]] = []
        for box in ordered:
            xs = box[:, 0]
            ys = box[:, 1]
            x0, x1 = float(xs.min()), float(xs.max())
            y0, y1 = float(ys.min()), float(ys.max())
            box_w, box_h = x1 - x0, y1 - y0
            # 太小的框多半是噪点/单笔画，识别也没有意义。
            if box_w < 6 or box_h < 6:
                continue
            # 上下多留 12%：检测框偶尔切掉汉字上下沿；左右留 3% 防止贴边。
            pad_y = max(2.0, box_h * 0.12)
            pad_x = max(2.0, box_w * 0.03)
            points = np.array(
                [
                    [max(0.0, x0 - pad_x), max(0.0, y0 - pad_y)],
                    [min(width - 1.0, x1 + pad_x), max(0.0, y0 - pad_y)],
                    [min(width - 1.0, x1 + pad_x), min(height - 1.0, y1 + pad_y)],
                    [max(0.0, x0 - pad_x), min(height - 1.0, y1 + pad_y)],
                ],
                dtype=np.float32,
            )
            crop_boxes.append(points * scale)
            kept.append((x0, y0, x1, y1))
        if not crop_boxes:
            self.last_rec_ms = 0.0
            return []
        try:
            started = time.perf_counter()
            crops = self._engine.get_crop_img_list(big, crop_boxes)
            results, _ = self._engine.text_rec(crops)
            self.last_rec_ms = (time.perf_counter() - started) * 1000.0
        except Exception:  # noqa: BLE001 - 识别失败退回旧路径
            return self._read_single_stage(target, off_x, off_y, scale)
        lines: list[OcrLine] = []
        for (x0, y0, x1, y1), (text, score) in zip(kept, results, strict=False):
            confidence = float(score)
            if confidence < self.min_score:
                continue
            # 检测框本来就在**原图坐标**（检测输入是原图；小 ROI 的 det_ratio 已还原），
            # 只有识别裁剪用了 scale 倍图，所以这里不要再除 scale。
            x = round(x0) + off_x
            y = round(y0) + off_y
            w = max(1, round(x1 - x0))
            h = max(1, round(y1 - y0))
            lines.append(OcrLine(str(text).strip(), confidence, (x, y, w, h)))
        return self._dedupe(lines)

    def find(
        self,
        needle: str,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> OcrLine | None:
        for line in self.read(image, roi):
            if needle and needle in line.text:
                return line
        return None

    # ------------------------------------------------------------------ 单行快路径
    def line(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int],
        *,
        scale: float = 4.0,
        min_score: float | None = None,
        digits_only: bool = False,
    ) -> OcrLine | None:
        """已知位置的一小段文字/数字，只跑识别不跑检测（实测 10-30ms）。

        手牌上的分数预览、体力费用、体力/回合数都是固定位置的小数字，
        走这条路径比整屏 OCR（2-5s）便宜两个数量级。

        ``digits_only`` 为 True 时只返回纯数字（允许 x2 这类倍率由调用方处理）。
        """
        x, y, w, h = roi
        height, width = image.shape[:2]
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))
        key_roi = (x, y, w, h)
        if self.line_cache is not None:
            hit, cached = self.line_cache.get(
                image, key_roi, scale=scale, digits_only=digits_only
            )
            if hit:
                self.line_cache_hits += 1
                return cached
            self.line_cache_misses += 1
        crop = image[y : y + h, x : x + w]
        if crop.size == 0:
            return None
        if scale and scale != 1.0:
            crop = cv2.resize(
                crop, None, fx=float(scale), fy=float(scale), interpolation=cv2.INTER_CUBIC
            )
        try:
            result, _ = self._line_core()(crop)
        except Exception:  # noqa: BLE001 - 快路径失败就退回整块识别
            if self._line_engine is not self._engine:
                return None
            lines = self.read(image, (x, y, w, h))
            text = " ".join(line.text for line in lines).strip()
            if not text:
                return None
            return OcrLine(text, max((line.score for line in lines), default=0.0), (x, y, w, h))

        best_text = ""
        best_score = 0.0
        for entry in result or []:
            text = str(entry[0]).strip()
            score = float(entry[1])
            if score > best_score:
                best_text, best_score = text, score
        if min_score is None:
            min_score = self.min_score
        if not best_text or best_score < min_score:
            return None
        if digits_only and not re.fullmatch(r"\d+", best_text):
            match = re.search(r"\d+", best_text)
            if match is None:
                return None
            best_text = match.group(0)
        line = OcrLine(best_text, best_score, (x, y, w, h))
        self._remember_line(image, key_roi, line, scale, digits_only)
        return line

    def _remember_line(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int],
        line: OcrLine | None,
        scale: float,
        digits_only: bool,
    ) -> None:
        if self.line_cache is not None:
            self.line_cache.put(image, roi, line, scale=scale, digits_only=digits_only)

    def _line_core(self):
        """懒加载"只识别"引擎（RapidOCR use_det=False），失败时退回整块引擎。

        自定义模型配置必须带进这个引擎：单行路径（分数/体力/回合数）也会用到
        日文/多语言字典，否则数字末尾的「/」、汉字都会读歪。
        """
        if self._line_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]

                options: dict = {"use_det": False, "use_cls": False}
                if self._threads is not None:
                    options["intra_op_num_threads"] = int(self._threads)
                    options["inter_op_num_threads"] = 1
                if self._config_path is not None:
                    options["config_path"] = str(self._config_path)
                    options.update(self._config_overrides)
                self._line_engine = RapidOCR(**options)
            except Exception:  # noqa: BLE001 - 老版本 rapidocr 没有该开关
                self._line_engine = self._engine
        return self._line_engine

    def text(self, image: np.ndarray, roi: tuple[int, int, int, int] | None = None) -> str:
        return " ".join(line.text for line in self.read(image, roi))

    @staticmethod
    def _dedupe(lines: list[OcrLine]) -> list[OcrLine]:
        kept: list[OcrLine] = []
        for line in sorted(lines, key=lambda item: -item.score):
            duplicate = False
            for other in kept:
                if line.text != other.text:
                    continue
                ax, ay, _, _ = line.box
                bx, by, _, _ = other.box
                if abs(ax - bx) < 12 and abs(ay - by) < 12:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(line)
        return kept
