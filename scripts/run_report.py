"""跑局报告：读 ``data/runs/<episode>.json``，打印摘要 + 模拟器预测 vs 实际对账。

用法（venv，任何 cwd）：
    python scripts/run_report.py <episode>

摘要：周数 / 总属性 / 考试名次 / 评价点 / 时长。
对账：用模拟器口径 ``终试得分 = 2 × 三维总和 × audition_coefficient`` 和官方
评价公式 ``eval_value(...)`` 算出预测值，逐项对比本局真机实际值（评价点、
评价等级、考试名次），差异直接打印出来，作为 6 参数标定的偏差信号。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "data" / "runs"
sys.path.insert(0, str(ROOT / "src"))

from gkagent.sim.produce import eval_value, grade_for  # noqa: E402


def load_run(episode: str, runs_dir: Path | str | None = None) -> tuple[dict, Path]:
    """读一局 json；找不到/坏文件抛 ``FileNotFoundError`` / ``ValueError``。"""
    base = Path(runs_dir) if runs_dir is not None else RUNS
    path = base / f"{episode}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"读不了 {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} 顶层不是对象")
    return payload, path


def _attrs_text(attrs: Any) -> str:
    if not isinstance(attrs, (list, tuple)) or len(attrs) != 3:
        return "?"
    return "/".join(str(int(value)) for value in attrs)


def _delta_text(actual: float, predicted: float) -> str:
    delta = actual - predicted
    percent = delta / predicted * 100 if predicted else 0.0
    return f"Δ {delta:+.0f} ({percent:+.1f}%)"


def _duration_minutes(record: dict, path: Path | None) -> float | None:
    """时长 = 文件最后一次 flush 的时间 - started_at（跑局没有显式 ended_at）。"""
    try:
        started = datetime.strptime(str(record.get("started_at")), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    try:
        ended = datetime.fromtimestamp(Path(path).stat().st_mtime) if path else datetime.now()
    except OSError:
        ended = datetime.now()
    return max(0.0, (ended - started).total_seconds() / 60)


def _exam_summary(exams: list[dict]) -> str:
    parts = []
    for exam in exams:
        kind = {"mid": "期中", "final": "期末"}.get(str(exam.get("kind")), str(exam.get("kind")))
        rank = exam.get("rank")
        score = exam.get("score")
        parts.append(f"{kind} rank={rank if rank is not None else '?'} / {score if score is not None else '?'} Pt")
    return " | ".join(parts) if parts else "未采集"


def build_report(record: dict, *, path: Path | str | None = None) -> str:
    """把一局 record 渲染成可打印报告（纯函数，测试直接调用）。"""
    weeks = record.get("weeks") or []
    exams = record.get("exams") or []
    final = record.get("final") if isinstance(record.get("final"), dict) else {}
    meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
    last_week_attrs = weeks[-1].get("attrs_after") if weeks else None
    attrs = final.get("attrs") or last_week_attrs
    total = sum(int(value) for value in attrs) if isinstance(attrs, (list, tuple)) and len(attrs) == 3 else None
    duration = _duration_minutes(record, Path(path) if path is not None else None)
    coefficient = meta.get("audition_coefficient", 4.11)

    lines: list[str] = [f"=== {record.get('episode') or '?'} ==="]
    duration_text = f"{duration:.1f} 分钟" if duration is not None else "?"
    lines.append(
        f"开始时间: {record.get('started_at') or '?'}    "
        f"时长: {duration_text}    周记录: {len(weeks)} 周"
    )
    lines.append(f"最终属性: {_attrs_text(attrs)}" + (f"（总 {total}）" if total is not None else ""))
    lines.append(f"考试: {_exam_summary(exams)}")
    if final:
        lines.append(
            f"评价: {final.get('grade') or '?'} / "
            f"{final.get('eval_points') if final.get('eval_points') is not None else '?'} 评价点"
        )
    else:
        lines.append("评价: 未采集到（final=null）")
    lines.append(
        f"配置: 考试属性倍率 {coefficient} / 课程最低体力 "
        f"{meta.get('lesson_min_stamina', 10)}"
    )

    lines.append("")
    lines.append("对账（模拟器预测 vs 实际）:")
    rank = final.get("rank")
    if rank is None and exams:
        rank = exams[-1].get("rank")
    actual_exam = final.get("exam_score")
    actual_points = final.get("eval_points")
    actual_grade = final.get("grade")
    if final and attrs is not None and total is not None:
        try:
            coefficient_value = float(coefficient)
        except (TypeError, ValueError):
            coefficient_value = 4.11
        predicted_exam = int(total * 2 * coefficient_value)
        if actual_exam is not None:
            lines.append(
                f"  终试得分  模拟 2×{total}×{coefficient_value:g}={predicted_exam}   "
                f"实际 {actual_exam}  {_delta_text(float(actual_exam), predicted_exam)}"
            )
        else:
            lines.append(f"  终试得分  模拟 2×{total}×{coefficient_value:g}={predicted_exam}   实际 未采集")
        if rank is not None:
            predicted_points = eval_value(total, int(rank), predicted_exam)
            predicted_grade = grade_for(total, int(rank), predicted_exam)
            if actual_points is not None:
                lines.append(
                    f"  评价点    模拟 eval_value({total},{rank},{predicted_exam})={predicted_points}   "
                    f"实际 {actual_points}  {_delta_text(float(actual_points), predicted_points)}"
                )
            else:
                lines.append(
                    f"  评价点    模拟 eval_value({total},{rank},{predicted_exam})={predicted_points}   实际 未采集"
                )
            lines.append(
                f"  评价等级  模拟 {predicted_grade}   实际 {actual_grade or '未采集'}   "
                f"{'一致' if actual_grade == predicted_grade else '不一致'}"
            )
        else:
            lines.append("  评价点/等级  实际 rank 未采集，跳过")
    else:
        lines.append("  数据不全（final/attrs/总属性缺失），跳过对账")

    for exam in exams:
        kind = {"mid": "期中", "final": "期末"}.get(str(exam.get("kind")), str(exam.get("kind")))
        others = exam.get("others")
        score = exam.get("score")
        actual_rank = exam.get("rank")
        if isinstance(others, list) and score is not None:
            ordered = sorted((int(value) for value in others), reverse=True)
            predicted_rank = ordered.index(int(score)) + 1 if int(score) in ordered else None
            if predicted_rank is not None:
                lines.append(
                    f"  {kind}名次   模拟排序 {predicted_rank}   实际 {actual_rank}   "
                    f"{'一致' if actual_rank == predicted_rank else '不一致'}"
                )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not argv:
        print("用法: python scripts/run_report.py <episode>", file=sys.stderr)
        return 2
    episode = argv[0]
    runs_dir = Path(argv[1]) if len(argv) > 1 else None
    try:
        record, path = load_run(episode, runs_dir)
    except FileNotFoundError as exc:
        print(f"找不到跑局记录: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(build_report(record, path=path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
