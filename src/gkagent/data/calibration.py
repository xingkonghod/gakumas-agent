"""真机属性标定：记录每周三维，反解「课程得分 → 属性成长」系数。

为什么需要：模拟器里 lesson_gain_ratio 只有 2 个真机数据点，敏感性分析显示结论在
0.40~0.41 之间翻转。最好的解法是直接测：上课前后各读一次三维，除以这节课得分。

数据：data/attribute_log.jsonl，每行 {"ts": "...", "attrs": [Vo, Da, Vi], "tag": "..."}
"""

from __future__ import annotations

import json
import time
from itertools import pairwise
from pathlib import Path

LOG = Path(__file__).resolve().parents[3] / "data" / "attribute_log.jsonl"


def record(attrs, *, tag: str = "train-confirm", path: Path | None = None) -> bool:
    """追加一条三维记录；与上一条完全相同则跳过（避免同屏重复刷）。"""
    values = [int(v) for v in attrs]
    if len(values) != 3:
        return False
    target = Path(path) if path else LOG
    last = None
    if target.exists():
        try:
            with target.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        last = line
        except OSError:
            last = None
    if last:
        try:
            if json.loads(last).get("attrs") == values:
                return False
        except json.JSONDecodeError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "attrs": values, "tag": tag}, ensure_ascii=False)
            + "\n"
        )
    return True


def load(path: Path | None = None) -> list[dict]:
    target = Path(path) if path else LOG
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize(path: Path | None = None) -> dict:
    """相邻两条记录之差 = 这段时间的属性增长（通常是一周）。"""
    rows = load(path)
    deltas = []
    for before, after in pairwise(rows):
        delta = [b - a for a, b in zip(before["attrs"], after["attrs"])]
        if all(value >= 0 for value in delta) and sum(delta) > 0:
            deltas.append({"ts": after["ts"], "delta": delta, "total": sum(delta), "attrs": after["attrs"]})
    totals = [item["total"] for item in deltas]
    return {
        "records": len(rows),
        "weeks": len(deltas),
        "mean_growth": round(sum(totals) / len(totals), 1) if totals else 0.0,
        "max_growth": max(totals) if totals else 0,
        "min_growth": min(totals) if totals else 0,
        "last_attrs": rows[-1]["attrs"] if rows else None,
        "deltas": deltas[-20:],
    }


def estimate_ratio(lesson_scores, path: Path | None = None) -> float | None:
    """课程成长系数 ≈ 周成长 / 该周课程得分（有课程得分的周才算）。"""
    pairs = [
        (item["total"], score)
        for item, score in zip(summarize(path)["deltas"], lesson_scores)
        if score and score > 0
    ]
    if not pairs:
        return None
    return round(sum(total for total, _ in pairs) / sum(score for _, score in pairs), 3)
