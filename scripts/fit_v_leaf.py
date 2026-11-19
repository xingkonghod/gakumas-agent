"""贪心采样 + ridge 拟合 V_leaf（bootstrap 基线）。

第一版曾标成"专家迭代"，但采样策略始终是贪心、``leaf`` 参数从未参与采样。
真正的专家迭代（用上一轮 V 跑搜索采样）在 ``scripts/fit_v_leaf_iter.py``；
本脚本保留为便宜的数据生成/基线拟合。

用法：python scripts/fit_v_leaf.py --episodes 8000 --rounds 1
输出：data/knowledge/v_leaf.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "data" / "knowledge" / "v_leaf.json"


def collect(episodes: int, seed: int) -> list[tuple[np.ndarray, float]]:
    """跑课程模拟，在每个回合边界采 (特征, 剩余得分)。

    状态先经 ``state_from_sim`` 转成 ``ExpectState``，再经 ``leaf_features``
    转成搜索叶子形态（手牌并进弃牌堆）。直接用 ``features(LessonSim)`` 会把
    ``clear`` / ``focus`` / ``condition_turns`` 等读成 0，训练与推理两个分布。
    """
    import sim_produce as sp

    from gkagent.sim.expectimax import state_from_sim
    from gkagent.sim.lesson import LessonConfig, LessonSim
    from gkagent.sim.v_leaf import leaf_features

    deck = [sp._spec_from_row(r) for r in sp.build_deck(rich=True)]
    rng = random.Random(seed)
    samples: list[tuple[np.ndarray, float]] = []
    for episode in range(episodes):
        config = LessonConfig(
            turns=rng.choice([5, 6, 7, 8, 9]),
            stamina=rng.choice([24, 28, 32, 35]),
            target_clear=rng.choice([100, 150, 200, 250, 300]),
            hand_size=3,
        )
        sim = LessonSim(deck, config, rng_seed=seed + episode)
        pending: list[tuple[np.ndarray, float]] = []

        def policy(inner):
            # 只按解析式挑最高分牌；ε=0.1 随机保证覆盖面
            # 用模拟器自己的合法动作表（它算上了指針/消耗修正后的实际费用）
            legal_idx = [a for a in inner.legal_actions() if isinstance(a, int)]
            if rng.random() < 0.1:
                return rng.choice(legal_idx) if legal_idx else None
            best, best_score = None, -1.0
            for index, card in enumerate(inner.hand):
                if index not in legal_idx:
                    continue
                value = (card.score + inner.buffs.focus) * (1.5 if inner.buffs.condition_turns > 0 else 1.0)
                if value > best_score:
                    best, best_score = index, value
            return best

        # 包一层：每回合开始记录一次状态（LessonSim 每回合抽完牌后调用 policy 多次，
        # 用 turns_left 变化判断回合边界）
        last_turn = None

        def traced(inner, _pending=pending, _policy=policy):
            nonlocal last_turn
            if inner.turns_left != last_turn:
                last_turn = inner.turns_left
                _pending.append((leaf_features(state_from_sim(inner)), float(inner.score)))
            return _policy(inner)

        final_score, _ = sim.run(traced)
        for feat, score_at_turn in pending:
            samples.append((feat, max(float(final_score) - score_at_turn, 0.0)))
    return samples


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=8000)
    parser.add_argument(
        "--rounds", type=int, default=1, help="重复采样轮数；各轮样本合并后拟合"
    )
    parser.add_argument("--ridge", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    from gkagent.sim.v_leaf import FEATURE_NAMES, LinearLeafValue, fit_ridge

    t0 = time.perf_counter()
    samples: list[tuple[np.ndarray, float]] = []
    history = []
    for round_index in range(max(args.rounds, 1)):
        batch = collect(args.episodes, args.seed + round_index * 1000)
        samples.extend(batch)
        history.append({"round": round_index + 1, "n": len(batch), "total": len(samples)})
        print(
            f"第 {round_index + 1} 轮：本批 {len(batch)} 个样本，累计 {len(samples)}"
            f"（{time.perf_counter() - t0:.0f}s）",
            flush=True,
        )

    weights, sigma, r2 = fit_ridge(samples, ridge=args.ridge)
    model = LinearLeafValue(weights=weights, sigma=sigma)
    model.meta = {
        "method": "greedy_bootstrap",
        "rounds": max(args.rounds, 1),
        "episodes": args.episodes,
        "ridge": args.ridge,
        "history": history,
    }
    model.save(OUT)
    print(f"\n样本 {len(samples)}，σ={sigma:.1f}，r²={r2:.4f}")
    print(f"权重已写入 {OUT}")
    top = sorted(zip(model.weights[:-1], FEATURE_NAMES))
    print("最强负权重:", [(n, round(float(w), 3)) for w, n in top[:5]])
    print("最强正权重:", [(n, round(float(w), 3)) for w, n in top[-5:]][::-1])
    print(json.dumps(history, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
