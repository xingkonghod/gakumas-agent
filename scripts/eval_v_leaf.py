"""L3 配对评测：analytic vs learned V_leaf（同牌组同种子）。

用法：python scripts/eval_v_leaf.py --episodes 300
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def to_expect_state(sim) -> object:
    """LessonSim → ExpectState（只带公开字段）。"""
    from gkagent.sim.expectimax import ExpectState

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
        plays_used=int(getattr(sim, "plays_used", 0) or 0),
        play_limit=3,
        clear=int(sim.config.target_clear),
        perfect=int(getattr(sim, "target_perfect", 0) or sim.config.target_clear * 2),
        condition_turns=int(sim.buffs.condition_turns),
        focus=int(sim.buffs.focus),
        impression=int(sim.buffs.impression),
    )


def play(episodes: int, seed: int, mode: str, value=None) -> list[tuple[int, bool]]:
    from gkagent.sim.expectimax import expectimax
    from gkagent.sim.lesson import LessonConfig, LessonSim
    import sim_produce as sp

    deck = [sp._spec_from_row(r) for r in sp.build_deck(rich=True)]
    out: list[tuple[int, bool]] = []
    for episode in range(episodes):
        config = LessonConfig(turns=6, stamina=32, target_clear=200, hand_size=3)
        sim = LessonSim(deck, config, rng_seed=seed + episode)

        def policy(inner):
            if mode == "greedy":
                best, best_score = None, -1.0
                for index, card in enumerate(inner.hand):
                    if index not in [a for a in inner.legal_actions() if isinstance(a, int)]:
                        continue
                    gain = (card.score + inner.buffs.focus) * (1.5 if inner.buffs.condition_turns > 0 else 1.0)
                    if gain > best_score:
                        best, best_score = index, gain
                return best
            state = to_expect_state(inner)
            try:
                card = expectimax(state, value=value, time_budget_ms=120.0)
            except Exception:  # noqa: BLE001 - 搜索失败退回贪心
                return None
            if card is None:
                return None
            legal_idx = [a for a in inner.legal_actions() if isinstance(a, int)]
            for index, hand_card in enumerate(inner.hand):
                if hand_card.name == card.name and index in legal_idx:
                    return index
            # 搜索给的动作在当前体力下不可行（指針费用修正差异）→ 退回该回合最强合法牌
            best, best_score = None, -1.0
            for index in legal_idx:
                hand_card = inner.hand[index]
                gain = (hand_card.score + inner.buffs.focus) * (
                    1.5 if inner.buffs.condition_turns > 0 else 1.0
                )
                if gain > best_score:
                    best, best_score = index, gain
            return best

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
    from gkagent.sim.v_leaf import LinearLeafValue

    model = LinearLeafValue.load(ROOT / "data" / "knowledge" / "v_leaf.json")
    print(f"learned: σ={model.sigma:.1f} r²={model.meta.get('history', [{}])[-1].get('r2')}")
    results = [
        report("greedy", play(args.episodes, args.seed, "greedy")),
        report("analytic", play(args.episodes, args.seed, "expectimax", AnalyticLeafValue())),
        report("learned", play(args.episodes, args.seed, "expectimax", model)),
    ]
    base = results[0]["mean"]
    for row in results[1:]:
        print(f"  {row['name']} vs greedy: 均值 {row['mean'] - base:+.1f} ({row['mean'] / base - 1:+.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
