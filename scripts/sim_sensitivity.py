"""敏感性分析：训练成长系数从 0.2 扫到 1.0，看"纯上课 vs 能训练就训练"谁更强。

背景：真机锚点只有"评价 C / 4135 评价点 / 三维约 1000-1200"，`training_gain_ratio`
的机制值是 1.0，但模拟牌组比真机强约 2 倍，所以校准默认值取 0.5；这张图用来看
"结论在什么系数下成立"，避免把一次拟合当真理。

用法：python scripts/sim_sensitivity.py --episodes 400
产物：data/sim_sensitivity.png
"""

from __future__ import annotations

import argparse
import itertools
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

RATIOS = (0.20, 0.40, 0.50, 0.60, 0.80, 0.90, 1.00)
CALIBRATED = 0.50

VARIANTS = {
    "纯上课": {
        "training_every": 0, "rest_threshold": 8, "attr_choice": "weight",
        "outing_below": -1, "min_stamina_for_class": 10,
    },
    "能训练就训练": {
        "training_every": 1, "rest_threshold": 8, "attr_choice": "weight",
        "outing_below": 16, "min_stamina_for_class": 8,
    },
}
COLORS = {"纯上课": "#3fa7d6", "能训练就训练": "#e0556b"}


def run_cell(task: tuple) -> dict:
    ratio, name, params_dict, episodes, seed = task

    import sim_produce as sp

    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import ProduceConfig, ProduceSim, StrategyParams, strategy_from_params

    deck_raw = sp.build_deck()
    pool_raw = sp.build_pool()
    deck = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in deck_raw]
    pool = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in pool_raw]
    config = ProduceConfig(
        weights=(0.40, 0.38, 0.22),
        training_gain_ratio=ratio,
        reward_pick="best",
        support_bonus=1.2,
    )
    strategy = strategy_from_params(StrategyParams(**params_dict))
    totals, exam_pass = [], 0
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=seed + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        totals.append(result.total)
        exams = [row["exam"] for row in sim.trace if row["action"] == "exam"]
        exam_pass += sum(1 for exam in exams if exam["passed"])
    return {
        "ratio": ratio,
        "name": name,
        "mean": round(st.mean(totals), 1),
        "p10": round(sorted(totals)[len(totals) // 10], 1),
        "exam_pass": round(exam_pass / (episodes * 2), 3),
    }


def draw(rows: list[dict]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1400, 720
    image = Image.new("RGB", (width, height), "white")
    canvas = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
        small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
        title_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
    except OSError:
        font = small = title_font = ImageFont.load_default()

    canvas.text((60, 24), "敏感性分析：训练成长系数 → 两种打法的总分", fill="#111111", font=title_font)
    box = (100, 100, 1320, 600)
    x0, y0, x1, y1 = box
    canvas.rectangle(box, outline="#cccccc")
    values = [row["mean"] for row in rows]
    max_y = max(values) * 1.12
    min_y = min(values) * 0.88
    for index in range(6):
        value = min_y + (max_y - min_y) * index / 5
        y = y1 - (y1 - y0) * index / 5
        canvas.line([(x0, y), (x1, y)], fill="#eeeeee")
        canvas.text((x0 - 66, y - 10), f"{value:.0f}", fill="#666666", font=small)
    for index, ratio in enumerate(RATIOS):
        x = x0 + (x1 - x0) * index / (len(RATIOS) - 1)
        canvas.text((x - 16, y1 + 12), f"{ratio:.2f}", fill="#333333", font=small)
    canvas.text(((x0 + x1) / 2 - 70, y1 + 44), "training_gain_ratio（训练得分→属性）", fill="#333333", font=font)

    for name in VARIANTS:
        series = [row for row in rows if row["name"] == name]
        series.sort(key=lambda row: row["ratio"])
        points = []
        for row in series:
            index = RATIOS.index(row["ratio"])
            x = x0 + (x1 - x0) * index / (len(RATIOS) - 1)
            y = y1 - (y1 - y0) * (row["mean"] - min_y) / (max_y - min_y)
            points.append((x, y))
            canvas.ellipse([x - 5, y - 5, x + 5, y + 5], fill=COLORS[name])
        canvas.line(points, fill=COLORS[name], width=3)
        lx, ly = x0 + 30, y0 + 20 + list(VARIANTS).index(name) * 30
        canvas.line([(lx, ly + 8), (lx + 28, ly + 8)], fill=COLORS[name], width=3)
        canvas.text((lx + 36, ly - 2), name, fill="#333333", font=small)

    # 标定值竖线
    index = RATIOS.index(CALIBRATED)
    x = x0 + (x1 - x0) * index / (len(RATIOS) - 1)
    canvas.line([(x, y0), (x, y1)], fill="#999999", width=2)
    canvas.text((x + 8, y0 + 6), "校准值 0.50（真机 C/4135 反推）", fill="#777777", font=small)

    # 交叉点
    by_name = {name: {row["ratio"]: row["mean"] for row in rows if row["name"] == name} for name in VARIANTS}
    names = list(VARIANTS)
    for left, right in itertools.pairwise(RATIOS):
        diff_left = by_name[names[0]][left] - by_name[names[1]][left]
        diff_right = by_name[names[0]][right] - by_name[names[1]][right]
        if diff_left * diff_right <= 0:
            canvas.text((x0 + 40, y0 + 70), f"交叉点在 {left:.2f}~{right:.2f} 之间", fill="#8a6d3b", font=font)
            break
    else:
        winner = max(names, key=lambda n: by_name[n][CALIBRATED])
        canvas.text((x0 + 40, y0 + 70), f"0.20~0.80 全程 {winner} 更强", fill="#8a6d3b", font=font)

    image.save(ROOT / "data" / "sim_sensitivity.png")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=400)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    tasks = [
        (ratio, name, params, args.episodes, 9000 + index * 53 + int(ratio * 100))
        for index, (name, params) in enumerate(VARIANTS.items())
        for ratio in RATIOS
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_cell, tasks))

    rows.sort(key=lambda row: (row["name"], row["ratio"]))
    for row in rows:
        print(f"ratio={row['ratio']:.2f} {row['name']:8s} 总和={row['mean']:>7} p10={row['p10']:>6} 考试通过={row['exam_pass']*100:.0f}%")
    draw(rows)
    print("图已生成: data/sim_sensitivity.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
