"""模拟器整局 A/B：同一批种子，对比 rules / expectimax / beam 在完整培育局的表现。

背景（用户规则 2026-11-21）：**bot 不许回退 rules**。上真机前先在无画面模拟器里
验证：

* 搜索引擎在「训练 + 考试」全流程里**不会抛 ``RuleFallbackBlocked``**；
* 不会出现一局卡死（每局决策数/耗时可控，``LessonSim`` 有 ``_MAX_STEPS`` 兜底）；
* 分数/评价不比 rules 差（同一组种子做配对比较）。

做法：把真 ``LessonPolicy`` 通过适配器接进 ``ProduceSim``——训练注入
``training_policy_fn``、考试注入 ``exam_policy_fn``（2026-11-21 新加），所以
这条链路和真机 ``auto_produce`` 用的是同一个 ``LessonPolicy.decide``。

注意：本模拟器是**比较用**的简化模型（考裁判/机制与真机有偏差，见
docs/SIMULATOR.md），不能当绝对分数预测。

用法::

    .venv\\Scripts\\python.exe scripts\\sim_engine_ab.py
    .venv\\Scripts\\python.exe scripts\\sim_engine_ab.py --episodes 10 --engines rules,expectimax
    .venv\\Scripts\\python.exe scripts\\sim_engine_ab.py --budget-ms 30 --out out\\sim_engine_ab.json
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent\.agents\worktrees\m8-fresh-baseline")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gkagent.policy.lesson import LessonPolicy, RuleFallbackBlocked
from gkagent.sim.produce import (
    ProduceConfig,
    ProduceSim,
    StrategyParams,
    eval_value,
    grade_for,
    strategy_from_params,
)
from gkagent.vision.lesson import LessonCard, LessonState

# 和 sim_search.py 的 warm start 一致（已知能跑出稳定成绩的培育策略）。
WARM_STRATEGY = StrategyParams(
    rest_threshold=8,
    training_every=1,
    training_min_stamina=12,
    attr_choice="weight",
    outing_below=16,
    min_stamina_for_class=8,
)

_MASTER_TEXT: dict[str, str] = {}


def master_text(name: str) -> str:
    """卡面中文文本（rules 引擎按「打分+N」估分需要；搜索路径不读）。"""
    if not _MASTER_TEXT:
        path = ROOT / "data" / "master" / "produce_cards.json"
        if path.exists():
            try:
                for row in json.loads(path.read_text(encoding="utf-8")):
                    _MASTER_TEXT[str(row.get("name", ""))] = str(row.get("text", ""))
            except (OSError, json.JSONDecodeError):
                _MASTER_TEXT["__missing__"] = ""
    return _MASTER_TEXT.get(name, "")


def _lesson_state(sim_inner, *, exam: bool) -> LessonState:
    """LessonSim 局面 → 真机 LessonPolicy 的 LessonState。"""
    cards = []
    for index, card in enumerate(sim_inner.hand):
        base = card.name.split("#")[0]
        cards.append(
            LessonCard(
                index=index,
                box=(0, 0, 0, 0),
                point=(0, 0),
                name=base,
                score=card.score or None,
                cost=card.cost,
                buff=card.score <= 0,
                text=master_text(base),
            )
        )
    gauge = int(getattr(sim_inner, "target_clear", 0) or 0)
    return LessonState(
        kind="audition" if exam else "lesson",
        turns_left=sim_inner.turns_left,
        total_turns=getattr(sim_inner, "total_turns", sim_inner.turns_left),
        score=int(getattr(sim_inner, "score", 0) or 0),
        gauge=gauge if gauge > 0 else None,
        stamina=int(sim_inner.stamina),
        cards=tuple(cards),
    )


def run_episode(
    *,
    engine: str,
    deck_raw: list,
    pool_specs: list,
    table,
    seed: int,
    budget_ms: float,
    config: ProduceConfig,
    strategy,
) -> dict:
    """跑一局完整培育，返回该局统计（搜索引擎失败会抛 RuleFallbackBlocked）。"""
    import sim_produce as sp

    deck = [sp._spec_from_row(row) for row in deck_raw]
    sim = ProduceSim(deck, config=config, rng_seed=seed)
    sim.reward_pool = pool_specs
    params = {
        "expectimax_budget_ms": float(budget_ms),
        "beam_deadline_ms": float(budget_ms),
    }
    policy = LessonPolicy(engine=engine, params=params)
    policy._table = table  # 复用同一张卡表（生产 CardTable）

    stats_ = {
        "train_decisions": 0,
        "exam_decisions": 0,
        "train_skips": 0,
        "exam_skips": 0,
        "train_illegal": 0,
        "exam_illegal": 0,
        "train_turn_ends": 0,
        "exam_turn_ends": 0,
        "blocked": "",
    }

    def make_adapter(*, exam: bool):
        def adapter(sim_inner) -> int | None:
            try:
                action = policy.decide(
                    _lesson_state(sim_inner, exam=exam), allow_skip=not exam
                )
            except RuleFallbackBlocked as exc:
                stats_["blocked"] = str(exc)
                raise
            key = "exam" if exam else "train"
            stats_[f"{key}_decisions"] += 1
            legal = [index for index in sim_inner.legal_actions() if index is not None]
            if action.kind == "card" and action.index in legal:
                policy.note_play(action.card)
                return int(action.index)
            if not legal:
                # 出牌次数用完 / 一张都付不起：模拟器要求结束回合。真机这时回合会自动
                # 结束、不会再问策略，所以不算"引擎选错"（单独记 turn_end，不记 illegal）。
                stats_[f"{key}_turn_ends"] += 1
                stats_[f"{key}_skips"] += 1
                return None
            # 模拟器的费用模型（指針修正/元气抵扣）和策略读到的费用不一致；真机由
            # 点击前确认/浮层失败重选兜底。这里给模拟器一个合法动作并计数：某个引擎
            # illegal 特别多 = 它的费用模型偏乐观。
            stats_[f"{key}_illegal"] += 1
            index = min(legal, key=lambda i: (sim_inner._effective_cost(sim_inner.hand[i]), i))
            chosen = sim_inner.hand[index]
            base = chosen.name.split("#")[0]
            policy.note_play(
                LessonCard(
                    index=index,
                    box=(0, 0, 0, 0),
                    point=(0, 0),
                    name=base,
                    score=chosen.score or None,
                    cost=chosen.cost,
                    buff=chosen.score <= 0,
                    text=master_text(base),
                )
            )
            return int(index)

        return adapter

    sim.training_policy_fn = make_adapter(exam=False)
    sim.exam_policy_fn = make_adapter(exam=True)

    started = time.perf_counter()
    blocked = ""
    error = ""
    total = None
    grade = None
    exam_score = None
    rank = None
    try:
        result = sim.run(strategy)
        total = sum(result.attrs)
        grade = result.grade
        exam_score = result.exam_score
        exams = [row["exam"] for row in sim.trace if row.get("exam")]
        rank = exams[-1]["rank"] if exams else 3
    except RuleFallbackBlocked as exc:
        blocked = stats_["blocked"] or str(exc)
        total = sum(sim.attrs)
        exams = [row["exam"] for row in sim.trace if row.get("exam")]
        rank = exams[-1]["rank"] if exams else 3
        exam_score = exams[-1]["score"] if exams else None
        grade = grade_for(total, rank, exam_score)
    except Exception as exc:  # noqa: BLE001 - 记录后继续跑下一局，不中断 A/B
        error = repr(exc)
        total = sum(sim.attrs)
        exams = [row["exam"] for row in sim.trace if row.get("exam")]
        rank = exams[-1]["rank"] if exams else 3
        exam_score = exams[-1]["score"] if exams else None
        grade = grade_for(total, rank, exam_score)
    elapsed = time.perf_counter() - started

    decisions = stats_["train_decisions"] + stats_["exam_decisions"]
    skips = stats_["train_skips"] + stats_["exam_skips"]
    illegal = stats_["train_illegal"] + stats_["exam_illegal"]
    return {
        "seed": seed,
        "engine": engine,
        "total": total,
        "eval": eval_value(total, rank, exam_score),
        "grade": grade,
        "rank": rank,
        "exam_score": exam_score,
        "exams_passed": sim.exams_passed,
        "trainings": sim.trainings,
        "cleared": sim.cleared,
        "decisions": decisions,
        "skips": skips,
        "illegal": illegal,
        "skip_rate": round(skips / decisions, 3) if decisions else 0.0,
        "blocked": blocked,
        "error": error,
        "seconds": round(elapsed, 2),
        "pending_week": sim.week,
    }


def _summary(rows: list[dict]) -> dict:
    n = len(rows)
    totals = [row["total"] or 0 for row in rows]
    evals = [row["eval"] or 0 for row in rows]
    seconds = [row["seconds"] for row in rows]
    blocked = sum(1 for row in rows if row["blocked"])
    errors = sum(1 for row in rows if row["error"])
    decisions = sum(row["decisions"] for row in rows)
    skips = sum(row["skips"] for row in rows)
    return {
        "n": n,
        "mean_total": round(stats.mean(totals), 1),
        "mean_eval": round(stats.mean(evals), 1),
        "p50_eval": round(sorted(evals)[n // 2], 1),
        "p90_eval": round(sorted(evals)[int(n * 0.9)], 1),
        "cplus_rate": round(sum(1 for value in evals if value >= 4500) / n, 3),
        "exam_pass": round(sum(row["exams_passed"] for row in rows) / n, 2),
        "cleared": round(sum(row["cleared"] for row in rows) / n, 2),
        "trainings": round(sum(row["trainings"] for row in rows) / n, 2),
        "decisions": round(decisions / n, 1),
        "illegal": round(sum(row.get("illegal", 0) for row in rows) / n, 1),
        "skip_rate": round(skips / decisions, 3) if decisions else 0.0,
        "blocked": blocked,
        "errors": errors,
        "mean_seconds": round(stats.mean(seconds), 2),
        "max_seconds": round(max(seconds), 2),
    }


def _print_table(engines: list[str], summary: dict[str, dict]) -> None:
    header = (
        f"{'engine':<12}{'n':>4}{'mean_tot':>10}{'mean_eval':>10}{'P50':>8}{'P90':>8}"
        f"{'C+率':>7}{'考试过':>7}{'决策/局':>8}{'skip%':>7}{'非法/局':>8}"
        f"{'blocked':>8}{'error':>6}{'均秒':>7}{'最慢':>7}"
    )
    print(header)
    print("-" * len(header))
    for engine in engines:
        row = summary[engine]
        print(
            f"{engine:<12}{row['n']:>4}{row['mean_total']:>10.1f}{row['mean_eval']:>10.1f}"
            f"{row['p50_eval']:>8.1f}{row['p90_eval']:>8.1f}"
            f"{row['cplus_rate'] * 100:>6.0f}%{row['exam_pass']:>7.2f}"
            f"{row['decisions']:>8.1f}{row['skip_rate'] * 100:>6.0f}%"
            f"{row['illegal']:>8.1f}{row['blocked']:>8}{row['errors']:>6}"
            f"{row['mean_seconds']:>7.2f}{row['max_seconds']:>7.2f}"
        )


def _paired_vs_baseline(
    engines: list[str], rows_by_engine: dict[str, list[dict]]
) -> None:
    base = rows_by_engine.get("rules")
    if not base:
        return
    base_by_seed = {row["seed"]: row for row in base}
    for engine in engines:
        if engine == "rules":
            continue
        rows = rows_by_engine.get(engine) or []
        deltas, wins, ties, losses = [], 0, 0, 0
        for row in rows:
            ref = base_by_seed.get(row["seed"])
            if ref is None:
                continue
            delta = (row["eval"] or 0) - (ref["eval"] or 0)
            deltas.append(delta)
            wins += delta > 0
            ties += delta == 0
            losses += delta < 0
        if deltas:
            print(
                f"配对(rules 基线, {len(deltas)} 局): {engine} 评价点 Δmean="
                f"{stats.mean(deltas):+.1f} Δmedian={stats.median(deltas):+.1f}  "
                f"胜/平/负={wins}/{ties}/{losses}"
            )


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=8, help="每个引擎跑多少局")
    parser.add_argument(
        "--engines",
        default="rules,expectimax",
        help="逗号分隔：rules / expectimax / beam",
    )
    parser.add_argument(
        "--budget-ms", type=float, default=25.0, help="expectimax/beam 单次决策预算"
    )
    parser.add_argument("--seed", type=int, default=9000, help="局 i 用 seed+ i")
    parser.add_argument("--weeks", type=int, default=16, help="培育周数（默认 16）")
    parser.add_argument(
        "--no-stance-costs",
        action="store_true",
        help=(
            "关闭模拟器的指針体力代价（温存减半/強気双倍）。LessonPolicy 目前不建模 "
            "stance 费用（已知 G5 缺口），开着会出现较多「引擎选的牌实际付不起」的 "
            "模拟器合法动作替换；比较引擎时可关掉，数字更干净。"
        ),
    )
    parser.add_argument("--out", default="", help="可选：把逐局/汇总 JSON 写到这个路径")
    args = parser.parse_args(argv)

    engines = [item.strip() for item in args.engines.split(",") if item.strip()]
    allowed = {"rules", "expectimax", "beam", "uinet"}
    bad = [item for item in engines if item not in allowed]
    if bad:
        print(f"未知引擎 {bad}（可选 {sorted(allowed)}）", file=sys.stderr)
        return 2

    import sim_produce as sp

    from gkagent.data.card_table import CardTable

    deck_raw = sp.build_deck(rich=True)
    pool_raw = sp.build_pool(rich=True)
    pool_specs = [sp._spec_from_row(row) for row in pool_raw]
    table = CardTable()
    config = ProduceConfig(
        reward_pick="best",
        weeks=int(args.weeks),
        stance_costs=not args.no_stance_costs,
    )
    strategy = strategy_from_params(WARM_STRATEGY)

    print(
        f"== 模拟器整局 A/B（{args.weeks} 周、{len(config.exam_weeks)} 场考试；"
        f"训练+考试都用真 LessonPolicy.decide）=="
    )
    print(
        f"engines={engines}  episodes={args.episodes}  seed={args.seed}..{args.seed + args.episodes - 1}"
        f"  budget={args.budget_ms}ms  牌组={len(deck_raw)} 张  奖励池={len(pool_specs)} 张"
        f"  stance_costs={config.stance_costs}"
    )
    if "beam" in engines:
        print(
            "注意：模拟器没有 ExamDrawPlan/known_draw，beam 会退回合内 expectimax（这是设计），"
            "不是回退 rules。"
        )

    rows_by_engine: dict[str, list[dict]] = {}
    summary: dict[str, dict] = {}
    for engine in engines:
        rows = []
        for episode in range(args.episodes):
            row = run_episode(
                engine=engine,
                deck_raw=deck_raw,
                pool_specs=pool_specs,
                table=table,
                seed=args.seed + episode,
                budget_ms=args.budget_ms,
                config=config,
                strategy=strategy,
            )
            rows.append(row)
            flag = ""
            if row["blocked"]:
                flag = f"  ⚠️ BLOCKED: {row['blocked']}"
            elif row["error"]:
                flag = f"  ⚠️ ERROR: {row['error']}"
            print(
                f"  {engine:<10} ep{episode + 1:02d} seed={row['seed']} "
                f"total={row['total']} grade={row['grade']} eval={row['eval']} "
                f"rank={row['rank']} 考试分={row['exam_score']} "
                f"决策={row['decisions']} skip={row['skip_rate'] * 100:.0f}% "
                f"{row['seconds']:.2f}s{flag}"
            )
        rows_by_engine[engine] = rows
        summary[engine] = _summary(rows)

    print()
    _print_table(engines, summary)
    _paired_vs_baseline(engines, rows_by_engine)

    blocked_all = {engine: row["blocked"] for engine, row in summary.items() if row["blocked"]}
    if blocked_all:
        print(f"\n❌ 出现 RuleFallbackBlocked：{blocked_all}")
        return 1
    if any(row["errors"] for row in summary.values()):
        print("\n❌ 出现异常，见上表 error 列")
        return 1
    print("\n✅ 整局 A/B 完成：无 RuleFallbackBlocked、无异常")

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "weeks": args.weeks,
                    "budget_ms": args.budget_ms,
                    "seed": args.seed,
                    "engines": engines,
                    "summary": summary,
                    "rows": rows_by_engine,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"逐局/汇总已写 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

