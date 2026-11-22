"""扫描本地截图（data/manual、data/arun、data/auto 等），找「事件选项屏」帧。

原理：用生产快速读屏的固定小框（``FAST_EVENT_ROW_BOXES`` + ``FAST_EVENT_FAST_BOX``）做
廉价探测（每帧 ~0.1s），命中关键词才打印——不整屏 OCR，扫几千张也很快。
用来给离线回放/回归 fixture 挑素材（WORKPLAN A4）。

用法::

    # 默认扫 data/manual + data/arun + data/auto
    python scripts/scan_event_frames.py

    # 只扫某个目录 / 只找饮料事件
    python scripts/scan_event_frames.py data\\auto --keywords ドリンク ヨーグルト パフェ ハンバーグ

    # 任何带「快进」的帧（剧情/事件屏都算）
    python scripts/scan_event_frames.py data\\auto --fast-only
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.tasks.produce_ui import (
    FAST_EVENT_FAST_BOX,
    FAST_EVENT_ROW_BOXES,
)
from gkagent.vision.ocr import OcrEngine

DEFAULT_DIRS = ("data/manual", "data/arun", "data/auto")
DEFAULT_KEYWORDS = ("ドリンク", "ヨーグルト", "パフェ", "ハンバーグ", "飲み物", "快进", "快進")


def probe(engine: OcrEngine, image) -> tuple[list[str], str]:
    rows: list[str] = []
    for roi in FAST_EVENT_ROW_BOXES:
        try:
            line = engine.line(image, roi, digits_only=False)
        except Exception:  # noqa: BLE001 - 单框失败不影响扫描
            line = None
        if line is not None and line.text:
            rows.append(line.text.strip())
    fast = ""
    try:
        line = engine.line(image, FAST_EVENT_FAST_BOX, digits_only=False)
        fast = line.text.strip() if line is not None and line.text else ""
    except Exception:  # noqa: BLE001, S110 - 单框识别失败不影响整帧扫描
        pass
    return rows, fast


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dirs", nargs="*", help=f"要扫的目录（默认 {DEFAULT_DIRS}）")
    parser.add_argument("--keywords", nargs="+", default=list(DEFAULT_KEYWORDS))
    parser.add_argument("--fast-only", action="store_true", help="只要读到「快进」的帧")
    parser.add_argument("--ocr-config", default=None, help="显式 OCR 配置路径；默认自动发现")
    args = parser.parse_args()

    engine = OcrEngine(config_path=args.ocr_config) if args.ocr_config else OcrEngine()
    print(f"[ocr] 模型 = {engine.describe_model()}")
    directories = [Path(d) if Path(d).is_absolute() else ROOT / d for d in (args.dirs or DEFAULT_DIRS)]
    hits = 0
    for directory in directories:
        files = sorted(directory.glob("*.png")) if directory.is_dir() else []
        for index, path in enumerate(files):
            image = cv2.imread(str(path))
            if image is None:
                continue
            rows, fast = probe(engine, image)
            joined = " ".join(rows)
            hit = bool(fast) if args.fast_only else any(k in joined for k in args.keywords)
            if hit:
                stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%m-%d %H:%M:%S")
                print(f"{path.name:24s} {stamp} rows={rows} fast={fast!r}")
                hits += 1
            if (index + 1) % 200 == 0:
                print(f"  ...{directory.name}: {index + 1}/{len(files)}", flush=True)
    print(f"命中 {hits} 帧（扫了 {sum(len(list(d.glob('*.png'))) for d in directories if d.is_dir())} 张）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
