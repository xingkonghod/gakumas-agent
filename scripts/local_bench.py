"""本地 gkbench 对比跑分器：同一批题、同一批种子、不同算法。

数据流（全程只在本地，不上传）：

1. 题集：``--problems <path>`` 切换，默认 ``data/bench_local/problems_hajime.json``
   （gkbench「初」题集 48 题；GET ``/api/sets/hajime/problems`` 落盘）。
   H.I.F 题集在 ``data/bench_local/problems_hif.json``（GET
   ``/api/sets/hif/problems``，505 题）。
2. 裁判：**我们自己的** ``LessonSim``（``gkagent.sim.lesson``）。gkbench 官方
   裁判是 GKMS native 引擎（rules 59），不在这台机器上；gkumas-tools 的
   ``gakumas-engine`` 只模拟 contest 舞台，不能跑 produce 考试（见
   ``tools/referee_cli.mjs`` 的自测与 unsupported 分支）。
3. 每个决策点把 UIObs v1（``sim_to_uiobs``，底层复用
   ``gkagent.sim.uiobs.to_uiobs``）交给算法；算法返回 ``play(i)`` /
   ``end``（当前裁判没有建模饮料，UINet 若选 ``drink`` 按贪心回退）。
4. 记录 ``score / step_ms / turns``，聚合均值、P50、P90、每步耗时、样本数。

**题集结构差异（实测，不靠猜）**：

- hajime 的 ``archive.loadout`` 与 H.I.F 大体同构（``deck_cards`` /
  ``starting_stamina`` / ``max_stamina`` / ``parameters`` /
  ``score_bonus_permils`` / ``round``），H.I.F 额外有 ``step_type`` /
  ``step_id`` / ``produce_id`` 以及 H.I.F 专属附魔/回忆/研究卡字段；
- H.I.F 的 ``loadout.produce_id`` 直接就是 UINet 词表里的 produce-007/008，
  不再按 round 猜；``loadout.step_type`` 16/17/18 与 ``step_id``
  AuditionMid1/Mid2/Final 在数据里一一对应，缺 ``step_type`` 的题用 round 兜底
  （两条规则在所有同时有值的题上一致）；
- ``scene.plan`` 只接受 PLAN2/3/4（sense/logic/anomaly）。PLAN1 是免费方案
  （deck 里是 ``p_card-01-*``），LessonSim 与 UINet 的考试方案词表都没有它，
  整题跳过并在 ``problems.skipped`` 里记原因，**不猜映射**；
- ``--limit`` / ``--sample`` 都在“可映射题”上取子集；``--sample`` 是固定种子的
  随机抽样，避免 ``--limit`` 只取到题集开头某一种场景。

**UINet（``uinet`` 算法）的观测缺口**（详见 ``sim_to_uiobs`` 的 docstring）：

- LessonSim 没有逐回合属性（``exam.types`` 一律保守填 1=Vo）；
- 饮料 M6 opt-in（``--drinks auto``，**默认 off 逐位不变**）：``loadout.drink_ids`` →
  ``LessonConfig.drinks`` 效果段结算（sim/drinks.py，29 瓶/51 段/33 实现）；
  附魔/保留区仍空（P 道具已从 loadout 接入，见 ``--p-items``）；
- 卡牌定制不建模，``c``/``g`` 省略；
- hajime 的 produce 是 produce-001/006（33/48 是 lesson），不在 UINet 词表里，
  只能按 round 映射到最接近的 H.I.F 枚举；**H.I.F 题集则直接使用题面自带的
  produce-007/008 + step_type/step_id**，这是 UINet 的训练分布。
- 模型/主数据/``gkms_uinet``/``onnxruntime`` 缺失时 **整组跳过** 并打印原因，
  不影响其它算法。

**明确结论：分数与 gkbench 排行榜不可比。** 原因：
- 裁判不同：LessonSim 简化模型 vs gkbench 的 GKMS native（rules 59）；
- 种子不同：hajime 的 ``public_seeds=false``，``/api/sets/hajime/seeds`` 返回
  401，题集接口只给 ``exam_sha`` / ``fixed_id``，不给种子；这里用自选种子；
  H.I.F 同理，用 ``--seed-base`` 起的自选种子；
- 机制覆盖不全：卡牌定制、饮料、逐回合属性/审查基准回合、gimmick 未建模，
  P 道具按 ``loadout.produce_item_ids`` 接入且只实现语义确定的效果类型
  （详见输出的 ``p_items`` / ``deck_modeling`` 与 ``referee`` 字段）。
- H.I.F 题集把 produce/step/plan/deck/parameters/permil 都放进了 UINet 的训练
  词表，但裁判仍是 LessonSim，分值尺度与真实 GKMS 不同。

用法::

    .venv\\Scripts\\python.exe scripts\\local_bench.py --episodes 1
    .venv\\Scripts\\python.exe scripts\\local_bench.py --episodes 2 --limit 2
    .venv\\Scripts\\python.exe scripts\\local_bench.py --algos greedy,uinet,expectimax-ensemble
    .venv\\Scripts\\python.exe scripts\\local_bench.py --problems data\\bench_local\\problems_hif.json
    .venv\\Scripts\\python.exe scripts\\local_bench.py --problems data\\bench_local\\problems_hif.json --sample 60 --episodes 2
    # P 道具 A/B 对照（auto=按 loadout 接入，off=不结算）：
    .venv\\Scripts\\python.exe scripts\\local_bench.py --problems data\\bench_local\\problems_hif.json --sample 30 --episodes 2 --p-items off

``--episodes N`` = 每题 N 个种子（总局数 = 题数 × N × 算法数）。
所有算法共用同一组 ``(题, 种子)``。``--sample N`` 从可映射题里固定种子随机抽 N 题；
``--limit N`` 取前 N 道可映射题。
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import random
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

from gkagent.data.drinks_db import (
    DrinkDataUnavailable,
    resolve_drink_ids,
)
from gkagent.data.p_items_db import (
    PItemDataUnavailable,
    get_catalog,
    resolve_produce_item_ids,
)
from gkagent.sim import uinet
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
from gkagent.sim.uiobs import to_uiobs
from gkagent.sim.v_leaf import EnsembleLeafValue, LinearLeafValue
from gkagent.vision.lesson import LessonCard, LessonState

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
    "题集官方种子不公开（hajime 的 /api/sets/hajime/seeds 401），本跑分用自选种子；"
    "卡牌定制/饮料/逐回合属性/审查基准回合未建模（P 道具已按 loadout.produce_item_ids "
    "接入 LessonSim，部分效果类型仍是 no-op）。"
    "H.I.F 题集已把 produce/step/plan 放回 UINet 词表，但裁判仍是简化模拟器，"
    "分值尺度与真实 GKMS 不同。只能作本地同题同种子的相对排名。"
)

MECHANIC_TO_PLAN = {"aggressive": "sense", "full_power": "logic", "stance": "anomaly"}
#: 题集 ``scene.plan`` 的权威值（PLAN2=感性 / PLAN3=理性 / PLAN4=非凡）。
SCENE_PLAN = {"PLAN2": "sense", "PLAN3": "logic", "PLAN4": "anomaly"}
PLAN_CODE = {"sense": 2, "logic": 3, "anomaly": 4}
#: UINet 的 ``exam.produce``/``step`` 词表只认 H.I.F。
UINET_PRODUCES = ("produce-007", "produce-008")
#: 旧 hajime 题没有 produce-007/008：round -> (produce, step) 的保守替换。
UINET_ROUND = {
    "mid1": ("produce-007", "AUDITION_MID1"),
    "mid2": ("produce-007", "AUDITION_MID2"),
    "final": ("produce-008", "AUDITION_FINAL"),
}
#: H.I.F ``loadout.step_type`` -> UINet ``exam.step``。
#: 数据里同一批题还带 ``step_id``（AuditionMid1/Mid2/Final），下面交叉校验。
HIF_STEP_TYPE = {16: "AUDITION_MID1", 17: "AUDITION_MID2", 18: "AUDITION_FINAL"}
HIF_STEP_ID = {
    "AuditionMid1": "AUDITION_MID1",
    "AuditionMid2": "AUDITION_MID2",
    "AuditionFinal": "AUDITION_FINAL",
}
#: 少数 H.I.F 题缺 ``step_type``/``step_id``：用 ``scene.round`` 兜底。
ROUND_STEP = {"mid1": "AUDITION_MID1", "mid2": "AUDITION_MID2", "final": "AUDITION_FINAL"}
#: H.I.F 题集 ``loadout.schema``；带这个 schema 的题按 H.I.F 规则映射。
HIF_SCHEMA = "gkms.hif_loadout.v1"
#: LessonSim 的指針 -> UINet ``stance[0]``（无指針 = None）。
STANCE_SAVE = ("Preservation", "OverPreservation")
STANCE_STRONG = "Concentration"
STANCE_FULL = "FullPower"

_DECK_RE = re.compile(r"^(p_card-[^+/]+)(?:\+(\d+))?(?:/(.+))?$")


class UnmappableProblem(Exception):
    """题集里某道题无法映射到 LessonSim/UINet 词表：跳过并统计，不猜。"""

    def __init__(self, pid: str, reason: str) -> None:
        super().__init__(f"{pid}: {reason}")
        self.pid = pid
        self.reason = reason



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
class PItemStats:
    """一道题 ``loadout.produce_item_ids`` 的解析结果（T5③ P 道具数据接入）。

    ``mode="off"`` 时全部为 0/空（A/B 对照用：不结算 P 道具）；``unknown`` 是
    ``p_items.json`` 里仍没有的 id（显式上报，不猜、不影响这道题可映射）——B7 起
    catalog 覆盖上游 1115 件，正常应为空；``condition_unknown`` 是条件没解析出来的
    spec 段数（新增道具的新触发 id，``apply_passive`` 保守跳过）。
    """

    mode: str = "auto"
    ids: int = 0
    known: int = 0
    unknown: tuple[str, ...] = ()
    duplicate: tuple[str, ...] = ()
    specs: int = 0
    implemented: int = 0
    condition_unknown: int = 0


@dataclass(frozen=True)
class DrinkStats:
    """一道题 ``loadout.drink_ids`` 的解析结果（M6 饮料 opt-in）。

    ``mode="off"``（默认）全 0/空 = 逐位不变；``unknown`` 是 catalog（29 瓶）
    里没有的 id（显式上报，不猜、不影响本题可映射）；不去重（每 id 一瓶槽位）。
    """

    mode: str = "off"
    ids: int = 0
    known: int = 0
    unknown: tuple[str, ...] = ()
    slots: int = 0
    segments: int = 0
    implemented: int = 0


@dataclass(frozen=True)
class ProblemSpec:
    """一道题转换到 LessonSim 的静态部分（牌组/配置/统计）。"""

    pid: str
    name: str
    kind: str
    stage: str
    plan: str
    uinet_exam: tuple[str | None, str | None]
    core: bool
    raw: dict[str, Any]
    deck: tuple[CardSpec, ...]
    config: LessonConfig
    deck_stats: DeckStats
    refs: Mapping[str, tuple[str, int]]
    p_item_stats: PItemStats = PItemStats()
    drink_stats: DrinkStats = DrinkStats()


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
    completed: int = 0
    errors: int = 0
    recursion_errors: int = 0


@dataclass
class AlgorithmRun:
    """一个算法的全部对局与计数器。"""

    name: str
    label: str
    episodes: list[EpisodeResult] = field(default_factory=list)
    fallbacks: int = 0
    incomplete: int = 0
    completed: int = 0
    decisions: int = 0
    errors: int = 0
    recursion_errors: int = 0

    def add(self, episode: EpisodeResult) -> None:
        self.episodes.append(episode)
        self.fallbacks += episode.fallbacks
        self.incomplete += episode.incomplete
        self.completed += int(getattr(episode, "completed", 0))
        self.errors += int(getattr(episode, "errors", 0))
        self.recursion_errors += int(getattr(episode, "recursion_errors", 0))
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


def problem_plan(scene: Mapping[str, Any]) -> str:
    """题面方案：优先 ``scene.plan``（PLAN2/3/4），缺失时才用 mechanic 猜。

    之前只用 ``mechanic`` 猜（aggressive→sense / full_power→logic /
    stance→anomaly），但 ``scene.plan`` 才是偶像/剧本的真实方案；48 题里
    46 题是 PLAN3=logic，旧映射会把 22 道 stance 题错标成 anomaly。
    """
    plan = SCENE_PLAN.get(str(scene.get("plan") or "").strip().upper())
    if plan is not None:
        return plan
    return MECHANIC_TO_PLAN.get(str(scene.get("mechanic") or ""), "sense")


def _int_or_none(value: Any) -> int | None:
    """题集字段可能是 int/数字串；``None`` 或坏值返回 ``None``（不猜）。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def uinet_exam_for(
    loadout: Mapping[str, Any], *, pid: str, is_hif: bool
) -> tuple[str | None, str | None]:
    """题面 -> UINet 的 ``exam.produce`` / ``exam.step``。

    H.I.F（``loadout.schema=gkms.hif_loadout.v1``）用题面自带的
    ``produce_id`` 和 ``step_type``/``step_id``；两者缺失时用 ``round`` 兜底。
    只有 H.I.F 题会出现 ``step_type`` 与 ``step_id`` 不一致、或 produce 不在
    UINet 词表里的情况——这时抛 :class:`UnmappableProblem`，不猜。

    hajime 保持旧行为：``produce_id`` 是 produce-001/006（不在 UINet 词表），
    只能按 round 做最接近的合法枚举替换；lesson 题返回 ``(None, None)``。
    """
    round_code = str(loadout.get("round") or "")
    if not is_hif:
        return UINET_ROUND.get(round_code, (None, None))

    produce = str(loadout.get("produce_id") or "")
    if produce not in UINET_PRODUCES:
        raise UnmappableProblem(
            pid, f"loadout.produce_id={produce!r} 不在 UINet 词表 {UINET_PRODUCES}"
        )

    by_type = HIF_STEP_TYPE.get(_int_or_none(loadout.get("step_type")))
    by_id = HIF_STEP_ID.get(str(loadout.get("step_id") or ""))
    if by_type is not None and by_id is not None and by_type != by_id:
        raise UnmappableProblem(
            pid,
            "loadout.step_type 与 step_id 不一致："
            f"step_type={loadout.get('step_type')!r} / step_id={loadout.get('step_id')!r}",
        )
    step = by_type or by_id or ROUND_STEP.get(round_code)
    if step is None:
        raise UnmappableProblem(
            pid,
            "loadout.step_type/step_id/round 都无法映射 exam.step："
            f"step_type={loadout.get('step_type')!r} "
            f"step_id={loadout.get('step_id')!r} round={round_code!r}",
        )
    return produce, step


