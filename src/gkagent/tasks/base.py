"""任务接口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gkagent.agent import Agent


@dataclass
class TaskResult:
    ok: bool
    message: str = ""


class Task(Protocol):
    name: str

    def run(self, agent: Agent) -> TaskResult:
        ...
