"""课程读屏两条路径的耗时/质量对比：整块 OCR vs 轮廓定框 + 单行识别。

用法：python scripts/bench_lesson_read.py [image]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

from gkagent.data.cards_db import CardLibrary  # noqa: E402
from gkagent.data.master import MasterData  # noqa: E402
from gkagent.vision.cards import scan_hand  # noqa: E402
from gkagent.vision.lesson import LessonReader, _parse_int, _parse_score  # noqa: E402
from gkagent.vision.ocr import OcrEngine  # noqa: E402


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = Path(argv[0]) if argv else ROOT / "data" / "live_lesson.png"
    image = cv2.imread(str(path))
    if image is None:
        print("找不到图片", path)
        return 1
    library = CardLibrary(MasterData(ROOT / "data" / "master"))
    engine = OcrEngine()
    reader = LessonReader(engine, cards=library)

    start = time.perf_counter()
    lines = engine.read(image, (0, 1060, 720, 100))
    ocr_ms = (time.perf_counter() - start) * 1000
    print(f"整块 OCR 卡名: {ocr_ms:.0f}ms, {len(lines)} 行")
    for line in lines:
        print("   ", line.text, line.box)

    start = time.perf_counter()
    scan = scan_hand(image)
    scan_ms = (time.perf_counter() - start) * 1000
    print(f"\nscan_hand 轮廓定框: {scan_ms:.0f}ms, {len(scan.cards)} 张")
    for card in scan.cards:
        print("   ", tuple(int(v) for v in card.box), "cost_read=", card.cost)

    start = time.perf_counter()
    engine2 = OcrEngine(scale=1.0)
    lines2 = engine2.read(image, (0, 1060, 720, 100))
    fast_ms = (time.perf_counter() - start) * 1000
    print(f"\n整块 OCR(scale=1.0): {fast_ms:.0f}ms, {len(lines2)} 行")
    for line in lines2:
        print("   ", line.text, line.box)

    # 轮廓定框 + 单行识别（每条 ~20ms）
    start = time.perf_counter()
    names = []
    for card in scan.cards:
        x, y, w, h = card.box
        name_line = engine.line(image, (x + 6, y + 190, w - 12, 36))
        score_line = engine.line(image, (x, y - 26, 112, 62), digits_only=True)
        cost_line = engine.line(image, (x + 118, y + 160, 74, 52), digits_only=True)
        names.append(
            (
                name_line.text if name_line else "",
                _parse_score(score_line.text if score_line else "")[0],
                _parse_int(cost_line.text if cost_line else ""),
            )
        )
    percard_ms = (time.perf_counter() - start) * 1000
    print(f"\n定框+单行识别: {percard_ms:.0f}ms")
    for row in names:
        print("   ", row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
