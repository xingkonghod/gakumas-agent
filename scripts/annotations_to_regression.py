"""T7③ 标注闭环：复盘页导出的人工标注 JSON → 回归用例夹具。

用法：
    .venv\\Scripts\\python.exe scripts\\annotations_to_regression.py annotations_ep-xxx.json
    .venv\\Scripts\\python.exe scripts\\annotations_to_regression.py ann.json --record data\\runs\\ep-xxx.json
    .venv\\Scripts\\python.exe scripts\\annotations_to_regression.py ann.json --fixture tests\\fixtures\\review_regressions.json

只转 verdict=bad 且带 expected 的标注：周/考试/结算修正 → 追加观测事件重放整态冻结；
逐步修正 → summarize_traces 分类结论冻结。用例按 id 去重合并进夹具（新覆盖旧），
tests/test_review_regressions.py 逐条重算比对——以后重放/复盘口径变了立刻红。
夹具里 provenance=synthetic-demo 的条目是演示闭环的合成样例，不是真机 ground truth。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.report.annotations import cases_from_annotations, merge_cases
from gkagent.runtime.trace import TraceLog

RUNS = ROOT / "data" / "runs"
FIXTURE = ROOT / "tests" / "fixtures" / "review_regressions.json"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="人工标注 → 回归用例（T7③ 闭环）")
    parser.add_argument("annotations", help="复盘页导出的 annotations_<ep>.json")
    parser.add_argument("--record", default=None, help="该局记录（默认 data/runs/<episode>.json）")
    parser.add_argument("--trace", default=str(ROOT / "data" / "step_trace.jsonl"))
    parser.add_argument("--fixture", default=str(FIXTURE))
    parser.add_argument("--dry-run", action="store_true", help="只打印用例，不写夹具")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(Path(args.annotations).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不了标注 {args.annotations}: {exc}", file=sys.stderr)
        return 2
    episode = payload.get("episode") if isinstance(payload, dict) else None
    record_path = Path(args.record) if args.record else RUNS / f"{episode}.json"
    if not record_path.exists():
        print(f"找不到跑局记录：{record_path}（用 --record 指定）", file=sys.stderr)
        return 2
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读不了 {record_path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(record, dict):
        print(f"{record_path} 顶层不是对象", file=sys.stderr)
        return 2

    rows = [row for row in TraceLog(args.trace).read() if row.get("episode") == episode]
    try:
        cases = cases_from_annotations(payload, record, rows)
    except ValueError as exc:
        print(f"标注不合法: {exc}", file=sys.stderr)
        return 2
    if not cases:
        print("没有可转用例的标注（需要 verdict=bad 且带 expected）")
        return 0

    fixture_path = Path(args.fixture)
    fixture = None
    if fixture_path.exists():
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fixture = None
    merged = merge_cases(fixture, cases)
    if args.dry_run:
        print(json.dumps(merged, ensure_ascii=False, indent=1))
        return 0
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = fixture_path.with_name(fixture_path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(merged, ensure_ascii=False, indent=1) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, fixture_path)
    print(f"✅ {len(cases)} 条标注 → 回归用例；夹具共 {len(merged['cases'])} 条: {fixture_path}")
    for case in cases:
        print(f"   {case['id']}（{case['kind']}）{case['comment']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
