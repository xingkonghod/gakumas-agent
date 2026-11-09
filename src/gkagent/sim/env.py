"""模拟器统一接口。竞赛/培育环境都实现 Env。

约定：
- reset() 返回 Observation；
- step() 返回 StepResult；
- legal_actions() 返回当前合法动作列表（供 policy 做掩码）；
- 所有随机性由 seed 控制，保证可复现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from gkagent.contract.models import Action, Observation, StepResult


class Env(ABC):
    """Gym 风格的极简环境。"""

    @abstractmethod
    def reset(self, seed: int | None = None) -> Observation:
        raise NotImplementedError

    @abstractmethod
    def step(self, action: Action) -> StepResult:
        raise NotImplementedError

    @abstractmethod
    def legal_actions(self) -> list[Action]:
        raise NotImplementedError

    @property
    @abstractmethod
    def episode_id(self) -> str:
        raise NotImplementedError
