"""一百万局模拟 + 五张诊断图（2026-11-16 新版模型）。

图 1：分数分布直方图（random / greedy / optimal 三种策略，标 P50/P90）
图 2：sim-real 散点（模拟预测 vs 真机实测）
图 3：策略门槛扫描（rest_threshold 4→15，模拟 beam 宽度的边际收益）
图 4：rollout 次数 K 扫描（1/2/4/8/16/32，模拟 determinization 饱和点）
图 5：失败归因柱状（没进 C+ 的局按死因分类）

用法：python scripts/sim_million.py --episodes 1000000 --workers 20
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT_JSON = ROOT / "data" / "million_stats.json"
OUT_PNG = ROOT / "data" / "million_charts.png"

STATE: dict = {}


def _init() -> None:
    import sim_produce as sp
    from gkagent.sim.produce import ProduceConfig

    STATE["deck"] = [sp._spec_from_row(r) for r in sp.build_deck(rich=True)]
    STATE["pool"] = [sp._spec_from_row(r) for r in sp.build_pool(rich=True)]
    STATE["cfg"] = ProduceConfig(reward_pick="best", schedule_source="official")


def _one(seed: int, mode: str):
    from gkagent.sim.produce import ProduceSim, eval_value, random_strategy, strategy_from_params, strategy_optimal, StrategyParams

    sim = ProduceSim(STATE["deck"], config=STATE["cfg"], rng_seed=seed)
    sim.reward_pool = STATE["pool"]
    if mode == "random":
        strategy = random_strategy(seed)
    elif mode == "greedy":
        strategy = strategy_from_params(StrategyParams(training_every=1, rest_threshold=10,
                                                       training_min_stamina=12, attr_choice="weight",
                                                       outing_below=-1, min_stamina_for_class=8))
    else:
        strategy = strategy_optimal
    result = sim.run(strategy)
    total = sum(result.attrs)
    rank = 3
    for row in reversed(sim.trace):
        if row.get("exam"):
            rank = row["exam"]["rank"]
            break
    exam_score = (sim.last_exam or {}).get("score", 0)
    ev = eval_value(total, rank, exam_score)
    # 死因
    if ev >= 4500:
        cause = "C+达成"
    elif rank > 3:
        cause = "考试名次不够"
    elif total < 950:
        cause = "属性不足(练少了)"
    elif exam_score < 4000:
        cause = "考试得分低(没叠buff)"
    else:
        cause = "其他"
    return total, rank, exam_score, ev, cause


def _batch(args):
    seeds, mode = args
    return [_one(seed, mode) for seed in seeds]


def run(episodes: int, workers: int) -> dict:
    t0 = time.time()
    chunks = max(workers * 4, 40)
    per = max(episodes // chunks, 1)
    modes = ("optimal", "greedy", "random")
    tasks = []
    base = 0
    for mode in modes:
        n = episodes if mode == "optimal" else max(episodes // 10, 2000)
        for i in range(0, n, per):
            tasks.append((list(range(base + i, base + min(i + per, n))), mode))
        base += n
    results = {mode: [] for mode in modes}
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as pool:
        for (seeds, mode), rows in zip(tasks, pool.map(_batch, tasks)):
            results[mode].extend(rows)
    elapsed = time.time() - t0
    stats = {"elapsed_s": round(elapsed, 1), "n": {m: len(v) for m, v in results.items()}, "runs": results}
    print(f"总 {sum(len(v) for v in results.values())} 局 / {elapsed:.1f}s")
    for mode, rows in results.items():
        totals = sorted(r[0] for r in rows)
        evals = sorted(r[3] for r in rows)
        n = len(rows)
        print(f"  {mode:8s} n={n:7d} 三维P50={totals[n//2]:5d} 评价P50={evals[n//2]:5d} P90={evals[n*9//10]:5d} max={evals[-1]:5d} "
              f"C+率={sum(1 for e in evals if e >= 4500)/n*100:5.1f}%")
    OUT_JSON.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    return stats


def draw(stats: dict) -> None:
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1600, 1000
    img = Image.new("RGB", (W, H), "white")
    c = ImageDraw.Draw(img)
    try:
        ft = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 24)
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
        fs = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
    except OSError:
        ft = f = fs = ImageFont.load_default()
    c.text((40, 18), "一百万局模拟：分布 / 校准 / 边际收益 / 失败归因", fill="#111", font=ft)
    runs = stats["runs"]

    # 图1 分布直方图
    box = (80, 110, 760, 460)
    x0, y0, x1, y1 = box
    c.rectangle(box, outline="#ccc")
    c.text((x0, y0 - 26), "1. 分数分布（P50/P90 优先于均值）", fill="#333", font=f)
    lo, hi = 2500, 6500
    bins = 40
    colors = {"optimal": "#e0556b", "greedy": "#3fa7d6", "random": "#9aa7b8"}
    series = {}
    for mode, rows in runs.items():
        hist = [0] * bins
        for row in rows:
            idx = min(max((row[3] - lo) * bins // (hi - lo), 0), bins - 1)
            hist[idx] += 1
        peak = max(hist) or 1
        series[mode] = (hist, peak)
    for mode, (hist, peak) in series.items():
        pts = []
        for i, h in enumerate(hist):
            x = x0 + (x1 - x0) * i / (bins - 1)
            y = y1 - (y1 - y0) * h / peak
            pts.append((x, y))
        c.line(pts, fill=colors[mode], width=2)
    for thr, label in ((4500, "C+ 4500"), (6000, "B 6000")):
        x = x0 + (x1 - x0) * (thr - lo) / (hi - lo)
        c.line([(x, y0), (x, y1)], fill="#43aa8b", width=2)
        c.text((x + 2, y0 + 2), label, fill="#43aa8b", font=fs)
    for i, mode in enumerate(("optimal", "greedy", "random")):
        c.text((x0 + 10, y0 + 16 + i * 20), mode, fill=colors[mode], font=fs)

    # 图2 sim-real 散点
    box = (860, 110, 1500, 460)
    x0, y0, x1, y1 = box
    c.rectangle(box, outline="#ccc")
    c.text((x0, y0 - 26), "2. sim-real 校准（点=真机实测局）", fill="#333", font=f)
    real = [(1832, 1832, "美铃 632"), (3330, 3200, "手动 C"), (4135, 4100, "手动 C"), (5992, 4547, "手动 C+")]
    c.line([(x0, y1), (x1, y0)], fill="#ddd", width=2)
    for xv, yv, name in real:
        x = x0 + (x1 - x0) * xv / 7000
        y = y1 - (y1 - y0) * yv / 7000
        c.ellipse([x - 6, y - 6, x + 6, y + 6], fill="#e0556b")
        c.text((x + 8, y - 8), name, fill="#333", font=fs)

    # 图3 rest_threshold 扫描
    box = (80, 520, 760, 900)
    x0, y0, x1, y1 = box
    c.rectangle(box, outline="#ccc")
    c.text((x0, y0 - 26), "3. 策略门槛扫描（rest_threshold → 评价点 P50）", fill="#333", font=f)
    sweep = stats.get("sweep_rest", [])
    if sweep:
        vals = [s["p50"] for s in sweep]
        lo2, hi2 = min(vals), max(vals)
        pts = []
        for i, s in enumerate(sweep):
            x = x0 + (x1 - x0) * i / max(len(sweep) - 1, 1)
            y = y1 - (y1 - y0) * ((s["p50"] - lo2) / max(hi2 - lo2, 1) * 0.8 + 0.1)
            pts.append((x, y))
            c.text((x - 12, y1 + 8), str(s["rest_threshold"]), fill="#666", font=fs)
            c.text((x - 18, y - 20), f"{s['p50']}", fill="#333", font=fs)
        c.line(pts, fill="#7d5ba6", width=3)

    # 图4 rollout K 扫描
    box = (860, 520, 1500, 900)
    x0, y0, x1, y1 = box
    c.rectangle(box, outline="#ccc")
    c.text((x0, y0 - 26), "4. rollout 次数 K 扫描（决策质量边际收益）", fill="#333", font=f)
    ks = stats.get("sweep_k", [])
    if ks:
        vals = [s["expected"] for s in ks]
        lo2, hi2 = min(vals), max(vals)
        pts = []
        for i, s in enumerate(ks):
            x = x0 + (x1 - x0) * i / max(len(ks) - 1, 1)
            y = y1 - (y1 - y0) * ((s["expected"] - lo2) / max(hi2 - lo2, 1) * 0.8 + 0.1)
            pts.append((x, y))
            c.text((x - 10, y1 + 8), str(s["k"]), fill="#666", font=fs)
            c.text((x - 20, y - 20), f"{s['expected']:.0f}", fill="#333", font=fs)
        c.line(pts, fill="#43aa8b", width=3)

    # 图5 失败归因
    box = (120, 940, 1500, 990)
    causes = Counter()
    for row in runs["optimal"]:
        causes[row[4]] += 1
    total = sum(causes.values()) or 1
    x = box[0]
    for name, count in causes.most_common():
        w = (box[2] - box[0]) * count / total
        color = "#e0556b" if name != "C+达成" else "#43aa8b"
        c.rectangle([x, box[1], x + w, box[3]], fill=color)
        if w > 90:
            c.text((x + 4, box[1] + 6), f"{name} {count/total*100:.0f}%", fill="white", font=fs)
        x += w
    c.text((120, 915), "5. 失败归因（optimal 策略，按死因占比）", fill="#333", font=f)

    img.save(OUT_PNG)
    print("图已生成:", OUT_PNG)


def sweep_rest(workers: int, n: int = 20000) -> list[dict]:
    from gkagent.sim.produce import ProduceSim, eval_value, strategy_from_params, StrategyParams

    _init()
    out = []
    for threshold in (4, 6, 8, 10, 12, 15):
        params = StrategyParams(rest_threshold=threshold, training_every=1, training_min_stamina=12,
                                attr_choice="weight", outing_below=-1, min_stamina_for_class=8)
        strategy = strategy_from_params(params)
        evals = []
        for seed in range(n):
            sim = ProduceSim(STATE["deck"], config=STATE["cfg"], rng_seed=seed)
            sim.reward_pool = STATE["pool"]
            result = sim.run(strategy)
            total = sum(result.attrs)
            rank = 3
            for row in reversed(sim.trace):
                if row.get("exam"):
                    rank = row["exam"]["rank"]
                    break
            evals.append(eval_value(total, rank, (sim.last_exam or {}).get("score", 0)))
        evals.sort()
        out.append({"rest_threshold": threshold, "p50": evals[len(evals) // 2]})
        print(f"  rest={threshold}: P50={evals[len(evals)//2]}")
    return out


def sweep_k() -> list[dict]:
    """rollout 次数 K → 单次决策的期望得分（模拟 determinization 饱和点）。"""
    from gkagent.sim.play_choice import estimate_hand
    from gkagent.vision.lesson import LessonCard

    _init()
    hand = [
        LessonCard(index=0, box=(0, 0, 0, 0), point=(0, 0), name="在我发现的世界", score=0, cost=4, buff=True, text=""),
        LessonCard(index=1, box=(0, 0, 0, 0), point=(0, 0), name="试行错误+", score=84, cost=5, buff=False, text=""),
        LessonCard(index=2, box=(0, 0, 0, 0), point=(0, 0), name="轻快步伐", score=25, cost=4, buff=False, text=""),
    ]
    out = []
    for k in (1, 2, 4, 8, 16, 32):
        est = estimate_hand(hand, turns_left=6, stamina=20, episodes=k, time_budget_ms=100000)
        best = max((e.expected for e in est), default=0)
        out.append({"k": k, "expected": round(best, 1)})
        print(f"  K={k}: 最佳期望 {best:.1f}")
    return out


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=1_000_000)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--skip-sweeps", action="store_true")
    args = parser.parse_args(argv)
    stats = run(args.episodes, args.workers)
    if not args.skip_sweeps:
        print("门槛扫描…")
        stats["sweep_rest"] = sweep_rest(args.workers)
        print("rollout K 扫描…")
        stats["sweep_k"] = sweep_k()
        OUT_JSON.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    draw(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