def build_problem(
    raw: dict[str, Any],
    card_rows: Mapping[str, dict[str, Any]],
    card_index: Mapping[tuple[str, int], str],
    refs: Mapping[str, tuple[str, int]],
    *,
    p_items_mode: str = "auto",
    drinks_mode: str = "off",
) -> ProblemSpec:
    """一道 gkbench 题 -> LessonSim 静态配置（不可映射时抛 UnmappableProblem）。

    ``p_items_mode="auto"``（默认）把 ``loadout.produce_item_ids`` 解析成
    ``PItemSpec`` 塞进 ``LessonConfig.p_items``（训练/考试开始、回合开始、出牌…
    由 LessonSim 照常触发）；``"off"`` 不清算任何 P 道具，只用于 A/B 对照。
    """
    archive = raw.get("archive") or {}
    loadout = archive.get("loadout") or {}
    scene = raw.get("scene") or {}
    pid = str(raw.get("id") or archive.get("id") or "?")
    kind = str(scene.get("kind") or loadout.get("round") or "?")
    stage = str(scene.get("stage") or loadout.get("step_id") or "")
    is_hif = str(loadout.get("schema") or "") == HIF_SCHEMA
    if not is_hif and str(loadout.get("produce_id") or "") in UINET_PRODUCES:
        # 兼容没写 schema 但明显是 H.I.F 编成的题；仍然按 H.I.F 规则映射。
        is_hif = True

    plan_code = str(scene.get("plan") or "").strip().upper()
    plan = SCENE_PLAN.get(plan_code)
    if plan is None:
        if is_hif:
            # PLAN1=免费方案（deck 是 p_card-01-*）：LessonSim 只有
            # sense/logic/anomaly，UINet 的考试方案词表也只有 2/3/4，不猜。
            raise UnmappableProblem(
                pid, f"scene.plan={plan_code or '?'} 不在 LessonSim/UINet 方案词表"
            )
        plan = MECHANIC_TO_PLAN.get(str(scene.get("mechanic") or ""), "sense")
    uinet_exam = uinet_exam_for(loadout, pid=pid, is_hif=is_hif)

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
        raise UnmappableProblem(pid, f"牌组 {len(loadout.get('deck_cards') or [])} 条一张都解析不出来")

    turns = int(scene.get("turns") or 8)
    stamina = int(loadout.get("starting_stamina") or 30)
    stamina_max = int(loadout.get("max_stamina") or stamina)
    # P 道具（T5③）：gkbench 题模板把每局的 P 道具 id 放在 loadout 里（公开配置、
    # 不含种子）。解析成 PItemSpec 后由 LessonSim/ExpectState 在对应时机结算；
    # 未知 id 显式记进 p_item_stats.unknown（不猜、不影响本题可映射）。
    p_items: tuple = ()
    p_item_stats = PItemStats(mode="off")
    if p_items_mode != "off":
        resolved = resolve_produce_item_ids(loadout.get("produce_item_ids"))
        p_items = resolved.specs
        summary = resolved.summary()
        p_item_stats = PItemStats(
            mode="auto",
            ids=int(summary["ids"]),
            known=int(summary["known_ids"]),
            unknown=tuple(summary["unknown_ids"]),
            duplicate=tuple(summary["duplicate_ids"]),
            specs=int(summary["specs"]),
            implemented=int(summary["implemented"]),
            condition_unknown=int(summary.get("condition_unknown") or 0),
        )
    # M6 饮料（opt-in，默认 off 逐位不变）：loadout.drink_ids → DrinkSpec 效果段；
    # 未知 id 显式记进 drink_stats.unknown（不猜、不影响本题可映射）。
    drinks: tuple = ()
    drink_stats = DrinkStats(mode="off")
    if drinks_mode != "off":
        dres = resolve_drink_ids(loadout.get("drink_ids"))
        drinks = dres.specs
        dsum = dres.summary()
        drink_stats = DrinkStats(
            mode="auto",
            ids=int(dsum["ids"]),
            known=int(dsum["known_ids"]),
            unknown=tuple(dsum["unknown_ids"]),
            slots=int(dsum["slots"]),
            segments=int(dsum["segments"]),
            implemented=int(dsum["implemented"]),
        )
    config = LessonConfig(
        turns=turns,
        stamina=stamina,
        # gkbench 按原始分数排名，没有 CLEAR/PERFECT 线；这里只给 LessonSim
        # 的内部档位一个下限，跑分器只用 score。
        target_clear=1,
        target_perfect=2,
        hand_size=3,
        # gkbench 用真机规则：每回合基础 1 张 + 卡效果/P 道具的额外出牌（B3）。
        plays_per_turn=1,
        stamina_max=stamina_max,
        plan=plan,
        p_items=p_items,
        drinks=drinks,
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
        plan=plan,
        uinet_exam=uinet_exam,
        core=bool(raw.get("core")),
        raw=raw,
        deck=tuple(deck),
        config=config,
        deck_stats=stats,
        refs=refs,
        p_item_stats=p_item_stats,
        drink_stats=drink_stats,
    )


