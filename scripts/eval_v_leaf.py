"""L3 配对评测：analytic vs learned V_leaf（同牌组同种子）。

用法：python scripts/eval_v_leaf.py --episodes 300
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def _greedy_pick(inner, legal_idx: list[int]):
    """退回贪心：按解析式挑最高分牌（搜索失败/动作不可执行时用）。"""
    best, best_score = None, -1.0
    for index in legal_idx:
        hand_card = inner.hand[index]
        gain = (hand_card.score + inner.buffs.focus) * (
            1.5 if inner.buffs.condition_turns > 0 else 1.0
        )
        if gain > best_score:
            best, best_score = index, gain
    return best


def play(episodes: int, seed: int, mode: str, value=None) -> list[tuple[int, bool]]:
    import sim_produce as sp

    from gkagent.sim.expectimax import expectimax, state_from_sim
    from gkagent.sim.lesson import LessonConfig, LessonSim

    deck = [sp._spec_from_row(r) for r in sp.build_deck(rich=True)]
    out: list[tuple[int, bool]] = []
    for episode in range(episodes):
        config = LessonConfig(turns=6, stamina=32, target_clear=200, hand_size=3)
        sim = LessonSim(deck, config, rng_seed=seed + episode)

        def policy(inner):
            legal_idx = [a for a in inner.legal_actions() if isinstance(a, int)]
            if mode == "greedy":
                return _greedy_pick(inner, legal_idx)
            failed = False
            try:
                card = expectimax(
                    state_from_sim(inner), value=value, time_budget_ms=120.0
                )
            except Exception:  # noqa: BLE001 - 搜索失败退回贪心，不能直接 SKIP
                card = None
                failed = True
            if card is not None:
                # 搜索用的就是 sim.hand 里的牌对象，按 identity 映射回下标
                for index in legal_idx:
                    if inner.hand[index] is card:
                        return index
                # 搜索给的动作在当前指針/体力下不可行 → 退回该回合最强合法牌
                return _greedy_pick(inner, legal_idx)
            if failed:
                return _greedy_pick(inner, legal_idx)
            # 搜索成功且返回 None：这是策略选择的 SKIP
            return None

        score, grade = sim.run(policy)
        out.append((int(score), grade == "PERFECT"))
    return out


def report(name: str, rows: list[tuple[int, bool]]) -> dict:
    scores = sorted(r[0] for r in rows)
    perfect = sum(1 for r in rows if r[1]) / max(len(rows), 1)
    n = len(scores)
    stats = {
        "name": name,
        "mean": round(st.mean(scores), 1),
        "p10": scores[n // 10],
        "p50": scores[n // 2],
        "p90": scores[n * 9 // 10],
        "perfect_rate": round(perfect * 100, 1),
    }
    print(
        f"{name:10s} 均值 {stats['mean']:7.1f} | P10 {stats['p10']:5d} P50 {stats['p50']:5d} "
        f"P90 {stats['p90']:5d} | PERFECT {stats['perfect_rate']:5.1f}%"
    )
    return stats


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--seed", type=int, default=900)
    args = parser.parse_args(argv)

    from gkagent.sim.expectimax import AnalyticLeafValue

    model = None
    model_path = ROOT / "data" / "knowledge" / "v_leaf.json"
    if model_path.exists():
        try:
            from gkagent.sim.v_leaf import LinearLeafValue

            model = LinearLeafValue.load(model_path)
            history = model.meta.get("history") or [{}]
            print(f"learned: σ={model.sigma:.1f} r²={history[-1].get('r2')}")
        except Exception as exc:  # noqa: BLE001 - 模型坏了不该挡住 baseline 评测
            print(f"learned 加载失败（跳过该组）: {type(exc).__name__}: {exc}")
    else:
        print(f"未找到 {model_path.name}，跳过 learned 组（只跑 greedy / analytic）")

    results = [
        report("greedy", play(args.episodes, args.seed, "greedy")),
        report("analytic", play(args.episodes, args.seed, "expectimax", AnalyticLeafValue())),
    ]
    if model is not None:
        results.append(report("learned", play(args.episodes, args.seed, "expectimax", model)))
        from gkagent.sim.v_leaf import EnsembleLeafValue

        ensemble = EnsembleLeafValue(primary=AnalyticLeafValue(), secondary=model, weight=0.5)
        results.append(report("ensemble", play(args.episodes, args.seed, "expectimax", ensemble)))
    base = results[0]["mean"]
    for row in results[1:]:
        print(f"  {row['name']} vs greedy: 均值 {row['mean'] - base:+.1f} ({row['mean'] / base - 1:+.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
