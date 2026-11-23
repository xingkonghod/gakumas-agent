"""C1 每步可复盘：离线回放 step_trace.jsonl，逐步回答「点了哪/为什么/预算/兑现」。

用法：
    .venv\\Scripts\\python.exe scripts\\replay_steps.py                 # 最近一局
    .venv\\Scripts\\python.exe scripts\\replay_steps.py --episode ep-xxx
    .venv\\Scripts\\python.exe scripts\\replay_steps.py --anomalies     # 只看 lost/failed/stuck
    .venv\\Scripts\\python.exe scripts\\replay_steps.py --json          # 机器可读

数据源 = auto_produce 每步写的 ``data/step_trace.jsonl``（StepTrace：
screen/action/point/reason/engine_note/expect_kind/expect_words/outcome/tries）。
真机跑局后不需要任何游戏环境就能复盘每一步（真机验收留阶段 E）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.runtime.trace import TraceLog, format_trace, summarize_traces


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="离线复盘 auto_produce 每步动作轨迹")
    parser.add_argument("--trace", default=str(ROOT / "data" / "step_trace.jsonl"))
    parser.add_argument("--episode", default=None, help="只看这一局（默认最近一局）")
    parser.add_argument("--anomalies", action="store_true", help="只打印 lost/failed/stuck 步")
    parser.add_argument("--json", action="store_true", help="输出 JSON（rows+summary）")
    parser.add_argument("--limit", type=int, default=None, help="最多打印多少步")
    args = parser.parse_args(argv)

    rows = TraceLog(args.trace).read()
    if not rows:
        print(f"没有轨迹数据：{args.trace}", file=sys.stderr)
        return 2
    episode = args.episode or rows[-1].get("episode")
    rows = [row for row in rows if row.get("episode") == episode]
    if args.limit:
        rows = rows[-args.limit :]
    summary = summarize_traces(rows)
    if args.json:
        print(json.dumps({"episode": episode, "rows": rows, "summary": summary},
                         ensure_ascii=False, indent=1))
        return 0
    print(f"== 复盘 {episode}（{len(rows)} 步）==")
    for row in rows:
        if args.anomalies and row not in summary["anomalies"]:
            continue
        print(format_trace(row))
    outcomes = " ".join(f"{key}={value}" for key, value in sorted(summary["outcomes"].items()))
    print(f"-- 汇总: {outcomes or '（无互验记录）'}")
    if summary["anomalies"]:
        print(f"-- ⚠️ 异常 {len(summary['anomalies'])} 步（lost/failed/stuck），逐条见 --anomalies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
