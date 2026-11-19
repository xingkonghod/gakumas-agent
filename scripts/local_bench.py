"""本地 gkbench 对比跑分器：同一批题、同一批种子、不同算法。

数据流（全程只在本地，不上传）：

1. ``data/bench_local/problems_hajime.json``：gkbench「初」题集 48 题
   （GET ``/api/sets/hajime/problems`` 落盘；题模板 + 固定种子题的公开元数据）。
2. 裁判：**我们自己的** ``LessonSim``（``gkagent.sim.lesson``）。gkbench 官方
   裁判是 GKMS native 引擎（rules 59），不在这台机器上；gkumas-tools 的
   ``gakumas-engine`` 只模拟 contest 舞台，不能跑 produce 考试（见
   ``tools/referee_cli.mjs`` 的自测与 unsupported 分支）。
3. 每个决策点把 UIObs v1（``sim_to_uiobs``）交给算法；算法返回
   ``play(i)`` / ``end``（当前没有建模饮料）。
4. 记录 ``score / step_ms / turns``，聚合均值、P50、P90、每步耗时、样本数。

**明确结论：分数与 gkbench 排行榜不可比。** 原因：
- 裁判不同：LessonSim 简化模型 vs gkbench 的 GKMS native（rules 59）；
- 种子不同：hajime 的 ``public_seeds=false``，``/api/sets/hajime/seeds`` 返回
  401，题集接口只给 ``exam_sha`` / ``fixed_id``，不给种子；这里用自选种子；
- 机制覆盖不全：卡牌定制（52/883 条）、饮料、P 道具、审查基准/属性回合、
  gimmick 未建模（详见输出的 ``deck_modeling`` 与 ``referee`` 字段）。

用法::

    .venv\\Scripts\\python.exe scripts\\local_bench.py --episodes 1
    .venv\\Scripts\\python.exe scripts\\local_bench.py --episodes 2 --limit 2
    .venv\\Scripts\\python.exe scripts\\local_bench.py --algos greedy,expectimax-analytic

``--episodes N`` = 每题 N 个种子（总局数 = 题数 × N × 算法数）。
所有算法共用同一组 ``(题, 种子)``。
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import re
import statistics
import sys
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sim_produce as sp  # 复用卡表 effects -> CardSpec 的成熟映射

from gkagent.sim.expectimax import (
    AnalyticLeafValue,
    expectimax_with_stats,
    state_from_sim,
)
from gkagent.sim.lesson import (
    CardSpec,
    LessonConfig,
    LessonSim,
    greedy_policy,
)
from gkagent.sim.v_leaf import EnsembleLeafValue, LinearLeafValue

PROBLEMS_PATH = ROOT / "data" / "bench_local" / "problems_hajime.json"
CARD_TABLE_PATH = ROOT / "data" / "knowledge" / "card_table.json"
V_LEAF_PATH = ROOT / "data" / "knowledge" / "v_leaf.json"
REPORT_PATH = ROOT / "data" / "bench_local" / "leaderboard.json"

MAX_STEPS = 2000
DEFAULT_BUDGET_MS = 300.0
DEFAULT_EPISODES = 1
DEFAULT_SEED_BASE = 1000

COMPARABILITY = (
    "不可比：裁判=我们的 LessonSim（非 gkbench GKMS native rules 59）；"
    "hajime 官方种子不公开（public_seeds=false，/api/sets/hajime/seeds 401）；"
    "本跑分用自选种子，且卡牌定制/饮料/P 道具/审查基准回合未建模。"
    "只能作本地同题同种子的相对排名。"
)

MECHANIC_TO_PLAN = {"aggressive": "sense", "full_power": "logic", "stance": "anomaly"}
PLAN_CODE = {"sense": 2, "logic": 3, "anomaly": 4}

_DECK_RE = re.compile(r"^(p_card-[^+/]+)(?:\+(\d+))?(?:/(.+))?$")


# ------------------------------------------------------------------ 基础结构
@dataclass(frozen=True)
class DeckStats:
    entries: int
    unresolved: int
    customized: int
    effect_count: int
    modeled_effect_count: int
    unmodeled_types: tuple[str, ...]


@dataclass(frozen=True)
class ProblemSpec:
    """一道题转换到 LessonSim 的静态部分（牌组/配置/统计）。"""

    pid: str
    name: str
    kind: str
    stage: str
    raw: dict[str, Any]
    deck: tuple[CardSpec, ...]
    config: LessonConfig
    deck_stats: DeckStats
    refs: Mapping[str, tuple[str, int]]


@dataclass
class EpisodeResult:
    problem: str
    kind: str
    seed: int
    algo: str
    score: int
    finished: bool
    turns: int
    decisions: int
    step_ms: list[float]
    route: list[str]
    fallbacks: int
    incomplete: int
    wall_s: float


@dataclass
class AlgorithmRun:
    """一个算法的全部对局与计数器。"""

    name: str
    label: str
    episodes: list[EpisodeResult] = field(default_factory=list)
    fallbacks: int = 0
    incomplete: int = 0
    decisions: int = 0

    def add(self, episode: EpisodeResult) -> None:
        self.episodes.append(episode)
        self.fallbacks += episode.fallbacks
        self.incomplete += episode.incomplete
        self.decisions += episode.decisions


# ------------------------------------------------------------------ 题/牌表
def load_problems(path: Path = PROBLEMS_PATH) -> list[dict[str, Any]]:
    """读题集 JSON；兼容直接给数组或 ``{"problems": [...]}`` 两种落盘。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("problems") or payload.get("items") or []
    else:
        rows = payload
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"题集为空或格式不对：{path}")
    return rows


