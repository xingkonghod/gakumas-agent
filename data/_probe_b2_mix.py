"""B2-R 根因诊断 2：μ 来源 × σ × tiebreak 分解（选择段 seed 2000–2079，beam only）。

诊断 1 结论：learned μ 比 analytic μ 更准（bias≈0 vs −28）且排序更好（分歧时 71.6% 对），
信息条件漂移假设被推翻（y_known≈y_unknown）。假设 H2：伤害来自**档位效用变换**——
U=Φ((μ−clear_gap)/σ)+Φ((μ−perfect_gap)/σ)：
  - learned σ≈11 锐利 → 远低于 CLEAR 的状态 U≈0 打平（尾部平手）；
  - learned μ 准确 → 投影分更接近/超过 CLEAR → U≈1 打平（顶部饱和）；
  - analytic μ 系统性悲观（−28）+ σ=60 → 大多数状态落在 sigmoid 中段，梯度处处存在。
平手时 beam 退化为枚举顺序（T4 已记录：偏好少打牌/存体力）。
预测：learned μ + 大 tiebreak（平手按分数排开）应恢复甚至超过基线。
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

from gkagent.sim.expectimax import AnalyticLeafValue, _phi
from gkagent.sim.leaf_mlp import MLPLeafValue

MODEL = ROOT / "out" / "b2r_leaf_mlp_small.json"


class MixLeaf:
    """μ 取自 mu_leaf，σ 固定常数；utility 与解析式/MLP 同式（高斯档位 + tiebreak）。"""

    def __init__(self, mu_leaf, sigma: float, tiebreak: float) -> None:
        self.mu_leaf = mu_leaf
        self.sigma = float(sigma)
        self.score_tiebreak = float(tiebreak)

    def predict(self, state):
        if state.turns_left <= 0:
            return 0.0, 0.0
        mu = self.mu_leaf.predict(state)[0]
        return mu, self.sigma

    def utility(self, state):
        if state.clear <= 0:
            return 0.0
        mu, sigma = self.predict(state)
        projected = state.score + mu
        scale = float(state.perfect if state.perfect > 0 else state.clear)
        tb = self.score_tiebreak * projected / scale if scale > 0 else 0.0
        if sigma <= 0:
            base = (1.0 if projected >= state.clear else 0.0) + (
                1.0 if projected >= state.perfect else 0.0
            )
            return base + tb
        base = _phi((mu - (state.clear - state.score)) / sigma) + _phi(
            (mu - (state.perfect - state.score)) / sigma
        )
        return base + tb


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    deck, config = ee.build_deck("small"), ee.make_config("small")
    learned = MLPLeafValue.load(MODEL)
    learned.score_tiebreak = 1e-3
    analytic = AnalyticLeafValue(sigma=60.0, score_tiebreak=1e-3)

    configs = {
        "beam_analytic": analytic,
        "learned_s11_tb1e-3": learned,
        "muL_s60_tb1e-3": MixLeaf(learned, 60.0, 1e-3),
        "muA_s11_tb1e-3": MixLeaf(analytic, 11.1, 1e-3),
        "muL_s60_tb1e-2": MixLeaf(learned, 60.0, 1e-2),
        "muL_s11_tb1e-2": MixLeaf(learned, 11.1, 1e-2),
        "muL_s60_tb0.1": MixLeaf(learned, 60.0, 0.1),
    }
    rows: dict[str, list[dict]] = {}
    for name, leaf in configs.items():
        rows[name] = [
            ekd.play(
                deck, config, 2000 + i, known=False, policy="beam",
                budget_ms=100.0, width=4, branching=None,
                score_tiebreak=1e-3, leaf_model=leaf,
            )
            for i in range(80)
        ]
        print(f"  {name} done", flush=True)

    table = eb1._table(rows, "beam_analytic")
    print(f"\n{'策略':<22}{'均值':>8}{'CLEAR':>8}{'vs analytic':>13}{'95% CI':>18}{'胜/平/负':>11}")
    for name, stat in table.items():
        d = stat["vs_within"]
        print(
            f"{name:<22}{stat['mean']:>8.1f}{stat['clear_rate']*100:>7.1f}%"
            f"{d['mean']:>+13.1f}  [{d['ci_low']:>+6.1f},{d['ci_high']:>+6.1f}]"
            f"{d['wins']:>5d}/{d['ties']:d}/{d['losses']:<4d}"
        )


if __name__ == "__main__":
    main()
