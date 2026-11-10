"""日常任务串：活动费 → 工作 → 挑战 → 社团。"""

from __future__ import annotations

from gkagent.agent import Agent
from gkagent.tasks.activity_fee import ActivityFeeTask
from gkagent.tasks.base import Task, TaskResult
from gkagent.tasks.challenge import ChallengeTask
from gkagent.tasks.society import SocietyTask
from gkagent.tasks.work import WorkTask


class DailyTask:
    name = "daily"

    def __init__(self, tasks: list[Task] | None = None) -> None:
        self.tasks: list[Task] = tasks or [
            ActivityFeeTask(),
            WorkTask(),
            ChallengeTask(),
            SocietyTask(),
        ]

    def run(self, agent: Agent) -> TaskResult:
        parts: list[str] = []
        ok = True
        for task in self.tasks:
            result = task.run(agent)
            ok = ok and result.ok
            parts.append(f"{task.name}:{'ok' if result.ok else 'fail'}")
        return TaskResult(ok, "; ".join(parts))
