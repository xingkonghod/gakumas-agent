"""抓 wiki + leafierlemon 模拟器 → ``data/knowledge/official.json``。

用法：
    .venv\\Scripts\\python.exe scripts\\wiki_formula_ingest.py
    .venv\\Scripts\\python.exe scripts\\wiki_formula_ingest.py --refresh

产出结构（给模拟器与 dual_fit 读）：

- ``schedule``：逐周 ``{week, action, clear, perfect, train_clear, train_perfect}``。
  ``clear+perfect`` 是「授業（lesson）」的基础属性上升；``train_clear`` 是
  「レッスン/追い込み（train）」的基础上升。两者分开是因为模拟器的默认策略
  仍按自己的节奏选课/训练，不能保证和官方排期一一对应。
  注意：这里沿用 official.json 的历史 schema（``lesson`` = 授業、``train`` = レッスン），
  与模拟器 2026-11-16 改名后的新名（training = レッスン、class = 授業）方向相反；
  写盘键名保持不变，避免已有 official.json 与旧消费者失效。
- ``formulas``：官方公式的字符串形式；日文原文存在 ``wiki_*`` 字段里。
- ``source``：每个字段的来源（leafierlemon / seesaawiki / manual / assumed / real）。
- ``constants``：周数、考试周、训练曲线、评价点公式常量。

网络不可用时：先用 ``data/cache/wiki/*.html``；缓存也没有就用脚本内置的
16 周プロ排期和公式，并在 ``source`` 标 ``manual``（验收要求）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gkagent.knowledge.wiki import (
    WIKI_SOURCES,
    WikiClient,
    content_html,
    parse_schedule_rows,
    plain_text,
)

OUT = ROOT / "data" / "knowledge" / "official.json"
CACHE = ROOT / "data" / "cache" / "wiki"

# 16 周プロ排期（leafierlemon simulator.html）。抓不到页面时用这份内置数据。
MANUAL_ROWS = [
    {"week": 1, "label": "レッスン", "action": "train"},
    {"week": 2, "label": "授業", "action": "lesson"},
    {"week": 3, "label": "---", "action": "free"},
    {"week": 4, "label": "レッスン", "action": "train"},
    {"week": 5, "label": "---", "action": "free"},
    {"week": 6, "label": "追い込み", "action": "train"},
    {"week": 7, "label": "中間試験", "action": "exam"},
    {"week": 8, "label": "---", "action": "free"},
    {"week": 9, "label": "授業", "action": "lesson"},
    {"week": 10, "label": "レッスン", "action": "train"},
    {"week": 11, "label": "授業（確率レッスン）", "action": "lesson"},
    {"week": 12, "label": "レッスン", "action": "train"},
    {"week": 13, "label": "レッスン", "action": "train"},
    {"week": 14, "label": "---", "action": "free"},
    {"week": 15, "label": "追い込み", "action": "train"},
    {"week": 16, "label": "最終試験", "action": "exam"},
]

# 官方锚点（用户已查证）：week1 授業 40/CLEAR + 25/PERFECT；后期授業 110/40；
# 训练从 40 涨到 165（165 同时是最终追い込み的 CLEAR）。
CLASS_CLEAR_START, CLASS_PERFECT_START = 40, 25
CLASS_CLEAR_END, CLASS_PERFECT_END = 110, 40
# 非授業周的 fallback 课程曲线（assumed）：65 → 125，供模拟器的默认策略
# 在「レッスン/空周」也选上课时使用；授業周直接用页面上的 CLEAR/PERFECT。
FALLBACK_CLEAR_END, FALLBACK_PERFECT_END = 100, 25
TRAIN_START, TRAIN_END = 40, 165
SPECIAL_GAINS = {6: (90, 90), 15: (165, 145)}  # 追い込み: (CLEAR, PERFECT)

CANONICAL_FORMULAS = {
    "lesson_gain": "(clear+perfect)*(1+lesson_bonus)*condition",
    "condition_multiplier": "1.5+0.1*condition_turns",
    "eval": "rank_points+2.3*total+score_conversion",
}

MANUAL_CONSTANTS = {
    "weeks": 16,
    "exam_weeks": [7, 16],
    "lesson_gain_ratio": 0.5,  # official.json 历史 schema 键名（旧口径 fallback 系数）
    "support_bonus": 1.2,
    "audition_coefficient": 4.11,
    # official.json 历史 schema：train = レッスン(训练) 的 40→165 成长曲线。
    # 不改成 training_*，保持与磁盘上已有 official.json 的键名一致。
    "train_gain_start": TRAIN_START,
    "train_gain_end": TRAIN_END,
    "rank_points": {"1": 1700, "2": 900, "3": 500},
    "score_brackets": [
        [5000, 0.30],
        [10000, 0.15],
        [20000, 0.08],
        [30000, 0.04],
        [40000, 0.02],
        [1000000000, 0.01],
    ],
}

REAL_MACHINE = {
    "source": "data/runs/ep-rule1.json (真机第二局)",
    "attrs": [365, 234, 372],
    "total": 971,
    "eval_points": 5992,
    "grade": "C+",
    "note": "8 次课 + 4 次训练；评价点 5992；本局是 16 周プロ口径",
}


def _linear(start: float, end: float, week: int, weeks: int) -> int:
    if weeks <= 1:
        return round(end)
    ratio = min(max((week - 1) / (weeks - 1), 0.0), 1.0)
    return round(start + (end - start) * ratio)


def _read_cache(key: str) -> str:
    path = CACHE / f"{key}.html"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def fetch_html(client: WikiClient, key: str, *, refresh: bool) -> tuple[str, str]:
    """返回 ``(html, source)``；网络失败退回缓存，再失败返回空串。"""
    try:
        result = client.fetch(key, refresh=refresh)
        return result.html, "live" if not result.cached else "cache"
    except Exception as exc:  # noqa: BLE001 - 网络/证书/超时都按离线处理
        cached = _read_cache(key)
        if cached:
            print(f"[warn] {key} 抓取失败（{exc}），改用磁盘缓存")
            return cached, "cache"
        print(f"[warn] {key} 抓取失败且无缓存（{exc}），改用内置值")
        return "", "manual"


def extract_schedule(html: str) -> tuple[list[dict], str]:
    """页面 → 排期行；失败返回内置排期 + ``manual``。"""
    rows = parse_schedule_rows(html)
    if not rows:
        return [dict(row) for row in MANUAL_ROWS], "manual"
    # 页面若变成 18 周マスター，仍按 16 周プロ口径截断并提示；避免静默改周数。
    if max(row["week"] for row in rows) != 16:
        print(
            f"[warn] 排期有 {max(row['week'] for row in rows)} 周（预期 16 周プロ）；"
            "仍按页面写盘，模拟器默认配置可能对不上"
        )
    return rows, "leafierlemon"


def build_schedule(rows: list[dict]) -> list[dict]:
    by_week = {int(row["week"]): row for row in rows}
    weeks = max(by_week) if by_week else 16
    schedule: list[dict] = []
    for week in range(1, weeks + 1):
        row = by_week.get(week) or {"week": week, "label": "---", "action": "free"}
        action = str(row.get("action") or "free")
        base = list(row.get("base") or ())
        if action == "exam":
            clear = perfect = train_clear = train_perfect = 0
        else:
            if action == "lesson" and base:
                # 授業行：页面「上昇量ベース」前两个数就是 CLEAR/PERFECT 口径。
                clear = int(base[0])
                perfect = int(base[1]) if len(base) >= 2 else 0
            else:
                # 追い込み/空周/训练周：默认策略可能仍选上课，用 assumed 曲线兜底。
                clear = _linear(CLASS_CLEAR_START, FALLBACK_CLEAR_END, week, weeks)
                perfect = _linear(CLASS_PERFECT_START, FALLBACK_PERFECT_END, week, weeks)
            train_clear = _linear(TRAIN_START, TRAIN_END, week, weeks)
            train_perfect = 0
            if week in SPECIAL_GAINS:
                train_clear, train_perfect = SPECIAL_GAINS[week]
        schedule.append(
            {
                "week": week,
                "action": action,
                "label": str(row.get("label") or ""),
                "clear": clear,
                "perfect": perfect,
                "train_clear": train_clear,
                "train_perfect": train_perfect,
            }
        )
    return schedule


def extract_formulas(mechanics_html: str) -> tuple[dict, str]:
    text = plain_text(content_html(mechanics_html)) if mechanics_html else ""
    has_lesson = "最終パラメータ上昇値" in text and "好調" in text
    has_condition = "1.5+0.1" in text and "好調のターン数" in text
    formulas = dict(CANONICAL_FORMULAS)
    if has_lesson:
        match = re.search(r"最終パラメータ上昇値\s*=\s*[^※]+", text)
        if match:
            line = match.group(0).split("アノマリー")[0].strip()
            formulas["wiki_lesson_gain"] = line
    if has_condition:
        match = re.search(r"1\.5\+0\.1×好調のターン数", text)
        formulas["wiki_condition_multiplier"] = match.group(0) if match else "1.5+0.1×好調のターン数"
    source = "seesaawiki" if has_lesson or has_condition else "manual"
    return formulas, source


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="忽略 24h 缓存，强制重新抓取")
    parser.add_argument(
        "--offline", action="store_true", help="不联网：只用磁盘缓存，缓存也没有则用内置值"
    )
    args = parser.parse_args(argv)

    client = WikiClient(CACHE)
    if args.offline:
        mechanics_html = _read_cache("mechanics")
        schedule_html = _read_cache("schedule")
        mechanics_kind = "cache" if mechanics_html else "manual"
        schedule_kind = "cache" if schedule_html else "manual"
    else:
        mechanics_html, mechanics_kind = fetch_html(client, "mechanics", refresh=args.refresh)
        schedule_html, schedule_kind = fetch_html(client, "schedule", refresh=args.refresh)

    rows, schedule_source = extract_schedule(schedule_html)
    formulas, formula_source = extract_formulas(mechanics_html)
    schedule = build_schedule(rows)
    weeks = max(row["week"] for row in schedule)
    exam_weeks = [row["week"] for row in schedule if row["action"] == "exam"]

    source = {
        "schedule": schedule_source,
        "schedule_url": WIKI_SOURCES["schedule"]["url"],
        "schedule_kind": schedule_kind,
        "formulas": formula_source,
        "formulas_url": WIKI_SOURCES["mechanics"]["url"],
        "formulas_kind": mechanics_kind,
        "eval": "official_prompt",
        "class_gain_curve": "assumed",
        "train_gain_curve": "real",  # 历史 schema：train = レッスン(训练) 的成长曲线来源
        "weeks": schedule_source,
    }
    data = {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scenario": "初/プロ（16 周；真机第二局口径）",
        "schedule": schedule,
        "formulas": formulas,
        "constants": {
            **MANUAL_CONSTANTS,
            "weeks": weeks,
            "exam_weeks": exam_weeks,
            "train_gain_start": TRAIN_START,
            "train_gain_end": TRAIN_END,
            "class_gain_start": {"clear": CLASS_CLEAR_START, "perfect": CLASS_PERFECT_START},
            "class_gain_end": {"clear": CLASS_CLEAR_END, "perfect": CLASS_PERFECT_END},
            "fallback_class_gain_end": {
                "clear": FALLBACK_CLEAR_END,
                "perfect": FALLBACK_PERFECT_END,
            },
        },
        "source": source,
        "real_machine": REAL_MACHINE,
        "notes": [
            (
                "schedule 的 action 是官方排期（授業/レッスン/追い込み/試験/空周），"
                "模拟器仍按自己的策略选行动；clear/perfect 和 train_clear/train_perfect "
                "是同一周两种行动各自的基础收益。"
            ),
            (
                "class 收益：授業周直接用页面 CLEAR/PERFECT；非授業周用 65→125 线性插值兜底"
                "（assumed，供模拟器默认策略在训练周仍选上课时用）。"
            ),
            "训练 40→165 来自真机实测；追い込み 90/165 来自 leafierlemon 页面。",
            (
                "formulas 的 eval 公式来自官方评价点公式（顺位点 + 2.3×三维 + 终试分段），"
                "本轮没有在 mechanics 页解析到，标 official_prompt。"
            ),
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"写入 {OUT}")
    print(
        f"  schedule: {schedule_source} ({weeks} 周, exam={exam_weeks}, "
        f"actions={ {row['action'] for row in schedule} })"
    )
    print(
        f"  formulas: {formula_source} "
        f"(lesson={bool(formulas.get('wiki_lesson_gain'))}, "
        f"condition={bool(formulas.get('wiki_condition_multiplier'))})"
    )
    print(
        f"  gains: class {CLASS_CLEAR_START}+{CLASS_PERFECT_START} → "
        f"{CLASS_CLEAR_END}+{CLASS_PERFECT_END}; train {TRAIN_START} → {TRAIN_END}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
