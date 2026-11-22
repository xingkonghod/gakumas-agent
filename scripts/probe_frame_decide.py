"""把真机截图按**生产链路**回放一遍：``read_fast``/``read`` → ``ProduceDriver.decide``。

用途：离线复现/定位某一步"为什么点这里"（F#43 就是这么查出"结果页"其实是外出饮料选择屏）。
不碰游戏、不点鼠标：只打印 OCR 行、屏幕分类、动作和（假 agent 记录的）点击坐标。

用法::

    # 单帧（data/auto/step_021.png）
    python scripts/probe_frame_decide.py 21

    # 多帧 / 任意路径
    python scripts/probe_frame_decide.py 20 21 29
    python scripts/probe_frame_decide.py data\\manual\\182343.png

    # 连续决策（同一个 driver 上喂同一帧 N 次，可看两步点击/确认逻辑）
    python scripts/probe_frame_decide.py 21 --repeat 2

    # 指定 OCR 配置（默认按 OcrEngine 规则：configs/ocr_jp.yaml > 内置中文模型）
    python scripts/probe_frame_decide.py 21 --ocr-config configs/ocr_jp.example.yaml
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.tasks.produce_ui import ProduceDriver
from gkagent.vision.ocr import OcrEngine


@dataclass
class FakeDevice:
    clicks: list[tuple[int, int]] = field(default_factory=list)

    def click_force(self, x: int, y: int) -> None:
        self.clicks.append((int(x), int(y)))


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)


def resolve_frame(arg: str) -> Path:
    """参数是纯数字时按 data/auto/step_NNN.png 解释，否则当路径。"""
    if arg.isdigit():
        return ROOT / "data" / "auto" / f"step_{int(arg):03d}.png"
    path = Path(arg)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", nargs="+", help="step 编号（如 21）或截图路径")
    parser.add_argument("--repeat", type=int, default=1, help="每帧连续决策次数（默认 1）")
    parser.add_argument("--ocr-config", default=None, help="显式 OCR 配置路径；默认自动发现")
    parser.add_argument("--full-read", action="store_true", help="用整屏 read 代替 read_fast")
    args = parser.parse_args()

    engine = OcrEngine(config_path=args.ocr_config) if args.ocr_config else OcrEngine()
    print(f"[ocr] 模型 = {engine.describe_model()}")
    missing = 0
    for arg in args.frames:
        path = resolve_frame(arg)
        if not path.is_file():
            print(f"--- {arg}: 缺帧 {path}")
            missing += 1
            continue
        image = cv2.imread(str(path))
        if image is None:
            print(f"--- {arg}: 图像读不出 {path}")
            missing += 1
            continue
        driver = ProduceDriver(ocr=engine, sleep=lambda _seconds: None)
        agent = FakeAgent()
        lines = driver.read(image) if args.full_read else driver.read_fast(image)
        text = driver.text_of(lines)
        print(f"--- {path.name}: {len(lines)} 行, text={text[:160]!r}")
        for index in range(args.repeat):
            tick = driver.decide(agent, lines, image)
            print(
                f"    decide#{index + 1}: {tick.screen}/{tick.action}"
                f" clicks={agent.device.clicks} detail={tick.detail!r}"
            )
        for line in lines:
            if line.text.strip():
                x, y, w, h = line.box
                print(f"    y={y:4d} x={x:4d} w={w:3d} h={h:3d} {line.text!r}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
