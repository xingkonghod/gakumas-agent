"""T7② 纯函数状态重放 CLI：同观测序列 → 同状态 → 逐步比对。

用法：
    .venv\\Scripts\\python.exe scripts\\replay_run.py --episode ep-xxx
    .venv\\Scripts\\python.exe scripts\\replay_run.py --record data\\runs\\ep-xxx.json --verify
    .venv\\Scripts\\python.exe scripts\\replay_run.py --episode ep-a --compare data\\runs\\ep-b.json
    .venv\\Scripts\\python.exe scripts\\replay_run.py --episode ep-xxx --json

默认打印逐事件状态推进 + 终态摘要 + 三方对账（events 重放 vs 旧格式重建 vs 记录汇总）。
``--verify``：重放两遍指纹逐位相等 + 三方对账一致 → 退出码 0，否则 1（DoD 可脚本化）。
``--compare``：两条观测序列逐步比对，打印首个分歧步与字段差异；全等退出 0，否则 1。
纯离线：只读 data/runs/*.json，不碰游戏/不联网/不改任何规则。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.data.run_replay import (
    compare_replays,
    consistency_check,
    events_of,
    fingerprint,
    replay,
    state_to_dict,
)

RUNS = ROOT / "data" / "runs"


def _load_record(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} 顶层不是对象")  # noqa: TRY004 - 调用方按 ValueError 处理坏数据
    return payload


def _latest_record(runs_dir: Path) -> Path | None:
    candidates = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _state_line(state) -> str:
    data = state_to_dict(state)
    attrs = "/".join(str(v) for v in data["attrs"]) if data["attrs"] else "null"
    return (
        f"seq={data['seq']:>3} week={data['week']!s:>4} phase={data['phase']!s:>5} "
        f"attrs={attrs:>11} stamina={data['stamina']!s:>4} "
        f"lesson={data['lesson_total']:>5} exams={len(data['exams'])} "
        f"weeks={data['weeks_seen']} dup={data['duplicates']} miss={data['missing_fields']}"
    )


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="纯函数重放跑局观测序列（T7②）")
    parser.add_argument("--episode", default=None, help="data/runs/<episode>.json")
    parser.add_argument("--record", default=None, help="直接指定记录 JSON 路径")
    parser.add_argument("--runs-dir", default=str(RUNS))
    parser.add_argument("--verify", action="store_true", help="重放两遍指纹相等 + 三方对账（退出码=DoD）")
    parser.add_argument("--compare", default=None, help="与另一条记录逐步比对")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--limit", type=int, default=None, help="最多打印多少步状态")
    args = parser.parse_args(argv)

    if args.record:
        path = Path(args.record)
    elif args.episode:
        path = Path(args.runs_dir) / f"{args.episode}.json"
    else:
        latest = _latest_record(Path(args.runs_dir))
        if latest is None:
            print(f"没有跑局记录：{args.runs_dir}", file=sys.stderr)
            return 2
        path = latest
    if not path.exists():
        print(f"找不到记录：{path}", file=sys.stderr)
        return 2
    try:
        record = _load_record(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"读不了 {path}: {exc}", file=sys.stderr)
        return 2

    events, source = events_of(record)
    states = replay(events)
    again = replay(events)
    check = consistency_check(record)
    deterministic = fingerprint(states) == fingerprint(again)

    if args.compare:
        other_path = Path(args.compare)
        if not other_path.exists():
            print(f"找不到对照记录：{other_path}", file=sys.stderr)
            return 2
        other_events, _ = events_of(_load_record(other_path))
        comparison = compare_replays(states, replay(other_events))
        if args.json:
            print(json.dumps({"compare": comparison}, ensure_ascii=False, indent=1))
        else:
            print(f"== 逐步比对 {path.name} vs {other_path.name} ==")
            print(f"步数 {comparison['steps_a']} vs {comparison['steps_b']}；全等={comparison['equal']}")
            if comparison["first_divergence"] is not None:
                print(f"首个分歧步: {comparison['first_divergence']}")
            for diff in comparison["diffs"][:20]:
                print(f"  step {diff['step']}: " + "; ".join(
                    f"{key}: {va!r} ≠ {vb!r}" for key, (va, vb) in diff["fields"].items()
                ))
        return 0 if comparison["equal"] else 1

    if args.json:
        print(json.dumps(
            {
                "episode": record.get("episode"),
                "source": source,
                "steps": len(states),
                "deterministic": deterministic,
                "fingerprint": check["fingerprint"],
                "consistency": check,
                "final_state": state_to_dict(states[-1]) if states else None,
            },
            ensure_ascii=False,
            indent=1,
        ))
    else:
        print(f"== 重放 {record.get('episode')}（{path.name}，{len(events)} 条观测，来源 {source}）==")
        shown = states[-args.limit :] if args.limit else states
        for state in shown:
            print(_state_line(state))
        if states:
            final = state_to_dict(states[-1])
            print(f"-- 终态: 课程分合计 {final['lesson_total']}（读到 {final['lesson_known']} / 未读 {final['lesson_unread']}）"
                  f"；考试 {len(final['exams'])} 场合计 {final['exam_score_total']}；重复观测 {final['duplicates']}")
        print(f"-- 确定性: 两遍重放指纹{'逐位相等' if deterministic else '不一致！'} {check['fingerprint'][:16]}…")
        if check["consistent"]:
            print("-- 三方对账: ✅ 一致（events 重放 = 旧格式重建 = 记录汇总）")
        else:
            print(f"-- 三方对账: ⚠️ {len(check['discrepancies']) + len(check['record_diffs'])} 项差异")
            for item in check["discrepancies"]:
                print(f"   [漂移] {item['field']}: events={item['events']!r} legacy={item['legacy']!r}")
            for item in check["record_diffs"]:
                print(f"   [对账] {item['field']}: replay={item['replay']!r} record={item['record']!r}")
    if args.verify:
        return 0 if deterministic and check["consistent"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
