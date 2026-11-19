"""生成训练数据并拟合 V_leaf（专家迭代 3 轮）。

用法：python scripts/fit_v_leaf.py --episodes 8000 --rounds 3
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

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "data" / "knowledge" / "v_leaf.json"


def collect(episodes: int, seed: int, leaf=None) -> list[tuple[np.ndarray, float]]:
    """跑课程模拟，在每个回合边界采 (特征, 剩余得分)。"""
    from gkagent.sim.lesson import LessonConfig, LessonSim
    from gkagent.sim.v_leaf import features
    import sim_produce as sp

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

        def traced(inner):
            nonlocal last_turn
            if inner.turns_left != last_turn:
                last_turn = inner.turns_left
                pending.append((features(inner), float(inner.score)))
            return policy(inner)

        final_score, _ = sim.run(traced)
        for feat, score_at_turn in pending:
            samples.append((feat, max(float(final_score) - score_at_turn, 0.0)))
    return samples


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=8000)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--ridge", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    from gkagent.sim.v_leaf import LinearLeafValue, fit_ridge

    t0 = time.perf_counter()
    history = []
    model = None
    for round_index in range(args.rounds):
        samples = collect(args.episodes, args.seed + round_index * 1000, leaf=model)
        weights, sigma, r2 = fit_ridge(samples, ridge=args.ridge)
        model = LinearLeafValue(weights=weights, sigma=sigma)
        history.append({"round": round_index + 1, "n": len(samples), "sigma": round(sigma, 2), "r2": round(r2, 4)})
        print(
            f"第 {round_index + 1} 轮：样本 {len(samples)}，σ={sigma:.1f}，r²={r2:.4f}（{time.perf_counter() - t0:.0f}s）",
            flush=True,
        )
    assert model is not None
    model.meta = {"rounds": args.rounds, "episodes": args.episodes, "ridge": args.ridge, "history": history}
    model.save(OUT)
    print(f"\n权重已写入 {OUT}")
    top = sorted(zip(model.weights[:-1], __import__("gkagent.sim.v_leaf", fromlist=["FEATURE_NAMES"]).FEATURE_NAMES))
    print("最强负权重:", [(n, round(float(w), 3)) for w, n in top[:5]])
    print("最强正权重:", [(n, round(float(w), 3)) for w, n in top[-5:]][::-1])
    print(json.dumps(history, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
