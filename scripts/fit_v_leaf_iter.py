"""真·专家迭代：用 expectimax 自己的策略采样（不是贪心），训练 V_leaf。

第 1 轮用解析式 V 采样（bootstrap），第 2/3 轮用上一轮学到的 V 采样。

用法：python scripts/fit_v_leaf_iter.py --episodes 600 --rounds 3
输出：data/knowledge/v_leaf.json
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "data" / "knowledge" / "v_leaf.json"


def to_expect_state(sim, perfect: int):
    from gkagent.sim.expectimax import ExpectState

    legal = [a for a in sim.legal_actions() if isinstance(a, int)]
    return ExpectState(
        hand=tuple(sim.hand),
        deck=tuple(sim.deck),
        discard=tuple(sim.discard),
        stamina=int(sim.stamina),
        stamina_max=int(getattr(sim.config, "stamina_max", 35) or 35),
        vitality=int(getattr(sim, "vitality", 0) or 0),
        score=int(sim.score),
        turns_left=int(sim.turns_left),
        total_turns=int(sim.config.turns),
        plays_used=0,
        play_limit=3,
        clear=int(sim.config.target_clear),
        perfect=int(perfect),
        condition_turns=int(sim.buffs.condition_turns),
        focus=int(sim.buffs.focus),
        impression=int(sim.buffs.impression),
        hand_size=len(sim.hand),
    )


def collect(episodes: int, seed: int, value, budget_ms: float) -> list[tuple[np.ndarray, float]]:
    from gkagent.sim.expectimax import expectimax
    from gkagent.sim.lesson import LessonConfig, LessonSim
    from gkagent.sim.v_leaf import features
    import sim_produce as sp

    deck = [sp._spec_from_row(r) for r in sp.build_deck(rich=True)]
    samples: list[tuple[np.ndarray, float]] = []
    rng = np.random.default_rng(seed)
    for episode in range(episodes):
        turns = int(rng.choice([5, 6, 7, 8, 9]))
        clear = int(rng.choice([100, 150, 200, 250]))
        config = LessonConfig(turns=turns, stamina=int(rng.choice([24, 28, 32, 35])), target_clear=clear, hand_size=3)
        sim = LessonSim(deck, config, rng_seed=seed + episode)
        perfect = clear * 2
        pending: list[tuple[np.ndarray, float]] = []
        seen_turn = None

        def policy(inner):
            nonlocal seen_turn
            if inner.turns_left != seen_turn:
                seen_turn = inner.turns_left
                pending.append((features(inner), float(inner.score)))
            state = to_expect_state(inner, perfect)
            try:
                card = expectimax(state, value=value, time_budget_ms=budget_ms)
            except Exception:  # noqa: BLE001
                return None
            legal_idx = [a for a in inner.legal_actions() if isinstance(a, int)]
            if card is not None:
                for index in legal_idx:
                    if inner.hand[index].name == card.name:
                        return index
            # 搜索没给出合法动作 → 退回贪心（保证采样有分，不产生全 0 标签）
            best, best_score = None, -1.0
            for index in legal_idx:
                hand_card = inner.hand[index]
                gain = (hand_card.score + inner.buffs.focus) * (
                    1.5 if inner.buffs.condition_turns > 0 else 1.0
                )
                if gain > best_score:
                    best, best_score = index, gain
            return best

        final_score, _ = sim.run(policy)
        for feat, score_at_turn in pending:
            samples.append((feat, max(float(final_score) - score_at_turn, 0.0)))
    return samples


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=600)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--ridge", type=float, default=1.0)
    parser.add_argument("--budget-ms", type=float, default=15.0)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args(argv)

    from gkagent.sim.expectimax import AnalyticLeafValue
    from gkagent.sim.v_leaf import LinearLeafValue, fit_ridge

    t0 = time.perf_counter()
    history = []
    value = AnalyticLeafValue()
    model = None
    for round_index in range(args.rounds):
        samples = collect(args.episodes, args.seed + round_index * 100, value, args.budget_ms)
        weights, sigma, r2 = fit_ridge(samples, ridge=args.ridge)
        model = LinearLeafValue(weights=weights, sigma=sigma)
        value = model  # 下一轮用新 V 采样（真专家迭代）
        history.append(
            {"round": round_index + 1, "n": len(samples), "sigma": round(sigma, 2), "r2": round(r2, 4),
             "secs": round(time.perf_counter() - t0, 1)}
        )
        print(
            f"第 {round_index + 1} 轮：样本 {len(samples)}，σ={sigma:.1f}，r²={r2:.4f}"
            f"（{time.perf_counter() - t0:.0f}s）",
            flush=True,
        )
    assert model is not None
    model.meta = {"method": "expert_iteration", "rounds": args.rounds, "episodes": args.episodes, "history": history}
    model.save(OUT)
    print(f"\n权重已写入 {OUT}")
    print(history)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