def load_card_table(
    path: Path = CARD_TABLE_PATH,
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, int], str], dict[str, tuple[str, int]]]:
    """返回 ``(name -> 卡表行, (id, 强化) -> name, name -> (id, 强化))``。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    cards = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(cards, dict):
        raise SystemExit(f"卡表格式不对（缺 cards）：{path}")
    rows = {name: row for name, row in cards.items() if isinstance(row, dict)}
    index: dict[tuple[str, int], str] = {}
    refs: dict[str, tuple[str, int]] = {}
    for name, row in rows.items():
        card_id = row.get("id")
        if not card_id:
            continue
        upgrade = int(row.get("upgrade") or 0)
        index.setdefault((str(card_id), upgrade), name)
        refs.setdefault(name, (str(card_id), upgrade))
    return rows, index, refs


def parse_deck_entry(entry: str) -> tuple[str, int, str | None] | None:
    """``p_card-…+2/定制…`` -> ``(基础卡号, 强化次数, 定制串或 None)``。"""
    match = _DECK_RE.match(str(entry).strip())
    if match is None:
        return None
    return match.group(1), int(match.group(2) or 0), match.group(3)


def build_problem(
    raw: dict[str, Any],
    card_rows: Mapping[str, dict[str, Any]],
    card_index: Mapping[tuple[str, int], str],
    refs: Mapping[str, tuple[str, int]],
) -> ProblemSpec:
    """一道 gkbench 题 -> LessonSim 静态配置。"""
    archive = raw.get("archive") or {}
    loadout = archive.get("loadout") or {}
    scene = raw.get("scene") or {}
    pid = str(raw.get("id") or archive.get("id") or "?")
    kind = str(scene.get("kind") or loadout.get("round") or "?")
    stage = str(scene.get("stage") or loadout.get("step_id") or "")

    deck: list[CardSpec] = []
    effect_count = 0
    modeled_effects = 0
    unmodeled: Counter[str] = Counter()
    unresolved = 0
    customized = 0
    for entry in loadout.get("deck_cards") or []:
        parsed = parse_deck_entry(str(entry))
        if parsed is None:
            unresolved += 1
            continue
        card_id, upgrade, customization = parsed
        if customization:
            customized += 1
        name = card_index.get((card_id, upgrade))
        row = card_rows.get(name) if name is not None else None
        if name is None or row is None:
            unresolved += 1
            continue
        fields = sp._effect_fields(row)
        cost = int(row.get("cost") or 0)
        deck.append(sp._spec_from_row(sp._rich_row(name, cost, fields)))
        for effect in row.get("effects") or []:
            effect_type = str(effect.get("type") or "")
            effect_count += 1
            if effect_type in sp.MODELED_EFFECTS:
                modeled_effects += 1
            else:
                unmodeled[str(effect_type)] += 1

    if not deck:
        raise SystemExit(f"题 {pid} 的牌组一张都解析不出来")

    turns = int(scene.get("turns") or 8)
    stamina = int(loadout.get("starting_stamina") or 30)
    stamina_max = int(loadout.get("max_stamina") or stamina)
    plan = MECHANIC_TO_PLAN.get(str(scene.get("mechanic") or ""), "sense")
    config = LessonConfig(
        turns=turns,
        stamina=stamina,
        # gkbench 按原始分数排名，没有 CLEAR/PERFECT 线；这里只给 LessonSim
        # 的内部档位一个下限，跑分器只用 score。
        target_clear=1,
        target_perfect=2,
        hand_size=3,
        plays_per_turn=3,
        stamina_max=stamina_max,
        plan=plan,
    )
    stats = DeckStats(
        entries=len(loadout.get("deck_cards") or []),
        unresolved=unresolved,
        customized=customized,
        effect_count=effect_count,
        modeled_effect_count=modeled_effects,
        unmodeled_types=tuple(sorted(unmodeled)),
    )
    return ProblemSpec(
        pid=pid,
        name=str(raw.get("name") or pid),
        kind=kind,
        stage=stage,
        raw=raw,
        deck=tuple(deck),
        config=config,
        deck_stats=stats,
        refs=refs,
    )


# ------------------------------------------------------------------ UIObs
def _zone(zone: Any, refs: Mapping[str, tuple[str, int]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for card in zone or ():
        ref = refs.get(card.name)
        if ref is not None:
            out.append({"id": ref[0], "u": ref[1]})
    return out


def sim_to_uiobs(
    sim: LessonSim,
    spec: ProblemSpec,
    *,
    decision: int,
    played: list[CardSpec],
) -> dict[str, Any]:
    """当前 LessonSim 局面 -> UIObs v1（算法只看这个观测）。

    缺口按 UIObs 的保守默认：``types`` 全 1（逐回合属性不在题模板里）、
    ``status``/``ench``/``drinks`` 空（LessonSim 不建模饮料/附魔）、
    ``hold`` 空、``g`` 为 0（卡牌成长不建模）。
    """
    loadout = (spec.raw.get("archive") or {}).get("loadout") or {}
    scene = spec.raw.get("scene") or {}
    limit = max(int(sim.total_turns), 1)
    legal_slots = sim.legal_actions()
    hand_legal = {index for index in legal_slots if index is not None}
    hand: list[dict[str, Any]] = []
    for index, card in enumerate(sim.hand):
        ref = spec.refs.get(card.name)
        if ref is None:
            hand.append({"id": "", "u": 0, "g": 0, "p": 0})
            continue
        hand.append(
            {"id": ref[0], "u": ref[1], "g": 0, "p": 1 if index in hand_legal else 0}
        )
    legal: list[list[Any]] = [["play", index] for index in sorted(hand_legal)]
    if None in legal_slots:
        legal.append(["end"])
    permil = loadout.get("score_bonus_permils") or [1000, 1000, 1000]
    crit = loadout.get("parameters") or [0, 0, 0]
    plan = MECHANIC_TO_PLAN.get(str(scene.get("mechanic") or ""), "sense")
    return {
        "v": "uiobs.v1",
        "i": decision,
        "exam": {
            "produce": str(loadout.get("produce_id") or scene.get("exam") or ""),
            "step": str(loadout.get("step_id") or loadout.get("step_type") or scene.get("stage") or ""),
            "plan": PLAN_CODE[plan],
            "turn": int(sim.current_turn),
            "limit": limit,
            "types": [1] * limit,
            "permil": [int(value) for value in permil][:3],
            "crit": [int(value) for value in crit][:3],
        },
        "num": {
            "score": int(sim.score),
            "stamina": int(sim.stamina),
            "max_stamina": int(sim.stamina_max),
            "block": int(sim.vitality),
            "playable": max(0, int(sim.plays_per_turn + sim.extra_plays - sim.plays_this_turn)),
            "plays": int(sim.plays_this_turn),
        },
        "stance": [str(sim.stance.stance), int(sim.stance.strong_level)],
        "status": [],
        "ench": [],
        "hand": hand,
        "deck": _zone(sim.deck, spec.refs),
        "grave": _zone(sim.discard, spec.refs),
        "hold": [],
        "lost": _zone(sim.excluded, spec.refs),
        "played": _zone(played, spec.refs),
        "drinks": [],
        "legal": legal,
    }


# ------------------------------------------------------------------ 算法
@dataclass(frozen=True)
class ScoreObjectiveLeaf:
    """把 ``AnalyticLeafValue.predict`` 的 μ 当未来分，效用 = 当前分 + μ。

    gkbench 只按原始分数排名，没有 CLEAR/PERFECT 线；直接用
    ``AnalyticLeafValue.utility``（档位概率）在无阈值时会退化成常数，搜索会
    学不到任何东西。这里保留 analytic / ensemble 的 **预测**，只换目标函数。
    """

    inner: Any

    def predict(self, state: Any) -> tuple[float, float]:
        return self.inner.predict(state)

    def utility(self, state: Any) -> float:
        mean, _sigma = self.inner.predict(state)
        return float(state.score) + float(mean)


def _greedy_action(sim: LessonSim) -> tuple[str, int | None]:
    index = greedy_policy(sim)
    if index is None:
        return ("end", None)
    return ("play", int(index))


def _hand_index(sim: LessonSim, card: CardSpec) -> int | None:
    for index, candidate in enumerate(sim.hand):
        if candidate == card:
            return index
    return None


class GreedyPolicy:
    """直接调用 ``greedy_policy``；不做搜索。"""

    name = "greedy"
    label = "greedy"

    def __init__(self, *_args: Any) -> None:
        self.fallbacks = 0
        self.incomplete = 0

    def decide(self, _obs: dict[str, Any], sim: LessonSim) -> tuple[str, int | None]:
        return _greedy_action(sim)


class ExpectimaxPolicy:
    """回合内 expectimax（``expectimax_with_stats``）+ 超时贪心回退。

    每一步给 ``budget_ms`` 毫秒；搜索未完成（``complete=False``）时退回
    ``greedy_policy``，并记录 fallback。这样在 0 费过牌很多、机会节点爆炸的
    牌组上不会退化成“整局 SKIP”。
    """

    def __init__(
        self,
        *,
        name: str,
        label: str,
        leaf: Any,
        budget_ms: float,
    ) -> None:
        self.name = name
        self.label = label
        self.leaf = leaf
        self.budget_ms = float(budget_ms)
        self.fallbacks = 0
        self.incomplete = 0
        self.completed = 0

    def decide(self, _obs: dict[str, Any], sim: LessonSim) -> tuple[str, int | None]:
        result = expectimax_with_stats(
            state_from_sim(sim), self.leaf, time_budget_ms=self.budget_ms
        )
        if result.complete:
            self.completed += 1
            if result.drink is not None:
                return ("drink", int(result.drink))
            if result.card is None:
                return ("end", None)
            index = _hand_index(sim, result.card)
            if index is not None:
                return ("play", index)
            # 模型/画面分歧：退回贪心，不抛错
            self.fallbacks += 1
            return _greedy_action(sim)
        self.incomplete += 1
        self.fallbacks += 1
        return _greedy_action(sim)


@functools.cache
def make_leaf(name: str) -> Any:
    """按算法名构造（并缓存）叶子估值；模型只加载一次。"""
    if name == "expectimax-analytic":
        return ScoreObjectiveLeaf(AnalyticLeafValue())
    if name == "expectimax-ensemble":
        if not V_LEAF_PATH.exists():
            raise SystemExit(f"ensemble 需要 {V_LEAF_PATH}（learned V_leaf）")
        return ScoreObjectiveLeaf(
            EnsembleLeafValue(
                primary=AnalyticLeafValue(),
                secondary=LinearLeafValue.load(V_LEAF_PATH),
                weight=0.5,
            )
        )
    raise SystemExit(f"没有叶子估值：{name}")


def make_algorithms(names: list[str], budget_ms: float) -> list[GreedyPolicy | ExpectimaxPolicy]:
    """按名字构造算法实例（每个算法独立计数）。"""
    out: list[GreedyPolicy | ExpectimaxPolicy] = []
    for name in names:
        if name == "greedy":
            out.append(GreedyPolicy())
        elif name in ("expectimax-analytic", "expectimax-ensemble"):
            label = {
                "expectimax-analytic": "expectimax(analytic)",
                "expectimax-ensemble": "expectimax(ensemble)",
            }[name]
            out.append(
                ExpectimaxPolicy(
                    name=name,
                    label=label,
                    leaf=make_leaf(name),
                    budget_ms=budget_ms,
                )
            )
        else:
            raise SystemExit(
                f"未知算法 {name!r}；可选 greedy / expectimax-analytic / expectimax-ensemble"
            )
    return out


# ------------------------------------------------------------------ 跑一局
def run_episode(spec: ProblemSpec, seed: int, policy: Any) -> EpisodeResult:
    """同题同种子跑一局；返回该局的分数/每步耗时/路线。"""
    sim = LessonSim(list(spec.deck), spec.config, rng_seed=seed)
    step_ms: list[float] = []
    route: list[str] = []
    played: list[CardSpec] = []
    decisions = 0
    fallbacks = 0
    started = time.perf_counter()
    while not sim.done:
        obs = sim_to_uiobs(sim, spec, decision=decisions, played=played)
        began = time.perf_counter()
        action, target = policy.decide(obs, sim)
        elapsed_ms = (time.perf_counter() - began) * 1000.0
        step_ms.append(float(elapsed_ms))
        legal = obs["legal"]
        if action == "drink":
            # 当前题/裁判没有建模饮料；真出现只能说明模型分歧，按贪心回退。
            action, target = _greedy_action(sim)
            fallbacks += 1
        if action == "play":
            index = int(target) if target is not None else -1
            if ["play", index] not in legal:
                fallbacks += 1
                action, target = _greedy_action(sim)
                index = int(target) if target is not None else -1
            if index < 0 or index >= len(sim.hand):
                raise RuntimeError(f"{spec.pid} seed={seed}: 非法出牌下标 {index}")
            played.append(sim.hand[index])
            route.append(f"p{index}")
            sim.step(index)
        else:
            if ["end"] not in legal:
                raise RuntimeError(f"{spec.pid} seed={seed}: 回合无法结束（legal={legal}）")
            route.append("e")
            sim.step(None)
        decisions += 1
        if decisions > MAX_STEPS:
            raise RuntimeError(f"{spec.pid} seed={seed}: 超过 {MAX_STEPS} 步未结束")
    wall_s = time.perf_counter() - started
    return EpisodeResult(
        problem=spec.pid,
        kind=spec.kind,
        seed=seed,
        algo=policy.name,
        score=int(sim.score),
        finished=sim.turns_left <= 0,
        turns=int(sim.current_turn),
        decisions=decisions,
        step_ms=step_ms,
        route=route,
        fallbacks=fallbacks + int(getattr(policy, "fallbacks", 0)),
        incomplete=int(getattr(policy, "incomplete", 0)),
        wall_s=wall_s,
    )


# ------------------------------------------------------------------ 聚合/输出
def _percentile(values: list[float], pct: float) -> float:
    """nearest-rank 百分位（空列表返回 0）。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return float(ordered[min(rank - 1, len(ordered) - 1)])


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p90": 0.0}
    return {
        "mean": float(statistics.fmean(values)),
        "p50": _percentile(values, 50),
        "p90": _percentile(values, 90),
    }


