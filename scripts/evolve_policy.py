"""进化训练出牌权重：w·φ(s,a) 在课程模拟器里搜。

目标：固定牌组、固定随机种子集合上，最大化平均课程得分（等价于属性成长）。

用法：python scripts/evolve_policy.py --generations 20 --population 12 --episodes 300
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "data" / "knowledge" / "policy_weights.json"


def evaluate(weights: list[float], episodes: int, seed_base: int) -> float:
    from gkagent.policy.scored import ScoredPolicy, decide
    from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim
    import sim_produce as sp

    deck = [sp._spec_from_row(r) for r in sp.build_deck(rich=True)]
    policy = ScoredPolicy()
    policy.set_vector(weights)
    scores = []
    rng = random.Random(seed_base)
    for episode in range(episodes):
        config = LessonConfig(
            turns=rng.choice([5, 6, 7, 8]),
            stamina=rng.choice([24, 28, 32, 35]),
            target_clear=rng.choice([100, 150, 200, 250]),
            target_perfect=None,
            hand_size=3,
        )
        sim = LessonSim(deck, config, rng_seed=seed_base + episode)
        result = sim.run(lambda inner: decide(inner, inner.hand, policy,
                                             target_clear=config.target_clear,
                                             target_perfect=config.target_clear * 2))
        score = result[0] if isinstance(result, tuple) else result
        scores.append(score)
    return st.mean(scores)


def mutate(weights: list[float], rng: random.Random, sigma: float = 0.35) -> list[float]:
    return [w + rng.gauss(0, sigma) for w in weights]


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--generations", type=int, default=20)
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    from gkagent.policy.scored import FEATURES, ScoredPolicy

    rng = random.Random(args.seed)
    base = ScoredPolicy().vector()
    print(f"训练集: {args.episodes} 节课/候选 × {args.population} 候选 × {args.generations} 代")
    t0 = time.perf_counter()
    base_score = evaluate(base, args.episodes, 1000)
    print(f"手调先验: {base_score:.1f}")

    population = [base] + [mutate(base, rng) for _ in range(args.population - 1)]
    best_weights, best_score = base, base_score
    curve = []
    for generation in range(1, args.generations + 1):
        results = [(evaluate(candidate, args.episodes, 1000), candidate) for candidate in population]
        results.sort(key=lambda pair: pair[0], reverse=True)
        top = results[0][0]
        if top > best_score:
            best_score, best_weights = top, results[0][1]
        curve.append({"generation": generation, "best": round(top, 1), "overall": round(best_score, 1)})
        print(f"  第 {generation} 代: 本代最优 {top:.1f} | 历史最优 {best_score:.1f}")
        survivors = [candidate for _, candidate in results[: max(2, args.population // 4)]]
        population = list(survivors)
        while len(population) < args.population:
            population.append(mutate(rng.choice(survivors), rng))

    print(f"\n手调先验 {base_score:.1f} → 进化后 {best_score:.1f} (+{(best_score/max(base_score,1)-1)*100:.1f}%)")
    print(f"耗时 {time.perf_counter()-t0:.1f}s")
    OUT.write_text(
        json.dumps(
            {
                "version": 1,
                "features": list(FEATURES),
                "base_score": round(base_score, 2),
                "best_score": round(best_score, 2),
                "weights": {name: round(value, 4) for name, value in zip(FEATURES, best_weights)},
                "curve": curve,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print("权重已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
