"""L3 配对评测：固定优先级（greedy）vs 回合内 expectimax vs 跨回合 beam。

2000 局同牌组、同牌序（同 seed）配对；报告评价点 P10/P50/P90/均值 + PERFECT 率。
主门槛（用户 2026-11-16 新口径）：**评价点 P50 提升 ≥6% 且 95% CI 下界 >2%**；
PERFECT 率提升 ≥5pp。不再输出 C+率/B率（C+ 是课题要求，不是优化目标）。

用法（venv，任意 cwd）：
    .venv\\Scripts\\python.exe scripts\\eval_expectimax.py
    .venv\\Scripts\\python.exe scripts\\eval_expectimax.py --episodes 2000 --sweep
    .venv\\Scripts\\python.exe scripts\\eval_expectimax.py --scenario small --episodes 500

规模：
    large = 31 张牌 / 9 回合 / 体力 60（对齐"大牌组，捨札基本不洗回"）
    small = 14 张牌 / 5 回合 / 体力 34（对齐"小牌组，捨札洗回 1-2 次"）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    expectimax,
    search_beam,
    state_from_sim,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim, greedy_policy

MASTER_PATH = ROOT / "data" / "master" / "produce_cards.json"
RESULT_PATH = ROOT / "data" / "bench" / "expectimax_eval.json"
DEFAULT_SIGMA = 60.0

SCENARIOS: dict[str, dict[str, Any]] = {
    "large": {
        "turns": 9,
        "stamina": 60,
        "clear": 300,
        "perfect": 450,
        "deck_size": 31,
    },
    "small": {
        "turns": 5,
        "stamina": 34,
        "clear": 120,
        "perfect": 170,
        "deck_size": 14,
    },
}


# ---------------------------------------------------------------- 牌组
def _master_texts() -> dict[str, str]:
    if not MASTER_PATH.exists():
        return {}
    rows = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
    return {row.get("name", ""): row.get("text", "") for row in rows}


def _is_once(name: str, texts: dict[str, str]) -> bool:
    text = texts.get(name, "")
    return "仅限1次" in text or "訓練中1回" in text or "レッスン中1回" in text


def _with_once(spec: CardSpec, texts: dict[str, str]) -> CardSpec:
    if spec.once == _is_once(spec.name, texts):
        return spec
    return CardSpec(
        **{
            field: getattr(spec, field)
            for field in spec.__dataclass_fields__
            if field != "once"
        },
        once=_is_once(spec.name, texts),
    )


def build_deck(scenario: str) -> list[CardSpec]:
    """按场景构造真实卡组（14 张基础 + 奖励池补到 31 张），并标「训练中1次」。"""
    import sim_produce as sp

    texts = _master_texts()
    base = [_with_once(sp._spec_from_row(row), texts) for row in sp.build_deck(rich=True)]
    wanted = SCENARIOS[scenario]["deck_size"]
    if len(base) >= wanted:
        return base[:wanted]
    have = {card.name for card in base}
    picked = list(base)
    pool = [_with_once(sp._spec_from_row(row), texts) for row in sp.build_pool(rich=True)]
    # 先保证抽牌/好印象/元气/可出牌次数/指針等各种机制都至少有一张
    signatures = (
        lambda c: c.draw > 0,
        lambda c: c.impression > 0 or c.impression_scale > 0,
        lambda c: c.vitality > 0 or c.block_scale > 0,
        lambda c: c.extra_play > 0,
        lambda c: c.preservation > 0 or c.full_power_point > 0 or c.strong_level > 0,
        lambda c: c.focus > 0,
        lambda c: c.condition > 0,
    )
    for signature in signatures:
        for row in pool:
            if len(picked) >= wanted:
                break
            if row.name not in have and signature(row):
                have.add(row.name)
                picked.append(row)
                break
    for row in pool:
        if len(picked) >= wanted:
            break
        if row.name not in have:
            have.add(row.name)
            picked.append(row)
    return picked[:wanted]


def make_config(scenario: str) -> LessonConfig:
    meta = SCENARIOS[scenario]
    return LessonConfig(
        turns=int(meta["turns"]),
        stamina=int(meta["stamina"]),
        target_clear=int(meta["clear"]),
        target_perfect=int(meta["perfect"]),
    )


# ---------------------------------------------------------------- 策略
def _card_index(sim: LessonSim, card: CardSpec | None) -> int | None:
    if card is None:
        return None
    for index, hand_card in enumerate(sim.hand):
        if hand_card == card:
            return index
    return None


def _fallback_greedy(sim: LessonSim) -> int | None:
    action = greedy_policy(sim)
    return action


def rules_policy(sim: LessonSim) -> int | None:
    """固定优先级基线（与模拟器/真机 LessonPolicy 同源的 greedy_policy）。"""
    return _fallback_greedy(sim)


class ExpectimaxPolicy:
    """每个出牌点用回合内 expectimax；异常退回 greedy（会记录次数）。"""

    def __init__(self, *, sigma: float = DEFAULT_SIGMA, budget_ms: float = 200.0) -> None:
        self.model = AnalyticLeafValue(sigma=sigma)
        self.budget_ms = budget_ms
        self.fallbacks = 0
        self.latencies: list[float] = []

    def reset(self) -> None:
        self.fallbacks = 0
        self.latencies = []

    def __call__(self, sim: LessonSim) -> int | None:
        try:
            started = time.perf_counter()
            card = expectimax(
                state_from_sim(sim), self.model, time_budget_ms=self.budget_ms
            )
            self.latencies.append((time.perf_counter() - started) * 1000.0)
            index = _card_index(sim, card)
            if card is not None and index is None:
                self.fallbacks += 1
                return _fallback_greedy(sim)
            return index
        except Exception:  # noqa: BLE001 - 评测里退回规则，单独计数
            self.fallbacks += 1
            return _fallback_greedy(sim)


class BeamPolicy:
    """每回合开始 search_beam 一次；回合内按计划序列出牌，偏离时退回 expectimax。"""

    def __init__(
        self,
        *,
        width: int = 4,
        sigma: float = DEFAULT_SIGMA,
        deadline_ms: float = 500.0,
        budget_ms: float = 200.0,
    ) -> None:
        self.model = AnalyticLeafValue(sigma=sigma)
        self.width = width
        self.deadline_ms = deadline_ms
        self.budget_ms = budget_ms
        self.queue: list[str] = []
        self.last_turn: int | None = None
        self.fallbacks = 0
        self.latencies: list[float] = []
        self.beam_complete = 0

    def reset(self) -> None:
        self.queue = []
        self.last_turn = None
        self.fallbacks = 0
        self.latencies = []
        self.beam_complete = 0

    def __call__(self, sim: LessonSim) -> int | None:
        try:
            if sim.plays_this_turn >= sim.plays_per_turn + sim.extra_plays:
                self.queue = []
                return None
            turn = sim.turns_left
            if turn != self.last_turn:
                self.last_turn = turn
                self.queue = []
                started = time.perf_counter()
                result = search_beam(
                    state_from_sim(sim),
                    self.model,
                    width=self.width,
                    depth=turn,
                    deadline_ms=self.deadline_ms,
                )
                self.latencies.append((time.perf_counter() - started) * 1000.0)
                if result.complete:
                    self.beam_complete += 1
                self.queue = list(result.sequence)
            while self.queue:
                name = self.queue.pop(0)
                legal = {
                    index
                    for index in sim.legal_actions()
                    if index is not None
                }
                for index, card in enumerate(sim.hand):
                    if card.name == name and index in legal:
                        return index
                # 计划牌被抽牌/状态变化弄丢：退回回合内 expectimax（只此一次）
                card = expectimax(
                    state_from_sim(sim), self.model, time_budget_ms=self.budget_ms
                )
                index = _card_index(sim, card)
                if card is not None and index is None:
                    self.fallbacks += 1
                    return _fallback_greedy(sim)
                return index
            # 计划序列已经打完：按计划结束回合，不用 expectimax 改写
            return None
        except Exception:  # noqa: BLE001
            self.fallbacks += 1
            return _fallback_greedy(sim)


# ---------------------------------------------------------------- 单局
def _run_episode(
    scenario: str,
    seed: int,
    *,
    beam_width: int = 4,
    sigma: float = DEFAULT_SIGMA,
    expect_budget_ms: float = 200.0,
    beam_deadline_ms: float = 500.0,
    beam_depth: int | None = None,
) -> dict[str, Any]:
    deck = build_deck(scenario)
    config = make_config(scenario)

    rules = LessonSim(deck, config, rng_seed=seed)
    rules_score, rules_grade = rules.run(rules_policy)

    exp_policy = ExpectimaxPolicy(sigma=sigma, budget_ms=expect_budget_ms)
    exp_sim = LessonSim(deck, config, rng_seed=seed)
    exp_score, exp_grade = exp_sim.run(exp_policy)

    beam_policy = BeamPolicy(
        width=beam_width,
        sigma=sigma,
        deadline_ms=beam_deadline_ms,
        budget_ms=expect_budget_ms,
    )
    beam_sim = LessonSim(deck, config, rng_seed=seed)
    beam_score, beam_grade = beam_sim.run(beam_policy)

    return {
        "seed": seed,
        "rules": rules_score,
        "expectimax": exp_score,
        "beam": beam_score,
        "rules_grade": rules_grade,
        "expectimax_grade": exp_grade,
        "beam_grade": beam_grade,
        "perfect": int(config.target_perfect),
        "rules_perfect": int(rules_score >= int(config.target_perfect)),
        "expectimax_perfect": int(exp_score >= int(config.target_perfect)),
        "beam_perfect": int(beam_score >= int(config.target_perfect)),
        "rules_clear": int(rules_score >= int(config.target_clear)),
        "expectimax_clear": int(exp_score >= int(config.target_clear)),
        "beam_clear": int(beam_score >= int(config.target_clear)),
        "expectimax_fallbacks": exp_policy.fallbacks,
        "beam_fallbacks": beam_policy.fallbacks,
        "beam_turns": len(beam_policy.latencies),
        "beam_complete": beam_policy.beam_complete,
        "expectimax_ms": list(exp_policy.latencies),
        "beam_ms": list(beam_policy.latencies),
    }


def _run_chunk(task: tuple[str, list[int], dict[str, Any]]) -> list[dict[str, Any]]:
    scenario, seeds, kwargs = task
    return [_run_episode(scenario, seed, **kwargs) for seed in seeds]


def run_batch(
    scenario: str,
    episodes: int,
    *,
    workers: int,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    seeds = list(range(int(episodes)))
    workers = max(int(workers), 1)
    if workers == 1 or episodes <= 4:
        return [_run_episode(scenario, seed, **kwargs) for seed in seeds]
    chunks = [seeds[index::workers] for index in range(workers)]
    tasks = [(scenario, chunk, kwargs) for chunk in chunks if chunk]
    with ProcessPoolExecutor(max_workers=len(tasks)) as pool:
        rows: list[dict[str, Any]] = []
        for chunk_rows in pool.map(_run_chunk, tasks):
            rows.extend(chunk_rows)
    rows.sort(key=lambda row: row["seed"])
    return rows


# ---------------------------------------------------------------- 统计
def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = min(max(q, 0.0), 1.0) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _mean_ci(values: list[float], *, z: float = 1.959963984540054) -> tuple[float, float, float]:
    n = len(values)
    if n <= 1:
        return statistics.fmean(values) if values else 0.0, 0.0, 0.0
    mean = statistics.fmean(values)
    half = z * statistics.pstdev(values) / (n**0.5)
    return mean, mean - half, mean + half


def _bootstrap_median_diff(
    a: list[float], b: list[float], *, rounds: int = 800, seed: int = 20261116
) -> tuple[float, float]:
    """配对 bootstrap：median(a)-median(b) 的 95% CI（评价点 P50 差用）。"""
    if not a or not b:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(a)
    estimates = []
    for _ in range(rounds):
        indices = [rng.randrange(n) for _ in range(n)]
        sample_a = [a[index] for index in indices]
        sample_b = [b[index] for index in indices]
        estimates.append(statistics.median(sample_a) - statistics.median(sample_b))
    estimates.sort()
    return estimates[int(0.025 * len(estimates))], estimates[int(0.975 * len(estimates))]


def summarize(
    rows: list[dict[str, Any]], policy: str, *, perfect: int
) -> dict[str, float]:
    scores = [float(row[policy]) for row in rows]
    return {
        "mean": statistics.fmean(scores),
        "p10": _pct(scores, 0.10),
        "p50": _pct(scores, 0.50),
        "p90": _pct(scores, 0.90),
        "perfect_rate": sum(1 for score in scores if score >= perfect) / len(scores),
    }


def compare(
    rows: list[dict[str, Any]], baseline: str, candidate: str, *, perfect: int
) -> dict[str, Any]:
    base_scores = [float(row[baseline]) for row in rows]
    cand_scores = [float(row[candidate]) for row in rows]
    diffs = [cand - base for cand, base in zip(cand_scores, base_scores)]
    mean_diff, mean_lo, mean_hi = _mean_ci(diffs)
    p50_diff = _pct(cand_scores, 0.50) - _pct(base_scores, 0.50)
    p50_lo, p50_hi = _bootstrap_median_diff(cand_scores, base_scores)
    base_p50 = _pct(base_scores, 0.50)
    p50_ci_rel = (
        [p50_lo / base_p50 * 100.0, p50_hi / base_p50 * 100.0]
        if base_p50
        else [0.0, 0.0]
    )
    base_perfect = sum(1 for score in base_scores if score >= perfect) / len(rows)
    cand_perfect = sum(1 for score in cand_scores if score >= perfect) / len(rows)
    perfect_diffs = [
        int(candidate_row[candidate] >= perfect) - int(candidate_row[baseline] >= perfect)
        for candidate_row in rows
    ]
    perfect_diff, perfect_lo, perfect_hi = _mean_ci([float(x) for x in perfect_diffs])
    base_mean = statistics.fmean(base_scores) if base_scores else 0.0
    return {
        "baseline": baseline,
        "candidate": candidate,
        "mean_abs": mean_diff,
        "mean_rel_pct": mean_diff / base_mean * 100.0 if base_mean else 0.0,
        "mean_ci": [mean_lo, mean_hi],
        "p50_abs": p50_diff,
        "p50_rel_pct": p50_diff / base_p50 * 100.0 if base_p50 else 0.0,
        "p50_ci": [p50_lo, p50_hi],
        "p50_ci_rel_pct": p50_ci_rel,
        "perfect_base": base_perfect,
        "perfect_candidate": cand_perfect,
        "perfect_pp": perfect_diff * 100.0,
        "perfect_ci_pp": [perfect_lo * 100.0, perfect_hi * 100.0],
        "win_rate": sum(1 for diff in diffs if diff > 0) / len(diffs),
        "n": len(rows),
    }


def _fmt(value: float) -> str:
    return f"{value:+.1f}"


def print_policy_table(rows: list[dict[str, Any]], *, label: str, perfect: int) -> dict[str, Any]:
    result = {}
    for policy in ("rules", "expectimax", "beam"):
        stats = summarize(rows, policy, perfect=perfect)
        result[policy] = stats
        print(
            f"{label:7s} {policy:10s} 均值 {stats['mean']:7.1f} "
            f"P10 {stats['p10']:7.1f} P50 {stats['p50']:7.1f} P90 {stats['p90']:7.1f} "
            f"PERFECT {stats['perfect_rate'] * 100:5.1f}%"
        )
    return result


def print_compare(comparison: dict[str, Any], *, label: str) -> None:
    print(
        f"{label}: 均值 {comparison['mean_abs']:+.1f} "
        f"({comparison['mean_rel_pct']:+.1f}%) "
        f"95%CI [{comparison['mean_ci'][0]:+.1f}, {comparison['mean_ci'][1]:+.1f}] | "
        f"P50 {comparison['p50_abs']:+.1f} "
        f"({comparison['p50_rel_pct']:+.1f}%) "
        f"95%CI [{comparison['p50_ci_rel_pct'][0]:+.1f}%, "
        f"{comparison['p50_ci_rel_pct'][1]:+.1f}%] | "
        f"PERFECT {comparison['perfect_base'] * 100:.1f}% → "
        f"{comparison['perfect_candidate'] * 100:.1f}% "
        f"({comparison['perfect_pp']:+.1f}pp, "
        f"CI [{comparison['perfect_ci_pp'][0]:+.1f}, {comparison['perfect_ci_pp'][1]:+.1f}]pp)"
    )


def sweep_widths(
    scenario: str,
    widths: list[int],
    *,
    episodes: int,
    workers: int,
    sigma: float,
    expect_budget_ms: float,
    deadline_ms: float,
) -> list[dict[str, Any]]:
    curve = []
    for width in widths:
        started = time.perf_counter()
        rows = run_batch(
            scenario,
            episodes,
            workers=workers,
            beam_width=width,
            sigma=sigma,
            expect_budget_ms=expect_budget_ms,
            beam_deadline_ms=deadline_ms,
        )
        elapsed = time.perf_counter() - started
        scores = [float(row["beam"]) for row in rows]
        perfect = int(rows[0]["perfect"]) if rows else 0
        latencies = [value for row in rows for value in row["beam_ms"]]
        curve.append(
            {
                "width": width,
                "mean": statistics.fmean(scores),
                "p10": _pct(scores, 0.10),
                "p50": _pct(scores, 0.50),
                "p90": _pct(scores, 0.90),
                "perfect_rate": (
                    sum(1 for score in scores if score >= perfect) / len(scores)
                    if rows
                    else 0.0
                ),
                "latency_mean_ms": statistics.fmean(latencies) if latencies else 0.0,
                "latency_p95_ms": _pct(latencies, 0.95) if latencies else 0.0,
                "beam_complete_rate": (
                    sum(1 for row in rows if row["beam_complete"] >= row["beam_turns"])
                    / max(sum(1 for row in rows if row["beam_turns"]), 1)
                ),
                "elapsed_s": elapsed,
            }
        )
        entry = curve[-1]
        print(
            f"  width={width:3d} 均值 {entry['mean']:7.1f} P50 {entry['p50']:7.1f} "
            f"P90 {entry['p90']:7.1f} PERFECT {entry['perfect_rate'] * 100:5.1f}% "
            f"决策均值 {entry['latency_mean_ms']:6.1f}ms "
            f"p95 {entry['latency_p95_ms']:6.1f}ms "
            f"complete {entry['beam_complete_rate'] * 100:5.1f}%"
        )
    return curve


# ---------------------------------------------------------------- 主入口
def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["large", "small", "both"], default="both")
    parser.add_argument("--episodes", type=int, default=2000, help="主场景每策略局数")
    parser.add_argument("--small-episodes", type=int, default=500, help="小牌组局数")
    parser.add_argument("--workers", type=int, default=0, help="0 = CPU 核数（最多 8）")
    parser.add_argument("--beam-width", type=int, default=4)
    parser.add_argument("--beam-deadline-ms", type=float, default=500.0)
    parser.add_argument("--expect-budget-ms", type=float, default=200.0)
    parser.add_argument("--sigma", type=float, default=DEFAULT_SIGMA)
    parser.add_argument("--sweep", action="store_true", help="扫描 beam 宽度 4/8/16/32/64")
    parser.add_argument("--sweep-episodes", type=int, default=200)
    parser.add_argument("--out", type=Path, default=RESULT_PATH)
    args = parser.parse_args(argv)

    workers = args.workers or min(8, os.cpu_count() or 1)
    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "inputs": {
            "card_table_sha256": hashlib.sha256(
                (ROOT / "data" / "knowledge" / "card_table.json").read_bytes()
            ).hexdigest(),
            "master_cards_sha256": hashlib.sha256(
                MASTER_PATH.read_bytes()
            ).hexdigest()
            if MASTER_PATH.exists()
            else "",
        },
        "settings": {
            "episodes": args.episodes,
            "small_episodes": args.small_episodes,
            "beam_width": args.beam_width,
            "beam_deadline_ms": args.beam_deadline_ms,
            "expect_budget_ms": args.expect_budget_ms,
            "sigma": args.sigma,
            "workers": workers,
        },
        "scenarios": {},
    }

    scenarios = ["large", "small"] if args.scenario == "both" else [args.scenario]
    for scenario in scenarios:
        episodes = args.episodes if scenario == "large" else args.small_episodes
        if episodes <= 0:
            continue
        print(f"\n=== 场景 {scenario}：{episodes} 局（{workers} workers） ===")
        started = time.perf_counter()
        rows = run_batch(
            scenario,
            episodes,
            workers=workers,
            beam_width=args.beam_width,
            sigma=args.sigma,
            expect_budget_ms=args.expect_budget_ms,
            beam_deadline_ms=args.beam_deadline_ms,
        )
        elapsed = time.perf_counter() - started
        perfect = int(rows[0]["perfect"]) if rows else 0
        print(
            f"牌组 {len(build_deck(scenario))} 张，{SCENARIOS[scenario]['turns']} 回合，"
            f"体力 {SCENARIOS[scenario]['stamina']}，CLEAR {SCENARIOS[scenario]['clear']}，"
            f"PERFECT {perfect}；耗时 {elapsed:.1f}s"
        )
        policy_stats = print_policy_table(rows, label=scenario, perfect=perfect)
        comparisons = {
            "expectimax_vs_rules": compare(rows, "rules", "expectimax", perfect=perfect),
            "beam_vs_rules": compare(rows, "rules", "beam", perfect=perfect),
            "beam_vs_expectimax": compare(
                rows, "expectimax", "beam", perfect=perfect
            ),
        }
        for name, comparison in comparisons.items():
            print_compare(comparison, label=name)
        exp_lat = [value for row in rows for value in row["expectimax_ms"]]
        beam_lat = [value for row in rows for value in row["beam_ms"]]
        latency = {
            "expectimax_mean_ms": statistics.fmean(exp_lat) if exp_lat else 0.0,
            "expectimax_p95_ms": _pct(exp_lat, 0.95) if exp_lat else 0.0,
            "beam_mean_ms": statistics.fmean(beam_lat) if beam_lat else 0.0,
            "beam_p95_ms": _pct(beam_lat, 0.95) if beam_lat else 0.0,
            "expectimax_fallbacks": sum(row["expectimax_fallbacks"] for row in rows),
            "beam_fallbacks": sum(row["beam_fallbacks"] for row in rows),
        }
        print(
            f"决策耗时：expectimax 均值 {latency['expectimax_mean_ms']:.1f}ms "
            f"p95 {latency['expectimax_p95_ms']:.1f}ms | "
            f"beam(width={args.beam_width}) 均值 {latency['beam_mean_ms']:.1f}ms "
            f"p95 {latency['beam_p95_ms']:.1f}ms；"
            f"fallback {latency['expectimax_fallbacks']}/{latency['beam_fallbacks']}"
        )
        primary = comparisons["beam_vs_rules"]
        passed_p50 = (
            primary["p50_rel_pct"] >= 6.0
            and primary["p50_ci_rel_pct"][0] > 2.0
        )
        passed_perfect = primary["perfect_pp"] >= 5.0
        print(
            f"门槛（beam vs rules）：P50 {primary['p50_rel_pct']:+.1f}% "
            f"CI下界 {primary['p50_ci_rel_pct'][0]:+.1f}% → "
            f"{'PASS' if passed_p50 else 'FAIL'}；"
            f"PERFECT {primary['perfect_pp']:+.1f}pp → "
            f"{'PASS' if passed_perfect else 'FAIL'}"
        )
        report["scenarios"][scenario] = {
            "config": {**SCENARIOS[scenario], "perfect": perfect},
            "policies": policy_stats,
            "comparisons": comparisons,
            "scores": {
                "rules": [int(row["rules"]) for row in rows],
                "expectimax": [int(row["expectimax"]) for row in rows],
                "beam": [int(row["beam"]) for row in rows],
            },
            "latency": latency,
            "gate": {
                "p50_rel_pct": primary["p50_rel_pct"],
                "p50_ci_rel_pct": primary["p50_ci_rel_pct"],
                "perfect_pp": primary["perfect_pp"],
                "passed_p50": passed_p50,
                "passed_perfect": passed_perfect,
            },
            "elapsed_s": elapsed,
        }
        if args.sweep and scenario == "large":
            print("\nbeam 宽度扫描（主场景，找饱和点）：")
            curve = sweep_widths(
                scenario,
                [4, 8, 16, 32, 64],
                episodes=max(args.sweep_episodes, 20),
                workers=workers,
                sigma=args.sigma,
                expect_budget_ms=args.expect_budget_ms,
                deadline_ms=args.beam_deadline_ms,
            )
            report["scenarios"][scenario]["beam_width_curve"] = curve

    args.out.parent.mkdir(parents=True, exist_ok=True)
    report["elapsed_s"] = elapsed if "elapsed" in locals() else 0.0
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n结果已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
