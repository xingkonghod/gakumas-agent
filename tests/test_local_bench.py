"""本地 gkbench 跑分器（scripts/local_bench.py）的离线冒烟测试。

不联网、不跑真机；只验证：题集能解析成 LessonSim、UIObs 形状对、
greedy 同种子可复现、score 目标叶子按“当前分 + 预测分”计算。
"""

from __future__ import annotations

import copy
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import local_bench

PROBLEMS = local_bench.PROBLEMS_PATH
HIF_PROBLEMS = ROOT / "data" / "bench_local" / "problems_hif.json"
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


def _hif_like(
    base: dict,
    *,
    pid: str = "AS-HIFTEST",
    plan: str = "PLAN2",
    produce: str = "produce-008",
    round_: str = "mid1",
    step_type: int | None = 16,
    step_id: str | None = None,
    kind: str = "main",
    stage: str = "hif.main1",
) -> dict:
    """把一道 hajime 题改写成 H.I.F 编成（只用于测试映射，不猜真实数据）。"""
    raw = copy.deepcopy(base)
    raw["id"] = pid
    raw["name"] = f"hif-like-{pid}"
    raw["core"] = True
    scene = raw.setdefault("scene", {})
    scene.update({"kind": kind, "stage": stage, "exam": produce, "plan": plan, "round": round_})
    loadout = raw["archive"]["loadout"]
    loadout["schema"] = local_bench.HIF_SCHEMA
    loadout["produce_id"] = produce
    loadout["round"] = round_
    loadout["step_type"] = step_type
    loadout.pop("step_id", None)
    if step_id is not None:
        loadout["step_id"] = step_id
    return raw


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


def test_uiobs_fills_sim_zones_legal_and_status(first_spec) -> None:
    """LessonSim -> UIObs：合法动作用 sim.legal_actions 覆盖，已知 buff 进 status。"""
    sim = local_bench.LessonSim(
        list(first_spec.deck), first_spec.config, rng_seed=1000
    )
    sim.buffs.focus = 2
    sim.buffs.impression = 1
    sim.motivation = 3
    sim.buffs.condition_turns = 2
    sim.stance.full_power_point = 4
    sim.stance.stance = "save"
    sim.stance.save_level = 2
    obs = local_bench.sim_to_uiobs(sim, first_spec, decision=7, played=[])

    hand_legal = sorted(i for i in sim.legal_actions() if i is not None)
    expected_legal = [["play", index] for index in hand_legal]
    if None in sim.legal_actions():
        expected_legal.append(["end"])
    assert obs["legal"] == expected_legal
    assert [card["p"] for card in obs["hand"]] == [
        1 if index in hand_legal else 0 for index in range(len(sim.hand))
    ]
    assert obs["i"] == 7
    assert len(obs["deck"]) == len(sim.deck)
    assert obs["grave"] == [] and obs["lost"] == [] and obs["played"] == []
    assert obs["exam"]["types"] == [1] * sim.total_turns
    assert obs["exam"]["plan"] in {2, 3, 4}
    assert obs["stance"] == ["OverPreservation", 2]
    assert ["lesson_buff", 2.0, -1] in obs["status"]
    assert ["review", 1.0, -1] in obs["status"]
    assert ["aggressive", 3.0, -1] in obs["status"]
    assert ["full_power_point", 4.0, -1] in obs["status"]
    assert ["parameter_buff", 2.0, 2] in obs["status"]


def test_uinet_policy_only_returns_legal_actions(first_spec, monkeypatch) -> None:
    """UINet 的动作必须映射回当前合法动作；模型说 play/drink/end 各走各的。"""
    sim = local_bench.LessonSim(
        list(first_spec.deck), first_spec.config, rng_seed=1000
    )
    obs = local_bench.sim_to_uiobs(sim, first_spec, decision=0, played=[])
    policy = local_bench.UinetPolicy()

    def fake(action):
        return types.SimpleNamespace(action=tuple(action))

    monkeypatch.setattr(local_bench.uinet, "predict", lambda _obs: fake(["play", 0]))
    assert policy.decide(obs, sim) == ("play", 0)

    monkeypatch.setattr(local_bench.uinet, "predict", lambda _obs: fake(["end"]))
    assert policy.decide(obs, sim) == ("end", None)

    drink_obs = {**obs, "legal": [["drink", 0], ["end"]]}
    monkeypatch.setattr(local_bench.uinet, "predict", lambda _obs: fake(["drink", 0]))
    assert policy.decide(drink_obs, sim) == ("drink", 0)

    # 模型给了不在 legal 里的下标：退回贪心并计数，不能崩。
    monkeypatch.setattr(local_bench.uinet, "predict", lambda _obs: fake(["play", 99]))
    assert policy.decide(obs, sim) == local_bench._greedy_action(sim)
    assert policy.fallbacks == 1


