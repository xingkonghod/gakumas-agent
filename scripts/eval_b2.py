"""B2 配对评测：learned MLP 叶子 vs 解析式叶子（复用 B1 修正 harness）。

同样牌组 / 同 seed 配对，跑：

* ``within_analytic``：B1 的 within 基线（解析式 leaf，σ=60，tiebreak=0）；
* ``within_learned``：同一 within 搜索，叶子换成 ``leaf_mlp.MLPLeafValue``；
* ``within_ensemble_<w>``：``EnsembleLeafValue(analytic, learned, weight=w)``；
* ``beam_*``：B1 的 beam（width/budget/tiebreak 同 B1）套三种叶子。

信息条件 ``unknown`` / ``known``（同 B1）。输出配对差 + 95% CI；B2 判定：
**任一 learned/ensemble 配置在 unknown 条件下显著优于同搜索的解析式基线**
（配对差 95% CI 下界 > 0）即视为叶子改进成立。

用法::

    .venv\\Scripts\\python.exe scripts\\eval_b2.py \
        --leaf-model data\\knowledge\\b2_leaf_mlp_small.json --games 60 \
        --json out\\b2_eval.json

    # 快速看 within（不跑 beam，约几秒）
    .venv\\Scripts\\python.exe scripts\\eval_b2.py --leaf-model ... --no-beam --info unknown
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd
import eval_t4_b1 as eb1

from gkagent.sim.expectimax import AnalyticLeafValue
from gkagent.sim.leaf_mlp import MLPLeafValue
from gkagent.sim.v_leaf import EnsembleLeafValue


def _load_model(path: Path) -> MLPLeafValue:
    model = MLPLeafValue.load(path)
    print(
        f"learned leaf: {path}（val r²={model.meta.get('val_metrics', {}).get('r2', '?')}，"
        f"σ={model.sigma:.1f}）"
    )
    return model


def _model_with_tiebreak(path: Path, tiebreak: float, sigma_scale: float = 1.0) -> MLPLeafValue:
    model = MLPLeafValue.load(path)
    model.score_tiebreak = float(tiebreak)
    model.sigma_scale = float(sigma_scale)
    return model


def _run_rows(
    deck,
    config,
    games: int,
    seed0: int,
    *,
    info: str,
    args,
    model_path: Path,
) -> dict[str, list[dict]]:
    known = info == "known"
    rows: dict[str, list[dict]] = {}

    def run(name: str, *, policy: str, leaf, budget: float, tiebreak: float) -> None:
        rows[name] = [
            ekd.play(
                deck,
                config,
                seed0 + offset,
                known=known,
                policy=policy,
                budget_ms=budget,
                width=args.width,
                branching=args.within_branching if policy == "within" else (args.branching or None),
                score_tiebreak=tiebreak,
                leaf_model=leaf,
            )
            for offset in range(games)
        ]

    # within 家族：解析式 vs learned vs ensemble（tiebreak=0，与 B1 within 一致）
    run(
        "within_analytic",
        policy="within",
        leaf=AnalyticLeafValue(sigma=args.sigma, score_tiebreak=0.0),
        budget=args.within_budget_ms,
        tiebreak=0.0,
    )
    learned_within = _model_with_tiebreak(model_path, 0.0, args.learned_sigma_scale)
    run("within_learned", policy="within", leaf=learned_within, budget=args.within_budget_ms, tiebreak=0.0)
    for weight in args.ensembles:
        run(
            f"within_ensemble_{weight:g}",
            policy="within",
            leaf=EnsembleLeafValue(
                primary=AnalyticLeafValue(sigma=args.sigma, score_tiebreak=0.0),
                secondary=_model_with_tiebreak(model_path, 0.0, args.learned_sigma_scale),
                weight=weight,
            ),
            budget=args.within_budget_ms,
            tiebreak=0.0,
        )

    if args.no_beam:
        return rows
    # beam 家族：同 B1（width=4 / budget=100ms / tiebreak=1e-3）
    run(
        "beam_analytic",
        policy="beam",
        leaf=AnalyticLeafValue(sigma=args.sigma, score_tiebreak=args.score_tiebreak),
        budget=args.beam_budget_ms,
        tiebreak=args.score_tiebreak,
    )
    run(
        "beam_learned",
        policy="beam",
        leaf=_model_with_tiebreak(model_path, args.score_tiebreak, args.learned_sigma_scale),
        budget=args.beam_budget_ms,
        tiebreak=args.score_tiebreak,
    )
    for weight in args.ensembles:
        run(
            f"beam_ensemble_{weight:g}",
            policy="beam",
            leaf=EnsembleLeafValue(
                primary=AnalyticLeafValue(sigma=args.sigma, score_tiebreak=args.score_tiebreak),
                secondary=_model_with_tiebreak(
                    model_path, args.score_tiebreak, args.learned_sigma_scale
                ),
                weight=weight,
            ),
            budget=args.beam_budget_ms,
            tiebreak=args.score_tiebreak,
        )
    return rows


def _print_family(table: dict, family: str, baseline: str) -> None:
    print(f"\n-- {family}（baseline = {baseline}） --")
    print(
        f"{'策略':<22}{'均值':>8}{'P50':>7}{'CLEAR':>8}{'PERFECT':>9}"
        f"{'vs 基线':>10}{'95% CI':>18}{'胜/平/负':>11}{'回退':>5}"
    )
    for name, stat in table.items():
        delta = stat["vs_within"]
        print(
            f"{name:<22}{stat['mean']:>8.1f}{stat['p50']:>7.0f}"
            f"{stat['clear_rate'] * 100:>7.1f}%{stat['perfect_rate'] * 100:>8.1f}%"
            f"{delta['mean']:>+10.1f}"
            f"  [{delta['ci_low']:>+6.1f},{delta['ci_high']:>+6.1f}]"
            f"{delta['wins']:>5d}/{delta['ties']:d}/{delta['losses']:<4d}"
            f"{stat['fallbacks']:>5d}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B2 learned leaf 配对评测（B1 修正 harness）")
    parser.add_argument("--leaf-model", type=Path, required=True)
    parser.add_argument("--games", type=int, default=60)
    parser.add_argument("--scenario", choices=("small", "large"), default="small")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--width", type=int, default=4)
    parser.add_argument("--branching", type=int, default=0, help="beam 抽样分支（0=默认）")
    parser.add_argument("--within-branching", type=int, default=0, help="within 不走 beam，忽略")
    parser.add_argument("--beam-budget-ms", type=float, default=100.0)
    parser.add_argument("--within-budget-ms", type=float, default=200.0)
    parser.add_argument("--sigma", type=float, default=60.0, help="解析式叶子 σ（与 B1 口径一致）")
    parser.add_argument(
        "--learned-sigma-scale",
        type=float,
        default=1.0,
        help="learned 叶子 σ 缩放（1=数据学到；>1 更平滑，用作 σ 敏感性对照）",
    )
    parser.add_argument("--score-tiebreak", type=float, default=1e-3)
    parser.add_argument(
        "--ensembles",
        type=float,
        nargs="*",
        default=[0.25, 0.5, 0.75],
        help="ensemble 的解析式权重（0.5 = 生产现用权重）",
    )
    parser.add_argument("--info", nargs="+", choices=("unknown", "known"), default=["unknown", "known"])
    parser.add_argument("--no-beam", action="store_true")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    model = _load_model(args.leaf_model)
    if model.meta.get("val_metrics"):
        print(
            f"  train/val r² = {model.meta['train_metrics']['r2']:.3f}/"
            f"{model.meta['val_metrics']['r2']:.3f}"
        )
    deck, config = ee.build_deck(args.scenario), ee.make_config(args.scenario)
    print(
        f"scenario={args.scenario} games={args.games} seeds={args.seed}..{args.seed + args.games - 1} "
        f"within_budget={args.within_budget_ms:.0f}ms beam_budget={args.beam_budget_ms:.0f}ms "
        f"width={args.width} tiebreak={args.score_tiebreak:g} ensembles={args.ensembles}"
    )

    results: dict[str, dict] = {}
    verdicts: list[dict] = []
    for info in args.info:
        raw = _run_rows(
            deck,
            config,
            args.games,
            args.seed,
            info=info,
            args=args,
            model_path=args.leaf_model,
        )
        # within 家族：以 within_analytic 为基线
        within_rows = {name: rows for name, rows in raw.items() if name.startswith("within")}
        beam_rows = {name: rows for name, rows in raw.items() if name.startswith("beam")}
        within_table = eb1._table(within_rows, "within_analytic") if len(within_rows) > 1 else {}
        beam_table = eb1._table(beam_rows, "beam_analytic") if len(beam_rows) > 1 else {}
        results[info] = {"within": within_table, "beam": beam_table}
        print(f"\n=== {info} ===")
        if within_table:
            _print_family(within_table, "within", "within_analytic")
        if beam_table:
            _print_family(beam_table, "beam", "beam_analytic")

        for family, table, baseline in (
            ("within", within_table, "within_analytic"),
            ("beam", beam_table, "beam_analytic"),
        ):
            for name, stat in table.items():
                if name == baseline:
                    continue
                delta = stat["vs_within"]
                verdicts.append(
                    {
                        "info": info,
                        "family": family,
                        "candidate": name,
                        "baseline": baseline,
                        "mean": stat["mean"],
                        "baseline_mean": table[baseline]["mean"],
                        "delta": delta["mean"],
                        "ci_low": delta["ci_low"],
                        "ci_high": delta["ci_high"],
                        "wins": delta["wins"],
                        "losses": delta["losses"],
                        "significant_positive": delta["ci_low"] > 0,
                        "fallbacks": stat["fallbacks"],
                    }
                )

    print("\n== B2 判定（learned/ensemble vs 同搜索解析式，配对 95% CI） ==")
    unknown_significant = [
        row for row in verdicts if row["info"] == "unknown" and row["significant_positive"]
    ]
    for row in verdicts:
        flag = (
            "✅ 显著正"
            if row["significant_positive"]
            else ("❌ 显著负" if row["ci_high"] < 0 else "— 不显著")
        )
        print(
            f"[{row['info']:<7}] {row['family']:<7} {row['candidate']:<22} {row['delta']:+7.1f} "
            f"CI [{row['ci_low']:+6.1f},{row['ci_high']:+6.1f}] {flag}"
        )
    b2_pass = bool(unknown_significant)
    print(
        f"\nB2 叶子改进判定：{'PASS' if b2_pass else 'FAIL'}"
        "（unknown 条件下任一 learned/ensemble 配置显著优于同搜索解析式基线）"
    )
    verdict = {
        "b2_pass": b2_pass,
        "unknown_significant_candidates": [
            {"family": row["family"], "candidate": row["candidate"]} for row in unknown_significant
        ],
        "all_rows": verdicts,
    }
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
                    "model": str(args.leaf_model),
                    "results": results,
                    "verdict": verdict,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"json → {args.json}")
    return 0 if b2_pass else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
