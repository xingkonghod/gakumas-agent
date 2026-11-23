"""B11 渐退式专家迭代：决策记录 + on-policy 优势标签（精确重放分支）。

核心思路（docs/EXPECTIMAX.md「再下一候选方向」）：优势标签必须来自**学生自己
的对局**——打法变了标签跟着变，绕开 B2-R 的「价值-策略失配」根因。

做法（不经过搜索镜像，零近似）：

1. ``DecisionRecordingSim`` 在学生自对弈时记录每个**真实决策点**
   （``legal_actions() != [None]``）：``state_from_sim`` 快照 + 合法动作 +
   实际选择 + 之前执行过的完整动作前缀；
2. 对每个决策的每张可出牌：``LessonSim(deck, config, seed)`` 重放前缀到达
   **逐字段相同**的局面（``state_from_sim`` 全等校验，不静默容忍失配），
   打出候选牌，再用**当前学生策略**把剩余回合打完 → 终局分 R(s,a)；
3. ``A(s,a) = R(s,a) − mean_b R(s,b)``（「这张比平均好多少」）。

确定性基础：``LessonSim`` 同 (deck, config, seed) + 同动作序列完全可复现
（``rng`` 只在构造洗牌/重洗时用），学生 argmax 策略也是确定性的——每个分支
是精确的 on-policy 延续，不是采样估计。分支间共享同一 rng 状态（共同随机数，
天然方差缩减）。

教师示范样本（``demo_samples``）：教师出的牌 +1、其余 −1/(k−1)；k=1 的强制
决策与教师「有牌却 SKIP」的决策无蒸馏信息，剔除并计数（学生硬规矩不允许
有牌 SKIP，见 ``policy_mlp.net_action``）。

第 1 轮口径：small 场景（14 张 / 5 回合 / CLEAR 120 / PERFECT 170），
``config.drinks`` 为空——饮料动作不在本轮动作空间（与 B1/B2 harness 一致）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from gkagent.sim.expectimax import ExpectState, state_from_sim
from gkagent.sim.lesson import Action, CardSpec, LessonConfig, LessonSim
from gkagent.sim.policy_mlp import PolicyMLP, decision_features, net_action


@dataclass(frozen=True)
class DecisionRecord:
    """一个真实决策点：局面快照 + 合法动作 + 实际选择 + 之前的动作前缀。"""

    state: ExpectState
    legal: tuple[Action, ...]
    action: Action
    prefix: tuple[Action, ...]

    @property
    def playable(self) -> tuple[int, ...]:
        return tuple(index for index in self.legal if index is not None)


class DecisionRecordingSim(LessonSim):
    """``LessonSim`` + 记录每个真实决策点（自动 SKIP 不算决策）。"""

    def __init__(self, *args, **kwargs) -> None:
        self.decisions: list[DecisionRecord] = []
        self._action_prefix: list[Action] = []
        super().__init__(*args, **kwargs)

    def step(self, action: Action) -> None:
        if not self.done:
            legal = self.legal_actions()
            if legal != [None]:
                self.decisions.append(
                    DecisionRecord(
                        state=state_from_sim(self),
                        legal=tuple(legal),
                        action=action,
                        prefix=tuple(self._action_prefix),
                    )
                )
        self._action_prefix.append(action)
        super().step(action)


def replay_to(
    deck: list[CardSpec],
    config: LessonConfig,
    seed: int,
    prefix: tuple[Action, ...],
) -> LessonSim:
    """从 (deck, config, seed) 精确重放动作前缀，返回到达的模拟器。"""
    sim = LessonSim(deck, config, rng_seed=seed)
    for action in prefix:
        sim.step(action)
    return sim


def verify_replay(sim: LessonSim, state: ExpectState) -> None:
    """重放局面必须与记录快照**逐字段全等**；失配 = 数据 bug，直接抛错。"""
    reached = state_from_sim(sim)
    if reached != state:
        raise RuntimeError(
            "重放局面与决策快照不一致（deck/config/seed/前缀有错，或模拟器非确定性）："
            f"score {reached.score} vs {state.score}, "
            f"stamina {reached.stamina} vs {state.stamina}, "
            f"turns_left {reached.turns_left} vs {state.turns_left}, "
            f"hand {[c.name for c in reached.hand]} vs {[c.name for c in state.hand]}"
        )


def play_selfplay(
    deck: list[CardSpec],
    config: LessonConfig,
    seed: int,
    model: PolicyMLP,
    *,
    explore_eps: float = 0.0,
) -> tuple[DecisionRecordingSim, dict]:
    """学生自对弈一局（argmax + 硬规矩禁跳）；返回记录 sim 与成绩。

    ``explore_eps``（B11 r7 设计变量，仅采集侧）：>0 时每个决策以概率 ε 在
    **可出牌**里均匀随机选（ε-greedy 探索），扩大 argmax 路径之外的状态覆盖；
    优势标签仍由 ``advantage_samples`` 用当前学生精确重放延续（on-policy 不变）。
    硬规矩不变：探索只在可出牌里选，有牌绝不 SKIP。ε=0 = 原 argmax 行为逐位不变。
    探索 rng 由 seed 派生（独立偏移），同 seed 完全可复现。
    """
    if not 0.0 <= explore_eps <= 1.0:
        raise ValueError(f"explore_eps 必须在 [0,1]：{explore_eps}")
    sim = DecisionRecordingSim(deck, config, rng_seed=seed)
    if explore_eps == 0.0:
        score, _grade = sim.run(lambda current: net_action(current, model))
    else:
        rng = np.random.default_rng(seed + 900_000_000)

        def _explore_policy(current: LessonSim) -> Action:
            playable = [index for index in current.legal_actions() if index is not None]
            if not playable:
                return None
            if rng.random() < explore_eps:
                return playable[int(rng.integers(len(playable)))]
            return net_action(current, model)

        score, _grade = sim.run(_explore_policy)
    return sim, {
        "score": float(score),
        "clear": 1.0 if score >= config.target_clear else 0.0,
        "perfect": 1.0 if score >= config.target_perfect else 0.0,
        "decisions": len(sim.decisions),
    }


def advantage_samples(
    deck: list[CardSpec],
    config: LessonConfig,
    seed: int,
    record: DecisionRecord,
    rollout_policy: Callable[[LessonSim], Action],
    *,
    verify: bool = True,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """一个决策点 → (X, A, meta)：每张可出牌一行，标签 = 分支优势。

    ``rollout_policy`` = 分支后的延续策略（on-policy 口径下就是当前学生）。
    分支用精确重放（``replay_to`` + ``verify_replay``），不走搜索镜像。
    """
    playable = record.playable
    if not playable:
        raise ValueError("决策记录没有可出牌（记录条件 legal != [None] 被违反）")
    finals: dict[int, float] = {}
    for index in playable:
        branch = replay_to(deck, config, seed, record.prefix)
        if verify:
            verify_replay(branch, record.state)
        branch.step(index)
        final, _grade = branch.run(rollout_policy)
        finals[index] = float(final)
    mean_final = sum(finals.values()) / len(finals)
    cards = [record.state.hand[index] for index in playable]
    X = np.asarray(
        [decision_features(record.state, card) for card in cards], dtype=np.float64
    )
    y = np.asarray([finals[index] - mean_final for index in playable], dtype=np.float64)
    return X, y, {
        "finals": finals,
        "mean_final": mean_final,
        "chosen": record.action,
        "n": len(playable),
    }


def demo_samples(record: DecisionRecord) -> tuple[np.ndarray, np.ndarray, dict] | None:
    """教师示范 → 软目标（教师牌 +1、其余 −1/(k−1)）。

    剔除（返回 None，meta.reason 计数）：k=1 强制决策（无信息）、教师有牌却
    SKIP（学生动作空间里没有这个选项，硬规矩）。
    """
    playable = record.playable
    if len(playable) < 2:
        return None
    if record.action is None or record.action not in playable:
        return None
    cards = [record.state.hand[index] for index in playable]
    X = np.asarray(
        [decision_features(record.state, card) for card in cards], dtype=np.float64
    )
    k = len(playable)
    y = np.full(k, -1.0 / (k - 1), dtype=np.float64)
    y[playable.index(record.action)] = 1.0
    return X, y, {"chosen": record.action, "n": k}
