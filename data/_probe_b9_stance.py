"""B9 预分析 4：ExamPreservation/Concentration 段文本分类 + 目标效果文本/limit 统计。"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "_b9_stance.txt"

TARGET = ("ExamPreservation", "ExamConcentration")


def main() -> int:
    payload = json.loads(
        (ROOT / "data" / "knowledge" / "p_items.json").read_text(encoding="utf-8-sig")
    )
    lines: list[str] = []
    for t in TARGET:
        rows = []
        for item in payload["items"]:
            for eff in item.get("effects") or []:
                if eff.get("type") == t:
                    rows.append((item["id"], item.get("trigger"), eff.get("text", "")))
        counter = collections.Counter(row[2][:14] for row in rows)
        lines.append(f"== {t} 段数 {len(rows)}；文本前 14 字分布:")
        for text, count in counter.most_common():
            lines.append(f"  {count:3d}  {text!r}")
        lines.append("")
        lines.append(f"== {t} 全部文本:")
        for item_id, trigger, text in rows:
            lines.append(f"  {item_id} | {trigger} | {text}")
        lines.append("")

    # limit 解析统计
    pat = re.compile(
        r"(?:训练内|培育中|レッスン内|プロデュース中)(\d+)(?:次|回)"
        r"|（(\d+)次）"
    )
    hits = 0
    missing = []
    for item in payload["items"]:
        text = (item.get("text_zh") or "") + (item.get("text_ja") or "")
        m = pat.search(text)
        if m:
            hits += 1
        else:
            missing.append(item["id"])
    lines.append(f"== limit 正则命中 {hits}/{len(payload['items'])}；未命中示例 {missing[:10]}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
