"""OCR 提速基准：改前（整屏检测 / full fallback）vs 改后（分区快路径）。

用法::

    python scripts/bench_ocr.py                # 改前 + 改后，默认 3 次中位数
    python scripts/bench_ocr.py --before       # 只测改前
    python scripts/bench_ocr.py --after        # 只测改后
    python scripts/bench_ocr.py --verify       # 额外做关键词/屏幕类型正确性检查
    python scripts/bench_ocr.py --frames-dir data/bench/ep-full1

测量项：
    full_read        整屏 OCR（改前：2 倍整图单阶段；改后：原生检测 + 2 倍裁剪识别）
    bottom_roi       底部按钮区（720x809）
    corner_roi       左上状态条（470x160）
    attrs_fast       行动页三维固定小框（3 个 line）
    attrs_full       三维整图兜底（旧的 5-15s 路径）
    card_detail      课程卡片详情 4 个探针
    line_cold        单个小框首次识别
    line_cached      同一小框第二次（改后语义缓存命中，改前无缓存）
    lesson_read      课程读屏（LessonReader：手牌名/分数/体力/回合）
    step_action      行动页单步 OCR（read + 三维）
    step_event       事件选项单步 OCR
    step_lesson      课程单步 OCR（含 detail/exam 探针）
    step_loading     加载页单步 OCR
    step_reward      领奖页单步 OCR

注意：真机后台可能还有别的进程在跑 OCR，wall time 会抖动；脚本默认取中位数，
并把 ``cpu``（process_time）也打出来。空载时以 wall 为准。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2
import numpy as np

from gkagent.tasks.produce_ui import (
    ATTR_ROIS,
    ProduceDriver,
)
from gkagent.vision.lesson import LessonReader
from gkagent.vision.ocr import OcrEngine

DEFAULT_FRAMES = ROOT / "data" / "bench" / "ep-full1"
FALLBACK_FRAMES = ROOT / "data" / "auto"


# ---------------------------------------------------------------- 引擎构造
def make_after_engine(threads: int | None = None) -> OcrEngine:
    """改后引擎：原生检测 + 2 倍裁剪识别 + 单行语义缓存。"""
    return OcrEngine(threads=threads)


def make_before_engine(threads: int | None = None) -> OcrEngine:
    """改前引擎：RapidOCR 默认配置（2 倍整图、检测 min=736），关闭新缓存/两阶段。"""
    from rapidocr_onnxruntime import RapidOCR

    options: dict = {}
    if threads is not None and int(threads) > 0:
        options["intra_op_num_threads"] = int(threads)
        options["inter_op_num_threads"] = 1
    return OcrEngine(
        engine=RapidOCR(**options),
        scale=2.0,
        fast=False,
        use_line_cache=False,
        threads=threads,
    )


def _warm(engine: OcrEngine) -> None:
    blank = np.full((48, 160, 3), 255, dtype=np.uint8)
    with suppress(Exception):
        engine.read(blank, (0, 0, 48, 160))
    with suppress(Exception):
        engine.line(blank, (0, 0, 48, 160))


# ---------------------------------------------------------------- 计时
def timed(fn, repeat: int = 1) -> tuple[float, float, object]:
    """返回 ``(wall_ms 中位数, cpu_ms 中位数, 最后一次结果)``。"""
    walls: list[float] = []
    cpus: list[float] = []
    result = None
    for _ in range(max(1, repeat)):
        started = time.perf_counter()
        cpu_started = time.process_time()
        result = fn()
        walls.append((time.perf_counter() - started) * 1000.0)
        cpus.append((time.process_time() - cpu_started) * 1000.0)
    return statistics.median(walls), statistics.median(cpus), result


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _speedup(before: float | None, after: float | None) -> str:
    if not before or not after:
        return "-"
    return f"{before / after:.1f}x"


# ---------------------------------------------------------------- 帧
def load_labels(frames_dir: Path) -> dict[str, str]:
    path = frames_dir / "labels.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def select_frames(frames_dir: Path) -> dict[str, Path]:
    """按标签挑代表帧；优先固定 step 号，保证改前/改后对比的是同一张图。"""
    preferred = {
        "action": "step_036.png",
        "event-choice": "step_039.png",
        "card-reward": "step_042.png",
        "lesson": "step_021.png",
        "loading": "step_038.png",
        "result-tap": "step_001.png",
        "action-confirm": "step_009.png",
        "story": "step_005.png",
    }
    labels = load_labels(frames_dir)
    images = sorted(frames_dir.glob("*.png"))
    if not images:
        images = sorted(FALLBACK_FRAMES.glob("step_*.png"))
    if not images:
        raise SystemExit(f"没有可用截图：{frames_dir}")
    by_name = {path.name: path for path in images}
    by_label: dict[str, Path] = {}
    for label, name in preferred.items():
        if name in by_name:
            by_label.setdefault(label, by_name[name])
    for path in images:
        label = labels.get(path.name)
        if label is None:
            label = "unknown"
        by_label.setdefault(label, path)
    return by_label


# ---------------------------------------------------------------- 测量
def measure(
    engine: OcrEngine,
    frames: dict[str, Path],
    *,
    before: bool,
    repeat: int,
) -> dict[str, float]:
    driver = ProduceDriver(ocr=engine, sleep=lambda _seconds: None)
    lesson_frame = frames.get("lesson") or frames.get("action")
    action_frame = frames.get("action") or frames.get("card-reward")
    event_frame = frames.get("event-choice") or action_frame
    reward_frame = frames.get("card-reward") or action_frame
    loading_frame = frames.get("loading") or frames.get("blank")
    result_frame = frames.get("result-tap") or frames.get("unknown")

    if action_frame is None:
        raise SystemExit("缺少行动页截图，无法基准")
    action = cv2.imread(str(action_frame))
    lesson = cv2.imread(str(lesson_frame)) if lesson_frame else action
    event = cv2.imread(str(event_frame)) if event_frame else action
    reward = cv2.imread(str(reward_frame)) if reward_frame else action
    loading = cv2.imread(str(loading_frame)) if loading_frame else action
    result = cv2.imread(str(result_frame)) if result_frame else action
    if action is None or lesson is None:
        raise SystemExit("截图读取失败")

    rows: dict[str, float] = {}
    cpu_rows: dict[str, float] = {}

    def record(name: str, fn, reps: int = 1) -> None:
        wall, cpu, _result = timed(fn, reps)
        rows[name] = wall
        cpu_rows[name] = cpu

    def reset_caches() -> None:
        cache = getattr(engine, "line_cache", None)
        if cache is not None:
            cache.clear()
        if driver.screen_cache is not None:
            driver.screen_cache.clear()

    # 单行冷/热：必须在其它探针之前测，否则 line_cold 会被前面调用预热成缓存命中。
    reset_caches()
    first, first_cpu, _ = timed(lambda: engine.line(action, ATTR_ROIS[0]), 1)
    start = time.perf_counter()
    cpu_start = time.process_time()
    engine.line(action, ATTR_ROIS[0])
    cached = (time.perf_counter() - start) * 1000.0
    cached_cpu = (time.process_time() - cpu_start) * 1000.0
    rows["line_cold"] = first
    rows["line_cached"] = cached
    cpu_rows["line_cold"] = first_cpu
    cpu_rows["line_cached"] = cached_cpu

    # 整屏/ROI：只在 2 张帧上测（单次 1-15s，跑多张太慢）
    record("full_read", lambda: engine.read(action), max(1, min(repeat, 2)))
    record("full_read_event", lambda: engine.read(event), max(1, min(repeat, 2)))
    record("full_read_result", lambda: engine.read(result), max(1, min(repeat, 2)))
    record("bottom_roi", lambda: engine.read(action, ProduceDriver.bottom_roi), max(1, min(repeat, 2)))
    record("corner_roi", lambda: engine.read(action, ProduceDriver.corner_roi), max(1, min(repeat, 2)))

    # 三维固定小框（清缓存后测冷路径）
    reset_caches()
    record(
        "attrs_fast",
        lambda: driver.read_attrs(action, allow_full=before, text_hint=None),
        repeat,
    )

    # 整图兜底（旧路径的 5-15s 元凶）
    record("attrs_full", lambda: driver._read_attrs_full(action), 1)

    # 课程 detail 4 探针
    reset_caches()
    record("card_detail", lambda: driver.card_detail_open(lesson), repeat)

    # 课程读屏
    reader = LessonReader(engine)
    reset_caches()
    record("lesson_read", lambda: reader.read(lesson), max(1, min(repeat, 2)))

    # 单步 OCR 组合
    if before:
        record(
            "step_action",
            lambda: (
                driver.read(action),
                driver.read_attrs(action, allow_full=True),
            ),
            max(1, min(repeat, 2)),
        )
        record(
            "step_event",
            lambda: (
                driver.read(event),
                driver.read_attrs(event, allow_full=True),
            ),
            max(1, min(repeat, 2)),
        )
        record(
            "step_reward",
            lambda: (
                driver.read(reward),
                driver.read_attrs(reward, allow_full=True),
            ),
            max(1, min(repeat, 2)),
        )
        record(
            "step_loading",
            lambda: driver.read(loading),
            max(1, min(repeat, 2)),
        )
        record(
            "step_lesson",
            lambda: (
                engine.read(lesson, ProduceDriver.corner_roi),
                reader.read(lesson),
                driver.read_attrs(lesson, allow_full=True),
                driver.card_detail_open(lesson),
                driver.exam_mode(lesson, []),
            ),
            max(1, min(repeat, 2)),
        )
    else:
        def after_action():
            lines = driver.read_fast(action)
            driver.read_attrs(action, text_hint=driver.text_of(lines))
            return lines

        def after_event():
            lines = driver.read_fast(event)
            driver.read_attrs(event, text_hint=driver.text_of(lines))
            return lines

        def after_reward():
            lines = driver.read_fast(reward)
            driver.read_attrs(reward, text_hint=driver.text_of(lines))
            return lines

        def after_loading():
            return driver.read_fast(loading)

        def after_lesson():
            corner = engine.read(lesson, ProduceDriver.corner_roi)
            state = reader.read(lesson)
            driver.read_attrs(lesson, text_hint=driver.text_of(corner))
            driver.card_detail_open(lesson)
            driver.exam_mode(lesson, corner)
            return state

        reset_caches()
        record("step_action", after_action, max(1, min(repeat, 2)))
        reset_caches()
        record("step_event", after_event, max(1, min(repeat, 2)))
        reset_caches()
        record("step_reward", after_reward, max(1, min(repeat, 2)))
        reset_caches()
        record("step_loading", after_loading, max(1, min(repeat, 2)))
        reset_caches()
        record("step_lesson", after_lesson, max(1, min(repeat, 2)))
    return rows, cpu_rows


# ---------------------------------------------------------------- 正确性检查
def verify(frames: dict[str, Path], engine: OcrEngine) -> tuple[int, int]:
    """关键词/屏幕类型检查：快速路径读出来的文字必须能支撑 decide 的原分支。"""
    driver = ProduceDriver(ocr=engine, sleep=lambda _seconds: None)
    expected_words = {
        "action": ("请选择行动", "授课", "训练", "外出", "咨询"),
        "lesson": ("剩余回合", "CLEAR", "PERFECT"),
        "loading": ("LOADING", "加载", "下载"),
        "event-choice": ("快进",),
        "card-reward": ("请选择要领取", "领取"),
        "result-tap": ("",),
        "action-confirm": ("",),
        "story": ("",),
        "blank": ("",),
        "unknown": ("",),
        "toast": ("",),
        "pause": ("",),
    }
    passed = 0
    total = 0
    for label, path in frames.items():
        words = expected_words.get(label, ("",))
        if not words or words == ("",):
            continue
        image = cv2.imread(str(path))
        if image is None:
            continue
        if label == "lesson":
            text = driver.text_of(engine.read(image, ProduceDriver.corner_roi))
        else:
            text = driver.text_of(driver.read_fast(image))
        total += 1
        ok = any(word in text for word in words)
        passed += int(ok)
        print(f"  verify {path.name:16s} {label:14s} {'OK' if ok else 'MISS'}  text={text[:60]}")
    return passed, total


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", action="store_true", help="只测改前")
    parser.add_argument("--after", action="store_true", help="只测改后")
    parser.add_argument("--repeat", type=int, default=3, help="每项重复次数（取中位数）")
    parser.add_argument("--frames-dir", default=str(DEFAULT_FRAMES))
    parser.add_argument("--verify", action="store_true", help="关键词/屏幕类型正确性检查")
    parser.add_argument("--cpu", action="store_true", help="额外打印 CPU 时间（多进程抢 CPU 时更稳）")
    parser.add_argument(
        "--threads",
        type=int,
        default=8,
        help="限制 onnxruntime 线程数（默认 8；0 = 用满全部核心）",
    )
    parser.add_argument("--json", default="", help="把结果写进 JSON 文件")
    args = parser.parse_args(argv)
    run_before = args.before or not args.after
    run_after = args.after or not args.before
    # 只测一边时减少重复，避免脚本跑太久
    repeat = max(1, args.repeat)
    frames_dir = Path(args.frames_dir)
    frames = select_frames(frames_dir)
    if not frames:
        print("没有可用截图")
        return 1
    print(f"截图目录: {frames_dir}  帧: {len(frames)}  重复: {repeat}")
    print(f"代表帧: {', '.join(f'{k}={v.name}' for k, v in sorted(frames.items()))}\n")

    results: dict[str, dict[str, float]] = {
        "before": {},
        "after": {},
        "before_cpu": {},
        "after_cpu": {},
    }
    if run_before:
        print("[1/2] 改前（整屏检测 + full fallback）…", flush=True)
        engine = make_before_engine(args.threads)
        _warm(engine)
        walls, cpus = measure(engine, frames, before=True, repeat=repeat)
        results["before"] = walls
        results["before_cpu"] = cpus
    if run_after:
        print("[2/2] 改后（分区快路径 + 语义缓存）…", flush=True)
        engine = make_after_engine(args.threads)
        _warm(engine)
        walls, cpus = measure(engine, frames, before=False, repeat=repeat)
        results["after"] = walls
        results["after_cpu"] = cpus
        if args.verify:
            print("\n正确性检查（快速路径文字能否支撑原 decide 分支）：")
            passed, total = verify(frames, engine)
            print(f"  关键词检查: {passed}/{total}")
            results["verify"] = {"passed": passed, "total": total}  # type: ignore[assignment]

    names = list(dict.fromkeys([*results["before"], *results["after"]]))
    print("\n" + "=" * 78)
    print(f"{'项目':22s} {'改前(ms)':>10s} {'改后(ms)':>10s} {'加速':>8s}")
    print("-" * 78)
    for name in names:
        before = results["before"].get(name)
        after = results["after"].get(name)
        print(f"{name:22s} {_fmt(before):>10s} {_fmt(after):>10s} {_speedup(before, after):>8s}")
    print("=" * 78)
    if args.cpu:
        print(f"\n{'项目':22s} {'改前CPU':>10s} {'改后CPU':>10s} {'加速':>8s}")
        print("-" * 78)
        for name in names:
            before = results["before_cpu"].get(name)
            after = results["after_cpu"].get(name)
            print(f"{name:22s} {_fmt(before):>10s} {_fmt(after):>10s} {_speedup(before, after):>8s}")
        print("=" * 78)
    if "step_action" in results["after"]:
        step = results["after"]["step_action"]
        print(f"改后行动页单步 OCR ≈ {step:.0f} ms（目标 ≤1500ms）")
    if "step_lesson" in results["after"]:
        print(f"改后课程页单步 OCR ≈ {results['after']['step_lesson']:.0f} ms")
    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"结果已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
