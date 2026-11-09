"""Observation / Action 契约。

所有层之间只通过这些模型交换数据；字段读不到就是 None，不猜。
契约版本变化必须升 schema_version，并保留旧版本的反序列化测试。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "1.0"


class Phase(str, Enum):
    UNKNOWN = "unknown"
    TITLE = "title"
    HOME = "home"
    CONTEST = "contest"
    PRODUCE = "produce"
    EXAM = "exam"
    RESULT = "result"


class Card(BaseModel):
    """手牌/卡组中的一张卡。"""

    model_config = ConfigDict(extra="forbid")

    card_id: str
    name: str | None = None
    cost: int | None = None
    kind: str | None = None  # attack / buff / debuff / heal / status ...
    playable: bool = True


class Scores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vocal: int = 0
    dance: int = 0
    visual: int = 0

    @property
    def total(self) -> int:
        return self.vocal + self.dance + self.visual


class Observation(BaseModel):
    """一帧的完整状态。perception 产出，policy 消费。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    frame_id: int
    ts_ms: int
    screen: str = "unknown"  # 界面 ID，例如 contest_select / produce_card
    phase: Phase = Phase.UNKNOWN
    turn: int | None = None
    hp: int | None = None
    stamina: int | None = None
    scores: Scores = Field(default_factory=Scores)
    hand: list[Card] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw: dict[str, Any] = Field(default_factory=dict)


class ActionKind(str, Enum):
    PLAY_CARD = "play_card"
    CHOOSE = "choose"
    END_TURN = "end_turn"
    CLICK = "click"
    WAIT = "wait"


class Action(BaseModel):
    """策略层输出的一个动作。action 层只执行白名单内的 kind。"""

    model_config = ConfigDict(extra="forbid")

    kind: ActionKind
    index: int | None = None
    target: str | None = None
    point: tuple[int, int] | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _require_index(self) -> "Action":
        if self.kind in (ActionKind.PLAY_CARD, ActionKind.CHOOSE) and self.index is None:
            raise ValueError(f"{self.kind.value} requires index")
        if self.index is not None and self.index < 0:
            raise ValueError("index must be >= 0")
        return self


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obs: Observation
    reward: float = 0.0
    done: bool = False
    info: dict[str, Any] = Field(default_factory=dict)


class ReplayStep(BaseModel):
    """回放的一步；落 SQLite，用于复盘与训练。"""

    model_config = ConfigDict(extra="forbid")

    episode_id: str
    step: int
    frame_hash: str | None = None
    obs: Observation
    action: Action
    latency_ms: float = 0.0
    reward: float = 0.0
    done: bool = False
