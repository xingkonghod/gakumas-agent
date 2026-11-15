"""双源训练：wiki/官方排期（official.json）+ 真机跑局（data/runs/*.json）。

输出 ``data/knowledge/calibration.json``：每个参数当前值、来源
（official / real / assumed）、证据；同时跑 300 局模拟，打印模拟 vs 真机。

用法：
    .venv\\Scripts\\python.exe scripts\\dual_fit.py
    .venv\\Scripts\\python.exe scripts\\dual_fit.py --episodes 300
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.sim.produce import (
    OFFICIAL_PATH,
    ProduceConfig,
    ProduceSim,
    StrategyParams,
    eval_value,
    strategy_from_params,
    strategy_official,
)

OUT = ROOT / "data" / "knowledge" / "calibration.json"
RUNS_DIR = ROOT / "data" / "runs"


def p50(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0


def load_official() -> dict:
    try:
        return json.loads(OFFICIAL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_real_runs() -> list[dict]:
    """读 data/runs/*.json 的结算（final.attrs/eval_points）；没有就返回空。"""
    runs: list[dict] = []
    if not RUNS_DIR.exists():
        return runs
    for path in sorted(RUNS_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        final = raw.get("final") or {}
        attrs = final.get("attrs")
        if not attrs or len(attrs) != 3:
            continue
        runs.append(
            {
                "episode": raw.get("episode") or path.stem,
                "file": str(path.relative_to(ROOT)),
                "attrs": [int(value) for value in attrs],
                "total": sum(int(value) for value in attrs),
                "eval_points": final.get("eval_points"),
                "grade": final.get("grade"),
            }
        )
    return runs


def _deck_and_pool():
    import sim_produce as sp

    deck = [sp._spec_from_row(row) for row in sp.build_deck(rich=True)]
    pool = [sp._spec_from_row(row) for row in sp.build_pool(rich=True)]
    return deck, pool


def run_simulation(strategy_name: str, episodes: int) -> dict:
    """按固定 seed 跑 N 局，返回 (三维均值, 评价点 P50, 行动分布)。"""
    deck, pool = _deck_and_pool()
    config = ProduceConfig()
    strategy = strategy_official if strategy_name == "official" else strategy_from_params(StrategyParams())
    totals: list[int] = []
    evals: list[int] = []
    actions: dict[str, int] = {}
    attrs = [0, 0, 0]
    for episode in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=9000 + episode)
        sim.reward_pool = pool
        result = sim.run(strategy)
        totals.append(result.total)
        for index, value in enumerate(result.attrs):
            attrs[index] += value
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"):
                rank = int(row["exam"]["rank"])
                break
        evals.append(eval_value(result.total, rank, result.exam_score))
        for row in sim.trace:
            key = f"{row['action']}"
            actions[key] = actions.get(key, 0) + 1
    return {
        "strategy": strategy_name,
        "episodes": episodes,
        "mean_total": round(stats.mean(totals), 1),
        "p50_total": p50(totals),
        "min_total": min(totals),
        "max_total": max(totals),
        "mean_eval": round(stats.mean(evals), 1),
        "p50_eval": p50(evals),
        "weekly_action_mix": {key: round(value / episodes, 2) for key, value in actions.items()},
        "seed": 9000,
    }


def parameter_rows(official: dict, config: ProduceConfig, real_runs: list[dict]) -> list[dict]:
    """当前参数 vs 哪个源支持它。"""
    src = official.get("source") or {}
    real_total = real_runs[0]["total"] if real_runs else None
    return [
        {
            "name": "weeks",
            "value": config.weeks,
            "source": "official",
            "evidence": "leafierlemon 16 周プロ排期（data/knowledge/official.json）",
        },
        {
            "name": "exam_weeks",
            "value": list(config.exam_weeks),
            "source": "official",
            "evidence": "排期第 7/16 周：中間試験/最終試験",
        },
        {
            "name": "class_gain_week1",
            "value": [40, 25],
            "source": "official",
            "evidence": "用户已查证 week1 授業 40 CLEAR + 25 PERFECT；页面 week2 为 40/30/15",
        },
        {
            "name": "class_gain_late",
            "value": [110, 40],
            "source": "official",
            "evidence": "leafierlemon 后期授業 110/40；用于评价/排期锚点",
        },
        {
            "name": "class_gain_fallback_curve",
            "value": [65, 125],
            "source": "assumed",
            "evidence": "非授業周（训练周/空周）默认策略仍可能选上课：65→125 线性插值",
        },
        {
            "name": "train_gain_curve",
            "value": [40, 165],
            "source": "real",
            "evidence": "真机实测训练 40→165；165 同时是最终追い込み CLEAR",
        },
        {
            "name": "special_gain",
            "value": {"week6": [90, 90], "week15": [165, 145]},
            "source": "official",
            "evidence": "leafierlemon 追い込み行 CLEAR/PERFECT",
        },
        {
            "name": "lesson_gain_formula",
            "value": (official.get("formulas") or {}).get("lesson_gain"),
            "source": "official" if src.get("formulas") == "seesaawiki" else "assumed",
            "evidence": "seesaawiki レッスン中パラメータ上昇値（好調倍率×上昇量增加）",
        },
        {
            "name": "condition_multiplier",
            "value": (official.get("formulas") or {}).get("condition_multiplier"),
            "source": "official" if src.get("formulas") == "seesaawiki" else "assumed",
            "evidence": "seesaawiki 好調・絶好調倍率：1.5+0.1×好調ターン数",
        },
        {
            "name": "eval_formula",
            "value": (official.get("formulas") or {}).get("eval"),
            "source": "official",
            "evidence": "官方评价点公式：順位点+2.3×三维+终试分段（未在缓存 mechanics 页解析到）",
        },
        {
            "name": "audition_coefficient",
            "value": config.audition_coefficient,
            "source": "real",
            "evidence": "真机 C+/5577 反推「歌唱 411%」；5992 那局的终试得分未采集",
        },
        {
            "name": "support_bonus",
            "value": config.support_bonus,
            "source": "real",
            "evidence": "支援卡 Lv10/10/10/20/10/60 的均值/SR 档折算 1.2",
        },
        {
            "name": "lesson_gain_ratio",
            "value": config.lesson_gain_ratio,
            "source": "assumed",
            "evidence": "旧口径 fallback；schedule_source=official 时不参与课程收益",
        },
        {
            "name": "stamina_max/train_cost/lesson_cost/rest_gain",
            "value": [
                config.stamina_max,
                config.train_cost,
                config.lesson_cost,
                config.rest_gain,
            ],
            "source": "assumed",
            "evidence": "模拟器手工设定，未用真机逐周体力/行动验证",
        },
        {
            "name": "exam_base/npc_factors",
            "value": [list(config.exam_base), list(config.npc_factors)],
            "source": "assumed",
            "evidence": "真机单局截图反推（1-2 样本），不是官方公式",
        },
        {
            "name": "start_attrs",
            "value": [0, 0, 0],
            "source": "assumed",
            "evidence": (
                "模拟从 0 起跑；真机起始 209/85/75=369。"
                f"真机 final total={real_total} 含起始值，模拟 total 只含成长，口径不同"
            ),
        },
        {
            "name": "official_source",
            "value": {
                "schedule": src.get("schedule"),
                "formulas": src.get("formulas"),
                "eval": src.get("eval"),
            },
            "source": "official" if src.get("schedule") == "leafierlemon" else "assumed",
            "evidence": "official.json 的 source 字段；抓取失败时 schedule 会标 manual",
        },
    ]


def diagnosis(sim: dict, real: dict) -> list[str]:
    """把「差在哪」写成可执行诊断，而不是继续调常数。"""
    items: list[str] = []
    if real:
        total_delta = (sim["mean_total"] - real["mean_total"]) / max(real["mean_total"], 1)
        eval_delta = (sim["p50_eval"] - real["mean_eval"]) / max(real["mean_eval"], 1)
        items.append(
            f"三维：模拟 {sim['mean_total']} vs 真机 {real['mean_total']} "
            f"({total_delta:+.1%})；评价点：模拟 P50 {sim['p50_eval']} vs 真机 "
            f"{real['mean_eval']} ({eval_delta:+.1%})。"
        )
    items.append(
        "评价点差额的结构性原因：真机 971 三维那局是 5992，而当前考试 proxy "
        "exam_score=2×total×4.11；在 total≈970、rank=3 时官方公式上限约 4830。"
        "rank1 在当前 NPC 基准下也不可能（第 1 名 594.5 > 满属性理论上限 ~388），"
        "所以 5992 等价于终试原始得分≈16700（4.11 系数下）。"
        "真实局终试得分/顺位没有采集，这是剩余最大未知量。"
    )
    items.append(
        "口径差异：真机 971 是 final total（含起始 209/85/75=369），模拟 total "
        "从 0 起跑、只含成长。若按「成长」对齐，真机成长约 602，而模拟 ~970；"
        "本轮按用户给定目标（final total 971）对齐，起始属性未建模。"
    )
    items.append(
        "周数分配：模拟默认策略在 16 周里做 10 次课 + 4 次休息 + 2 次考试；"
        "官方行动排期是 3 次课 + 6 次训练 + 5 次休息 + 2 次考试（体力门导致部分"
        "训练周变休息）。两者 total 都在目标附近，但「8 次课 + 4 次训练」的真机"
        "动作组合没有被强制复现。"
    )
    items.append(
        "仍 assumed 的参数：起始三维、体力/费用、npc 基准与倍率、非授课周课程收益曲线、"
        "lesson_gain_ratio（official 模式不用）。这些需要真机逐周记录或更多跑局才能收紧。"
    )
    return items


def print_table(rows: list[dict]) -> None:
    print(f"{'参数':34s} {'当前值':38s} {'来源':9s} 证据")
    print("-" * 120)
    for row in rows:
        value = str(row["value"])
        if len(value) > 38:
            value = value[:35] + "..."
        print(f"{row['name']:34s} {value:38s} {row['source']:9s} {row['evidence']}")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=300)
    args = parser.parse_args(argv)

    official = load_official()
    real_runs = load_real_runs()
    real = None
    if real_runs:
        real = {
            "count": len(real_runs),
            "mean_total": round(stats.mean([run["total"] for run in real_runs]), 1),
            "mean_eval": round(
                stats.mean([run["eval_points"] for run in real_runs if run["eval_points"]]), 1
            )
            if any(run["eval_points"] for run in real_runs)
            else None,
        }

    config = ProduceConfig()
    rows = parameter_rows(official, config, real_runs)
    print("== 当前参数 vs 来源 ==")
    print_table(rows)

    print("\n== 300 局模拟（official schedule） ==")
    official_sim = run_simulation("official", args.episodes)
    default_sim = run_simulation("default", args.episodes)
    for sim in (official_sim, default_sim):
        print(
            f"{sim['strategy']:8s} n={sim['episodes']} 三维均值={sim['mean_total']} "
            f"P50={sim['p50_total']} 评价点P50={sim['p50_eval']} "
            f"行动/局={sim['weekly_action_mix']}"
        )

    diag = diagnosis(official_sim, real or {})
    print("\n== 诊断 ==")
    for item in diag:
        print(f"- {item}")

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "inputs": {
            "official": str(OFFICIAL_PATH.relative_to(ROOT)),
            "runs": [run["file"] for run in real_runs],
        },
        "parameters": rows,
        "real_runs": {
            "count": len(real_runs),
            "runs": real_runs,
            "mean_total": real["mean_total"] if real else None,
            "mean_eval": real["mean_eval"] if real else None,
        },
        "simulation": {"official": official_sim, "default_strategy": default_sim},
        "comparisons": {
            "official_total_delta_pct": round(
                (official_sim["mean_total"] - real["mean_total"]) / max(real["mean_total"], 1) * 100,
                1,
            )
            if real
            else None,
            "official_eval_delta_pct": round(
                (official_sim["p50_eval"] - real["mean_eval"]) / max(real["mean_eval"], 1) * 100,
                1,
            )
            if real and real.get("mean_eval")
            else None,
        },
        "assumed_parameters": [row["name"] for row in rows if row["source"] == "assumed"],
        "diagnosis": diag,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