def algorithm_summary(run: AlgorithmRun) -> dict[str, Any]:
    scores = [episode.score for episode in run.episodes]
    steps = [ms for episode in run.episodes for ms in episode.step_ms]
    step_summary = _summary(steps)
    return {
        "name": run.name,
        "label": run.label,
        "episodes": len(run.episodes),
        "mean": round(float(statistics.fmean(scores)), 3) if scores else 0.0,
        "p50": _percentile([float(v) for v in scores], 50),
        "p90": _percentile([float(v) for v in scores], 90),
        "min": min(scores) if scores else 0,
        "max": max(scores) if scores else 0,
        "turns_mean": round(
            float(statistics.fmean([episode.turns for episode in run.episodes])), 2
        )
        if run.episodes
        else 0.0,
        "finished_rate": round(
            sum(1 for episode in run.episodes if episode.finished) / len(run.episodes), 4
        )
        if run.episodes
        else 0.0,
        "decisions": run.decisions,
        "decisions_per_episode": round(run.decisions / len(run.episodes), 2)
        if run.episodes
        else 0.0,
        "fallbacks": run.fallbacks,
        "fallback_rate": round(run.fallbacks / run.decisions, 4) if run.decisions else 0.0,
        "incomplete": run.incomplete,
        "step_ms_mean": round(step_summary["mean"], 3),
        "step_ms_p50": round(step_summary["p50"], 3),
        "step_ms_p90": round(step_summary["p90"], 3),
        "wall_s": round(sum(episode.wall_s for episode in run.episodes), 3),
    }


