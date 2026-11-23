"""B11 渐退式专家迭代：配对评测门（学生 vs beam 教师，B1 修正 harness）。

同牌组 / 同 seed 配对（small：14 张 / 5 回合 / CLEAR 120 / PERFECT 170）：

* ``net``：学生策略网（argmax，只看可观测状态；有牌绝不 SKIP——硬规矩）；
* ``beam_analytic``：教师 = width4/100ms/tiebreak1e-3 解析式叶子（B2-R 处置后
  的 T2 候选档）；**评测门的基线**；
* ``within_analytic`` / ``greedy``：上下文参照（回合内 expectimax / 固定优先级）。

**放手门（用户设计：学生 ≥ 教师才放手）**：``net − beam`` 配对差 95% CI
下界 > 0（显著强）→ PASS，下一轮教师占比降档（30→15→0）且教师换成上一轮学生；
否则 CONTINUE（继续扶：教师占比不降，用新学生再采自对弈数据迭代）。
非 inferior 不算过——「学生强于老师后反过来当老师」要求显著正。

seed 纪律：确认段默认 3000–3119（120 局，不参与采集/训练）；选择段 2000–2079。

用法::

    .venv\\Scripts\\python.exe scripts\\eval_ei.py --net-model out\\ei_r1_v1_mix.json \
        --games 120 --seed 3000 --json out\\ei_r1_eval_confirm.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd
import eval_t4_b1 as eb1

from gkagent.sim.policy_mlp import PolicyMLP


def _run_rows(deck, config, args, net: PolicyMLP, *, info: str) -> dict[str, list[dict]]:
    known = info == "known"
    rows: dict[str, list[dict]] = {}

    def run(name: str, policy: str, *, budget: float, tiebreak: float) -> None:
        rows[name] = [
            ekd.play(
                deck,
                config,
                args.seed + offset,
                known=known,
                policy=policy,
                budget_ms=budget,
                width=args.width,
                score_tiebreak=tiebreak,
                net_model=net if policy == "net" else None,
            )
            for offset in range(args.games)
        ]

    run("net", "net", budget=0.0, tiebreak=0.0)
    run(
        "beam_analytic",
        "beam",
        budget=args.beam_budget_ms,
        tiebreak=args.score_tiebreak,
    )
    if not args.no_within:
        run("within_analytic", "within", budget=args.within_budget_ms, tiebreak=0.0)
    if not args.no_greedy:
        run("greedy", "greedy", budget=0.0, tiebreak=0.0)
    return rows


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="B11 学生网配对评测门（vs beam 教师）")
    parser.add_argument("--net-model", type=Path, required=True)
    parser.add_argument("--games", type=int, default=120)
    parser.add_argument("--seed", type=int, default=3000)
    parser.add_argument("--scenario", choices=("small", "large"), default="small")
    parser.add_argument("--width", type=int, default=4)
    parser.add_argument("--beam-budget-ms", type=float, default=100.0)
    parser.add_argument("--within-budget-ms", type=float, default=200.0)
    parser.add_argument("--score-tiebreak", type=float, default=1e-3)
    parser.add_argument("--info", nargs="+", choices=("unknown", "known"), default=["unknown"])
    parser.add_argument("--no-within", action="store_true")
    parser.add_argument("--no-greedy", action="store_true")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    net = PolicyMLP.load(args.net_model)
    deck, config = ee.build_deck(args.scenario), ee.make_config(args.scenario)
    print(
        f"net={args.net_model} scenario={args.scenario} games={args.games} "
        f"seeds={args.seed}..{args.seed + args.games - 1} "
        f"teacher=beam(width={args.width}, {args.beam_budget_ms:.0f}ms, "
        f"tiebreak={args.score_tiebreak:g})"
    )
    if net.meta.get("mix"):
        print(f"  训练混合：{net.meta['mix']}")

    results: dict[str, dict] = {}
    verdicts: dict[str, dict] = {}
    started = time.perf_counter()
    for info in args.info:
        rows = _run_rows(deck, config, args, net, info=info)
        table = eb1._table(rows, "beam_analytic")
        results[info] = table
        print(f"\n=== {info}（基线 = beam 教师） ===")
        print(
            f"{'策略':<18}{'均值':>8}{'P50':>7}{'CLEAR':>8}{'PERFECT':>9}"
            f"{'vs 教师':>10}{'95% CI':>18}{'胜/平/负':>11}{'回退':>5}"
        )
        for name, stat in table.items():
            delta = stat["vs_within"]
            print(
                f"{name:<18}{stat['mean']:>8.1f}{stat['p50']:>7.0f}"
                f"{stat['clear_rate'] * 100:>7.1f}%{stat['perfect_rate'] * 100:>8.1f}%"
                f"{delta['mean']:>+10.1f}"
                f"  [{delta['ci_low']:>+6.1f},{delta['ci_high']:>+6.1f}]"
                f"{delta['wins']:>5d}/{delta['ties']:d}/{delta['losses']:<4d}"
                f"{stat['fallbacks']:>5d}"
            )
        net_delta = table["net"]["vs_within"]
        gate_pass = net_delta["ci_low"] > 0
        verdicts[info] = {
            "gate_pass": gate_pass,
            "criterion": "net − beam 配对差 95% CI 下界 > 0（学生显著强于教师才放手）",
            "net_mean": table["net"]["mean"],
            "teacher_mean": table["beam_analytic"]["mean"],
            "delta": net_delta["mean"],
            "ci_low": net_delta["ci_low"],
            "ci_high": net_delta["ci_high"],
            "wins": net_delta["wins"],
            "ties": net_delta["ties"],
            "losses": net_delta["losses"],
            "next": "PASS → 下一轮教师占比降档、教师换成该学生"
            if gate_pass
            else "CONTINUE → 教师占比不降，用该学生再采自对弈数据继续扶",
        }
        print(
            f"\n评测门 [{info}]：{'PASS（放手）' if gate_pass else 'CONTINUE（继续扶）'}"
            f"  net {table['net']['mean']:.1f} vs 教师 {table['beam_analytic']['mean']:.1f}"
            f"  Δ={net_delta['mean']:+.1f} CI [{net_delta['ci_low']:+.1f},{net_delta['ci_high']:+.1f}]"
        )

    elapsed = time.perf_counter() - started
    print(f"\n总耗时 {elapsed:.1f}s")
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        serializable_args = {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in vars(args).items()
        }
        args.json.write_text(
            json.dumps(
                {
                    "args": serializable_args,
                    "model": str(args.net_model),
                    "model_meta": net.meta,
                    "results": results,
                    "verdicts": verdicts,
                    "elapsed_s": round(elapsed, 2),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"json → {args.json}")
    primary = verdicts.get("unknown") or next(iter(verdicts.values()))
    return 0 if primary["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
