"""B2-R 根因诊断：learned μ 为什么在 B3 规则下对 beam 排序有害。

假设 H1（信息条件漂移）：训练标签来自 known teacher 自对弈，评测是 unknown 执行；
known return 系统性高于 unknown return，且差值随状态变化 → learned μ 排序失真。
解析式 μ 不依赖信息条件 → 偏差更均匀 → 排序保持。

做法：选择段 seed 2000–2079，每 seed 跑两遍 RecordingLessonSim（beam known / unknown，
解析式叶子、B1 配置），记录叶子状态 + 真实后续得分 y；对每个叶子算 learned/analytic 的
μ 与 utility，比较：
  1) 偏差 mean(μ−y)（known vs unknown 条件）；
  2) 按 turns_left 分桶的偏差；
  3) 同深度（turns_left 相同、跨局）配对排序正确率——近似 beam 同层跨分支比较；
  4) learned 与 analytic 排序分歧时谁对。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee
import eval_known_draw as ekd

from gkagent.sim.expectimax import AnalyticLeafValue
from gkagent.sim.leaf_data import RecordingLessonSim
from gkagent.sim.leaf_mlp import MLPLeafValue

MODEL = ROOT / "out" / "b2r_leaf_mlp_small.json"
GAMES = 80
SEED0 = 2000


def collect(known: bool):
    deck, config = ee.build_deck("small"), ee.make_config("small")
    rows = []
    for offset in range(GAMES):
        seed = SEED0 + offset
        instances: list[RecordingLessonSim] = []

        def factory(deck, config, rng_seed):
            sim = RecordingLessonSim(deck, config, rng_seed)
            instances.append(sim)
            return sim

        row = ekd.play(
            deck, config, seed, known=known, policy="beam", budget_ms=100.0,
            width=4, branching=None, score_tiebreak=1e-3, sim_factory=factory,
        )
        sim = instances[-1]
        final = float(row["score"])
        for state in sim.leaf_states:
            rows.append((seed, int(state.turns_left), state, final - float(state.score)))
    return rows


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    learned = MLPLeafValue.load(MODEL)
    learned.score_tiebreak = 1e-3
    analytic = AnalyticLeafValue(sigma=60.0, score_tiebreak=1e-3)

    data = {}
    for known in (True, False):
        rows = collect(known)
        recs = []
        for seed, tl, state, y in rows:
            lm, ls = learned.predict(state)
            am, as_ = analytic.predict(state)
            recs.append({
                "seed": seed, "tl": tl, "y": y,
                "lm": lm, "am": am,
                "lu": learned.utility(state), "au": analytic.utility(state),
            })
        data[known] = recs
        print(f"known={known}: {len(recs)} 叶子 / {GAMES} 局", flush=True)

    print("\n== 1) 真实后续得分与偏差 mean(μ−y) ==")
    for known in (True, False):
        recs = data[known]
        y = np.array([r["y"] for r in recs])
        lm = np.array([r["lm"] for r in recs])
        am = np.array([r["am"] for r in recs])
        print(f"known={known}: y mean={y.mean():.2f} | learned μ mean={lm.mean():.2f} "
              f"bias={np.mean(lm - y):+.2f} MAE={np.mean(np.abs(lm - y)):.2f} | "
              f"analytic μ mean={am.mean():.2f} bias={np.mean(am - y):+.2f} "
              f"MAE={np.mean(np.abs(am - y)):.2f}")
    yk = np.array([r["y"] for r in data[True]])
    yu = np.array([r["y"] for r in data[False]])
    print(f"teacher 信息优势: y_known mean={yk.mean():.2f} vs y_unknown mean={yu.mean():.2f} "
          f"(差 {yk.mean() - yu.mean():+.2f})")

    print("\n== 2) unknown 条件按 turns_left 分桶偏差 ==")
    recs = data[False]
    for tl in sorted({r["tl"] for r in recs}):
        sub = [r for r in recs if r["tl"] == tl]
        y = np.array([r["y"] for r in sub])
        lm = np.array([r["lm"] for r in sub])
        am = np.array([r["am"] for r in sub])
        print(f"turns_left={tl}: n={len(sub)} y={y.mean():6.2f} | "
              f"learned bias={np.mean(lm - y):+7.2f} MAE={np.mean(np.abs(lm - y)):6.2f} | "
              f"analytic bias={np.mean(am - y):+7.2f} MAE={np.mean(np.abs(am - y)):6.2f}")

    print("\n== 3) 同深度跨局配对排序正确率（vs y_unknown，近似 beam 同层比较） ==")
    rng = np.random.default_rng(0)

    def pair_acc(values_key: str, tl: int, max_pairs: int = 30000) -> tuple[float, int]:
        sub = [r for r in recs if r["tl"] == tl]
        n = len(sub)
        if n < 2:
            return float("nan"), 0
        idx = rng.integers(0, n, size=(max_pairs, 2))
        idx = idx[idx[:, 0] != idx[:, 1]]
        va = np.array([sub[i][values_key] for i in idx[:, 0]])
        vb = np.array([sub[i][values_key] for i in idx[:, 1]])
        ya = np.array([sub[i]["y"] for i in idx[:, 0]])
        yb = np.array([sub[i]["y"] for i in idx[:, 1]])
        dv, dy = va - vb, ya - yb
        mask = (dv != 0) & (dy != 0)
        if mask.sum() == 0:
            return float("nan"), 0
        acc = float(np.mean(np.sign(dv[mask]) == np.sign(dy[mask])))
        return acc, int(mask.sum())

    for tl in sorted({r["tl"] for r in recs}):
        line = f"turns_left={tl}: "
        for key, name in (("lm", "learnedμ"), ("am", "analyticμ"), ("lu", "learnedU"), ("au", "analyticU")):
            acc, n = pair_acc(key, tl)
            line += f"{name}={acc:.3f}(n={n}) "
        print(line)

    print("\n== 4) learnedμ 与 analyticμ 分歧配对：谁对（unknown，全深度合并） ==")
    n = len(recs)
    idx = rng.integers(0, n, size=(60000, 2))
    idx = idx[idx[:, 0] != idx[:, 1]]
    lm_a = np.array([recs[i]["lm"] for i in idx[:, 0]])
    lm_b = np.array([recs[i]["lm"] for i in idx[:, 1]])
    am_a = np.array([recs[i]["am"] for i in idx[:, 0]])
    am_b = np.array([recs[i]["am"] for i in idx[:, 1]])
    y_a = np.array([recs[i]["y"] for i in idx[:, 0]])
    y_b = np.array([recs[i]["y"] for i in idx[:, 1]])
    dl, da, dy = lm_a - lm_b, am_a - am_b, y_a - y_b
    disagree = (np.sign(dl) != np.sign(da)) & (dl != 0) & (da != 0) & (dy != 0)
    nd = int(disagree.sum())
    if nd:
        learned_right = float(np.mean(np.sign(dl[disagree]) == np.sign(dy[disagree])))
        print(f"分歧配对 {nd}/{len(dl)}：learned 对 {learned_right:.3f} / analytic 对 {1 - learned_right:.3f}")
    else:
        print("无分歧配对")


if __name__ == "__main__":
    main()
