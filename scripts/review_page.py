"""T7③ 自动复盘页 CLI：每局生成逐回合 + 逐步轨迹的自包含 HTML。

用法：
    .venv\\Scripts\\python.exe scripts\\review_page.py --episode ep-xxx
    .venv\\Scripts\\python.exe scripts\\review_page.py --record data\\runs\\ep-xxx.json --out out\\review
    .venv\\Scripts\\python.exe scripts\\review_page.py --episode ep-xxx --trace data\\step_trace.jsonl

数据源 = data/runs/<ep>.json（run_record）+ data/step_trace.jsonl（C1 逐步轨迹，
按 episode 过滤）。输出默认 out/review/<ep>.html（gitignore）；浏览器直接打开，
行内标注 → 导出 annotations_<ep>.json → scripts/annotations_to_regression.py 转回归。
auto_produce 局末也会自动生成（[review] 日志行）。纯离线，不碰游戏。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.report.review_page import write_review_page
from gkagent.runtime.trace import TraceLog

RUNS = ROOT / "data" / "runs"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="生成一局自动复盘页（T7③）")
    parser.add_argument("--episode", default=None)
    parser.add_argument("--record", default=None, help="直接指定记录 JSON 路径")
    parser.add_argument("--runs-dir", default=str(RUNS))
    parser.add_argument("--trace", default=str(ROOT / "data" / "step_trace.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "out" / "review"), help="输出目录")
    parser.add_argument("--trace-source", default="live", choices=("live", "synthetic-demo"))
    args = parser.parse_args(argv)

    if args.record:
        path = Path(args.record)
    elif args.episode:
        path = Path(args.runs_dir) / f"{args.episode}.json"
    else:
        candidates = sorted(Path(args.runs_dir).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print(f"没有跑局记录：{args.runs_dir}", file=sys.stderr)
            return 2
        path = candidates[0]
    if not path.exists():
        print(f"找不到记录：{path}", file=sys.stderr)
        return 2
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不了 {path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(record, dict):
        print(f"{path} 顶层不是对象", file=sys.stderr)
        return 2

    episode = str(record.get("episode") or path.stem)
    rows = [row for row in TraceLog(args.trace).read() if row.get("episode") == episode]
    out_path = write_review_page(record, rows, out_dir=args.out, trace_source=args.trace_source)
    print(f"✅ 复盘页: {out_path}（{len(rows)} 步轨迹；浏览器打开即可标注/导出）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