def test_hif_problem_uses_loadout_produce_and_step(table, first_spec) -> None:
    """H.I.F：produce/step 来自题面 produce_id + step_type，不再按 round 猜。"""
    rows, index, refs = table
    raw = _hif_like(first_spec.raw, produce="produce-008", round_="mid1", step_type=16)
    spec = local_bench.build_problem(raw, rows, index, refs)
    assert spec.plan == "sense"
    assert spec.uinet_exam == ("produce-008", "AUDITION_MID1")
    assert spec.core is True

    sim = local_bench.LessonSim(list(spec.deck), spec.config, rng_seed=1000)
    obs = local_bench.sim_to_uiobs(sim, spec, decision=0, played=[])
    assert obs["exam"]["produce"] == "produce-008"
    assert obs["exam"]["step"] == "AUDITION_MID1"
    assert obs["exam"]["plan"] == 2


def test_hif_selection_final_keeps_produce_007(table, first_spec) -> None:
    """選抜試験的 final 是 produce-007 + AUDITION_FINAL，不能沿用旧 round 映射。"""
    rows, index, refs = table
    raw = _hif_like(
        first_spec.raw,
        plan="PLAN3",
        produce="produce-007",
        round_="final",
        step_type=18,
        kind="selection",
        stage="hif.sel3",
    )
    spec = local_bench.build_problem(raw, rows, index, refs)
    assert spec.plan == "logic"
    assert spec.uinet_exam == ("produce-007", "AUDITION_FINAL")


def test_hif_missing_step_type_falls_back_to_round(table, first_spec) -> None:
    rows, index, refs = table
    raw = _hif_like(first_spec.raw, round_="mid2", step_type=None)
    spec = local_bench.build_problem(raw, rows, index, refs)
    assert spec.uinet_exam == ("produce-008", "AUDITION_MID2")


def test_hif_free_plan_is_skipped_not_guessed(table, first_spec) -> None:
    """PLAN1=免费方案：LessonSim/UINet 都没有对应方案，跳过并给原因。"""
    rows, index, refs = table
    raw = _hif_like(first_spec.raw, plan="PLAN1")
    with pytest.raises(local_bench.UnmappableProblem) as exc:
        local_bench.build_problem(raw, rows, index, refs)
    assert "PLAN1" in exc.value.reason


def test_hif_step_type_id_conflict_is_skipped(table, first_spec) -> None:
    rows, index, refs = table
    raw = _hif_like(first_spec.raw, step_type=16, step_id="AuditionFinal")
    with pytest.raises(local_bench.UnmappableProblem) as exc:
        local_bench.build_problem(raw, rows, index, refs)
    assert "不一致" in exc.value.reason


def test_run_bench_counts_skipped_problems(table, first_spec, tmp_path: Path) -> None:
    raw_ok = _hif_like(first_spec.raw, pid="AS-HIFOK")
    raw_skip = _hif_like(first_spec.raw, pid="AS-HIFSKIP", plan="PLAN1")
    problems = tmp_path / "problems.json"
    problems.write_text(json.dumps([raw_ok, raw_skip], ensure_ascii=False), encoding="utf-8")
    summary = local_bench.run_bench(
        problems_path=problems,
        episodes=1,
        seed_base=1000,
        algo_names=["greedy"],
        budget_ms=300.0,
        limit=None,
        output=tmp_path / "out.json",
    )
    assert summary["problems"]["source_total"] == 2
    assert summary["problems"]["count"] == 1
    assert summary["problems"]["skipped_count"] == 1
    assert "PLAN1" in summary["problems"]["skipped"][0]["reason"]
    assert summary["algorithms"]["greedy"]["episodes"] == 1


def test_real_hif_file_all_problems_mapped_or_counted(table) -> None:
    """真实 H.I.F 落盘：每道题要么映射到 UINet 词表，要么按 PLAN1 跳过。"""
    if not HIF_PROBLEMS.exists():
        pytest.skip("缺少 data/bench_local/problems_hif.json")
    rows, index, refs = table
    problems = local_bench.load_problems(HIF_PROBLEMS)
    mapped = []
    skipped = []
    for raw in problems:
        try:
            mapped.append(local_bench.build_problem(raw, rows, index, refs))
        except local_bench.UnmappableProblem as exc:
            skipped.append(exc)
    assert len(mapped) + len(skipped) == len(problems)
    assert all("PLAN1" in exc.reason for exc in skipped)
    assert all(spec.uinet_exam[0] in local_bench.UINET_PRODUCES for spec in mapped)
    assert all(spec.uinet_exam[1] in set(local_bench.HIF_STEP_ID.values()) for spec in mapped)
    assert all(spec.plan in {"sense", "logic", "anomaly"} for spec in mapped)


