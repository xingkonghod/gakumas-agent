"""主循环：env + policy → 回放/指标。

P0 只定义结构，不实现真实设备控制。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from gkagent.contract.models import ReplayStep, StepResult
from gkagent.policy.base import Policy
from gkagent.sim.env import Env


@dataclass
class LoopStats:
    episodes: int = 0
    steps: int = 0
    actions: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)

    def record(self, latency_ms: float) -> None:
        self.actions += 1
        self.total_latency_ms += latency_ms
        self.latencies_ms.append(latency_ms)

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        data = sorted(self.latencies_ms)
        idx = min(len(data) - 1, max(0, int(round((p / 100.0) * (len(data) - 1)))))
        return data[idx]


class AgentLoop:
    """跑若干局，产出 ReplayStep。

    真实的点击/截屏在 P3 接入；这里只保证：
    - 每步动作来自 policy；
    - 每步延迟被记录；
    - 异常不吞掉，交给上层熔断。
    """

    def __init__(self, env: Env, policy: Policy, max_steps: int = 2000) -> None:
        self.env = env
        self.policy = policy
        self.max_steps = max_steps
        self.stats = LoopStats()
        self.replay: list[ReplayStep] = []

    def run_episode(self, seed: int | None = None) -> StepResult:
        obs = self.env.reset(seed=seed)
        episode_id = self.env.episode_id or uuid.uuid4().hex
        result = StepResult(obs=obs)
        for step in range(self.max_steps):
            legal = self.env.legal_actions()
            if not legal:
                break
            t0 = time.perf_counter()
            action = self.policy.act(obs, legal)
            latency = (time.perf_counter() - t0) * 1000.0
            result = self.env.step(action)
            self.stats.steps += 1
            self.stats.record(latency)
            self.replay.append(
                ReplayStep(
                    episode_id=episode_id,
                    step=step,
                    obs=obs,
                    action=action,
                    latency_ms=latency,
                    reward=result.reward,
                    done=result.done,
                )
            )
            obs = result.obs
            if result.done:
                break
        self.stats.episodes += 1
        return result
