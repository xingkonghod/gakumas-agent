"""培育模拟诊断图：评价点分布直方图 + 失败归因柱状图（PIL，不依赖 matplotlib）。

用法：
    python scripts/sim_diag.py --episodes 800

产物：
    data/sim_diag.png   （左：三种策略的评价点分布；右：输局死因柱状图）

口径：
- 评价点使用官方公式 ``eval_value(total, rank, total*2)``（从 ``gkagent.sim.produce`` 导入）；
  P50/P90 用最近秩（与 ``scripts/sim_produce.py`` 一致），打榜看尾巴，所以 P90 单独画竖线。
- 输局 = 期末 rank>3 或 官方评价点 < 4500（C+）。
- 死因可多因：课程均分<120 / 牌组没成长 / 属性够但名次不够 / 体力长期<8；
  四类都不命中的输局单独记“属性积累不足”，不硬塞进任何一类。

不 import ``scripts/sim_produce.py`` 的 build_deck/build_pool：并行任务正在改它，
本脚本自带同一套读表规则，保证 ``python scripts/sim_diag.py`` 独立可跑。
卡组/奖励池口径对齐当前 sim_produce 的 rich 模式：抽牌、好印象、好印象依赖倍率
也带进 CardSpec（默认 14 张卡组 / 137 张奖励池）。
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

from gkagent.sim.lesson import CardSpec
from gkagent.sim.produce import (
    ProduceConfig,
    ProduceSim,
    StrategyParams,
    eval_value,
    random_strategy,
    strategy_from_params,
)

OUT = ROOT / "data" / "sim_diag.png"
CARD_TABLE = ROOT / "data" / "knowledge" / "card_table.json"

# 模拟器目前真正建模的效果类型（rich 口径：抽牌/好印象/好印象依赖也建模）
MODELED_EFFECTS = {
    "ExamLesson",
    "ExamBlock",
    "ExamLessonBuff",
    "ExamConcentration",
    "ExamCardDraw",
    "ExamReview",
    "ExamLessonDependExamReview",
    "ExamFullPowerPoint",
    "ExamPreservation",
}
STARTER_NAMES = (
    "好调", "集中", "魅力的基础", "魅力的基础+", "表现的基础", "表情的基础",
    "准备运动", "粉丝服务", "聊天时间", "凭势而行", "重新开始", "姿势的基础",
    "今天也早安", "视角的基础", "可爱的举动", "猛烈地",
)

SUPPORT_BONUS = 1.2
CONFIG = ProduceConfig(reward_pick="best", support_bonus=SUPPORT_BONUS)
BIN_WIDTH = 200

STRATEGIES: dict[str, StrategyParams | None] = {
    "random": None,
    "纯训练": StrategyParams(
        lesson_every=0,
        rest_threshold=8,
        attr_choice="weight",
        outing_below=-1,
        min_stamina_to_train=10,
    ),
    "能上课就上课": StrategyParams(
        lesson_every=1,
        rest_threshold=8,
        attr_choice="weight",
        outing_below=16,
        min_stamina_to_train=8,
    ),
}

CAUSE_ORDER = ("课程没打出分", "牌组没成长", "考试名次不够", "体力断档")
STRATEGY_COLORS = {
    "random": "#9aa7b8",
    "纯训练": "#f2b134",
    "能上课就上课": "#3fa7d6",
}
CAUSE_COLORS = {
    "课程没打出分": "#e0556b",
    "牌组没成长": "#f2b134",
    "考试名次不够": "#7d5ba6",
    "体力断档": "#43aa8b",
}
CARD_TABLE_ERROR = "缺少 data/knowledge/card_table.json"


# ---------------------------------------------------------------------- 卡表/卡组
def load_card_table() -> dict:
    if not CARD_TABLE.exists():
        return {}
    return json.loads(CARD_TABLE.read_text(encoding="utf-8")).get("cards", {})


class CardRow(NamedTuple):
    """一张卡的模拟器输入：白值 + 好调/集中 + 抽牌/好印象/依赖倍率。"""

    name: str
    cost: int
    score: int
    condition: int
    focus: int
    draw: int = 0
    impression: int = 0
    impression_scale: int = 0


def _effect_fields(row: dict) -> tuple[int, int, int, int, int, int]:
    """从卡表一行的 effects 提取 (score, condition, focus, draw, impression, scale)。"""
    score = condition = focus = draw = impression = impression_scale = 0
    for effect in row.get("effects") or []:
        kind = effect.get("type")
        values = [value for value in effect.get("values") or [] if value]
        value = int(values[0]) if values else 0
        if not value:
            continue
        if kind == "ExamLesson":
            score = max(score, value)
        elif kind == "ExamLessonBuff":
            condition = max(condition, value)
        elif kind == "ExamConcentration":
            focus = max(focus, value)
        elif kind == "ExamCardDraw":
            draw = max(draw, value)
        elif kind == "ExamReview":
            impression = max(impression, value)
        elif kind == "ExamLessonDependExamReview":
            impression_scale = max(impression_scale, value)
    return score, condition, focus, draw, impression, impression_scale


def build_deck_raw(table: dict) -> list[CardRow]:
    """卡组：14 张，数值来自 card_table（rich 口径）。

    与 scripts/sim_produce.py 的 build_deck(rich=True) 同规则；本脚本不 import 它，
    避免并行改文件时互相影响。
    """
    deck: list[CardRow] = []
    for name in STARTER_NAMES:
        row = table.get(name)
        if not row:
            continue  # 好调/集中不在 card_table（只有带数值的卡），与 sim_produce 一致
        score, condition, focus, draw, impression, scale = _effect_fields(row)
        deck.append(
            CardRow(name, int(row.get("cost", 4)), score, condition, focus,
                    draw, impression, scale)
        )
    return deck


def build_pool_raw(table: dict, max_score: int = 40) -> list[CardRow]:
    """奖励池：只收已建模、非 SSR/Legend、分数 <=40 的卡（rich 口径，137 张）。"""
    pool: list[CardRow] = []
    for name, row in table.items():
        cost = int(row.get("cost") or 0)
        if cost > 8 or cost < 0:
            continue
        score, condition, focus, draw, impression, scale = _effect_fields(row)
        if str(row.get("rarity") or "") in ("Ssr", "Legend"):
            continue
        if score <= 0 or score > max_score:
            continue
        effect_types = {str(effect.get("type") or "") for effect in row.get("effects") or []}
        if not effect_types or not effect_types <= MODELED_EFFECTS:
            continue
        pool.append(CardRow(name, cost, score, condition, focus, draw, impression, scale))
    return pool


def specs(raw: list[CardRow]) -> list[CardSpec]:
    return [
        CardSpec(
            name=row.name,
            cost=row.cost,
            score=row.score,
            condition=row.condition,
            focus=row.focus,
            draw=row.draw,
            impression=row.impression,
            impression_scale=row.impression_scale,
        )
        for row in raw
    ]


# ---------------------------------------------------------------------- 模拟
def final_rank(trace: list[dict]) -> int:
    for row in reversed(trace):
        exam = row.get("exam")
        if exam:
            return int(exam["rank"])
    return 3


def longest_low_stamina(trace: list[dict], threshold: int = 8) -> tuple[int, int]:
    """返回 (stamina_after<8 的总周数, 最长连续周数)。"""
    total = streak = best = 0
    for row in trace:
        if int(row.get("stamina_after", CONFIG.stamina_max)) < threshold:
            total += 1
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return total, best


def evaluate_run(sim: ProduceSim, result, deck_size: int) -> dict:
    rank = final_rank(sim.trace)
    total = result.total
    points = eval_value(total, rank, total * 2)
    lesson_scores = [
        int(row["lesson"]["score"])
        for row in sim.trace
        if row.get("action") == "lesson" and row.get("lesson")
    ]
    lesson_avg = st.mean(lesson_scores) if lesson_scores else 0.0
    low_weeks, low_streak = longest_low_stamina(sim.trace)
    growth = len(sim.deck) - deck_size
    return {
        "total": total,
        "rank": rank,
        "points": points,
        "lesson_avg": lesson_avg,
        "reward_picks": sim.reward_picks,
        "deck_growth": growth,
        "low_weeks": low_weeks,
        "low_streak": low_streak,
        "lost": rank > 3 or points < 4500,
        # rank>3 时顺位点=0，若这时评价点仍 >=4500，说明属性本身够 C+，只输在名次。
        "exam_limited": rank > 3 and points >= 4500,
        "course_failed": lesson_avg < 120,
        "deck_failed": sim.reward_picks == 0 or growth <= 0,
        "stamina_failed": low_weeks >= 4 or low_streak >= 3,
    }


def run_strategy(
    name: str,
    episodes: int,
    deck_raw: list[CardRow],
    pool_raw: list[CardRow],
    seed_base: int,
) -> dict:
    deck = specs(deck_raw)
    pool = specs(pool_raw)
    strategy_params = STRATEGIES[name]
    strategy = strategy_from_params(strategy_params) if strategy_params else None

    evals: list[int] = []
    totals: list[int] = []
    lesson_avgs: list[float] = []
    losses = 0
    causes: Counter[str] = Counter()
    residual = 0
    for episode in range(episodes):
        seed = seed_base + episode
        strategy_fn = random_strategy(seed) if strategy is None else strategy
        sim = ProduceSim(deck, config=CONFIG, rng_seed=seed)
        sim.reward_pool = pool
        result = sim.run(strategy_fn)
        row = evaluate_run(sim, result, len(deck))
        evals.append(row["points"])
        totals.append(row["total"])
        lesson_avgs.append(row["lesson_avg"])
        if not row["lost"]:
            continue
        losses += 1
        hit = False
        for cause in CAUSE_ORDER:
            flag = {
                "课程没打出分": row["course_failed"],
                "牌组没成长": row["deck_failed"],
                "考试名次不够": row["exam_limited"],
                "体力断档": row["stamina_failed"],
            }[cause]
            if flag:
                causes[cause] += 1
                hit = True
        if not hit:
            residual += 1

    ordered = sorted(evals)
    return {
        "name": name,
        "n": episodes,
        "evals": evals,
        "mean": st.mean(evals) if evals else 0.0,
        "p50": percentile(ordered, 0.50),
        "p90": percentile(ordered, 0.90),
        "p95": percentile(ordered, 0.95),
        "cplus_rate": sum(1 for value in evals if value >= 4500) / max(len(evals), 1),
        "mean_total": st.mean(totals) if totals else 0.0,
        "mean_lesson": st.mean(lesson_avgs) if lesson_avgs else 0.0,
        "losses": losses,
        "causes": causes,
        "residual": residual,
    }


def percentile(ordered: list[int], q: float) -> int:
    if not ordered:
        return 0
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


# ---------------------------------------------------------------------- 绘图
def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)
    except OSError:
        return ImageFont.load_default()


def _text_size(draw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _nice_axis(max_value: float, target_ticks: int = 5) -> tuple[int, int]:
    """返回 (轴上限, 刻度步长)，保证 max_value 上方还有一点余量。"""
    if max_value <= 0:
        return 1, 1
    padded = max_value * 1.10
    raw = padded / target_ticks
    magnitude = 10 ** math.floor(math.log10(raw))
    step = magnitude
    for mult in (1, 2, 2.5, 5, 10):
        step = magnitude * mult
        if step >= raw:
            break
    step = max(1, int(step))
    return step * math.ceil(padded / step), step


def _dashed_vertical(draw, x: int, y0: int, y1: int, fill, width: int = 2) -> None:
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + 8, y1))], fill=fill, width=width)
        y += 14


def draw_chart(
    results: list[dict],
    cause_counts: Counter[str],
    total_losses: int,
    total_runs: int,
    residual: int,
    out_path: Path,
) -> None:
    from PIL import Image, ImageDraw

    width, height = 1600, 960
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image, "RGBA")

    title_font = _font(28)
    head_font = _font(20)
    subtitle_font = _font(16)
    body_font = _font(16)
    small_font = _font(14)
    tick_font = _font(14)
    category_font = _font(17)

    draw.text((50, 22), "培育模拟诊断：评价点分布 + 失败归因", fill="#111111", font=title_font)
    draw.text(
        (50, 60),
        f"每策略 {results[0]['n']} 局  |  官方评价点 = eval_value(三维总和, 期末名次, 总和×2)  "
        f"|  支援加成 {SUPPORT_BONUS}  |  奖励选最强  |  {CONFIG.weeks} 周  "
        f"|  左图 {BIN_WIDTH} 点/箱",
        fill="#555555",
        font=subtitle_font,
    )

    # ---------------------------------------------------------------- 左：直方图
    left = (90, 195, 930, 740)
    lx0, ly0, lx1, ly1 = left
    all_evals = [value for result in results for value in result["evals"]]
    max_eval = max(all_evals) if all_evals else 0
    x_max = max(1000, math.ceil(max_eval / 1000) * 1000)
    bin_width = BIN_WIDTH
    bin_count = max(1, x_max // bin_width)
    hist_counts: dict[str, list[int]] = {}
    for result in results:
        counts = [0] * bin_count
        for value in result["evals"]:
            index = min(bin_count - 1, max(0, value // bin_width))
            counts[index] += 1
        hist_counts[result["name"]] = counts
    y_max, y_step = _nice_axis(max(max(counts) for counts in hist_counts.values()), 5)

    def x_of(value: float) -> int:
        return lx0 + int((lx1 - lx0) * value / max(x_max, 1))

    def y_of(value: float) -> int:
        return ly1 - int((ly1 - ly0) * value / max(y_max, 1))

    # 网格与坐标轴
    y_ticks = max(1, y_max // y_step) if y_step else 1
    for index in range(y_ticks + 1):
        value = index * y_step
        y = y_of(value)
        draw.line([(lx0, y), (lx1, y)], fill="#e9ecf1", width=1)
        draw.text((lx0 - 8, y - 9), str(int(value)), fill="#666666", font=tick_font, anchor="ra")
    for value in range(0, x_max + 1, 1000):
        x = x_of(value)
        draw.line([(x, ly0), (x, ly1)], fill="#f1f3f6", width=1)
        draw.text((x, ly1 + 8), str(value), fill="#666666", font=tick_font, anchor="ma")
    draw.rectangle(left, outline="#c9ced8", width=1)

    # 半透明叠加柱（后画的策略盖在前面的上面，仍能看出版形）
    bin_px = (lx1 - lx0) / bin_count
    for result in results:
        color = _rgb(STRATEGY_COLORS[result["name"]])
        counts = hist_counts[result["name"]]
        for index, count in enumerate(counts):
            if count <= 0:
                continue
            x0 = lx0 + int(index * bin_px)
            x1 = lx0 + int((index + 1) * bin_px) - 1
            top = y_of(count)
            draw.rectangle(
                [x0 + 1, top, x1, ly1],
                fill=(color[0], color[1], color[2], 65),
                outline=(color[0], color[1], color[2], 200),
                width=1,
            )

    # P50 / P90 竖线（实线 / 虚线）
    for result in results:
        color = _rgb(STRATEGY_COLORS[result["name"]])
        x_p50 = x_of(result["p50"])
        x_p90 = x_of(result["p90"])
        draw.line([(x_p50, ly0), (x_p50, ly1)], fill=color, width=2)
        _dashed_vertical(draw, x_p90, ly0, ly1, color, width=2)
        for label, x in (("P50", x_p50), ("P90", x_p90)):
            if abs(x_p90 - x_p50) <= 45:
                continue
            text_w, text_h = _text_size(draw, label, small_font)
            if label == "P50":
                tx = max(lx0 + 2, x - text_w - 6)
            else:
                tx = min(lx1 - text_w - 2, x + 6)
            ty = ly0 + 5 if label == "P50" else ly0 + 25
            draw.rectangle([tx - 3, ty - 2, tx + text_w + 3, ty + text_h + 2],
                           fill=(255, 255, 255, 235), outline=color, width=1)
            draw.text((tx, ty), label, fill=color, font=small_font)

    # 每策略的 P50/P90 文字（放在图上方，按策略占一行，避免与柱/彼此重叠）
    for index, result in enumerate(results):
        color = _rgb(STRATEGY_COLORS[result["name"]])
        text = f"{result['name']}  P50 {result['p50']}   P90 {result['p90']}"
        text_w, text_h = _text_size(draw, text, body_font)
        anchor = (x_of(result["p50"]) + x_of(result["p90"])) // 2
        box_w = text_w + 34
        box_x = min(max(lx0, anchor - box_w // 2), lx1 - box_w)
        box_y = 96 + index * 30
        draw.rectangle([box_x, box_y, box_x + box_w, box_y + text_h + 6],
                       fill="#ffffff", outline=color, width=2)
        draw.line([(box_x + 8, box_y + text_h // 2 + 3),
                   (box_x + 26, box_y + text_h // 2 + 3)], fill=color, width=3)
        draw.text((box_x + 31, box_y + 3), text, fill="#222222", font=body_font)

    draw.text(((lx0 + lx1) // 2, 770), "官方评价点", fill="#333333", font=body_font, anchor="ma")
    draw.text((lx0, ly0 - 20), "局数", fill="#666666", font=small_font)

    # 图例
    for index, result in enumerate(results):
        color = _rgb(STRATEGY_COLORS[result["name"]])
        y = 806 + index * 23
        draw.line([(lx0, y + 9), (lx0 + 28, y + 9)], fill=color, width=3)
        draw.text(
            (lx0 + 36, y),
            f"{result['name']}   n={result['n']}   输局 {result['losses']}",
            fill="#333333",
            font=small_font,
        )
    draw.text((lx0 + 330, 806), "实线=P50  虚线=P90", fill="#666666", font=small_font)
    draw.text((lx0 + 330, 829), "柱=局数（半透明叠加）", fill="#666666", font=small_font)

    # ---------------------------------------------------------------- 右：死因柱状图
    right = (1080, 195, 1560, 700)
    rx0, ry0, rx1, ry1 = right
    sorted_causes = sorted(
        ((cause, cause_counts.get(cause, 0)) for cause in CAUSE_ORDER),
        key=lambda item: (-item[1], CAUSE_ORDER.index(item[0])),
    )
    bar_y_max, bar_y_step = _nice_axis(max(value for _, value in sorted_causes), 5)

    def bar_y(value: float) -> int:
        return ry1 - int((ry1 - ry0) * value / max(bar_y_max, 1))

    draw.text((rx0, 108), "失败归因（只统计输局）", fill="#111111", font=head_font)
    draw.text(
        (rx0, 138),
        f"输局 {total_losses} / {total_runs}（{total_losses / max(total_runs, 1):.0%}）"
        "  |  一局可命中多条，柱=命中局数",
        fill="#555555",
        font=small_font,
    )

    bar_ticks = max(1, bar_y_max // bar_y_step) if bar_y_step else 1
    for index in range(bar_ticks + 1):
        value = index * bar_y_step
        y = bar_y(value)
        draw.line([(rx0, y), (rx1, y)], fill="#e9ecf1", width=1)
        draw.text((rx0 - 8, y - 9), str(int(value)), fill="#666666", font=tick_font, anchor="ra")
    draw.rectangle(right, outline="#c9ced8", width=1)

    slot = (rx1 - rx0) / len(sorted_causes)
    bar_width = int(slot * 0.56)
    loss_by_name = {result["name"]: result["losses"] for result in results}
    for index, (cause, count) in enumerate(sorted_causes):
        center = rx0 + int(slot * (index + 0.5))
        bx0, bx1 = center - bar_width // 2, center + bar_width // 2
        color = _rgb(CAUSE_COLORS[cause])
        if count > 0:
            top = bar_y(count)
            draw.rectangle(
                [bx0, top, bx1, ry1],
                fill=(color[0], color[1], color[2], 185),
                outline=color,
                width=2,
            )
            value_y = top - 24
        else:
            draw.rectangle([bx0, ry1 - 3, bx1, ry1], fill="#c9ced8")
            value_y = ry1 - 50
        percent = count / max(total_losses, 1) * 100
        draw.text(
            (center, value_y),
            f"{count}（{percent:.0f}%）",
            fill="#333333" if count else "#999999",
            font=small_font,
            anchor="ma",
        )
        label_lines = {
            "课程没打出分": ("课程没", "打出分"),
            "牌组没成长": ("牌组没", "成长"),
            "考试名次不够": ("考试名次", "不够"),
            "体力断档": ("体力", "断档"),
        }[cause]
        draw.text((center, ry1 + 12), label_lines[0], fill="#333333", font=category_font,
                  anchor="ma")
        draw.text((center, ry1 + 34), label_lines[1], fill="#333333", font=category_font,
                  anchor="ma")

    notes = [
        (
            f"random 输局 {loss_by_name['random']} / 纯训练 {loss_by_name['纯训练']} / "
            f"能上课就上课 {loss_by_name['能上课就上课']}"
        ),
        f"{residual} 局四类均未命中（属性积累/上课次数不足，单独统计）",
        "课程=课程均分<120；牌组=reward_picks==0 或牌组规模未涨",
        "考试=rank>3 且属性单独已够 C+；体力=≥4 周 stamina_after<8 或连续≥3 周",
    ]
    for index, note in enumerate(notes):
        draw.text((rx0, 760 + index * 22), note, fill="#666666", font=small_font)

    draw.text(
        (50, 912),
        "输局 = 期末 rank>3 或 eval_value(total, rank, total×2) < 4500（C+）；"
        "P50/P90 为最近秩，P90 是打榜看的尾部。",
        fill="#777777",
        font=small_font,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)


# ---------------------------------------------------------------------- 输出
def _pad(text: str, width: int) -> str:
    display = sum(2 if ord(char) > 0x2E80 else 1 for char in text)
    return text + " " * max(0, width - display)


def print_report(results: list[dict], cause_counts: Counter[str], total_losses: int,
                 total_runs: int, residual: int) -> None:
    print(
        f"配置: {CONFIG.weeks} 周 | 支援加成 {SUPPORT_BONUS} | 奖励选最强 | "
        f"每策略 {results[0]['n']} 局"
    )
    print(_pad("策略", 14) + _pad("局数", 7) + _pad("P50", 7) + _pad("P90", 7)
          + _pad("P95", 7) + _pad("均值", 8) + _pad("C+率", 7) + "输局")
    for result in results:
        print(
            _pad(result["name"], 14)
            + _pad(str(result["n"]), 7)
            + _pad(str(result["p50"]), 7)
            + _pad(str(result["p90"]), 7)
            + _pad(str(result["p95"]), 7)
            + _pad(f"{result['mean']:.0f}", 8)
            + _pad(f"{result['cplus_rate'] * 100:.0f}%", 7)
            + str(result["losses"])
        )
    print()
    print(f"输局 {total_losses} / {total_runs}（{total_losses / max(total_runs, 1):.1%}）")
    print("死因（一局可命中多条，按命中局数排序）:")
    for cause, count in sorted(
        ((cause, cause_counts.get(cause, 0)) for cause in CAUSE_ORDER),
        key=lambda item: (-item[1], CAUSE_ORDER.index(item[0])),
    ):
        print(f"  {_pad(cause, 12)}{count:5d}  ({count / max(total_losses, 1):.1%})")
    print(f"  {_pad('四类均未命中', 12)}{residual:5d}  "
          f"({residual / max(total_losses, 1):.1%})  ← 属性积累/上课次数不足")
    print("\n按策略拆分（命中局数，可多因）:")
    print(_pad("死因", 14) + "".join(_pad(result["name"], 14) for result in results))
    for cause in CAUSE_ORDER:
        print(_pad(cause, 14) + "".join(
            _pad(str(result["causes"].get(cause, 0)), 14) for result in results
        ))
    print(_pad("四类均未命中", 14) + "".join(
        _pad(str(result["residual"]), 14) for result in results
    ))


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="培育模拟：评价点分布 + 失败归因")
    parser.add_argument("--episodes", type=int, default=800, help="每种策略的局数")
    parser.add_argument("--seed", type=int, default=20261115, help="种子基数")
    parser.add_argument("--out", default=str(OUT), help="输出 PNG 路径")
    args = parser.parse_args(argv)
    if args.episodes < 1:
        parser.error("--episodes 必须 >= 1")

    table = load_card_table()
    if not table:
        print(CARD_TABLE_ERROR, file=sys.stderr)
        return 1
    deck_raw = build_deck_raw(table)
    pool_raw = build_pool_raw(table)
    if not deck_raw or not pool_raw:
        print("卡组/奖励池为空，无法模拟", file=sys.stderr)
        return 1
    print(f"卡组 {len(deck_raw)} 张，奖励池 {len(pool_raw)} 张，每策略 {args.episodes} 局")
    results = []
    for name in STRATEGIES:
        print(f"跑 {name} × {args.episodes} ...")
        results.append(run_strategy(name, args.episodes, deck_raw, pool_raw, args.seed))

    cause_counts: Counter[str] = Counter()
    residual = 0
    total_losses = 0
    for result in results:
        cause_counts.update(result["causes"])
        residual += result["residual"]
        total_losses += result["losses"]
    total_runs = sum(result["n"] for result in results)

    print_report(results, cause_counts, total_losses, total_runs, residual)
    out_path = Path(args.out)
    draw_chart(results, cause_counts, total_losses, total_runs, residual, out_path)
    print(f"\n图已生成: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
