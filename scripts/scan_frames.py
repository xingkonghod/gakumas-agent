"""把本地截图批量过一遍**生产链路**（``read_fast``/``read`` → ``decide``），按屏幕分类挑素材。

用途（WORKPLAN A4）：从历史真机截图里找某类屏（剧情二选一 / 课程 buff / 结果页 / 外出事件 /
考试浮层 / 回合结束确认框……），给 ``tests/fixtures/`` 选回归素材。只读截图、不碰游戏、不点鼠标。

和 :mod:`scan_event_frames` 的区别：那个是**廉价小框**扫「事件选项屏」；本脚本走完整
``ProduceDriver`` 判定，输出 ``screen/action/点击坐标/读到的文本``，能直接当 fixture 候选。

用法::

    # 扫默认目录（data/manual + data/arun + data/auto），只打印汇总
    python scripts/scan_frames.py

    # 只要某几类屏（逗号分隔），打印命中帧
    python scripts/scan_frames.py data\\auto --screen story,event-choice,result-tap

    # 按文本关键词找（中文/日文都行）
    python scripts/scan_frames.py data\\manual --contains 回合结束 得分+

    # 全量结果写 JSON（含每帧的 OCR 文本/点击坐标，供后续挑选）
    python scripts/scan_frames.py data\\auto data\\manual --json out\\scan_frames.json

    # 扫单个目录、只扫前 100 张
    python scripts/scan_frames.py data\\keep_ep1_190658 --limit 100

输出字段：``path/screen/action/clicks/detail/ok/text/lines``。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrEngine

DEFAULT_DIRS = ("data/manual", "data/arun", "data/auto")


@dataclass
class FakeDevice:
    clicks: list[tuple[int, int]] = field(default_factory=list)
    swipes: list[tuple[int, int, int, int]] = field(default_factory=list)

    def click_force(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))

    def click(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.swipes.append((int(x1), int(y1), int(x2), int(y2)))


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)


def frames_of(value: str) -> list[Path]:
    """把一个参数展开成截图列表：支持目录、单张截图、以及 glob（如 ``data/auto/step_*.png``）。"""
    if any(ch in value for ch in "*?["):
        pattern = value if Path(value).is_absolute() else str(ROOT / value)
        return sorted(Path(p) for p in glob.glob(pattern))
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    return sorted(path.glob("*.png"))


def classify(
    engine: OcrEngine,
    path: Path,
    *,
    full_read: bool = False,
) -> dict | None:
    """单帧走生产链路，返回分类记录；图像读不出返回 None。"""
    image = cv2.imread(str(path))
    if image is None:
        return None
    driver = ProduceDriver(ocr=engine, sleep=lambda _seconds: None)
    lines = driver.read(image) if full_read else driver.read_fast(image)
    agent = FakeAgent()
    tick = driver.decide(agent, lines, image)
    return {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "screen": tick.screen,
        "action": tick.action,
        "clicks": agent.device.clicks,
        "detail": tick.detail,
        "ok": tick.ok,
        "text": driver.text_of(lines)[:400],
        "lines": len(lines),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dirs", nargs="*", help=f"要扫的目录或单张截图（默认 {DEFAULT_DIRS}）")
    parser.add_argument("--screen", default=None, help="只打印这些 screen（逗号分隔，如 story,event-choice）")
    parser.add_argument("--contains", nargs="+", default=None, help="只打印文本含这些关键词的帧（任一命中）")
    parser.add_argument("--json", default=None, help="把全部结果写到该 JSON 路径")
    parser.add_argument("--limit", type=int, default=0, help="每个目录最多扫多少张（0=全部）")
    parser.add_argument("--full-read", action="store_true", help="用整屏 read 代替 read_fast（更慢更全）")
    parser.add_argument("--ocr-config", default=None, help="显式 OCR 配置；默认按 OcrEngine 规则自动发现")
    args = parser.parse_args()

    engine = OcrEngine(config_path=args.ocr_config) if args.ocr_config else OcrEngine()
    print(f"[ocr] 模型 = {engine.describe_model()}", flush=True)

    wanted = {name.strip() for name in (args.screen or "").split(",") if name.strip()}
    records: list[dict] = []
    scanned = 0
    t_start = time.perf_counter()
    for value in args.dirs or DEFAULT_DIRS:
        files = frames_of(value)
        if args.limit:
            files = files[: args.limit]
        if not files:
            print(f"[skip] {value}: 没有 png", flush=True)
            continue
        print(f"[scan] {value}: {len(files)} 张", flush=True)
        for path in files:
            record = classify(engine, path, full_read=args.full_read)
            scanned += 1
            if record is None:
                continue
            records.append(record)
            hit = (not wanted or record["screen"] in wanted) and (
                not args.contains or any(word in record["text"] for word in args.contains)
            )
            if hit:
                clicks = record["clicks"][-1] if record["clicks"] else None
                print(
                    f"{record['path']:44s} {record['screen']:14s} {record['action']:16s}"
                    f" click={clicks} text={record['text'][:110]!r}",
                    flush=True,
                )
            if scanned % 100 == 0:
                speed = scanned / max(time.perf_counter() - t_start, 1e-6)
                print(f"  ...{scanned} 帧 ({speed:.1f} 帧/s)", flush=True)
    elapsed = time.perf_counter() - t_start
    print(f"\n[scan] 完成：{scanned} 帧，{elapsed:.1f}s（{scanned / max(elapsed, 1e-6):.1f} 帧/s）")
    if args.json:
        out = Path(args.json)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[scan] 结果已写入 {out}（{len(records)} 条）")

    # 按 screen/action 汇总，方便一眼看数据里有哪些屏
    summary: dict[str, dict[str, int]] = {}
    for record in records:
        bucket = summary.setdefault(record["screen"], {})
        bucket[record["action"]] = bucket.get(record["action"], 0) + 1
    if summary:
        print("[scan] 分类汇总：")
        for screen in sorted(summary):
            actions = ", ".join(f"{a}×{n}" for a, n in sorted(summary[screen].items(), key=lambda kv: -kv[1]))
            print(f"  {screen:16s} {actions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
