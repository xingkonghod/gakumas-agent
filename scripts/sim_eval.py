"""S2/S4：在无画面模拟器上评估卡组、扫描出牌参数。

不依赖真机、不依赖截图：只读卡表（费用/数值）+ 模拟器核心。

用法：
    python scripts/sim_eval.py                 # 用默认卡组跑 200 局基线
    python scripts/sim_eval.py --sweep         # 扫描参数，打印 Top-5
    python scripts/sim_eval.py --sweep --write # 把最优参数写 data/knowledge/policy_sim.json

参数与真机 LessonPolicy 对齐（reserve_per_turn / buff_score_guard / negligible / last_turn_max_total）。
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics as stats
import sys
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

CARD_TABLE = ROOT / "data" / "knowledge" / "card_table.json"
POLICY_OUT = ROOT / "data" / "knowledge" / "policy_sim.json"

# 默认卡组：最近几局真机日志里反复出现的牌（实在牌库会替换，这里只做对比基准）
DEFAULT_DECK = [
    ("好调", 1),
    ("集中", 1),
    ("魅力的基础", 2),
    ("表现的基础", 3),
    ("表情的基础", 2),
    ("准备运动", 2),
    ("粉丝服务", 2),
    ("聊天时间", 1),
    ("凭势而行", 1),
    ("重新开始", 1),
]

# 卡表数值缺失时的兜底：按卡面文本里的「打分+N」估
# 卡表数值缺失时，buff 类卡按"层数/回合数"给个保守值
DEFAULT_BUFFS = {"好调": {"condition": 2}, "集中": {"focus": 2}}


DEFAULT_SCORES = {
    "魅力的基础": 9,
    "表现的基础": 4,
    "表情的基础": 6,
    "准备运动": 12,
    "粉丝服务": 10,
    "聊天时间": 27,
    "凭势而行": 15,
    "重新开始": 8,
    "好调": 0,
    "集中": 0,
}

BASE_PARAMS = {
    "reserve_per_turn": 2.0,
    "negligible": 0.5,
    "min_gain": 1.0,
    "buff_score_guard": 5.0,
    "last_turn_max_total": True,
    "buff_first": True,
}

SWEEP_GRID = {
    "reserve_per_turn": [0.0, 1.0, 2.0, 3.0],
    "buff_score_guard": [3.0, 5.0, 8.0],
    "negligible": [0.0, 0.5, 2.0],
    "last_turn_max_total": [True, False],
}


def load_card_table() -> dict:
    if not CARD_TABLE.exists():
        return {}
    return json.loads(CARD_TABLE.read_text(encoding="utf-8")).get("cards", {})


def card_score(name: str, table: dict) -> int:
    row = table.get(name) or {}
    for effect in row.get("effects") or []:
        if effect.get("type") == "ExamLesson":
            values = [v for v in effect.get("values") or [] if v]
            if values:
                return int(values[0])
    return DEFAULT_SCORES.get(name, 0)


def build_deck(table: dict, names: list[tuple[str, int]] | None = None):
    from gkagent.sim.lesson import CardSpec

    deck = []
    for name, count in names or DEFAULT_DECK:
        row = table.get(name) or {}
        cost = int(row.get("cost", 4) or 0)
        score = card_score(name, table)
        extra = DEFAULT_BUFFS.get(name, {})
        for index in range(count):
            deck.append(CardSpec(name=f"{name}#{index}", cost=cost, score=score, **extra))
    return deck


def make_policy(params: dict):
    """和真机 LessonPolicy 同构的简化策略（模拟器侧）。"""

    def policy(sim) -> int | None:
        legal = [index for index in sim.legal_actions() if index is not None]
        if not legal:
            return None
        turns = sim.turns_left
        stamina = sim.stamina
        budget = stamina
        if turns and turns > 1:
            reserve = params["reserve_per_turn"] * (turns - 1)
            budget = max(stamina - reserve, stamina / max(turns, 1))

        def value(index: int) -> float:
            card = sim.hand[index]
            return float(card.score) * (1.5 if sim.buffs.condition_turns > 0 else 1.0)

        scored = [(index, value(index)) for index in legal if value(index) > params["negligible"]]
        if not scored:
            cheapest = min(legal, key=lambda i: (sim.hand[i].cost, i))
            return cheapest
        if turns and turns <= 1 and params["last_turn_max_total"]:
            scored.sort(key=lambda item: item[1], reverse=True)
        else:
            in_budget = [item for item in scored if sim.hand[item[0]].cost <= budget]
            pool = in_budget or scored
            pool.sort(key=lambda item: (item[1] / max(sim.hand[item[0]].cost, 1), item[1]), reverse=True)
            scored = pool
        index = scored[0][0]
        return index

    return policy


def evaluate(
    params: dict, table: dict, *, episodes: int = 200, seed: int = 7,
    turns: int = 5, stamina: int = 34, target: int = 250,
) -> dict:
    from gkagent.sim.lesson import LessonConfig, LessonSim

    policy = make_policy(params)
    deck = build_deck(table)
    scores, grades = [], []
    for episode in range(episodes):
        sim = LessonSim(
            deck,
            LessonConfig(turns=turns, stamina=stamina, target_clear=target, target_perfect=int(target * 1.6)),
            rng_seed=seed + episode,
        )
        score, grade = sim.run(policy)
        scores.append(score)
        grades.append(grade)
    return {
        "mean": round(stats.mean(scores), 1),
        "p10": round(sorted(scores)[max(0, len(scores) // 10)], 1),
        "clear_rate": round(sum(1 for g in grades if g in ("CLEAR", "PERFECT")) / len(grades), 3),
        "perfect_rate": round(sum(1 for g in grades if g == "PERFECT") / len(grades), 3),
        "fail_rate": round(sum(1 for g in grades if g == "FAILED") / len(grades), 3),
        "n": len(scores),
    }


def sweep(table: dict, *, episodes: int = 120, **kwargs) -> list[tuple[float, dict, dict]]:
    keys = list(SWEEP_GRID)
    results = []
    for combo in itertools.product(*(SWEEP_GRID[key] for key in keys)):
        params = dict(BASE_PARAMS)
        params.update(dict(zip(keys, combo)))
        stats_ = evaluate(params, table, episodes=episodes, **kwargs)
        # 排序：先看 CLEAR 率，再看平均分
        results.append((stats_["clear_rate"] * 1000 + stats_["mean"], params, stats_))
    results.sort(key=lambda item: item[0], reverse=True)
    return results


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--target", type=int, default=250)
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--stamina", type=int, default=34)
    args = parser.parse_args(argv)

    table = load_card_table()
    if not table:
        print("缺少 data/knowledge/card_table.json")
        return 1
    kwargs = {"turns": args.turns, "stamina": args.stamina, "target": args.target}
    base = evaluate(BASE_PARAMS, table, episodes=args.episodes, **kwargs)
    print("基线:", json.dumps(base, ensure_ascii=False))
    if not args.sweep:
        return 0

    results = sweep(table, episodes=max(80, args.episodes // 2), **kwargs)
    print("\nTop-5 参数组合：")
    for score_key, params, stats_ in results[:5]:
        print(f"  score={score_key:.1f} {stats_} {params}")
    best_params = results[0][1]
    best_stats = evaluate(best_params, table, episodes=args.episodes, **kwargs)
    delta = best_stats["mean"] - base["mean"]
    print(f"\n最优 vs 基线: mean {base['mean']} -> {best_stats['mean']} ({delta:+.1f})")
    if args.write:
        POLICY_OUT.write_text(
            json.dumps({"version": 1, "lesson": best_params, "stats": best_stats}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print("已写入", POLICY_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
