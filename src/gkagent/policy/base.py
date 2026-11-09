"""策略接口与随机基线。"""

from __future__ import annotations

import random
from typing import Protocol

from gkagent.contract.models import Action, Observation


class Policy(Protocol):
    """输入状态与合法动作，输出一个动作。"""

    def act(self, obs: Observation, legal: list[Action]) -> Action:
        ...


class RandomPolicy:
    """随机基线；用于验证环境/回放/指标链路。"""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def act(self, obs: Observation, legal: list[Action]) -> Action:
        if not legal:
            raise ValueError("no legal actions")
        return self._rng.choice(legal)


class ScriptedPolicy:
    """按顺序回放固定动作；用于复现和冒烟测试。"""

    def __init__(self, actions: list[Action]) -> None:
        self._actions = list(actions)
        self._i = 0

    def act(self, obs: Observation, legal: list[Action]) -> Action:
        if self._i >= len(self._actions):
            raise StopIteration("scripted actions exhausted")
        action = self._actions[self._i]
        self._i += 1
        return action
