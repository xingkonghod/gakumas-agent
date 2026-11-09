from __future__ import annotations

import pytest

from gkagent.contract.models import (
    Action,
    ActionKind,
    Card,
    Observation,
    Phase,
    ReplayStep,
    Scores,
    StepResult,
)
from gkagent.policy.base import RandomPolicy
from gkagent.runtime.loop import AgentLoop
from gkagent.sim.env import Env


def test_action_requires_index_for_play_card() -> None:
    with pytest.raises(ValueError):
        Action(kind=ActionKind.PLAY_CARD)
    with pytest.raises(ValueError):
        Action(kind=ActionKind.CHOOSE)


def test_action_allows_end_turn_without_index() -> None:
    a = Action(kind=ActionKind.END_TURN)
    assert a.index is None


def test_observation_json_roundtrip() -> None:
    obs = Observation(
        frame_id=7,
        ts_ms=123456,
        screen="contest_select",
        phase=Phase.CONTEST,
        turn=3,
        hp=80,
        stamina=12,
        scores=Scores(vocal=100, dance=90, visual=110),
        hand=[Card(card_id="c001", name="测试卡", cost=2, kind="attack")],
        choices=["A", "B"],
        confidence=0.97,
    )
    raw = obs.model_dump_json()
    back = Observation.model_validate_json(raw)
    assert back == obs
    assert back.scores.total == 300


def test_replay_step_roundtrip() -> None:
    step = ReplayStep(
        episode_id="ep1",
        step=0,
        frame_hash="abc",
        obs=Observation(frame_id=0, ts_ms=0),
        action=Action(kind=ActionKind.WAIT),
        latency_ms=1.2,
    )
    assert ReplayStep.model_validate_json(step.model_dump_json()) == step


class DummyEnv(Env):
    """最小环境：3 步结束，用于验证 loop/replay 链路。"""

    def __init__(self) -> None:
        self._t = 0

    def reset(self, seed: int | None = None) -> Observation:
        self._t = 0
        return Observation(frame_id=0, ts_ms=0, screen="dummy")

    def step(self, action: Action) -> StepResult:
        self._t += 1
        return StepResult(
            obs=Observation(frame_id=self._t, ts_ms=self._t * 10, screen="dummy"),
            reward=1.0,
            done=self._t >= 3,
        )

    def legal_actions(self) -> list[Action]:
        return [Action(kind=ActionKind.WAIT)]

    @property
    def episode_id(self) -> str:
        return "dummy-ep"


def test_loop_records_replay_and_stats() -> None:
    loop = AgentLoop(DummyEnv(), RandomPolicy(seed=0), max_steps=10)
    result = loop.run_episode()
    assert result.done is True
    assert loop.stats.steps == 3
    assert len(loop.replay) == 3
    assert loop.stats.episodes == 1
    assert loop.stats.percentile(95) >= 0.0
