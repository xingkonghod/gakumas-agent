"""任务集合。"""

from gkagent.tasks.activity_fee import ActivityFeeTask
from gkagent.tasks.base import Task, TaskResult
from gkagent.tasks.challenge import ChallengeTask
from gkagent.tasks.daily import DailyTask
from gkagent.tasks.society import SocietyTask
from gkagent.tasks.work import WorkTask

__all__ = [
    "ActivityFeeTask",
    "ChallengeTask",
    "DailyTask",
    "SocietyTask",
    "Task",
    "TaskResult",
    "WorkTask",
]
