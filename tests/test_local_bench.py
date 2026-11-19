"""本地 gkbench 跑分器（scripts/local_bench.py）的离线冒烟测试。

不联网、不跑真机；只验证：题集能解析成 LessonSim、UIObs 形状对、
greedy 同种子可复现、score 目标叶子按“当前分 + 预测分”计算。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import local_bench

PROBLEMS = local_bench.PROBLEMS_PATH
CARD_TABLE = local_bench.CARD_TABLE_PATH


@pytest.fixture(scope="module")
def table():
    if not CARD_TABLE.exists():
        pytest.skip("缺少 data/knowledge/card_table.json")
    return local_bench.load_card_table()


@pytest.fixture(scope="module")
def first_spec(table):
    if not PROBLEMS.exists():
        pytest.skip("缺少 data/bench_local/problems_hajime.json")
    rows, index, refs = table
    problems = local_bench.load_problems()
    return local_bench.build_problem(problems[0], rows, index, refs)


def test_problem_builds_deck_and_stats(first_spec) -> None:
    assert first_spec.deck, "牌组不应为空"
    assert first_spec.deck_stats.unresolved == 0
    assert first_spec.deck_stats.entries >= len(first_spec.deck)
    assert first_spec.config.turns == int(first_spec.raw["scene"]["turns"])
    assert first_spec.kind in {"lesson", "mid", "final"}


def test_uiobs_shape_and_legal(first_spec) -> None:
    sim = local_bench.LessonSim(
        list(first_spec.deck), first_spec.config, rng_seed=1000
    )
    obs = local_bench.sim_to_uiobs(sim, first_spec, decision=0, played=[])
    assert obs["v"] == "uiobs.v1"
    assert obs["i"] == 0
    assert len(obs["hand"]) == len(sim.hand)
    assert obs["num"]["score"] == sim.score
    assert obs["num"]["stamina"] == sim.stamina
    assert obs["exam"]["turn"] == sim.current_turn
    assert obs["exam"]["limit"] == sim.total_turns
    assert isinstance(obs["legal"], list) and obs["legal"]
    for action in obs["legal"]:
        assert action[0] in {"play", "end"}


def test_greedy_episode_same_seed_reproducible(first_spec) -> None:
    first = local_bench.run_episode(first_spec, 1000, local_bench.GreedyPolicy())
    second = local_bench.run_episode(first_spec, 1000, local_bench.GreedyPolicy())
    assert first.score == second.score
    assert first.route == second.route
    assert first.decisions == second.decisions


def test_score_objective_leaf_is_total_score() -> None:
    class _Inner:
        def predict(self, _state):
            return (12.5, 1.0)

    class _State:
        score = 7

    leaf = local_bench.ScoreObjectiveLeaf(_Inner())
    assert leaf.utility(_State()) == pytest.approx(19.5)
