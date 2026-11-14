"""用模拟器选行动（训练/休息/上课/外出）。

真机每周遇到「请选择行动」时，不再只跟「推荐」气泡，而是：
对每个候选行动做 N 次前瞻 rollout（从当前局面出发，先执行该行动，
之后按默认策略打完剩余周），比较**最终评价点**，取期望最高的那个。

这样「选训练」这件事就是模拟器算出来的，而不是拍脑袋。

用法（真机侧）：`choose_action(attrs, stamina, week, deck, config)`
"""

from __future__ import annotations

import random

from gkagent.sim.lesson import CardSpec
from gkagent.sim.produce import (
    ProduceConfig,
    ProduceSim,
    StrategyParams,
    eval_value,
    strategy_from_params,
)

DEFAULT_PARAMS = StrategyParams(
    rest_threshold=8, lesson_every=1, attr_choice="weight", outing_below=16, min_stamina_to_train=8
)

ACTION_LABELS = {
    "train": "练审查基准最高属性",
    "train_low": "练最低属性",
    "rest": "休息",
    "lesson": "上课",
    "outing": "外出",
}


def _apply(sim: ProduceSim, action: str, weights: tuple[float, float, float]) -> None:
    if action == "train":
        best = max(range(3), key=lambda i: weights[i])
        sim.train(best)
    elif action == "train_low":
        sim.train(sim.lagging_attribute())
    elif action == "rest":
        sim.rest()
    elif action == "outing":
        sim.outing()
    elif action == "lesson":
        sim.lesson()
    else:
        raise ValueError(f"未知行动: {action}")


def _rollout(
    deck: list[CardSpec],
    pool: list[CardSpec],
    config: ProduceConfig,
    *,
    attrs: list[int],
    stamina: int,
    week: int,
    first_action: str,
    episodes: int,
    seed: int,
) -> float:
    """从当前局面出发：先做 first_action，之后按默认策略跑完，返回平均评价点。"""
    params = DEFAULT_PARAMS
    strategy = strategy_from_params(params)
    values = []
    for offset in range(episodes):
        sim = ProduceSim(deck, config=config, rng_seed=seed + offset)
        sim.reward_pool = pool
        sim.attrs = list(attrs)
        sim.stamina = stamina
        sim.week = week
        sim.deck = list(deck)
        sim.lessons = sim.cleared = sim.exams_passed = 0
        sim.fans = 0
        sim.trace = []
        _apply(sim, first_action, config.weights)
        sim.week += 1
        while not sim.done:
            sim.step(strategy)
        total = sum(sim.attrs)
        rank = 3
        for row in reversed(sim.trace):
            if row.get("exam"):
                rank = row["exam"]["rank"]
                break
        values.append(eval_value(total, rank, total * 2))
    return sum(values) / len(values)


def choose_action(
    deck: list[CardSpec],
    pool: list[CardSpec] | None = None,
    *,
    attrs: list[int],
    stamina: int,
    week: int,
    config: ProduceConfig | None = None,
    actions: tuple[str, ...] = ("train", "train_low", "rest", "lesson", "outing"),
    episodes: int = 16,
    seed: int = 12345,
) -> dict:
    """返回 {action, eval, ranking}：按模拟评价点排序的候选行动。"""
    cfg = config or ProduceConfig()
    reward_pool = pool or []
    # 外出只在特定周开放；不开放时不该被选
    available = [action for action in actions if action != "outing" or week in cfg.outing_weeks]
    ranking = []
    for index, action in enumerate(available):
        score = _rollout(
            deck,
            reward_pool,
            cfg,
            attrs=attrs,
            stamina=stamina,
            week=week,
            first_action=action,
            episodes=episodes,
            seed=seed + index * 1000,
        )
        ranking.append({"action": action, "label": ACTION_LABELS.get(action, action), "eval": round(score, 1)})
    ranking.sort(key=lambda row: row["eval"], reverse=True)
    return {"action": ranking[0]["action"], "eval": ranking[0]["eval"], "ranking": ranking}


def random_pool(seed: int = 0) -> list[CardSpec]:
    """构造一个小奖励池（离线测试/真机没有卡表数据时用）。"""
    rng = random.Random(seed)
    pool = []
    for index in range(12):
        pool.append(
            CardSpec(
                name=f"reward{index}",
                cost=rng.choice([0, 1, 2, 3, 4, 5]),
                score=rng.choice([6, 8, 10, 12, 15, 18, 20, 24, 27, 30]),
                condition=rng.choice([0, 0, 0, 2]),
                focus=rng.choice([0, 0, 0, 1, 2]),
            )
        )
    return pool