# ------------------------------------------------------------------ UIObs
def _zone(zone: Any, refs: Mapping[str, tuple[str, int]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for card in zone or ():
        ref = refs.get(card.name)
        if ref is not None:
            out.append({"id": ref[0], "u": ref[1]})
    return out


class _SimCardTable:
    """把 ``ProblemSpec.refs`` 适配成 ``to_uiobs`` 需要的 CardTable 子集。

    ``to_uiobs`` 只调用 ``get(name)``（卡号/强化）和 ``cost(name)``（卡费兜底）；
    LessonSim 已经用同一套卡表建好牌组，所以这里直接查解析结果，不重复读 JSON。
    """

    def __init__(
        self,
        refs: Mapping[str, tuple[str, int]],
        costs: Mapping[str, int],
    ) -> None:
        self._refs = dict(refs)
        self._costs = dict(costs)

    def get(self, name: str) -> dict[str, Any] | None:
        ref = self._refs.get(name)
        if ref is None:
            return None
        return {"id": ref[0], "upgrade": int(ref[1])}

    def cost(self, name: str) -> int | None:
        return self._costs.get(name)


def _sim_status(sim: LessonSim) -> list[list[Any]]:
    """LessonSim 已建模的 buff -> UIObs ``status``（UINet 的 4 个 scalar + 好调）。

    只映射语义一一对应的项；``status`` 的回合数用 UINet 训练的写法：
    - 集中/好印象/やる気/全力值 是永久层数 -> -1（INF）；
    - 好调/絶好調 是剩余回合 -> 正数。
    不映射不調、状态获取量加成等 LessonSim 近似口径不一致的项（保守省略）。
    """
    buffs = sim.buffs
    status: list[list[Any]] = []
    if buffs.focus:
        status.append(["lesson_buff", float(buffs.focus), -1])  # 集中
    if buffs.impression:
        status.append(["review", float(buffs.impression), -1])  # 好印象
    if sim.motivation:
        status.append(["aggressive", float(sim.motivation), -1])  # やる気
    if sim.stance.full_power_point:
        status.append(["full_power_point", float(sim.stance.full_power_point), -1])
    if buffs.condition_turns:
        # 好調：UINet 训练数据把层数和剩余回合都记成剩余回合数。
        status.append(["parameter_buff", float(buffs.condition_turns), int(buffs.condition_turns)])
    if buffs.perfect_condition_turns:
        status.append(
            ["parameter_buff_multiple", 1.0, int(buffs.perfect_condition_turns)]
        )
    return status


def _sim_stance(sim: LessonSim) -> list[Any]:
    """LessonSim 的 5 种指針 -> UIObs ``stance`` 的 (Preservation/…/FullPower, step)。"""
    state = sim.stance
    stance = str(state.stance)
    if stance == "save":
        level = 2 if int(state.save_level or 0) >= 2 else 1
        return [STANCE_SAVE[level - 1], level]
    if stance in ("strong1", "strong2"):
        return [STANCE_STRONG, 1 if stance == "strong1" else 2]
    if stance == "strong":
        return [STANCE_STRONG, 2 if int(state.strong_level or 0) >= 2 else 1]
    if stance == "full":
        return [STANCE_FULL, 0]
    return [None, 0]


def sim_to_uiobs(
    sim: LessonSim,
    spec: ProblemSpec,
    *,
    decision: int,
    played: list[CardSpec],
) -> dict[str, Any]:
    """当前 LessonSim 局面 -> UIObs v1（复用 :func:`gkagent.sim.uiobs.to_uiobs`）。

    **从 LessonSim / 题面真实填进去的**：手牌（id/u/p，p 用 ``sim.legal_actions``
    的实际牌费/元气口径覆盖，而不是只看卡面费用）、山札/弃牌/除外/本回合已出牌、
    分数/体力/上限/元气/可出牌次数/已出牌数、回合/总回合、方案（``spec.plan``，
    来自 ``scene.plan`` 权威值）、指針、已建模的 buff（集中/好印象/やる気/全力值/
    好调/絶好調）、audition 题的审查基准（``parameters``）与三项倍率
    （``score_bonus_permils``）。

    H.I.F 题的 ``exam.produce`` / ``exam.step`` 直接用题面自带的
    produce-007/008 + step_type/step_id（见 :func:`uinet_exam_for`），不再是
    produce-001/006 的替换值。

    **LessonSim 没有、按保守默认的**（UINet 训练时能看到，本地看不到）：

    - ``exam.types``：没有逐回合属性 -> 全 1（Vo）；H.I.F 题也一样，题面只有
      编成、没有 types 序列；
    - ``hold`` / ``ench`` / ``drinks``：不建模保留区/附魔/P 道具/饮料 -> 空；
      题面的 H.I.F 附魔/回忆/研究卡字段也不进模拟器；
    - 卡牌 ``c``（定制）与 ``g``（考试中成长）省略；
    - hajime 的 lesson 题 ``exam.produce`` / ``exam.step`` 只给 UINet 词表内的
      保守默认 produce-007/AUDITION_MID1（题面的 produce-001/006 不在词表里）；
    - hajime 的 lesson 题审查基准未知 -> ``crit = [0, 0, 0]``；倍率未知 -> 1000‰；
    - 卡面/状态以外的模拟器简化（属性回合倍率、暴击、gimmick、追加回合、
      饮料、P 道具）都没有建模。
    """
    loadout = (spec.raw.get("archive") or {}).get("loadout") or {}
    scene = spec.raw.get("scene") or {}
    limit = max(int(sim.total_turns), 1)
    audition = str(loadout.get("round") or "") in UINET_ROUND
    costs = {card.name: int(card.cost) for card in spec.deck}
    cards = tuple(
        LessonCard(index=index, box=(0, 0, 0, 0), point=(0, 0), name=card.name, cost=card.cost)
        for index, card in enumerate(sim.hand)
    )
    state = LessonState(
        kind="audition" if audition else "lesson",
        turns_left=int(sim.turns_left),
        total_turns=int(sim.total_turns),
        score=int(sim.score),
        stamina=int(sim.stamina),
        cards=cards,
    )
    produce, step = spec.uinet_exam
    obs = to_uiobs(
        state,
        table=_SimCardTable(spec.refs, costs),
        plan=spec.plan,
        plays=int(sim.plays_this_turn),
        playable=max(0, int(sim.plays_per_turn + sim.extra_plays - sim.plays_this_turn)),
        max_stamina=int(sim.stamina_max),
        produce=produce,
        step=step,
        # 逐回合属性 LessonSim 不建模：保守全 Vo。
        types=[1] * limit,
        # 审查基准/倍率只有 audition 题面给；lesson 题给保守默认。
        permil=loadout.get("score_bonus_permils") if audition else None,
        crit=loadout.get("parameters") if audition else None,
        block=int(sim.vitality),
        status=_sim_status(sim),
        deck=_zone(sim.deck, spec.refs),
        grave=_zone(sim.discard, spec.refs),
        lost=_zone(sim.excluded, spec.refs),
        played=_zone(played, spec.refs),
    )
    # to_uiobs 的 p 只按卡面费用 <= 体力算；LessonSim 还要算元气和指針修正，
    # 这里用 sim.legal_actions() 覆盖，保证 UINet 只看到真正能出的牌。
    legal_slots = sim.legal_actions()
    hand_legal = {index for index in legal_slots if index is not None}
    for index, card in enumerate(obs["hand"]):
        card["p"] = 1 if index in hand_legal else 0
    obs["legal"] = [["play", index] for index in sorted(hand_legal)]
    if None in legal_slots:
        obs["legal"].append(["end"])
    # M6 阶段2：饮料 opt-in 时把合法饮料动作暴露进 legal（drinks off 时
    # legal_drinks()=[] → 逐位不变）。搜索/生产据此真正喝饮料（旧版吞掉 drink）。
    obs["legal"].extend(["drink", index] for index in sim.legal_drinks())
    obs["stance"] = _sim_stance(sim)
    obs["i"] = int(decision)
    obs["exam"]["idol"] = str(loadout.get("idol_card_id") or scene.get("idol") or "")
    return obs


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

    H.I.F 的部分牌组会让搜索树在 300ms 预算内先撞到 Python 递归深度上限
    （``RecursionError``）：这一步按贪心回退并单独计数，整局继续，不中断跑分。
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
        self.recursion_errors = 0

    def decide(self, _obs: dict[str, Any], sim: LessonSim) -> tuple[str, int | None]:
        try:
            result = expectimax_with_stats(
                state_from_sim(sim), self.leaf, time_budget_ms=self.budget_ms
            )
        except RecursionError:
            # 深层 0 费/抽牌链先撞到 Python 递归上限；按 anytime 的同一口径
            # 退回贪心，并单独计数（不混进 complete/anytime）。
            self.recursion_errors += 1
            self.fallbacks += 1
            return _greedy_action(sim)
        if result.complete:
            self.completed += 1
        else:
            self.incomplete += 1
        # anytime: 超时也用当前最优动作，不整步退回贪心
        if result.drink is not None:
            return ("drink", int(result.drink))
        if result.card is not None:
            index = _hand_index(sim, result.card)
            if index is not None:
                return ("play", index)
        self.fallbacks += 1
        return _greedy_action(sim)


class AlgorithmUnavailable(RuntimeError):
    """依赖缺失（模型/包/主数据）：整组跳过，不影响其它算法。"""


def uinet_skip_reason() -> str | None:
    """UINet 能否整组跑；不能跑时返回给人看的原因（``None`` = 可以跑）。"""
    model = uinet.model_path()
    if not model.is_file():
        return f"UINet 模型不存在：{model}"
    master = uinet.master_dir()
    if not uinet.available():
        return f"UINet 主数据缺表（需要 9 张）：{master}"
    try:
        import gkms_uinet  # noqa: F401 -- 只检查包能不能 import
        import onnxruntime  # noqa: F401 -- onnxruntime 缺失时 UINet 也跑不了
    except Exception as exc:  # noqa: BLE001 -- 任何 import 失败都按整组跳过
        return f"gkms_uinet/onnxruntime 不可用：{exc!r}"
    return None


class UinetPolicy:
    """``gkms_uinet`` 的 ONNX 贪心策略；动作必须映射回当前合法动作。

    模型/主数据缺失由 :func:`uinet_skip_reason` 在构造前整组跳过；这里只处理
    推理期异常（ONNX 报错等）——逐步骤退回 ``greedy_policy`` 并计数，不让
    整轮跑分崩掉。``drink`` 只有在 ``obs["legal"]`` 真提供饮料时才会被采纳；
    当前 LessonSim 不建模饮料，所以实际会走贪心回退。
    """

    name = "uinet"
    label = "uinet"

    def __init__(self) -> None:
        self.fallbacks = 0
        self.incomplete = 0
        self.completed = 0
        self.errors = 0
        self._warned = False

    def decide(self, obs: dict[str, Any], sim: LessonSim) -> tuple[str, int | None]:
        try:
            output = uinet.predict(obs)
            action = list(output.action)
        except Exception as exc:  # noqa: BLE001 -- 推理失败逐步骤回退，不中断跑分
            self.errors += 1
            if not self._warned:
                self._warned = True
                print(f"[uinet] 推理失败，后续按贪心回退：{exc!r}", file=sys.stderr)
            self.fallbacks += 1
            return _greedy_action(sim)
        if not action:
            self.fallbacks += 1
            return _greedy_action(sim)
        kind = str(action[0])
        try:
            target = int(action[1]) if len(action) > 1 else -1
        except (TypeError, ValueError):
            self.fallbacks += 1
            return _greedy_action(sim)
        legal = obs.get("legal") or []
        if kind == "play" and ["play", target] in legal:
            return ("play", target)
        if kind == "drink" and ["drink", target] in legal:
            return ("drink", target)
        if kind == "end" and ["end"] in legal:
            return ("end", None)
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


def make_algorithms(
    names: list[str], budget_ms: float
) -> list[GreedyPolicy | ExpectimaxPolicy | UinetPolicy]:
    """按名字构造算法实例（每个算法独立计数）。

    UINet 的模型/主数据/包缺失时抛 :class:`AlgorithmUnavailable`，由
    :func:`run_bench` 捕获后整组跳过并打印原因。
    """
    out: list[GreedyPolicy | ExpectimaxPolicy | UinetPolicy] = []
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
        elif name == "uinet":
            reason = uinet_skip_reason()
            if reason is not None:
                raise AlgorithmUnavailable(reason)
            out.append(UinetPolicy())
        else:
            raise SystemExit(
                "未知算法 "
                f"{name!r}；可选 greedy / uinet / expectimax-analytic / expectimax-ensemble"
            )
    return out


# ------------------------------------------------------------------ 跑一局
def run_episode(spec: ProblemSpec, seed: int, policy: Any) -> EpisodeResult:
    """同题同种子跑一局；返回该局的分数/每步耗时/路线。"""
    sim = LessonSim(list(spec.deck), spec.config, rng_seed=seed)
    step_ms: list[float] = []
    route: list[str] = []
    played_this_turn: list[CardSpec] = []
    last_turn = sim.current_turn
    decisions = 0
    fallbacks = 0
    started = time.perf_counter()
    while not sim.done:
        # 回合可能因手牌打空自动结束（sim.step 内部 _end_turn）；UIObs 的
        # played 只应包含"本回合已出牌"，换回合时清空。
        if sim.current_turn != last_turn:
            played_this_turn.clear()
            last_turn = sim.current_turn
        obs = sim_to_uiobs(sim, spec, decision=decisions, played=played_this_turn)
        began = time.perf_counter()
        action, target = policy.decide(obs, sim)
        elapsed_ms = (time.perf_counter() - began) * 1000.0
        step_ms.append(float(elapsed_ms))
        legal = obs["legal"]
        if action == "drink":
            # M6 阶段2：饮料已建模且 legal 提供时真正执行（--drinks auto + 搜索
            # 选中）；off 时 legal 无 drink，不会进此分支（逐位不变）。非法/未建模
            # 的 drink 建议仍按贪心回退（旧口径）。
            if ["drink", target] in legal:
                sim.use_drink(int(target))
                route.append(f"d{target}")
                decisions += 1
                continue
            action, target = _greedy_action(sim)
            fallbacks += 1
        if action == "play":
            index = int(target) if target is not None else -1
            if ["play", index] not in legal:
                fallbacks += 1
                # 回退到 greedy；greedy 也可能返回 end（没有能出的牌），
                # 这时必须走下面的 end 分支，不能把 target=None 当成 -1 出牌。
                action, target = _greedy_action(sim)
        if action == "play":
            index = int(target) if target is not None else -1
            if index < 0 or index >= len(sim.hand):
                raise RuntimeError(f"{spec.pid} seed={seed}: 非法出牌下标 {index}")
            played_this_turn.append(sim.hand[index])
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
        completed=int(getattr(policy, "completed", 0)),
        errors=int(getattr(policy, "errors", 0)),
        recursion_errors=int(getattr(policy, "recursion_errors", 0)),
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
        # complete = 预算内搜完；anytime = 超时但用了当前最优动作；fallback = 只能退回贪心
        "complete_rate": round(run.completed / run.decisions, 4) if run.decisions else 0.0,
        "anytime_rate": round(run.incomplete / run.decisions, 4) if run.decisions else 0.0,
        "completed": run.completed,
        "incomplete": run.incomplete,
        "errors": run.errors,
        "recursion_errors": run.recursion_errors,
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
        "errors": episode.errors,
        "recursion_errors": episode.recursion_errors,
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
    sample: int | None = None,
    sample_seed: int = 0,
    p_items_mode: str = "auto",
    drinks_mode: str = "off",
) -> dict[str, Any]:
    if p_items_mode not in {"auto", "off"}:
        raise SystemExit(f"--p-items 只支持 auto/off：{p_items_mode!r}")
    if p_items_mode != "off":
        try:
            get_catalog()  # 显式校验数据在位（缺失直接报错，不静默当没有 P 道具）
        except PItemDataUnavailable as exc:
            raise SystemExit(f"P 道具数据不可用：{exc}") from exc
    if drinks_mode not in {"auto", "off"}:
        raise SystemExit(f"--drinks 只支持 auto/off：{drinks_mode!r}")
    if drinks_mode != "off":
        try:
            from gkagent.data.drinks_db import get_catalog as get_drink_catalog

            get_drink_catalog()  # 缺失直接报错，不静默当没有饮料
        except DrinkDataUnavailable as exc:
            raise SystemExit(f"饮料数据不可用：{exc}") from exc
    card_rows, card_index, refs = load_card_table()
    raw_problems = load_problems(problems_path)
    specs: list[ProblemSpec] = []
    skipped_problems: list[dict[str, str]] = []
    for raw in raw_problems:
        try:
            specs.append(
                build_problem(
                    raw, card_rows, card_index, refs, p_items_mode=p_items_mode,
                    drinks_mode=drinks_mode,
                )
            )
        except UnmappableProblem as exc:
            skipped_problems.append(
                {
                    "id": exc.pid,
                    "name": str(raw.get("name") or exc.pid),
                    "reason": exc.reason,
                }
            )
    if limit is not None:
        specs = specs[: max(int(limit), 0)]
    if sample is not None:
        if int(sample) < 1:
            raise SystemExit("--sample 必须 >= 1")
        if int(sample) < len(specs):
            picked = set(random.Random(int(sample_seed)).sample(range(len(specs)), int(sample)))
            specs = [spec for index, spec in enumerate(specs) if index in picked]
    if not specs:
        detail = ""
        if skipped_problems:
            detail = f"（源题集 {len(raw_problems)} 题里跳过 {len(skipped_problems)} 题）"
        raise SystemExit(f"没有可跑的题{detail}")
    seeds = [int(seed_base) + index for index in range(max(int(episodes), 1))]

    runs: list[AlgorithmRun] = []
    skipped_algorithms: list[dict[str, str]] = []
    for name in algo_names:
        try:
            policies = make_algorithms([name], budget_ms)
        except AlgorithmUnavailable as exc:
            skipped_algorithms.append({"name": name, "reason": str(exc)})
            print(f"[skip] {name}: {exc}", file=sys.stderr)
            continue
        policy = policies[0]
        runs.append(AlgorithmRun(name=policy.name, label=policy.label))
    if not runs:
        details = "; ".join(f"{row['name']}={row['reason']}" for row in skipped_algorithms)
        raise SystemExit(f"没有可运行的算法（已跳过：{details}）")

    uinet_cold_ms: float | None = None
    if any(run.name == "uinet" for run in runs):
        # 预热：先加载主数据 + ONNX 会话并跑一次，避免第一局的第一个决策
        # 把冷启动算进 step_ms；冷启动单独记录到 summary。
        warm_spec = specs[0]
        warm_sim = LessonSim(list(warm_spec.deck), warm_spec.config, rng_seed=seeds[0])
        warm_obs = sim_to_uiobs(warm_sim, warm_spec, decision=0, played=[])
        began = time.perf_counter()
        try:
            uinet.predict(warm_obs)
        except Exception as exc:  # 预热失败也整组跳过，不崩跑分器
            reason = f"预热推理失败：{exc!r}"
            skipped_algorithms.append({"name": "uinet", "reason": reason})
            print(f"[skip] uinet: {reason}", file=sys.stderr)
            runs = [run for run in runs if run.name != "uinet"]
            if not runs:
                raise SystemExit(f"没有可运行的算法（uinet 预热失败：{exc!r}）") from exc
        else:
            uinet_cold_ms = (time.perf_counter() - began) * 1000.0
            print(
                f"[uinet] 冷启动 {uinet_cold_ms:.1f} ms（主数据 + ONNX 会话 + 首次推理）",
                file=sys.stderr,
            )

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
    # P 道具覆盖率（T5③）：按题聚合 loadout.produce_item_ids 的解析结果。
    p_item_stats = [spec.p_item_stats for spec in specs]
    p_item_unknown = sorted({item_id for st in p_item_stats for item_id in st.unknown})
    p_item_duplicate = sorted({item_id for st in p_item_stats for item_id in st.duplicate})
    p_item_ids = sum(st.ids for st in p_item_stats)
    p_item_known = sum(st.known for st in p_item_stats)
    p_item_specs = sum(st.specs for st in p_item_stats)
    p_item_implemented = sum(st.implemented for st in p_item_stats)
    p_item_condition_unknown = sum(st.condition_unknown for st in p_item_stats)
    p_item_problems = sum(1 for st in p_item_stats if st.ids)
    unmodeled = Counter(
        effect for spec in specs for effect in spec.deck_stats.unmodeled_types
    )
    kinds: Counter[str] = Counter(spec.kind for spec in specs)
    stages: Counter[str] = Counter(spec.stage for spec in specs)
    plans: Counter[str] = Counter(spec.plan for spec in specs)
    produces: Counter[str] = Counter(
        spec.uinet_exam[0] for spec in specs if spec.uinet_exam[0] is not None
    )
    steps: Counter[str] = Counter(
        spec.uinet_exam[1] for spec in specs if spec.uinet_exam[1] is not None
    )
    skip_reasons = Counter(row["reason"] for row in skipped_problems)
    is_hif = any(
        str(((spec.raw.get("archive") or {}).get("loadout") or {}).get("schema") or "")
        == HIF_SCHEMA
        for spec in specs
    )
    uinet_gaps = [
        "exam.types 全 1（LessonSim 没有逐回合属性）",
        (
            "hold / ench 为空（不建模保留区/附魔；饮料 M6 opt-in 见 drinks 块，默认 off；P 道具已从 loadout 接入 "
            "LessonSim/expectimax，但 UINet 的 UIObs 里没有 P 道具字段）"
        ),
        "卡牌定制 c 与考试中成长 g 省略",
    ]
    if is_hif:
        uinet_gaps.append(
            "H.I.F produce/step 用题面 produce_id + step_type/step_id（已在 UINet 词表）"
        )
        uinet_gaps.append("H.I.F 附魔/回忆/研究卡/追加回合没有进模拟器")
    else:
        uinet_gaps.append(
            "hajime lesson 题 produce-001/006 不在 UINet 词表，按 produce-007/AUDITION_MID1 保守默认"
        )
        uinet_gaps.append("hajime lesson 题 crit=[0,0,0]、permil=1000（题面没有審査基準/倍率）")

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
            "path": str(problems_path.relative_to(ROOT))
            if problems_path.is_relative_to(ROOT)
            else str(problems_path),
            "is_hif": is_hif,
            "source_total": len(raw_problems),
            "count": len(specs),
            "limit": limit,
            "sample": sample,
            "sample_seed": int(sample_seed) if sample is not None else None,
            "kinds": dict(sorted(kinds.items())),
            "stages": dict(sorted(stages.items())),
            "plans": dict(sorted(plans.items())),
            "core": sum(1 for spec in specs if spec.core),
            "uinet_produce": dict(sorted(produces.items())),
            "uinet_step": dict(sorted(steps.items())),
            "skipped_count": len(skipped_problems),
            "skipped_by_reason": dict(sorted(skip_reasons.items())),
            "skipped": skipped_problems,
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
            "p_items_modeled": p_item_implemented,
        },
        "drinks": {
            "mode": drinks_mode,
            "source": "loadout.drink_ids -> data/knowledge/drinks.json",
            "problems_with_drinks": sum(1 for s in specs if s.drink_stats.ids),
            "ids": sum(s.drink_stats.ids for s in specs),
            "known_ids": sum(s.drink_stats.known for s in specs),
            "unknown_ids": sorted({u for s in specs for u in s.drink_stats.unknown}),
            "slots": sum(s.drink_stats.slots for s in specs),
            "segments": sum(s.drink_stats.segments for s in specs),
            "implemented_segments": sum(s.drink_stats.implemented for s in specs),
        },
        "p_items": {
            "mode": p_items_mode,
            "source": "loadout.produce_item_ids -> data/knowledge/p_items.json",
            "problems_with_items": p_item_problems,
            "ids": p_item_ids,
            "known_ids": p_item_known,
            "unknown_ids": p_item_unknown,
            "duplicate_ids": p_item_duplicate,
            "specs": p_item_specs,
            "implemented_specs": p_item_implemented,
            "condition_unknown_specs": p_item_condition_unknown,
            "note": (
                "未知 id = p_items.json（1115 件，覆盖到 2026-11 上游）里都没有的道具，"
                "显式列出不作猜测；未实现效果类型仍是 no-op；新增 47 条里条件未解析的 "
                "spec 保守不触发（condition_unknown_specs，见 sim/p_items.py）。"
            ),
        },
        "algorithms": {row["name"]: row for row in algorithms},
        "skipped_algorithms": skipped_algorithms,
        "uinet": {
            "model": str(uinet.model_path()),
            "master": str(uinet.master_dir()),
            "cold_start_ms": round(uinet_cold_ms, 3) if uinet_cold_ms is not None else None,
            "exam_example": {
                "problem": specs[0].pid,
                "produce": specs[0].uinet_exam[0],
                "step": specs[0].uinet_exam[1],
                "plan": specs[0].plan,
            },
            "observation_gaps": uinet_gaps,
        }
        if uinet_cold_ms is not None
        else None,
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
        help="逗号分隔：greedy / uinet / expectimax-analytic / expectimax-ensemble",
    )
    parser.add_argument("--budget-ms", type=float, default=DEFAULT_BUDGET_MS, help="expectimax 每步预算")
    parser.add_argument(
        "--problems",
        type=Path,
        default=PROBLEMS_PATH,
        help="题集 JSON（默认 hajime；H.I.F 用 data/bench_local/problems_hif.json）",
    )
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 道可映射题（调试）")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="从可映射题里固定种子随机抽 N 题（避免 --limit 只覆盖题集开头）",
    )
    parser.add_argument("--sample-seed", type=int, default=0, help="--sample 的随机种子")
    parser.add_argument(
        "--p-items",
        choices=("auto", "off"),
        default="auto",
        help="P 道具：auto=按 loadout.produce_item_ids 接入（默认）；off=不结算（A/B 对照）",
    )
    parser.add_argument(
        "--drinks",
        default="off",
        choices=["auto", "off"],
        help="M6 饮料：auto=按 loadout.drink_ids 接入效果段结算；off=不结算（默认，逐位不变）",
    )
    parser.add_argument("--out", type=Path, default=REPORT_PATH, help="排行榜 JSON 输出")
    args = parser.parse_args(argv)

    algo_names = [name.strip() for name in args.algos.split(",") if name.strip()]
    summary = run_bench(
        problems_path=args.problems,
        episodes=args.episodes,
        seed_base=args.seed_base,
        algo_names=algo_names,
        budget_ms=args.budget_ms,
        limit=args.limit,
        output=args.out,
        sample=args.sample,
        sample_seed=args.sample_seed,
        p_items_mode=args.p_items,
        drinks_mode=args.drinks,
    )
    print("=" * 92)
    print("裁判 = 我们的模拟器 LessonSim（不是 gkbench 的 GKMS 引擎）")
    print("分数与他们排行榜不可比：裁判/种子/机制覆盖都不同（详见 leaderboard JSON）")
    print("=" * 92)
    problems = summary["problems"]
    kinds = problems["kinds"]
    print(
        f"题目 {problems['count']} 道（源题集 {problems['source_total']} 道，"
        f"跳过 {problems['skipped_count']} 道；"
        + " / ".join(f"{kind} {count}" for kind, count in kinds.items())
        + f"），每题 {summary['seeds_per_problem']} 个种子，"
        f"种子 {summary['seeds'][0]}..{summary['seeds'][-1]}（自选）"
    )
    print(
        "题集方案 "
        + " / ".join(f"{plan} {count}" for plan, count in problems["plans"].items())
        + "；UINet 词表内 produce "
        + " / ".join(f"{key} {count}" for key, count in problems["uinet_produce"].items())
        + "，step "
        + " / ".join(f"{key} {count}" for key, count in problems["uinet_step"].items())
    )
    if problems["skipped_count"]:
        for reason, count in problems["skipped_by_reason"].items():
            print(f"  [题目跳过] {count} 道：{reason}")
    drinks_sum = summary.get("drinks") or {}
    if drinks_sum and drinks_sum.get("mode") != "off":
        print(
            f"饮料（{drinks_sum.get('mode')}）：{drinks_sum.get('problems_with_drinks', 0)} 题带饮料，"
            f"槽位 {drinks_sum.get('slots', 0)}（已知 id {drinks_sum.get('known_ids', 0)} / "
            f"未知 {len(drinks_sum.get('unknown_ids') or [])}），"
            f"效果段 {drinks_sum.get('segments', 0)}"
            f"（已实现 {drinks_sum.get('implemented_segments', 0)}）"
        )
    p_items = summary.get("p_items") or {}
    if p_items:
        unknown = p_items.get("unknown_ids") or []
        print(
            f"P 道具（{p_items.get('mode')}）：{p_items.get('problems_with_items', 0)} 题带道具，"
            f"id {p_items.get('ids', 0)} 个（已知 {p_items.get('known_ids', 0)} / "
            f"未知 {len(unknown)}），spec {p_items.get('specs', 0)} 段"
            f"（已实现 {p_items.get('implemented_specs', 0)} 段，"
            f"条件未知不触发 {p_items.get('condition_unknown_specs', 0)} 段）"
        )
        if unknown:
            print(f"  [P 道具未知 id] {len(unknown)} 个（catalog 缺行，不猜）：{', '.join(unknown)}")
    for row in summary.get("skipped_algorithms") or []:
        print(f"  [算法跳过] {row['name']}: {row['reason']}")
    header = (
        f"{'算法':22s} {'局数':>4s} {'均值':>9s} {'P50':>7s} {'P90':>7s} "
        f"{'每步均值ms':>10s} {'每步P50':>8s} {'每步P90':>8s} "
        f"{'complete':>8s} {'anytime':>8s} {'fallback':>8s} {'errors':>6s}"
    )
    print(header)
    print("-" * len(header))
    for name in algo_names:
        row = summary["algorithms"].get(name)
        if row is None:
            continue
        print(
            f"{row['label']:22s} {row['episodes']:4d} {row['mean']:9.1f} {row['p50']:7.1f} "
            f"{row['p90']:7.1f} {row['step_ms_mean']:10.2f} {row['step_ms_p50']:8.2f} "
            f"{row['step_ms_p90']:8.2f} {row.get('complete_rate', 0.0) * 100:8.1f}% "
            f"{row.get('anytime_rate', 0.0) * 100:8.1f}% {row['fallback_rate'] * 100:8.1f}% "
            f"{row.get('errors', 0):6d}"
        )
    print("-" * len(header))
    if "greedy" in summary["algorithms"]:
        base = summary["algorithms"]["greedy"]["mean"]
        for name in algo_names:
            row = summary["algorithms"].get(name)
            if row is None or name == "greedy":
                continue
            delta = row["mean"] - base
            ratio = row["mean"] / base if base else float("nan")
            suffix = f"{delta / base:+.1%}" if base else "n/a"
            print(
                f"  {row['label']} vs greedy: {ratio:.3f}×"
                f"（{delta:+.1f} 分，{suffix}）"
            )
    ranked = sorted(
        summary["algorithms"].values(), key=lambda item: item["mean"], reverse=True
    )
    print("均值排名：" + " > ".join(f"{row['label']}({row['mean']:.1f})" for row in ranked))
    uinet_row = summary.get("uinet")
    if uinet_row:
        print(
            f"UINet 冷启动 {uinet_row['cold_start_ms']:.1f} ms；观测缺口："
            + "；".join(uinet_row["observation_gaps"])
        )
    print(f"\nJSON: {args.out}")
    print(f"可比性：{COMPARABILITY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
