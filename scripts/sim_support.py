"""支援卡 × 角色 × 等级 的模拟对照图。

左：折线 —— 支援卡平均等级（20→60），三条线 = SSR / SR / R 三种稀有度
右：分组柱状 —— 全角色，弱支援（SR Lv30）vs 强支援（SSR Lv50），灰柱 = 考试通过率

支援卡只建模"训练收益倍率"（模型里唯一可观测的支撑）：
    bonus = 1 + 0.40 * (平均等级/40) * 稀有度系数
稀有度系数：SSR 1.30 / SR 1.00 / R 0.75（按真机 Lv40/37/29 + 1.35 反推的近似）
上限 2.0，避免高等级线性膨胀。

用法：python scripts/sim_support.py --episodes 300
产物：data/sim_support.png
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "data" / "sim_support.png"

IDOLS: dict[str, tuple[float, float, float]] = {
    "花海咲季(平衡)": (0.35, 0.33, 0.32),
    "藤田ことね(2極)": (0.38, 0.36, 0.26),
    "有村麻央(2極)": (0.40, 0.38, 0.22),
    "月村手毬(1極)": (0.45, 0.30, 0.25),
    "紫云清夏(特化)": (0.55, 0.25, 0.20),
}
LEVELS = (20, 30, 40, 50, 60)
TIERS = {"SSR": 1.30, "SR": 1.00, "R": 0.75}
TIER_COLORS = {"SSR": "#e0556b", "SR": "#3fa7d6", "R": "#9aa7b8"}


def support_bonus(level: int, tier: str) -> float:
    return min(2.0, 1.0 + 0.40 * (level / 40.0) * TIERS[tier])


def run_cell(task: tuple) -> dict:
    label, weights, level, tier, episodes, seed = task
    import sim_produce as sp

    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import ProduceConfig, ProduceSim, StrategyParams, strategy_from_params

    deck_raw = sp.build_deck()
    pool_raw = sp.build_pool()
    deck = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in deck_raw]
    pool = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in pool_raw]
    config = ProduceConfig(
        weights=weights,
        support_bonus=support_bonus(level, tier),
        reward_pick="best",
    )
    strategy = strategy_from_params(
        StrategyParams(rest_threshold=8, lesson_every=1, attr_choice="weight", outing_below=16, min_stamina_to_train=8)
    )
    totals, exam_pass = [], 0
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=seed + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        totals.append(result.total)
        exams = [row["exam"] for row in sim.trace if row["action"] == "exam"]
        exam_pass += sum(1 for exam in exams if exam["passed"])
    return {
        "label": label,
        "level": level,
        "tier": tier,
        "support_bonus": round(support_bonus(level, tier), 3),
        "mean_total": round(st.mean(totals), 1),
        "exam_pass": round(exam_pass / (episodes * 2), 3),
    }


def draw(line_rows: list[dict], bar_rows: list[dict]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1560, 760
    image = Image.new("RGB", (width, height), "white")
    canvas = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
        small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
        title_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 25)
    except OSError:
        font = small = title_font = ImageFont.load_default()

    canvas.text((50, 20), "支援卡稀有度 × 等级 × 角色 对照（模拟）", fill="#111111", font=title_font)

    # ---------- 左：折线 ----------
    left = (90, 110, 760, 620)
    x0, y0, x1, y1 = left
    max_y = max(row["mean_total"] for row in line_rows) * 1.12
    canvas.rectangle(left, outline="#cccccc")
    for index in range(6):
        y = y1 - (y1 - y0) * index / 5
        canvas.line([(x0, y), (x1, y)], fill="#eeeeee")
        canvas.text((x0 - 60, y - 9), f"{max_y * index / 5:.0f}", fill="#666666", font=small)
    for index, level in enumerate(LEVELS):
        x = x0 + (x1 - x0) * index / (len(LEVELS) - 1)
        canvas.text((x - 14, y1 + 10), f"Lv{level}", fill="#333333", font=small)
    canvas.text(((x0 + x1) / 2 - 60, y1 + 40), "支援卡平均等级", fill="#333333", font=font)
    canvas.text((x0 - 60, y0 - 34), "12 周总和", fill="#666666", font=small)
    for tier_index, tier in enumerate(TIERS):
        series = sorted((row for row in line_rows if row["tier"] == tier), key=lambda row: row["level"])
        points = []
        for index, row in enumerate(series):
            x = x0 + (x1 - x0) * index / (len(LEVELS) - 1)
            y = y1 - (y1 - y0) * (row["mean_total"] / max_y)
            points.append((x, y))
            canvas.text((x - 18, y - 22), f"{row['mean_total']:.0f}", fill=TIER_COLORS[tier], font=small)
        canvas.line(points, fill=TIER_COLORS[tier], width=3)
        for x, y in points:
            canvas.ellipse([x - 5, y - 5, x + 5, y + 5], fill=TIER_COLORS[tier])
        canvas.line([(x0 + 20, y0 + 8 + tier_index * 26), (x0 + 50, y0 + 8 + tier_index * 26)], fill=TIER_COLORS[tier], width=3)
        canvas.text((x0 + 58, y0 + tier_index * 26 - 2), tier, fill="#333333", font=small)

    # ---------- 右：分组柱状 ----------
    right = (840, 110, 1520, 620)
    rx0, ry0, rx1, ry1 = right
    max_bar = max(row["mean_total"] for row in bar_rows) * 1.18
    canvas.rectangle(right, outline="#cccccc")
    for index in range(6):
        y = ry1 - (ry1 - ry0) * index / 5
        canvas.line([(rx0, y), (rx1, y)], fill="#eeeeee")
        canvas.text((rx0 - 58, y - 9), f"{max_bar * index / 5:.0f}", fill="#666666", font=small)
    canvas.text((rx0 - 58, ry0 - 34), "12 周总和", fill="#666666", font=small)

    labels = list(dict.fromkeys(row["label"] for row in bar_rows))
    slot = (rx1 - rx0) / len(labels)
    variants = list(dict.fromkeys((row["level"], row["tier"]) for row in bar_rows))
    variant_colors = ["#9aa7b8", "#e0556b"]
    for label_index, label in enumerate(labels):
        group = [row for row in bar_rows if row["label"] == label]
        group.sort(key=lambda row: row["level"])
        for variant_index, row in enumerate(group):
            bar_w = slot * 0.30
            bx = rx0 + slot * label_index + slot * (0.14 + variant_index * 0.38)
            bar_h = (ry1 - ry0) * (row["mean_total"] / max_bar)
            canvas.rectangle([bx, ry1 - bar_h, bx + bar_w, ry1], fill=variant_colors[variant_index % 2])
            canvas.text((bx + 2, ry1 - bar_h - 22), f"{row['mean_total']:.0f}", fill="#333333", font=small)
            canvas.text((bx - 2, ry1 + 8), f"{row['exam_pass']*100:.0f}%", fill="#777777", font=small)
        canvas.text((rx0 + slot * label_index + 6, ry1 + 30), label.replace("(", "\n("), fill="#333333", font=small)
    for variant_index, (level, tier) in enumerate(variants):
        lx = rx0 + 20 + variant_index * 150
        ly = ry0 + 8
        canvas.rectangle([lx, ly, lx + 22, ly + 14], fill=variant_colors[variant_index % 2])
        canvas.text((lx + 30, ly - 2), f"{tier} Lv{level}", fill="#333333", font=small)

    canvas.text((50, 700), "左：支援卡稀有度/等级对总分的影响（角色=有村麻央）  右：全角色 × 弱支援(SR30)/强支援(SSR50)",
                fill="#777777", font=small)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args(argv)

    base_weights = IDOLS["有村麻央(2極)"]
    line_tasks = [
        (f"{tier}Lv{level}", base_weights, level, tier, args.episodes, 20000 + index * 71)
        for index, (tier, level) in enumerate((tier, level) for tier in TIERS for level in LEVELS)
    ]
    bar_tasks = []
    for index, (label, weights) in enumerate(IDOLS.items()):
        bar_tasks.append((label, weights, 30, "SR", args.episodes, 30000 + index * 89))
        bar_tasks.append((label, weights, 50, "SSR", args.episodes, 31000 + index * 89))

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        line_rows = list(pool.map(run_cell, line_tasks))
        bar_rows = list(pool.map(run_cell, bar_tasks))

    print("支援卡（角色=有村麻央）：")
    for tier in TIERS:
        series = sorted((row for row in line_rows if row["tier"] == tier), key=lambda row: row["level"])
        print("  " + tier + ": " + "  ".join(f"Lv{row['level']}={row['mean_total']:.0f}" for row in series))
    print("全角色（Lv30 SR vs Lv50 SSR）：")
    for label in IDOLS:
        group = [row for row in bar_rows if row["label"] == label]
        group.sort(key=lambda row: row["level"])
        print(f"  {label:14s} " + "  ".join(f"{row['tier']}{row['level']}={row['mean_total']:.0f}({row['exam_pass']*100:.0f}%)" for row in group))
    draw(line_rows, bar_rows)
    print("图已生成:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