def test_uinet_group_is_skipped_when_model_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """模型缺失：整组跳过并记录原因，其它算法照常跑完。"""
    monkeypatch.setenv("GKMS_UINET_MODEL", str(tmp_path / "missing.onnx"))
    reason = local_bench.uinet_skip_reason()
    assert reason is not None and "模型不存在" in reason
    with pytest.raises(local_bench.AlgorithmUnavailable):
        local_bench.make_algorithms(["uinet"], 300.0)

    out = tmp_path / "leaderboard.json"
    summary = local_bench.run_bench(
        problems_path=PROBLEMS,
        episodes=1,
        seed_base=1000,
        algo_names=["greedy", "uinet"],
        budget_ms=300.0,
        limit=1,
        output=out,
    )
    assert set(summary["algorithms"]) == {"greedy"}
    skipped = summary["skipped_algorithms"]
    assert skipped and skipped[0]["name"] == "uinet"
    assert "模型不存在" in skipped[0]["reason"]
    assert out.is_file()


# ---- P 道具数据接入（T5③）：loadout.produce_item_ids -> LessonConfig ---------

#: 真数据里一个「训练/考试开始时」P 道具（2026-09-16 主数据快照里有）
EXAM_START_ITEM_ID = "pitem_02-3-293-0"


def _hif_with_items(first_spec, item_ids: list[str]) -> dict:
    raw = _hif_like(first_spec.raw)
    raw["archive"]["loadout"]["produce_item_ids"] = list(item_ids)
    return raw


def test_hif_problem_resolves_p_items_from_loadout(table, first_spec) -> None:
    """loadout.produce_item_ids -> PItemSpec：已知 id 进 config，未知 id 显式上报。"""
    rows, index, refs = table
    raw = _hif_with_items(first_spec, [EXAM_START_ITEM_ID, "pitem_no-such-item-999"])
    spec = local_bench.build_problem(raw, rows, index, refs)
    stats = spec.p_item_stats
    assert stats.mode == "auto"
    assert (stats.ids, stats.known) == (2, 1)
    assert stats.unknown == ("pitem_no-such-item-999",)
    catalog = local_bench.get_catalog()
    assert stats.specs == len(catalog.specs_for(EXAM_START_ITEM_ID))
    assert stats.implemented > 0
    # 未知 id 不猜：config 里只有已知道具的 spec 段。
    assert len(spec.config.p_items) == stats.specs


def test_p_items_exam_start_effects_reach_lesson_sim(table, first_spec) -> None:
    """数据 -> 模拟器端到端：考试开始类 P 道具在 LessonSim 构造时结算。"""
    rows, index, refs = table
    raw = _hif_with_items(first_spec, [EXAM_START_ITEM_ID])
    spec = local_bench.build_problem(raw, rows, index, refs)
    resolved = local_bench.resolve_produce_item_ids([EXAM_START_ITEM_ID])

    def expected(target: str) -> int:
        return sum(
            item.value
            for item in resolved.specs
            if item.implemented and item.target == target
        )

    sim = local_bench.LessonSim(list(spec.deck), spec.config, rng_seed=1000)
    assert expected("vitality") > 0
    assert sim.vitality == expected("vitality")
    assert sim.motivation == expected("aggressive")


def test_p_items_off_mode_disables_them(table, first_spec) -> None:
    """--p-items off：A/B 对照用，不解析、不结算（行为与旧版逐位一致）。"""
    rows, index, refs = table
    raw = _hif_with_items(first_spec, [EXAM_START_ITEM_ID])
    spec = local_bench.build_problem(raw, rows, index, refs, p_items_mode="off")
    assert spec.config.p_items == ()
    assert spec.p_item_stats.mode == "off"
    assert spec.p_item_stats.ids == 0
    sim = local_bench.LessonSim(list(spec.deck), spec.config, rng_seed=1000)
    assert sim.vitality == 0 and sim.motivation == 0


def test_run_bench_reports_p_item_coverage(table, first_spec, tmp_path: Path) -> None:
    """跑分报告里 P 道具覆盖率非 0，且 off 模式为 0（同一道题对照）。"""
    if not HIF_PROBLEMS.exists():
        pytest.skip("缺少 data/bench_local/problems_hif.json")
    out = tmp_path / "leaderboard.json"
    summary = local_bench.run_bench(
        problems_path=HIF_PROBLEMS,
        episodes=1,
        seed_base=1000,
        algo_names=["greedy"],
        budget_ms=300.0,
        limit=1,
        output=out,
        p_items_mode="auto",
    )
    p_items = summary["p_items"]
    assert p_items["mode"] == "auto"
    assert p_items["problems_with_items"] == 1
    assert p_items["ids"] > 0 and p_items["known_ids"] > 0
    assert p_items["implemented_specs"] > 0
    assert summary["deck_modeling"]["p_items_modeled"] == p_items["implemented_specs"]
    assert json.loads(out.read_text(encoding="utf-8"))["p_items"]["implemented_specs"] > 0

    off = local_bench.run_bench(
        problems_path=HIF_PROBLEMS,
        episodes=1,
        seed_base=1000,
        algo_names=["greedy"],
        budget_ms=300.0,
        limit=1,
        output=tmp_path / "off.json",
        p_items_mode="off",
    )
    assert off["p_items"]["mode"] == "off"
    assert off["p_items"]["implemented_specs"] == 0
