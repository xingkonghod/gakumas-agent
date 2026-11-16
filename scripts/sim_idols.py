"""不同偶像（审查基准权重不同）的模拟对照图：折线（每周属性成长）+ 柱状（最终总和/考试）。

用法：python scripts/sim_idols.py --episodes 600
产物：data/sim_idols.png

注意：审查基准权重是按"平衡型/1極型/2極型/特化型"的公开分类**近似**，不是官方精确值；
图的用途是看趋势差异，不是预测真机分数。
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "data" / "sim_idols.png"

# 偶像 → 审查基准权重（Vo, Da, Vi）；按公开的审查基准"型"近似
IDOLS: dict[str, tuple[float, float, float]] = {
    "花海咲季(平衡)": (0.35, 0.33, 0.32),
    "藤田ことね(2極)": (0.38, 0.36, 0.26),
    "有村麻央(2極)": (0.40, 0.38, 0.22),
    "月村手毬(1極)": (0.45, 0.30, 0.25),
    "紫云清夏(特化)": (0.55, 0.25, 0.20),
    "十王星南(平衡)": (0.35, 0.33, 0.32),
}


STRATEGIES: dict[str, dict] = {
    "能训练就训练": {"training_every": 1, "rest_threshold": 8, "attr_choice": "weight", "outing_below": 16, "min_stamina_for_class": 8},
    "纯上课": {"training_every": 0, "rest_threshold": 8, "attr_choice": "weight", "outing_below": -1, "min_stamina_for_class": 10},
    "每3周训练": {"training_every": 3, "rest_threshold": 8, "attr_choice": "weight", "outing_below": 16, "min_stamina_for_class": 8},
    "补短板": {"training_every": 1, "rest_threshold": 8, "attr_choice": "lowest", "outing_below": 16, "min_stamina_for_class": 8},
    "多休息": {"training_every": 0, "rest_threshold": 14, "attr_choice": "weight", "outing_below": 20, "min_stamina_for_class": 12},
}


def run_idol(task: tuple) -> dict:
    name, weights, params_dict, episodes, seed = task
    import sim_produce as sp

    from gkagent.sim.lesson import CardSpec
    from gkagent.sim.produce import ProduceConfig, ProduceSim, StrategyParams, strategy_from_params

    deck_raw = sp.build_deck()
    pool_raw = sp.build_pool()
    deck = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in deck_raw]
    pool = [CardSpec(name=n, cost=c, score=s, condition=cd, focus=f) for n, c, s, cd, f in pool_raw]
    params = StrategyParams(**params_dict)
    config = ProduceConfig(weights=weights, reward_pick="best", support_bonus=1.2)

    weekly: dict[int, list[int]] = {}
    finals, exam_pass, grades = [], 0, {}
    attrs_sum = [0, 0, 0]
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=seed + episode)
        sim.reward_pool = pool
        result = sim.run(strategy_from_params(params))
        finals.append(result.total)
        for i in range(3):
            attrs_sum[i] += result.attrs[i]
        exams = [row["exam"] for row in sim.trace if row["action"] == "exam"]
        exam_pass += sum(1 for exam in exams if exam["passed"])
        grades[result.grade] = grades.get(result.grade, 0) + 1
        for row in sim.trace:
            weekly.setdefault(row["week"], []).append(sum(row["attrs_after"]))
    return {
        "name": name,
        "weights": weights,
        "mean_total": round(st.mean(finals), 1),
        "p10": round(sorted(finals)[len(finals) // 10], 1),
        "exam_pass_rate": round(exam_pass / (episodes * 2), 3),
        "grades": dict(sorted(grades.items(), key=lambda kv: -kv[1])[:3]),
        "mean_attrs": [round(value / episodes, 1) for value in attrs_sum],
        "weekly": {week: round(st.mean(values), 1) for week, values in sorted(weekly.items())},
    }


def draw(results: list[dict], title: str = "不同偶像的培育模拟对照（审查基准权重不同）") -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1500, 720
    image = Image.new("RGB", (width, height), "white")
    draw_obj = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
        small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
        title_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
    except OSError:
        font = small = title_font = ImageFont.load_default()

    colors = ["#e0556b", "#3fa7d6", "#f2b134", "#7d5ba6", "#43aa8b"]
    left = (80, 90, 720, 620)      # 折线区
    right = (840, 90, 1450, 620)   # 柱状区

    def axis(box, xlabel, ylabel, max_y, y_ticks):
        x0, y0, x1, y1 = box
        draw_obj.rectangle(box, outline="#cccccc")
        for index in range(y_ticks + 1):
            value = max_y * index / y_ticks
            y = y1 - (y1 - y0) * index / y_ticks
            draw_obj.line([(x0, y), (x1, y)], fill="#eeeeee")
            draw_obj.text((x0 - 52, y - 10), f"{value:.0f}", fill="#666666", font=small)
        draw_obj.text(((x0 + x1) / 2 - 40, y1 + 12), xlabel, fill="#333333", font=font)
        draw_obj.text((x0 - 60, y0 - 34), ylabel, fill="#333333", font=small)

    draw_obj.text((60, 24), title, fill="#111111", font=title_font)

    # 折线：每周属性总和
    weeks = sorted({week for row in results for week in row["weekly"]})
    max_total = max(max(row["weekly"].values()) for row in results) * 1.1
    axis(left, "周", "三维总和", max_total, 6)
    x0, y0, x1, y1 = left
    for week in weeks[::2]:
        x = x0 + (x1 - x0) * (week - 1) / max(len(weeks) - 1, 1)
        draw_obj.text((x - 8, y1 + 8), f"W{week}", fill="#666666", font=small)
    for index, row in enumerate(results):
        color = colors[index % len(colors)]
        points = []
        for week in weeks:
            value = row["weekly"].get(week, 0)
            x = x0 + (x1 - x0) * (week - 1) / max(len(weeks) - 1, 1)
            y = y1 - (y1 - y0) * (value / max_total if max_total else 0)
            points.append((x, y))
        if len(points) > 1:
            draw_obj.line(points, fill=color, width=3)
        for x, y in points[-1:]:
            draw_obj.ellipse([x - 5, y - 5, x + 5, y + 5], fill=color)
        # 图例
        lx, ly = x0 + 16, y0 + 12 + index * 26
        draw_obj.line([(lx, ly + 8), (lx + 26, ly + 8)], fill=color, width=3)
        draw_obj.text((lx + 34, ly), f"{row['name']}  {row['mean_total']:.0f}", fill="#333333", font=small)

    # 柱状：最终总和 + 考试通过率
    max_component = max(sum(row["mean_attrs"]) for row in results) * 1.18
    axis(right, "", "三维（堆叠 Vo/Da/Vi）", max_component, 5)
    x0, y0, x1, y1 = right
    slot = (x1 - x0) / len(results)
    component_colors = ["#e0556b", "#3fa7d6", "#f2b134"]
    for index, row in enumerate(results):
        color = colors[index % len(colors)]
        bx0 = x0 + slot * index + slot * 0.14
        bx1 = bx0 + slot * 0.34
        base = y1
        for comp_index, value in enumerate(row["mean_attrs"]):
            comp_h = (y1 - y0) * (value / max_component)
            draw_obj.rectangle([bx0, base - comp_h, bx1, base], fill=component_colors[comp_index])
            draw_obj.text((bx0 + 2, base - comp_h + 2), f"{value:.0f}", fill="white", font=small)
            base -= comp_h
        draw_obj.text((bx0 + 2, base - 22), f"{sum(row['mean_attrs']):.0f}", fill="#333333", font=small)
        # 第二根：考试通过率
        rate_h = (y1 - y0) * row["exam_pass_rate"]
        cx0 = bx1 + slot * 0.06
        cx1 = cx0 + slot * 0.30
        draw_obj.rectangle([cx0, y1 - rate_h, cx1, y1], fill="#9aa7b8")
        draw_obj.text((cx0 - 4, y1 - rate_h - 24), f"{row['exam_pass_rate']*100:.0f}%", fill="#555555", font=small)
        label = row["name"].split("(")[0]
        draw_obj.text((bx0 - 2, y1 + 12), label, fill="#333333", font=small)

    draw_obj.text((840, 664), "柱=三维堆叠（Vo/Da/Vi）  灰=期中+期末通过率", fill="#777777", font=small)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=600)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--mode", choices=["idols", "strategies"], default="idols",
                        help="idols=不同角色（权重不同）; strategies=同一角色不同打法")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    global OUT
    OUT = Path(args.out) if args.out else (
        ROOT / "data" / ("sim_strategies.png" if args.mode == "strategies" else "sim_idols.png")
    )

    if args.mode == "strategies":
        base_weights = IDOLS.get("有村麻央(2極)", (0.40, 0.38, 0.22))
        tasks = [
            (name, base_weights, params, args.episodes, 4000 + index * 89)
            for index, (name, params) in enumerate(STRATEGIES.items())
        ]
    else:
        base_params = STRATEGIES["能训练就训练"]
        tasks = [
            (name, weights, base_params, args.episodes, 3000 + index * 97)
            for index, (name, weights) in enumerate(IDOLS.items())
        ]

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run_idol, tasks))

    for row in results:
        print(
            f"{row['name']:16s} weights={row['weights']} 总和={row['mean_total']:>6} "
            f"p10={row['p10']:>6} 考试通过={row['exam_pass_rate']*100:.0f}% 评价={row['grades']}"
        )
    draw(results, "同一角色不同打法对照（有村麻央 感性）" if args.mode == "strategies" else "不同偶像的培育模拟对照（审查基准权重不同）")
    suffix = "strategies" if args.mode == "strategies" else "idols"
    (ROOT / "data" / f"sim_{suffix}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("图已生成:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
