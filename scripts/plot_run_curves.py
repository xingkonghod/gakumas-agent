"""上一局（ep-sup1b）的两张折线图：三维成长 + 评价点 vs 门槛。

数据源：data/attribute_log.jsonl（真机每步读到的 X/1000）
产物：data/run_curves.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.sim.produce import eval_value  # noqa: E402

LOG = ROOT / "data" / "attribute_log.jsonl"
OUT = ROOT / "data" / "run_curves.png"


def load_points() -> list[dict]:
    rows = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        attrs = row.get("attrs") or []
        if len(attrs) != 3:
            continue
        total = sum(attrs)
        rows.append(
            {
                "ts": row.get("ts", ""),
                "attrs": attrs,
                "total": total,
                "eval": eval_value(total, 2, total * 2),
            }
        )
    return rows


def draw(rows: list[dict]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1500, 760
    image = Image.new("RGB", (width, height), "white")
    canvas = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 19)
        small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
        title = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 25)
    except OSError:
        font = small = title = ImageFont.load_default()

    canvas.text((50, 20), "上一局真机（ep-sup1b）：三维成长 与 评价点走势", fill="#111111", font=title)
    labels = [f"{index + 1}" for index in range(len(rows))]

    def panel(box, series, max_y, y_ticks, ylabel, thresholds=()):
        x0, y0, x1, y1 = box
        canvas.rectangle(box, outline="#cccccc")
        for index in range(y_ticks + 1):
            y = y1 - (y1 - y0) * index / y_ticks
            canvas.line([(x0, y), (x1, y)], fill="#eeeeee")
            canvas.text((x0 - 58, y - 9), f"{max_y * index / y_ticks:.0f}", fill="#666666", font=small)
        for value, text, color in thresholds:
            if value > max_y:
                continue
            y = y1 - (y1 - y0) * value / max_y
            canvas.line([(x0, y), (x1, y)], fill=color, width=2)
            canvas.text((x1 - 90, y - 18), text, fill=color, font=small)
        for name, color, values in series:
            points = []
            for index, value in enumerate(values):
                x = x0 + (x1 - x0) * index / max(len(values) - 1, 1)
                y = y1 - (y1 - y0) * min(value / max_y, 1.0)
                points.append((x, y))
            if len(points) > 1:
                canvas.line(points, fill=color, width=3)
            for x, y in points:
                canvas.ellipse([x - 4, y - 4, x + 4, y + 4], fill=color)
            canvas.text((points[-1][0] - 20, points[-1][1] - 22), f"{values[-1]:.0f}", fill=color, font=small)
        canvas.text((x0, y0 - 30), ylabel, fill="#333333", font=small)
        for index in range(len(rows)):
            x = x0 + (x1 - x0) * index / max(len(rows) - 1, 1)
            canvas.text((x - 4, y1 + 10), labels[index], fill="#666666", font=small)

    # 左：三维
    max_total = max(row["total"] for row in rows) * 1.25
    panel(
        (110, 110, 700, 620),
        [
            ("Vo", "#e0556b", [row["attrs"][0] for row in rows]),
            ("Da", "#3fa7d6", [row["attrs"][1] for row in rows]),
            ("Vi", "#f2b134", [row["attrs"][2] for row in rows]),
            ("总和", "#333333", [row["total"] for row in rows]),
        ],
        max_total,
        5,
        "三维（点 = 每次读到属性）",
    )

    # 右：评价点 vs 门槛
    max_eval = max(max(row["eval"] for row in rows) * 1.2, 6000)
    panel(
        (840, 110, 1450, 620),
        [("评价点", "#7d5ba6", [row["eval"] for row in rows])],
        max_eval,
        5,
        "评价点（按 2 名 + 终试=2×三维 估算）",
        thresholds=((4500, "C+ 门槛 4500", "#e0556b"), (3000, "C 门槛 3000", "#999999")),
    )

    canvas.text((50, 690), "横轴 = 第几次读到属性（attribute_log.jsonl）；总和与评价点随课程/训练上升。",
                fill="#777777", font=small)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT)
    print("图已生成:", OUT)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = load_points()
    if len(rows) < 2:
        print("数据点太少（需要 ≥2 条），先把 attribute_log.jsonl 攒起来")
        return 1
    for index, row in enumerate(rows):
        print(f"{index + 1}. {row['ts']}  {row['attrs']}  总和={row['total']}  评价点~{row['eval']}")
    draw(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
