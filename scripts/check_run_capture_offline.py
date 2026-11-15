"""离线验证跑局数据读取（不碰游戏窗口，只用真机截图）。

用法（venv，任何 cwd）：
    .venv\\Scripts\\python.exe scripts\\check_run_capture_offline.py

覆盖三张真机 720x1280 截图：

- ``data/manual/182343.png``：行动页「期中截止 4周」→ 第 2 周（mid）；
- ``data/manual/184806.png``：考试结算屏 1st..6th → rank=3 / 263Pt / 全员分数；
- ``data/manual/190647.png``：最终结算屏 → grade=C+ / eval_points=5577。

截图不入库（data/manual 是本地留档），缺图按 SKIP 处理。退出码 0 = 全部通过。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2

from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrEngine

WEEK_CASE = ("data/manual/182343.png", 2, "mid")
EXAM_CASE = ("data/manual/184806.png", 3, 263, [581, 387, 263, 229, 197])
FINAL_CASE = ("data/manual/190647.png", "C+", 5577)


def _read(name: str) -> object | None:
    path = ROOT / name
    image = cv2.imread(str(path))
    if image is None:
        print(f"[SKIP] 读不到图片（data/manual 是本地留档，不入库）：{path}")
        return None
    return image


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    driver = ProduceDriver(ocr=OcrEngine())
    failures: list[str] = []
    skipped = 0

    week_image = _read(WEEK_CASE[0])
    if week_image is None:
        skipped += 1
    else:
        text = driver.text_of(driver.read_fast(week_image))
        week, phase = driver.read_week(week_image, text)
        ok = (week, phase) == (WEEK_CASE[1], WEEK_CASE[2])
        print(f"行动页 182343: week={week} phase={phase} → {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"week 期望 {(WEEK_CASE[1], WEEK_CASE[2])}，实际 {(week, phase)}")

    exam_image = _read(EXAM_CASE[0])
    if exam_image is None:
        skipped += 1
    else:
        result = driver.read_exam_result(exam_image)
        expected = {"rank": EXAM_CASE[1], "score": EXAM_CASE[2], "others": EXAM_CASE[3]}
        ok = result is not None and all(result.get(key) == value for key, value in expected.items())
        print(f"考试结算屏 184806: {result} → {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"考试结算期望 {expected}，实际 {result}")

    final_image = _read(FINAL_CASE[0])
    if final_image is None:
        skipped += 1
    else:
        result = driver.read_final_result(final_image)
        ok = result is not None and result.get("grade") == FINAL_CASE[1] and result.get("eval_points") == FINAL_CASE[2]
        print(f"最终结算屏 190647: {result} → {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"最终结算期望 grade={FINAL_CASE[1]} eval_points={FINAL_CASE[2]}，实际 {result}")

    total = 3 - skipped
    print(f"\n汇总：{total - len(failures)}/{total} 张截图解析正确" + (f"（{skipped} 张缺图跳过）" if skipped else ""))
    for failure in failures:
        print(f"  - {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
