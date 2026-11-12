"""OCR 速度/精度基准：不同 scale 下读同一批游戏截图，比较耗时与关键词命中。"""

from __future__ import annotations

import glob
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

from gkagent.vision.ocr import OcrEngine  # noqa: E402

KEYS = ("领取", "请选择", "技能卡", "训练", "剩余回合数", "下一步", "确定", "主页", "活动奖励")


def main() -> None:
    files = sorted(glob.glob(str(ROOT / "data" / "auto" / "step_*.png")))[-8:]
    if not files:
        print("no frames")
        return
    engines = {scale: OcrEngine(scale=scale) for scale in (2.0, 1.5, 1.0)}
    for path in files:
        image = cv2.imread(path)
        row = [Path(path).name]
        for scale, engine in engines.items():
            start = time.perf_counter()
            lines = engine.read(image)
            elapsed = (time.perf_counter() - start) * 1000
            text = " ".join(line.text for line in lines)
            hits = sum(1 for key in KEYS if key in text)
            row.append(f"s={scale}: {elapsed:5.0f}ms hits={hits:2d} lines={len(lines):2d}")
        print(" | ".join(row))
    print("done")


if __name__ == "__main__":
    main()
