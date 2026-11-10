"""领取活动费：主页 → 活动经费 → 关闭弹窗。"""

from __future__ import annotations

from gkagent.agent import Agent
from gkagent.tasks.base import TaskResult


class ActivityFeeTask:
    name = "activity_fee"

    def run(self, agent: Agent) -> TaskResult:
        if not agent.ensure_home():
            return TaskResult(False, "不在主页")
        if not agent.claim_activity_fee():
            return TaskResult(False, "领取活动费失败")
        return TaskResult(True, "活动费已领取")
