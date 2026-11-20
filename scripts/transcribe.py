"""B 站视频转写：faster-whisper（CPU，中文）。

用法：python scripts/transcribe.py data/video/xxx.mp3 [--model small]
输出：同目录下 <name>.transcript.txt（带时间戳）
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute", default="int8")
    args = parser.parse_args(argv)

    from faster_whisper import WhisperModel

    audio = Path(args.audio)
    t0 = time.perf_counter()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute)
    segments, info = model.transcribe(
        str(audio), language="zh", vad_filter=True, beam_size=5,
        initial_prompt="学园偶像大师，学マス，初星攻略站，出牌算法，神经网络，UINet，PIMC，强度榜",
    )
    print(f"模型 {args.model} | 时长 {info.duration:.1f}s | 语言 {info.language}", flush=True)
    lines: list[str] = []
    for seg in segments:
        stamp = f"[{int(seg.start // 60):02d}:{seg.start % 60:05.2f}]"
        line = f"{stamp} {seg.text.strip()}"
        print(line, flush=True)
        lines.append(line)
    out = audio.with_suffix(".transcript.txt")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n完成，{time.perf_counter() - t0:.1f}s -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