def episode_summary(episode: EpisodeResult) -> dict[str, Any]:
    """逐局记录（score / turns / step_ms / fallback），便于复核。"""
    steps = _summary(episode.step_ms)
    return {
        "problem": episode.problem,
        "kind": episode.kind,
        "seed": episode.seed,
        "algo": episode.algo,
        "score": episode.score,
        "finished": episode.finished,
        "turns": episode.turns,
        "decisions": episode.decisions,
        "fallbacks": episode.fallbacks,
        "incomplete": episode.incomplete,
        "step_ms_mean": round(steps["mean"], 3),
        "step_ms_p50": round(steps["p50"], 3),
        "step_ms_p90": round(steps["p90"], 3),
        "wall_s": round(episode.wall_s, 3),
        "route": " ".join(episode.route),
    }


def per_problem_summary(runs: list[AlgorithmRun]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, list[int]]] = {}
    for run in runs:
        for episode in run.episodes:
            grouped.setdefault(episode.problem, {}).setdefault(run.name, []).append(
                episode.score
            )
    out: dict[str, dict[str, Any]] = {}
    for pid, by_algo in grouped.items():
        out[pid] = {
            algo: round(float(statistics.fmean(scores)), 3)
            for algo, scores in by_algo.items()
        }
    return out


def run_bench(
    *,
    problems_path: Path,
    episodes: int,
    seed_base: int,
    algo_names: list[str],
    budget_ms: float,
    limit: int | None,
    output: Path,
) -> dict[str, Any]:
    card_rows, card_index, refs = load_card_table()
    raw_problems = load_problems(problems_path)
    if limit is not None:
        raw_problems = raw_problems[: max(int(limit), 0)]
    specs = [build_problem(raw, card_rows, card_index, refs) for raw in raw_problems]
    if not specs:
        raise SystemExit("没有可跑的题")
    seeds = [int(seed_base) + index for index in range(max(int(episodes), 1))]

    runs: list[AlgorithmRun] = [
        AlgorithmRun(name=policy.name, label=policy.label)
        for policy in make_algorithms(algo_names, budget_ms)
    ]
    for spec in specs:
        for seed in seeds:
            for run in runs:
                policy = make_algorithms([run.name], budget_ms)[0]
                episode = run_episode(spec, seed, policy)
                run.add(episode)
                print(
                    f"  {spec.pid} seed={seed} {run.label}: score={episode.score} "
                    f"steps={episode.decisions} {episode.wall_s:.2f}s",
                    file=sys.stderr,
                )
        print(f"[{spec.pid}] {spec.kind} 完成", file=sys.stderr)

    algorithms = [algorithm_summary(run) for run in runs]
    deck_entries = sum(spec.deck_stats.entries for spec in specs)
    deck_unresolved = sum(spec.deck_stats.unresolved for spec in specs)
    deck_customized = sum(spec.deck_stats.customized for spec in specs)
    effects = sum(spec.deck_stats.effect_count for spec in specs)
    modeled_effects = sum(spec.deck_stats.modeled_effect_count for spec in specs)
    unmodeled = Counter(
        effect for spec in specs for effect in spec.deck_stats.unmodeled_types
    )
    kinds: Counter[str] = Counter(spec.kind for spec in specs)
    summary: dict[str, Any] = {
        "schema": "gkagent.local_bench.v1",
        "generated_at": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "referee": {
            "name": "LessonSim",
            "module": "gkagent.sim.lesson",
            "official_gkbench_referee": False,
            "gkbench_referee": "GKMS native（rules 59，不在本机；gkumas-tools 只支持 contest）",
            "score_comparable_to_gkbench_leaderboard": False,
        },
        "comparability": COMPARABILITY,
        "problems": {
            "path": str(problems_path.relative_to(ROOT)) if problems_path.is_relative_to(ROOT) else str(problems_path),
            "count": len(specs),
            "kinds": dict(sorted(kinds.items())),
            "ids": [spec.pid for spec in specs],
        },
        "seeds": seeds,
        "seeds_per_problem": len(seeds),
        "episodes_per_algo": len(specs) * len(seeds),
        "budget_ms": float(budget_ms),
        "deck_modeling": {
            "deck_entries": deck_entries,
            "unresolved_entries": deck_unresolved,
            "customized_entries_ignored": deck_customized,
            "effects": effects,
            "modeled_effects": modeled_effects,
            "modeled_effect_rate": round(modeled_effects / effects, 4) if effects else 0.0,
            "unmodeled_types": dict(sorted(unmodeled.items())),
            "drinks_modeled": 0,
            "p_items_modeled": 0,
        },
        "algorithms": {row["name"]: row for row in algorithms},
        "episodes": [
            episode_summary(episode)
            for run in runs
            for episode in run.episodes
        ],
        "per_problem": per_problem_summary(runs),
        "output": str(output),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="本地 gkbench 对比跑分（LessonSim 裁判）")
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES, help="每题种子数")
    parser.add_argument("--seed-base", type=int, default=DEFAULT_SEED_BASE, help="第一个种子")
    parser.add_argument(
        "--algos",
        default="greedy,expectimax-analytic,expectimax-ensemble",
        help="逗号分隔：greedy / expectimax-analytic / expectimax-ensemble",
    )
    parser.add_argument("--budget-ms", type=float, default=DEFAULT_BUDGET_MS, help="expectimax 每步预算")
    parser.add_argument("--problems", type=Path, default=PROBLEMS_PATH, help="题集 JSON")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（调试）")
    parser.add_argument("--out", type=Path, default=REPORT_PATH, help="排行榜 JSON 输出")
    args = parser.parse_args(argv)

    algo_names = [name.strip() for name in args.algos.split(",") if name.strip()]
    # 先验证算法名/依赖，避免跑完才报错
    make_algorithms(algo_names, args.budget_ms)
    summary = run_bench(
        problems_path=args.problems,
        episodes=args.episodes,
        seed_base=args.seed_base,
        algo_names=algo_names,
        budget_ms=args.budget_ms,
        limit=args.limit,
        output=args.out,
    )
    print("=" * 92)
    print("裁判 = 我们的模拟器 LessonSim（不是 gkbench 的 GKMS 引擎）")
    print("分数与他们排行榜不可比：裁判/种子/机制覆盖都不同（详见 leaderboard.json）")
    print("=" * 92)
    kinds = summary["problems"]["kinds"]
    print(
        f"题目 {summary['problems']['count']} 题（"
        + " / ".join(f"{kind} {count}" for kind, count in kinds.items())
        + f"），每题 {summary['seeds_per_problem']} 个种子，"
        f"种子 {summary['seeds'][0]}..{summary['seeds'][-1]}（自选）"
    )
    header = (
        f"{'算法':24s} {'局数':>4s} {'均值':>9s} {'P50':>7s} {'P90':>7s} "
        f"{'每步均值ms':>11s} {'每步P50':>8s} {'fallback':>9s}"
    )
    print(header)
    print("-" * len(header))
    for name in algo_names:
        row = summary["algorithms"][name]
        print(
            f"{row['label']:24s} {row['episodes']:4d} {row['mean']:9.1f} {row['p50']:7.1f} "
            f"{row['p90']:7.1f} {row['step_ms_mean']:11.2f} {row['step_ms_p50']:8.2f} "
            f"{row['fallback_rate'] * 100:8.1f}%"
        )
    print("-" * len(header))
    if "greedy" in summary["algorithms"]:
        base = summary["algorithms"]["greedy"]["mean"]
        for name in algo_names:
            if name == "greedy":
                continue
            mean = summary["algorithms"][name]["mean"]
            delta = mean - base
            suffix = f"{delta / base:+.1%}" if base else "n/a"
            print(f"  {summary['algorithms'][name]['label']} vs greedy: {delta:+.1f} 分（{suffix}）")
    print(f"\nJSON: {args.out}")
    print(f"可比性：{COMPARABILITY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
