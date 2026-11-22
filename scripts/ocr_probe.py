"""读一张游戏截图的 OCR 文本——验证日文模型、排查读字问题。

用法::

    # 默认：用 OcrEngine 的配置解析（显式 > GKAGENT_OCR_CONFIG > configs/ocr_jp.yaml > 内置中文）
    .venv\\Scripts\\python.exe scripts\\ocr_probe.py data/auto/step_025.png

    # 指定模型配置（例如先验证模板/魔改 MAA 的日文模型，不影响默认）
    .venv\\Scripts\\python.exe scripts\\ocr_probe.py data/auto/step_025.png --config configs/ocr_jp.example.yaml

    # 只读某块区域 / 输出 JSON / 看每行耗时
    .venv\\Scripts\\python.exe scripts\\ocr_probe.py IMG --roi 0,600,720,680 --json out/ocr.json

输出：每行 ``x,y 置信度 文本``（按 y 再 x 排序），最后一行是拼好的全文，方便 grep 关键词。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2


def parse_roi(value: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in value.replace("，", ",").split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("ROI 格式：x,y,w,h（例如 0,600,720,680）")
    return parts[0], parts[1], parts[2], parts[3]


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="OCR 单图探针")
    parser.add_argument("image", help="截图路径（720x1280）")
    parser.add_argument("--config", default=None, help="OCR 模型 YAML（默认按 OcrEngine 规则解析）")
    parser.add_argument("--roi", type=parse_roi, default=None, help="只读该区域 x,y,w,h")
    parser.add_argument("--scale", type=float, default=None, help="识别放大倍率（默认 2.0）")
    parser.add_argument("--min-score", type=float, default=0.4, help="低于该置信度的行丢弃")
    parser.add_argument("--threads", type=int, default=8, help="onnxruntime 线程数（0=默认）")
    parser.add_argument("--json", default="", help="把结果写进 JSON 文件")
    args = parser.parse_args(argv)

    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"截图不存在：{image_path}", file=sys.stderr)
        return 2
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"截图读取失败：{image_path}", file=sys.stderr)
        return 2

    from gkagent.vision.ocr import OcrEngine  # 慢导入放在参数校验后

    kwargs: dict = {"min_score": args.min_score}
    if args.config is not None:
        kwargs["config_path"] = args.config
    if args.scale is not None:
        kwargs["scale"] = args.scale
    if args.threads and args.threads > 0:
        kwargs["threads"] = args.threads
    engine = OcrEngine(**kwargs)

    print(f"截图：{image_path}  {image.shape[1]}x{image.shape[0]}")
    print(f"模型：{engine.describe_model()}")
    started = time.perf_counter()
    lines = engine.read(image, args.roi)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    lines.sort(key=lambda line: (line.box[1], line.box[0]))

    for line in lines:
        x, y, _w, _h = line.box
        print(f"  {x:4d},{y:4d}  {line.score:.2f}  {line.text}")
    text = " ".join(line.text for line in lines)
    print(f"\n共 {len(lines)} 行，耗时 {elapsed_ms:.0f} ms")
    print(f"全文：{text}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "image": str(image_path),
                    "model": engine.describe_model(),
                    "elapsed_ms": round(elapsed_ms, 1),
                    "roi": args.roi,
                    "lines": [
                        {"text": line.text, "score": line.score, "box": list(line.box)}
                        for line in lines
                    ],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"JSON 已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
