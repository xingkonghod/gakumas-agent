"""r9 解释报告探针：决策级行为比较（纯 net，确定性，无搜索预算）。

small 500 局（3000–3499）：v6 / r9 / v1 三方——
  逐局分差/CLEAR 翻转、动作序列一致率、首个分歧点（同局面）选牌特征对比
  （r9 是否更偏零分 buff 牌 / 更低即时分牌；r9 分歧时是否更像 v1）。
large 120 局（3000–3119）：v6 / r9 —— 增益来源（CLEAR 翻转/分歧点回合分布）。

用法：.venv\\Scripts\\python.exe data\\_r9_behavior_probe.py
一次性脚本，不提交。输出 out/_r9_behavior_probe.json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_expectimax as ee

from gkagent.sim.policy_data import play_selfplay
from gkagent.sim.policy_mlp import PolicyMLP

OUT = ROOT / "out"


def play_all(deck, config, seeds, models: dict[str, PolicyMLP]):
    rows = {name: [] for name in models}
    for seed in seeds:
        for name, model in models.items():
            sim, row = play_selfplay(deck, config, seed, model)
            rows[name].append(
                {
                    "seed": seed,
                    "score": row["score"],
                    "clear": row["clear"],
                    "actions": [d.action for d in sim.decisions],
                    "cards": [
                        {
                            "name": d.state.hand[d.action].name if d.action is not None else None,
                            "score": float(d.state.hand[d.action].score) if d.action is not None else 0.0,
                            "cost": float(d.state.hand[d.action].cost) if d.action is not None else 0.0,
                            "turns_left": int(d.state.turns_left),
                        }
                        for d in sim.decisions
                    ],
                }
            )
    return rows


def compare(rows, a: str, b: str, config) -> dict:
    """a 相对 b：分差/CLEAR 翻转/一致率/首分歧选牌特征。"""
    deltas, flips_up, flips_down = [], 0, 0
    agree_dec = 0
    total_dec = 0
    first_div = 0
    a_lower_score = 0
    a_zero_b_pos = 0
    a_pos_b_zero = 0
    div_turns = []
    for ra, rb in zip(rows[a], rows[b]):
        deltas.append(ra["score"] - rb["score"])
        if ra["clear"] and not rb["clear"]:
            flips_up += 1
        if rb["clear"] and not ra["clear"]:
            flips_down += 1
        aa, ab = ra["actions"], rb["actions"]
        n = min(len(aa), len(ab))
        same = sum(1 for i in range(n) if aa[i] == ab[i])
        agree_dec += same
        total_dec += max(len(aa), len(ab))
        k = next((i for i in range(n) if aa[i] != ab[i]), None)
        if k is not None:
            first_div += 1
            ca, cb = ra["cards"][k], rb["cards"][k]
            div_turns.append(ca["turns_left"])
            if ca["score"] < cb["score"]:
                a_lower_score += 1
            if ca["score"] <= 0 < cb["score"]:
                a_zero_b_pos += 1
            if cb["score"] <= 0 < ca["score"]:
                a_pos_b_zero += 1
    n_games = len(deltas)
    return {
        "games": n_games,
        "mean_delta": sum(deltas) / n_games,
        "clear_flips_up": flips_up,
        "clear_flips_down": flips_down,
        "decision_agreement": agree_dec / max(total_dec, 1),
        "games_with_divergence": first_div,
        "at_first_divergence": {
            "a_lower_immediate_score": a_lower_score,
            "a_zero_score_b_positive": a_zero_b_pos,
            "a_positive_b_zero_score": a_pos_b_zero,
            "mean_turns_left": (sum(div_turns) / len(div_turns)) if div_turns else None,
        },
    }


def main() -> None:
    models = {
        "v6": PolicyMLP.load(OUT / "ei_r6_v6_mix.json"),
        "r9": PolicyMLP.load(OUT / "ei_r9_v9_mix.json"),
        "v1": PolicyMLP.load(OUT / "ei_r1_v1_mix.json"),
    }
    report = {}
    for scenario, seeds, names in (
        ("small", range(3000, 3500), ("v6", "r9", "v1")),
        ("large", range(3000, 3120), ("v6", "r9")),
    ):
        deck, config = ee.build_deck(scenario), ee.make_config(scenario)
        rows = play_all(deck, config, seeds, {n: models[n] for n in names})
        sc = {}
        for a, b in (("r9", "v6"), ("r9", "v1"), ("v6", "v1")):
            if a in rows and b in rows:
                sc[f"{a}_vs_{b}"] = compare(rows, a, b, config)
        # 完整序列相同率（r9 更像谁）
        for a, b in (("r9", "v6"), ("r9", "v1")):
            if a in rows and b in rows:
                same = sum(
                    1 for ra, rb in zip(rows[a], rows[b]) if ra["actions"] == rb["actions"]
                )
                sc[f"{a}_vs_{b}"]["identical_game_sequences"] = same
        report[scenario] = sc
        print(f"=== {scenario} ===")
        for k, v in sc.items():
            print(k, json.dumps(v, ensure_ascii=False))
    (OUT / "_r9_behavior_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("→ out/_r9_behavior_probe.json")


if __name__ == "__main__":
    main()
