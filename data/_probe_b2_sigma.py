"""B2 重训诊断：learned 叶子 σ 敏感性（选择段 seed 2000–2079，beam only）。

重训后 beam_learned 显著负（−7.0）而 ensemble 0.75 中性。假设之一：learned σ
（val 11.1）相对解析式 σ=60 过小 → 效用过度自信、排序失真。用 sigma_scale
放大 learned σ 看方向是否翻转（只跑 beam 家族，省 within 预算）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd
import eval_t4_b1 as eb1

from gkagent.sim.expectimax import AnalyticLeafValue
from gkagent.sim.leaf_mlp import MLPLeafValue
from gkagent.sim.v_leaf import EnsembleLeafValue

MODEL = ROOT / "out" / "b2r_leaf_mlp_small.json"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    deck, config = ee.build_deck("small"), ee.make_config("small")
    rows: dict[str, list[dict]] = {}

    def run(name: str, leaf) -> None:
        rows[name] = [
            ekd.play(
                deck, config, 2000 + i, known=False, policy="beam",
                budget_ms=100.0, width=4, branching=None,
                score_tiebreak=1e-3, leaf_model=leaf,
            )
            for i in range(80)
        ]
        print(f"  {name} done", flush=True)

    def learned(scale: float) -> MLPLeafValue:
        m = MLPLeafValue.load(MODEL)
        m.score_tiebreak = 1e-3
        m.sigma_scale = scale
        return m

    run("beam_analytic", AnalyticLeafValue(sigma=60.0, score_tiebreak=1e-3))
    for scale in (2.0, 4.0):
        run(f"learned_sigma_x{scale:g}", learned(scale))
    for scale in (2.0, 4.0):
        run(
            f"ensemble_0.75_sigma_x{scale:g}",
            EnsembleLeafValue(
                primary=AnalyticLeafValue(sigma=60.0, score_tiebreak=1e-3),
                secondary=learned(scale),
                weight=0.75,
            ),
        )
    table = eb1._table(rows, "beam_analytic")
    print(f"\n{'策略':<28}{'均值':>8}{'CLEAR':>8}{'vs analytic':>13}{'95% CI':>18}{'胜/平/负':>11}")
    for name, stat in table.items():
        d = stat["vs_within"]
        print(
            f"{name:<28}{stat['mean']:>8.1f}{stat['clear_rate']*100:>7.1f}%"
            f"{d['mean']:>+13.1f}  [{d['ci_low']:>+6.1f},{d['ci_high']:>+6.1f}]"
            f"{d['wins']:>5d}/{d['ties']:d}/{d['losses']:<4d}"
        )


if __name__ == "__main__":
    main()
