"""B1 受控 policy-evaluation 叶子的回归测试。

覆盖：

* ``search_beam(frontier_value=...)`` 只在 beam 最深端点重排、终局端点不 rollout；
* 不给 ``frontier_value`` 时行为与历史逐位一致；
* ``scripts/eval_known_draw._execute_plan`` 不会在「手牌打空自动结束回合」后再补
  一个 SKIP（2026-11-22 B1 查出的评测 bug：旧实现每个 plan 白丢下一回合，导致
  T4 的 beam 数字被系统性低估）。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    ExpectState,
    search_beam,
)
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import eval_known_draw as ekd  # scripts 不是包，测试里按路径导入

SMALL = CardSpec("小分", 1, 5)
BIG = CardSpec("大分", 2, 20)


def _state(**kwargs) -> ExpectState:
    base = {
        "turns_left": 2,
        "total_turns": 2,
        "play_limit": 1,
        "stamina": 10,
        "clear": 10,
        "perfect": 1000,
    }
    base.update(kwargs)
    return ExpectState(**base)


class _FixedLeaf:
    """按分数返回固定效用的叶子，并记录被问过的状态。"""

    def __init__(self, score_fn=None) -> None:
        self.score_fn = score_fn or (lambda state: float(state.score))
        self.states: list[ExpectState] = []

    def utility(self, state: ExpectState) -> float:
        self.states.append(state)
        return self.score_fn(state)

    def predict(self, state: ExpectState) -> tuple[float, float]:
        return 0.0, 0.0


class _BoomLeaf:
    def utility(self, state: ExpectState) -> float:
        raise AssertionError("终局端点不应触发 policy-evaluation rollout")

    def predict(self, state: ExpectState) -> tuple[float, float]:
        return 0.0, 0.0


def test_frontier_value_reranks_root_plan() -> None:
    """能过 CLEAR 的大牌默认最优；前沿叶子偏爱小牌时根动作必须跟着换。"""
    state = _state(hand=(SMALL, BIG), deck=(), discard=())
    base = search_beam(
        state,
        AnalyticLeafValue(),
        width=3,
        depth=1,
        deadline_ms=2000,
        branching=3,
        rng=random.Random(0),
    )
    assert base.card is not None and base.card.name == "大分"

    prefers_small = _FixedLeaf(lambda frontier: 1.0 if frontier.score <= 5 else 0.0)
    reranked = search_beam(
        state,
        AnalyticLeafValue(),
        width=3,
        depth=1,
        deadline_ms=2000,
        branching=3,
        rng=random.Random(0),
        frontier_value=prefers_small,
    )
    assert reranked.depth_reached == 1
    assert reranked.card is not None and reranked.card.name == "小分"
    assert reranked.sequence[0] == "小分"
    assert len(prefers_small.states) == 3  # [skip, 小分, 大分] 三个前沿端点
    assert all(frontier.turns_left == 1 for frontier in prefers_small.states)


def test_frontier_value_skips_terminal_endpoints() -> None:
    """beam 跑到终局（turns_left=0）时用精确档位效用，不浪费 rollout。"""
    state = _state(hand=(BIG,), deck=(), discard=(), turns_left=1, total_turns=1)
    result = search_beam(
        state,
        AnalyticLeafValue(),
        width=2,
        depth=1,
        deadline_ms=2000,
        branching=2,
        rng=random.Random(0),
        frontier_value=_BoomLeaf(),
    )
    assert result.card is not None and result.card.name == "大分"
    assert result.depth_reached == 1


def test_frontier_value_none_keeps_history() -> None:
    """不传 frontier_value 与传等价的解析叶：结果逐位一致。"""
    state = _state(hand=(SMALL, BIG), deck=(), discard=())
    kwargs = {
        "width": 3,
        "depth": 1,
        "deadline_ms": 2000,
        "branching": 3,
        "rng": random.Random(0),
    }
    base = search_beam(state, AnalyticLeafValue(), **kwargs)
    explicit = search_beam(
        state,
        AnalyticLeafValue(),
        frontier_value=AnalyticLeafValue(),
        **kwargs,
    )
    assert base.card == explicit.card
    assert base.sequence == explicit.sequence
    assert base.utility == explicit.utility


def test_frontier_value_only_runs_at_deepest_layer() -> None:
    """3 回合状态只展开 1 层：只问前沿（turns_left=2），不碰根/中间层。"""
    state = _state(
        hand=(SMALL, BIG),
        deck=(BIG, SMALL, BIG, SMALL, BIG, SMALL),
        turns_left=3,
        total_turns=3,
    )
    counter = _FixedLeaf(lambda frontier: 0.0)
    search_beam(
        state,
        AnalyticLeafValue(),
        width=2,
        depth=1,
        deadline_ms=2000,
        branching=2,
        rng=random.Random(0),
        frontier_value=counter,
    )
    assert 1 <= len(counter.states) <= 2
    assert {frontier.turns_left for frontier in counter.states} == {2}


# ---------------------------------------------------------------- 评测执行器


def _sim(turns_left: int = 3) -> LessonSim:
    deck = [CardSpec(f"牌{i}", 1, 5) for i in range(6)]
    config = LessonConfig(
        turns=turns_left,
        stamina=20,
        target_clear=10,
        hand_size=3,
        plays_per_turn=3,
    )
    return LessonSim(deck, config, rng_seed=0)


def test_execute_plan_does_not_skip_next_turn_when_hand_empties() -> None:
    """打光当前手牌会自然结束回合，不能再补 SKIP 白丢下一回合。"""
    sim = _sim()
    names = [card.name for card in sim.hand]
    assert len(names) == 3
    ekd._execute_plan(sim, names)
    assert sim.turns_left == 2
    assert sim.score == 15
    assert len(sim.hand) == 3  # 下一回合的起手牌正常抽到


def test_execute_plan_ends_turn_once_for_short_plan() -> None:
    """计划没打光手牌：循环后补一次 SKIP 结束本回合，同样只推进一回合。"""
    sim = _sim()
    ekd._execute_plan(sim, [sim.hand[0].name])
    assert sim.turns_left == 2
    assert sim.score == 5
    assert len(sim.hand) == 3
