"""培育（produce）级模拟器：从开培育到最终评价，纯数值、无画面。

用途：在几十万局里比较**训练/休息/上课/外出**的行动策略，看哪种能把三维属性推得更高。

建模（有意简化，只保留对"属性成长"有影响的量）：
- 一周一个行动：训练(某属性，レッスン) / 上课(授業) / 休息 / 外出
- 训练（``training()``，レッスン）：跑训练模拟器(LessonSim)，用卡打分、涨三维、
  给卡奖励、耗体力；模型内部已建模：每回合 3 张手牌、体力、元气（ExamBlock）
  优先抵牌费、SKIP 换手牌、饮料（LessonSim.use_drink，每回合 1 瓶）
- 上课（``class_lesson()``，授業）：属性 +N(随机)、耗 P 点、不给卡；支援卡加成
  用倍率近似
- 休息：体力 +24；外出：体力 +24 且不消耗周数（近似）
- 期中/期末：按"属性×审查基准权重"和一个门槛比较，估算名次
- 最终评价：用三维总和映射到 S/A/B/C/E（回归到真机观测：总和 ~630 = E/不合格）

只依赖 `gkagent.sim.lesson`，不依赖真机、不联网、可多进程。

**双源口径（2026-11-15 夜间，当前默认）：**

- ``data/knowledge/official.json``（``scripts/wiki_formula_ingest.py`` 生成）
  提供 16 周プロ排期：week1 授業 CLEAR 40 + PERFECT 25，后期授業 110/40，
  训练 40→165，追い込み 90/165；考试在 week 7/16。
- ``schedule_source="official"``（默认）时，训练/上课的周收益直接取官方排期：
  ``train_clear`` / ``clear+perfect``。缺失时退回 ``class_gain=75`` 与
  ``training_gain_ratio=0.5`` 旧常数（``schedule_source="constants"`` 可强制旧口径）。
  （旧名 ``train_gain`` / ``lesson_gain_ratio`` 仍作为别名可用。）
- 300 局（seed 9000，真机卡组/奖励池）：默认策略 三维 990 / 评价点 P50 4747；
  按官方行动排期 三维 966 / 评价点 P50 4666。真机第二局 971 / 5992。
- 评价点仍差 ~22%：真机 5992 那局的终试得分/顺位没有采集；在 total≈970、
  rank=3 时，``2×total×4.11`` 的考试 proxy 加官方分段公式上限约 4830。
  这不是再调一个常数能解决的，详见 ``docs/WIKI_DUAL_SOURCE.md``。

**旧口径校准（2026-11-15 白天，现仅作 fallback 历史依据）：**

- 玩家手动打完一局：**评价 C / 4135 评价点 / 三维约 1000-1200**
  （有村麻央，支援卡 Lv10/10/10/20/10/60，起始三维 209/85/75）；
- 扫描 ``training_gain_ratio``：1.00 → 三维 2219 / 评价点 7309；0.60 → 1330 / 4739；
  **0.50 → 1108 / 4097（与真机 4135 误差 0.9%）**；0.40 → 886 / 3454；
- 旧默认取 **0.5**：机制上训练得分 1:1 转属性（1.0 是对的），但模拟器"奖励选最强"
  后的牌组约为真机牌组的 **2 倍强**（模拟训练均分 ~245，真机只有 90-120），
  1.0 会把总分放大约 2 倍；0.5 是吸收"牌组强度差"后的有效系数；
- 支援卡加成同步改成 **1.2**：真机 6 张卡均值 Lv20（Lv10/10/10/20/10/60）属 SR 档，
  旧的 1.35 假设 Lv40，会把上课收益再抬高一档。official 模式下排期收益已是
  最终值，不再乘 support_bonus；该倍率只用于 constants fallback。

**考试属性倍率（2026-11-15 19:06 真机 C+/5577 反推）：**

- 真机手动那局：**C+ / 5577 评价点**，考试原始得分约 **1.7 万**；按卡面公式
  37 分 + 集中 10 + 好调 × 屏幕「歌唱 411%」≈ 290 分/张——考试里每张牌都吃
  属性倍率，而训练里倍率 ≈ 1.0；
- 旧模拟器的终试得分 proxy 是 ``2 × 三维总和``（典型局 ~2480），完全没乘属性
  倍率，所以官方评价公式算出 ~4092（C），与真机 5577（C+）差一个档；
- 新增 ``audition_coefficient = 4.11``：``exam()`` 里
  ``终试得分 ≈ 2 × 三维总和 × 4.11``（典型局三维 1245 → ~10200 分），再喂给
  ``eval_value`` / ``exam_score_points``，典型局评价点回到 ~5600，与真机 5577
  对齐；训练仍用 1.0，训练分数不受影响。

**未建模（真机有、本层没有；影响已写明）：**

- P 道具 / 角色被动（真机部分角色每回合开始触发加分、元气、集中等）：不进训练
  与属性。影响：依赖 P 道具的卡组成长/得分被低估；
- 饮料/道具的配装与使用：``LessonSim`` 已支持 ``DrinkSpec`` + ``use_drink``，
  但 ``ProduceSim`` 没有饮料配置，``training_policy`` 也不会主动喝。影响：培育级
  模拟默认无饮料收益；要测饮料需直接构造 ``LessonConfig.drinks``；
- 支援卡技能（技能卡追加、事件卡、P 饮料获得等）：只按 ``support_bonus`` 的
  上课倍率近似。影响：支援卡越强、模拟越低估；
- 训练奖励三选一之外的奖励（P 道具、饮料、金钱/粉丝商店）：只看技能卡；
- 考试中对手伤害、元气挡伤害、追击等考试专属规则：考试只按三维加权比大小；
- 体力上限成长、训练/上课的具体随机分布：用固定参数 + 高斯近似。
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from gkagent.data.plans import DEFAULT_PLAN
from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim, greedy_policy
from gkagent.sim.p_items import PItemSpec

ATTRIBUTES = ("Vo", "Da", "Vi")

#: 周行动新名 → 旧名（旧调用方仍可传旧 action 字符串；新代码只用新名）。
ACTION_ALIASES = {
    "lesson": "training",
    "train": "class",
    "train_low": "class_low",
}

#: ``policy.json`` / ``policy_sim.json`` 的 produce 段旧键 → 新键；新键优先。
PRODUCE_KEY_ALIASES = {
    "lesson_every": "training_every",
    "lesson_min_stamina": "training_min_stamina",
    "min_stamina_to_train": "min_stamina_for_class",
    "train_cost": "class_cost",
    "train_p_cost": "class_p_cost",
    "train_gain": "class_gain",
    "train_sigma": "class_sigma",
    "lesson_cost": "training_cost",
    "lesson_targets": "training_targets",
    "lesson_gain_ratio": "training_gain_ratio",
}


def canonical_action(action: str) -> str:
    """旧行动名 → 新行动名（已是新名/未知值原样返回）。"""
    return ACTION_ALIASES.get(action, action)


def normalize_produce_params(raw: Mapping | None) -> dict:
    """policy 的 produce 段：新旧键都保留，新键优先且旧键同步为新值。

    返回的 dict 同时含 ``training_every`` 与 ``lesson_every`` 等两套键：
    新代码读新键，旧外部脚本读旧键，行为一致；旧文件只写旧键也能读。
    """
    result = dict(raw) if isinstance(raw, Mapping) else {}
    for old, new in PRODUCE_KEY_ALIASES.items():
        if new in result:
            result[old] = result[new]
        elif old in result:
            result[new] = result[old]
    return result


# 官方排期/公式（scripts/wiki_formula_ingest.py 生成）。
OFFICIAL_PATH = Path(__file__).resolve().parents[3] / "data" / "knowledge" / "official.json"


@lru_cache(maxsize=4)
def load_official_schedule(path: str | None = None) -> dict:
    """读 official.json；缺失/损坏时返回空 dict（调用方退回旧常数）。"""
    target = Path(path) if path else OFFICIAL_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


@dataclass(frozen=True, init=False)
class ProduceConfig:
    """一局培育的数值配置（默认值 = 官方排期 + 真机实测校准后的口径）。

    命名（2026-11-16 起，对齐游戏术语 / 中文翻译）：

    - 训练 = ``training`` = レッスン：用卡打、涨三维、给卡奖励、耗体力；
    - 上课 = ``class_lesson`` = 授業：选选项涨属性、耗 P 点、不给卡。

    旧名（``train_cost`` / ``lesson_cost`` / ``train_gain`` / ``lesson_gain_ratio``
    等）保留为 property 别名，构造参数也仍接受，至少兼容到 3 个月后。

    校准依据：16 周プロ官方排期 + 真机第二局 **C+ / 5992 评价点 / 三维 971**
    （起始 209/85/75，支援卡 Lv10/10/10/20/10/60）。

    - ``schedule_source="official"``：训练/上课周收益从 ``official.json`` 的
      ``schedule`` 取；缺失才退回 ``class_gain`` / ``training_gain_ratio`` 旧常数。
      官方排期下 300 局默认策略三维 ~990、评价点 P50 ~4747（真机 971/5992）。
    - ``weeks=16`` / ``exam_weeks=(7, 16)``：真机那局是 16 周プロ，旧默认
      12 周（exam 6/12）少 4 个行动周，是旧模拟 620 vs 真机 971 的主因之一。
    - ``training_gain_ratio=0.5``：旧口径 fallback 的训练得分→属性系数；official
      模式不使用（训练属性按 CLEAR/PERFECT 三档结算）。
    - 训练目标三档（official 模式）：``CLEAR = official.clear``、
      ``PERFECT = official.clear + official.perfect``；只有打到 PERFECT 才拿
      CLEAR+PERFECT 的完整属性，只到 CLEAR 只拿 clear 档，未到 CLEAR 为 0。
      缺失 official 时退回 ``training_targets`` 的单值 + 默认 PERFECT=2×CLEAR。
    - ``support_bonus=1.2``：真机支援卡均值 Lv20、SR 档 → 1.2；official 排期
      收益已是最终值，不再乘该倍率。
    - ``audition_coefficient=4.11``：考试/舞台的属性倍率（屏幕「歌唱 411%」），
      真机实测值；训练里倍率 1.0（训练得分/评价校准不受影响）。
    """

    weeks: int = 16
    stamina_max: int = 35
    # P点（游戏内资源）：上课(授業)耗 P，训练(レッスン)不耗
    p_start: int = 150
    class_p_cost: int = 30
    start_stamina: int = 35
    weights: tuple[float, float, float] = (0.40, 0.33, 0.27)  # 审查基准比例
    class_cost: int = 10
    class_gain: int = 75
    class_sigma: float = 6.0
    # 训练没有固定入场耗体（wiki 核实）：体力只在局内按打出的牌结算。
    training_cost: int = 0
    # 训练用当前体力开局（True=wiki 口径；False=旧 stamina_max 口径，仅 ablation）
    training_use_current_stamina: bool = True
    # PERFECT 返还「剩余回合 × 2」体力（wiki 核实；False=旧口径，仅 ablation）
    perfect_stamina_refund: bool = True
    # 指針体力代价（温存减半/強気双倍/2段穿透）；False=旧口径（仅 ablation）
    stance_costs: bool = True
    # 休息回复最大体力的比例（wiki：70%，向下取整）；rest_gain 仅作旧字段兼容
    rest_gain: int = 24
    rest_gain_ratio: float = 0.7
    outing_weeks: tuple[int, ...] = (3, 5, 8, 14)  # 官方排期的空周（可外出）
    exam_weeks: tuple[int, ...] = (7, 16)          # 16 周プロ：期中 7 / 期末 16
    training_targets: tuple[int, ...] = (100, 150, 200, 250, 300)
    # ↑ 仅非 official 兜底的 CLEAR 线；official 模式由 training_target_pair()
    #   从 official.json 的 (clear, perfect) 对取 CLEAR/PERFECT 线。
    support_levels: tuple[int, ...] = (10, 10, 10, 20, 10, 60)  # 真机实测支援卡等级
    support_bonus: float = 1.2      # 上课收益倍率：均值 Lv20 / SR 档（旧 1.35 假设 Lv40）
    # 支援卡レッスンボーナス总和（0.2 = +20%）；wiki：训练收益 ×(1+sum bonus%)
    support_lesson_bonus: float = 0.2
    # 考试名次：score=按局内最终得分排（wiki 核实）；attribute=旧属性加权（仅 ablation）
    exam_rank_mode: str = "score"
    # NPC 考试得分档（期中真机实测 603/387/206/205；期末缺数据，沿用同档）
    exam_npc_scores: tuple[tuple[int, ...], ...] = (
        (603, 387, 206, 205),
        (603, 387, 206, 205),
    )
    # 考试回合数：期中 9；期末 Sense/Anomaly 12、Logic 11（wiki 核实）
    exam_turns_mid: int = 9
    exam_turns_final: int = 12
    exam_turns_final_logic: int = 11
    # P 道具（被动）：默认空；传入后由 LessonSim 在课程 step 内触发
    p_items: tuple[PItemSpec, ...] = ()
    training_gain_ratio: float = 0.5  # 旧口径：训练得分→属性；official 模式改用官方排期
    # official：按 data/knowledge/official.json 的逐周收益；constants：退回旧常数
    schedule_source: str = "official"
    schedule_path: str | None = None  # 测试/离线可注入另一份 official.json
    reward_pick: str = "best"       # best=选最强卡 / random=随机 / none=不拿
    # 考试：6 人里进前 3 才算合格。基准分按真机标定：
    # 实拍期末 1st 589 / 2nd 406 / 3rd 203 / 4th 201 / 5th 195，我们 632 属性 = 6th（不合格）
    exam_base: tuple[float, ...] = (85.0, 205.0)     # 期中/期末第3名基准（期中真机能过，设为100）
    npc_factors: tuple[float, ...] = (2.9, 2.0, 1.0, 0.99, 0.95)  # 5 个对手相对第 3 名的倍数
    fans_per_clear: int = 800
    remove_weeks: tuple[int, ...] = ()       # 咨询删卡（默认关：占一周去删 1 张，模型里是负收益）
    min_deck_size: int = 8                   # 牌组不低于此张数才删
    # 出牌方案（プラン）：three-plan 打法配置，从 data/knowledge/plans.json 读
    plan: str = DEFAULT_PLAN
    # 考试/舞台属性倍率（真机屏幕「歌唱 411%」= 4.11，实测校准 C+/5577）。
    # 训练里倍率 ≈ 1.0：LessonConfig 默认 1.0，训练得分不受影响。
    audition_coefficient: float = 4.11

    def __init__(
        self,
        weeks: int | None = None,
        stamina_max: int | None = None,
        p_start: int | None = None,
        class_p_cost: int | None = None,
        start_stamina: int | None = None,
        weights: tuple[float, float, float] | None = None,
        class_cost: int | None = None,
        class_gain: int | None = None,
        class_sigma: float | None = None,
        training_cost: int | None = None,
        training_use_current_stamina: bool | None = None,
        perfect_stamina_refund: bool | None = None,
        stance_costs: bool | None = None,
        rest_gain: int | None = None,
        rest_gain_ratio: float | None = None,
        support_lesson_bonus: float | None = None,
        exam_rank_mode: str | None = None,
        exam_npc_scores: tuple[tuple[int, ...], ...] | None = None,
        exam_turns_mid: int | None = None,
        exam_turns_final: int | None = None,
        exam_turns_final_logic: int | None = None,
        p_items: tuple[PItemSpec, ...] | None = None,
        outing_weeks: tuple[int, ...] | None = None,
        exam_weeks: tuple[int, ...] | None = None,
        training_targets: tuple[int, ...] | None = None,
        support_levels: tuple[int, ...] | None = None,
        support_bonus: float | None = None,
        training_gain_ratio: float | None = None,
        schedule_source: str | None = None,
        schedule_path: str | None = None,
        reward_pick: str | None = None,
        exam_base: tuple[float, ...] | None = None,
        npc_factors: tuple[float, ...] | None = None,
        fans_per_clear: int | None = None,
        remove_weeks: tuple[int, ...] | None = None,
        min_deck_size: int | None = None,
        plan: str | None = None,
        audition_coefficient: float | None = None,
        *,
        # ---- 旧名（兼容别名，新名优先）----
        train_p_cost: int | None = None,
        train_cost: int | None = None,
        train_gain: int | None = None,
        train_sigma: float | None = None,
        lesson_cost: int | None = None,
        lesson_targets: tuple[int, ...] | None = None,
        lesson_gain_ratio: float | None = None,
    ) -> None:
        def pick(new, old, default):
            if new is not None:
                return new
            if old is not None:
                return old
            return default

        values = {
            "weeks": pick(weeks, None, 16),
            "stamina_max": pick(stamina_max, None, 35),
            "p_start": pick(p_start, None, 150),
            "class_p_cost": pick(class_p_cost, train_p_cost, 30),
            "start_stamina": pick(start_stamina, None, 35),
            "weights": pick(weights, None, (0.40, 0.33, 0.27)),
            "class_cost": pick(class_cost, train_cost, 10),
            "class_gain": pick(class_gain, train_gain, 75),
            "class_sigma": pick(class_sigma, train_sigma, 6.0),
            "training_cost": pick(training_cost, lesson_cost, 0),
            "training_use_current_stamina": pick(
                training_use_current_stamina, None, True
            ),
            "perfect_stamina_refund": pick(perfect_stamina_refund, None, True),
            "stance_costs": pick(stance_costs, None, True),
            "rest_gain": pick(rest_gain, None, 24),
            "rest_gain_ratio": pick(rest_gain_ratio, None, 0.7),
            "support_lesson_bonus": pick(support_lesson_bonus, None, 0.2),
            "exam_rank_mode": pick(exam_rank_mode, None, "score"),
            "exam_npc_scores": pick(
                exam_npc_scores, None, ((603, 387, 206, 205), (603, 387, 206, 205))
            ),
            "exam_turns_mid": pick(exam_turns_mid, None, 9),
            "exam_turns_final": pick(exam_turns_final, None, 12),
            "exam_turns_final_logic": pick(exam_turns_final_logic, None, 11),
            "p_items": pick(p_items, None, ()),
            "outing_weeks": pick(outing_weeks, None, (3, 5, 8, 14)),
            "exam_weeks": pick(exam_weeks, None, (7, 16)),
            "training_targets": pick(training_targets, lesson_targets, (100, 150, 200, 250, 300)),
            "support_levels": pick(support_levels, None, (10, 10, 10, 20, 10, 60)),
            "support_bonus": pick(support_bonus, None, 1.2),
            "training_gain_ratio": pick(training_gain_ratio, lesson_gain_ratio, 0.5),
            "schedule_source": pick(schedule_source, None, "official"),
            "schedule_path": pick(schedule_path, None, None),
            "reward_pick": pick(reward_pick, None, "best"),
            "exam_base": pick(exam_base, None, (85.0, 205.0)),
            "npc_factors": pick(npc_factors, None, (2.9, 2.0, 1.0, 0.99, 0.95)),
            "fans_per_clear": pick(fans_per_clear, None, 800),
            "remove_weeks": pick(remove_weeks, None, ()),
            "min_deck_size": pick(min_deck_size, None, 8),
            "plan": pick(plan, None, DEFAULT_PLAN),
            "audition_coefficient": pick(audition_coefficient, None, 4.11),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    # ---- 旧字段名：只读 property 别名（旧代码/测试/外部脚本继续可用）----
    @property
    def train_p_cost(self) -> int:
        return self.class_p_cost

    @property
    def train_cost(self) -> int:
        return self.class_cost

    @property
    def train_gain(self) -> int:
        return self.class_gain

    @property
    def train_sigma(self) -> float:
        return self.class_sigma

    @property
    def lesson_cost(self) -> int:
        return self.training_cost

    @property
    def lesson_targets(self) -> tuple[int, ...]:
        """旧名别名：非 official 兜底的 CLEAR 线（official 用 training_target_pair）。"""
        return self.training_targets

    @property
    def lesson_gain_ratio(self) -> float:
        return self.training_gain_ratio


@dataclass
class ProduceResult:
    attrs: tuple[int, int, int]
    fans: int
    trainings: int
    cleared: int
    exams_passed: int
    grade: str
    # 终试原始得分（已乘考试属性倍率），喂 eval_value / exam_score_points 用
    exam_score: int = 0

    @property
    def lessons(self) -> int:
        """旧名别名：``trainings``（训练次数）。"""
        return self.trainings

    @property
    def total(self) -> int:
        return sum(self.attrs)


# 官方评价公式（wiki/NGA 解包，剧本「初」レギュラー/プロ/マスター）
RANK_POINTS = {1: 1700, 2: 900, 3: 500}
SCORE_BRACKETS = ((5000, 0.30), (10000, 0.15), (20000, 0.08), (30000, 0.04), (40000, 0.02), (10**9, 0.01))
EVAL_RANKS = (
    (35000, "S5"), (30000, "S4+"), (26000, "S4"), (23000, "SSS+"), (20000, "SSS"),
    (18000, "SS+"), (16000, "SS"), (14500, "S+"), (13000, "S"), (11500, "A+"),
    (10000, "A"), (8000, "B+"), (6000, "B"), (4500, "C+"), (3000, "C"),
)


def exam_score_points(score: int) -> int:
    """终试得分 → 评价点（分段倍率）。"""
    points = 0.0
    lower = 0
    for upper, rate in SCORE_BRACKETS:
        if score <= lower:
            break
        points += (min(score, upper) - lower) * rate
        lower = upper
    return int(points)


def grade_for(total: int, rank: int = 3, exam_score: int | None = None) -> str:
    """官方评价：顺位点 + 2.3×三维总和 + 终试得分换算 → 评价字母。"""
    if exam_score is None:
        exam_score = total * 2  # 没有终试分数时的保守近似
    value = RANK_POINTS.get(rank, 0) + int(2.3 * total) + exam_score_points(exam_score)
    for limit, grade in EVAL_RANKS:
        if value >= limit:
            return grade
    return "E"


def eval_value(total: int, rank: int = 3, exam_score: int | None = None) -> int:
    if exam_score is None:
        exam_score = total * 2
    return RANK_POINTS.get(rank, 0) + int(2.3 * total) + exam_score_points(exam_score)


def training_policy(sim) -> int | None:
    """训练内策略：目标 PERFECT（CLEAR+PERFECT 满档），不是打够 CLEAR 就收手。

    没到 PERFECT 线时按"单张总分最大"选牌（先把缺口补上），到线后才回到
    分数/体力性价比；最后一回合同样按总分最大。旧名 ``lesson_policy`` 保留为
    模块级别名。
    """
    legal = [index for index in sim.legal_actions() if index is not None]
    if not legal:
        return None
    condition = sim.buffs.condition_turns > 0

    def value(index: int) -> float:
        card = sim.hand[index]
        base = card.score + sim.buffs.focus
        if condition:
            base = int(base * 1.5)
        return float(base)

    scored = [(index, value(index)) for index in legal if value(index) > 0]
    if not scored:
        return min(legal, key=lambda i: (sim._effective_cost(sim.hand[i]), i))
    if sim.score < sim.target_perfect:
        scored.sort(
            key=lambda item: (
                item[1],
                -sim._effective_cost(sim.hand[item[0]]),
                -item[0],
            ),
            reverse=True,
        )
        return scored[0][0]
    scored.sort(
        key=lambda item: (
            item[1] / max(sim._effective_cost(sim.hand[item[0]]), 1),
            item[1],
        ),
        reverse=True,
    )
    return scored[0][0]


# 旧名别名（模块级函数）：`lesson_policy` → `training_policy`
lesson_policy = training_policy


_REWARD_TABLE = None
_REWARD_CACHE: dict[str, float] = {}


def _reward_value(card) -> float:
    """模拟器选奖励也用与真机同一套估值（CardTable.value），否则 buff/SSR 新卡永远进不了牌组。"""
    global _REWARD_TABLE
    name = str(getattr(card, "name", "")).split("#")[0]
    cached = _REWARD_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        if _REWARD_TABLE is None:
            from gkagent.data.card_table import CardTable

            _REWARD_TABLE = CardTable()
        value = _REWARD_TABLE.value(name)
    except Exception:  # noqa: BLE001 - 估值失败退回白值
        value = None
    if value is None:
        return float(getattr(card, "score", 0)) / max(int(getattr(card, "cost", 1) or 1), 1)
    _REWARD_CACHE[name] = float(value)
    return float(value)


class ProduceSim:
    """一局培育。`strategy(state) -> action` 由外部传入，便于比较不同打法。"""

    def __init__(
        self,
        deck: list[CardSpec],
        config: ProduceConfig | None = None,
        rng_seed: int = 0,
    ) -> None:
        self.config = config or ProduceConfig()
        self.deck = list(deck)
        self.rng = random.Random(rng_seed)
        self.attrs = [0, 0, 0]  # Vo / Da / Vi
        self.stamina = self.config.start_stamina
        self.week = 1
        self.fans = 0
        self.p_point = int(getattr(self.config, "p_start", 0) or 0)
        self.trainings = 0
        self.cleared = 0
        self.exams_passed = 0
        self.log: list[str] = []
        self.reward_pool: list[CardSpec] = []
        self.reward_picks = 0
        self.trace: list[dict] = []       # 每周快照，给前端回放用
        self.training_policy_fn = training_policy  # 可注入真机 LessonPolicy 适配器
        self.last_training: dict | None = None
        self.last_exam: dict | None = None
        self._official = (
            load_official_schedule(self.config.schedule_path)
            if self.config.schedule_source == "official"
            else {}
        )
        self._schedule_by_week: dict[int, dict] = {}
        for row in self._official.get("schedule") or ():
            try:
                self._schedule_by_week[int(row["week"])] = row
            except (KeyError, TypeError, ValueError):
                continue

    # ---- 旧属性名：兼容别名 ----
    @property
    def lessons(self) -> int:
        return self.trainings

    @lessons.setter
    def lessons(self, value: int) -> None:
        self.trainings = value

    @property
    def lesson_policy_fn(self):
        return self.training_policy_fn

    @lesson_policy_fn.setter
    def lesson_policy_fn(self, value) -> None:
        self.training_policy_fn = value

    @property
    def last_lesson(self) -> dict | None:
        return self.last_training

    @last_lesson.setter
    def last_lesson(self, value: dict | None) -> None:
        self.last_training = value

    # ------------------------------------------------------------------ 局面
    @property
    def done(self) -> bool:
        return self.week > self.config.weeks

    def stamina_ratio(self) -> float:
        return self.stamina / self.config.stamina_max

    def weighted(self) -> float:
        return sum(a * w for a, w in zip(self.attrs, self.config.weights))

    def best_attribute(self) -> int:
        return max(range(3), key=lambda i: self.config.weights[i])

    def lagging_attribute(self) -> int:
        return min(range(3), key=lambda i: self.attrs[i])

    def can_afford(self, cost: int) -> bool:
        return self.stamina >= cost

    # ------------------------------------------------------------------ 行动
    def official_entry(self, week: int | None = None) -> dict | None:
        """当前周（或指定周）的官方排期行；非 official 模式返回 None。"""
        if self.config.schedule_source != "official":
            return None
        return self._schedule_by_week.get(self.week if week is None else week)

    def _class_base(self) -> tuple[float, bool]:
        """上课基础收益；第二项表示是否来自 official 排期（是则不再乘支援倍率）。

        注：official.json 沿用历史 schema：``train_clear`` 是该周「旧 train()
        = 现在的 class_lesson()」的基准收益；这里只为兼容旧数据，不改数值口径。
        """
        entry = self.official_entry()
        if entry is not None and entry.get("train_clear") is not None:
            return float(entry["train_clear"]), True
        return float(self.config.class_gain), False

    def _official_training_gain(self, score: int, grade: str = "") -> int | None:
        """官方排期的训练属性成长：按 CLEAR/PERFECT 的**已达成进度**连续结算。

        wiki 口径：
        ``gain = min(score, clear) + min(max(score-clear, 0), perfect)``，
        再乘支援卡レッスンボーナス ``(1 + support_lesson_bonus)``，向下取整。
        ``score=50 / clear=40 / perfect=25`` → 40 + 10 = 50（support=0 时）；
        score 未到 CLEAR 时按已达成部分给分（= score），不是整档 0；未打满的
        PERFECT 部分拿不到。``grade`` 只保留给旧调用方兼容，不参与计算。

        注：official.json 沿用历史 schema：``clear``/``perfect`` 是该周训练
        （旧 lesson() = 现在的 training()）的基础收益；这里只为兼容旧数据。
        """
        entry = self.official_entry()
        if entry is None:
            return None
        try:
            clear = max(int(entry.get("clear") or 0), 0)
            perfect = max(int(entry.get("perfect") or 0), 0)
        except (TypeError, ValueError):
            return None
        value = max(int(score), 0)
        base = min(value, clear) + min(max(value - clear, 0), perfect)
        # 支援卡レッスンボーナス：(CLEAR+PERFECT) 收益 ×(1+sum bonus%)，向下取整
        return int(base * (1.0 + float(self.config.support_lesson_bonus)))

    def training_target_pair(self, week: int | None = None) -> tuple[int, int]:
        """本周训练的 ``(CLEAR 线, PERFECT 线)``。

        official 模式直接从 ``official.json`` 的 ``(clear, perfect)`` 取：
        ``CLEAR = clear``、``PERFECT = clear + perfect``（perfect 是"达标后
        再往上打到的额外值"，不是独立阈值）。缺 official 时退回
        ``training_targets`` 的单值 CLEAR + 默认 PERFECT=2×CLEAR。
        """
        entry = self.official_entry(week)
        if entry is not None:
            try:
                clear = int(entry.get("clear") or 0)
                perfect = int(entry.get("perfect") or 0)
            except (TypeError, ValueError):
                clear = perfect = 0
            if clear > 0:
                return clear, clear + max(perfect, 0)
        # 非 official / 缺字段：旧单值表 + 默认 PERFECT=2×CLEAR
        stage = min(
            len(self.config.training_targets) - 1,
            (self.week - 1) * len(self.config.training_targets)
            // max(self.config.weeks, 1),
        )
        clear = int(self.config.training_targets[stage])
        return clear, clear * 2

    def class_lesson(self, index: int) -> bool:
        """上课(授業)：属性 +N、耗 P 点；体力/P 不足则**不发生**并返回 False。

        真机体力/P 不够时上课不成立（不是扣成负数），所以这里先查再扣，
        只有成功的上课才给属性。旧名 ``train()`` 保留为别名。
        """
        cost = self.config.class_cost
        p_cost = int(getattr(self.config, "class_p_cost", 0) or 0)
        if self.stamina < cost:
            self.log.append(f"W{self.week} class{ATTRIBUTES[index]} failed stamina{self.stamina}<{cost}")
            return False
        if p_cost and getattr(self, "p_point", 0) < p_cost:
            self.log.append(f"W{self.week} class{ATTRIBUTES[index]} failed P{getattr(self, 'p_point', 0)}<{p_cost}")
            return False
        self.stamina = max(0, self.stamina - cost)
        if p_cost:
            self.p_point -= p_cost
        base, from_official = self._class_base()
        if not from_official:
            base *= self.config.support_bonus
        gain = max(1, int(self.rng.gauss(base, self.config.class_sigma)))
        self.attrs[index] += gain
        self.log.append(f"W{self.week} class{ATTRIBUTES[index]}+{gain}")
        return True

    def _recovery_gain(self) -> int:
        """休息/外出的体力回复：默认最大体力的 70%（向下取整）。"""
        ratio = getattr(self.config, "rest_gain_ratio", 0.0) or 0.0
        if ratio > 0:
            return int(self.config.stamina_max * ratio)
        return int(self.config.rest_gain)

    def rest(self) -> bool:
        """休息：回复最大体力的 70%（向下取整）；满体力时不可选（no-op False）。"""
        if self.stamina >= self.config.stamina_max:
            self.log.append(f"W{self.week} rest skipped (full stamina)")
            return False
        self.stamina = min(
            self.config.stamina_max, self.stamina + self._recovery_gain()
        )
        self.log.append(f"W{self.week} rest")
        return True

    def outing(self) -> None:
        self.stamina = min(
            self.config.stamina_max, self.stamina + self._recovery_gain()
        )
        reward = self.pick_reward()
        if reward is not None:
            self.deck.append(reward)
            self.reward_picks += 1
        self.log.append(f"W{self.week} outing" + (f" +card:{reward.name.split('#')[0]}" if reward else ""))

    def pick_reward(self) -> CardSpec | None:
        """训练奖励三选一：按 分数/体力 选最强的一张进牌组。"""
        if not self.reward_pool or self.config.reward_pick == "none":
            return None
        if self.config.reward_pick == "random":
            return self.rng.choice(self.reward_pool)
        best = max(
            self.reward_pool,
            key=lambda card: (_reward_value(card), card.score),
        )
        return best

    def training(self) -> bool:
        """训练(レッスン)：跑训练模拟器；体力不足时**打不出牌**，返回 False。

        真机在体力不足时进训练只能一直 SKIP（不会把体力扣成负数）。这里直接
        判定失败：不跑训练、不加属性、不拿奖励，只记一次失败训练（grade=FAILED），
        让调用方/策略知道该休息。旧名 ``lesson()`` 保留为别名。
        """
        cost = self.config.training_cost
        min_card_cost = min((int(card.cost) for card in self.deck), default=0)
        gate = max(cost, min_card_cost if cost == 0 else cost)
        if self.stamina < gate:
            self.trainings += 1
            self.last_training = {
                "target": None,
                "score": 0,
                "grade": "FAILED",
                "plays": [],
                "reward": None,
                "reason": f"stamina {self.stamina} < {gate}",
                "attr_gain": 0,
                "gain_source": "gate",
            }
            self.log.append(f"W{self.week} training failed stamina{self.stamina}<{gate}")
            return False
        self.stamina = max(0, self.stamina - cost)
        # 训练目标是 PERFECT（CLEAR+PERFECT 满档），不是只到 CLEAR 就收手。
        target_clear, target_perfect = self.training_target_pair()
        plays: list[dict] = []

        base_policy = getattr(self, "training_policy_fn", None) or training_policy

        def traced_policy(inner):
            action = base_policy(inner)
            if action is None:
                plays.append({"skip": True, "turn": inner.turns_left})
            else:
                card = inner.hand[action]
                plays.append(
                    {
                        "card": card.name.split("#")[0],
                        "cost": card.cost,
                        "base": card.score,
                        "focus": inner.buffs.focus,
                        "condition": inner.buffs.condition_turns > 0,
                        "turn": inner.turns_left,
                    }
                )
            return action

        sim = LessonSim(
            self.deck,
            LessonConfig(
                turns=5,
                # 训练没有固定入场耗体：用当前体力开局，局内按牌结算
                stamina=(
                    self.stamina
                    if self.config.training_use_current_stamina
                    else self.config.stamina_max
                ),
                target_clear=target_clear,
                target_perfect=target_perfect,
                hand_size=3,
                plan=self.config.plan,
                stance_costs=self.config.stance_costs,
                p_items=self.config.p_items,
            ),
            rng_seed=self.rng.randrange(1 << 30),
        )
        score, grade = sim.run(traced_policy)
        # 局内实际消耗体力写回；PERFECT 返还「剩余回合 × 2」体力（wiki 核实）
        if self.config.training_use_current_stamina:
            self.stamina = max(0, sim.stamina)
        if self.config.perfect_stamina_refund and grade == "PERFECT":
            self.stamina = min(
                self.config.stamina_max, self.stamina + max(sim.turns_left, 0) * 2
            )
        self.trainings += 1
        if grade in ("CLEAR", "PERFECT"):
            self.cleared += 1
            self.fans += self.config.fans_per_clear
        # 训练的属性成长：official 模式按三档结算（FAILED=0 / CLEAR=clear /
        # PERFECT=clear+perfect）；旧口径才用 score×ratio，FAILED 同样不给属性。
        order = sorted(range(3), key=lambda i: self.config.weights[i], reverse=True)
        target_attr = order[self.trainings % 3]
        official_gain = self._official_training_gain(score, grade)
        if official_gain is not None:
            gain = official_gain
            gain_source = "official"
        else:
            # 支援卡レッスンボーナス：训练收益 ×(1+sum bonus%)，向下取整
            support_factor = 1.0 + float(self.config.support_lesson_bonus)
            gain = (
                0
                if grade == "FAILED"
                else int(score * self.config.training_gain_ratio * support_factor)
            )
            gain_source = "constants"
        self.attrs[target_attr] += gain
        # 训练奖励：真机每次训练后都有三选一，所以不管 CLEAR 都给（这才是牌组变强的来源）
        reward = self.pick_reward()
        if reward is not None:
            self.deck.append(reward)
            self.reward_picks += 1
        self.last_training = {
            "target": target_clear,
            "target_clear": target_clear,
            "target_perfect": target_perfect,
            "reward_tier": sim.reward_tier,
            "score": score,
            "grade": grade,
            "plays": plays,
            "reward": reward.name.split("#")[0] if reward else None,
            "attr_gain": gain,
            "gain_source": gain_source,
            # 训练逐回合 trace（SKIP 会记 skipped=True，剩余手牌弃掉且不回复体力）
            "turns": [dict(row) for row in sim.trace],
            "skipped": any(row.get("skipped") for row in sim.trace),
        }
        self.log.append(
            f"W{self.week} training CLEAR{target_clear}/PERFECT{target_perfect} "
            f"score{score} {grade} +{gain}"
        )
        return True

    # ---- 旧方法名别名（旧代码/测试/外部脚本继续可用）----
    train = class_lesson
    lesson = training

    # ------------------------------------------------------------------ 学期
    def exam(self, index: int) -> dict:
        """6 人考试：名次按**局内最终得分**与 NPC 得分档比较（wiki 核实）。

        旧实现拿属性加权 ``weighted()`` 与 NPC 比，这是 bug；属性只用于最终评价点，
        不进考试名次。NPC 得分档默认期中实测 603/387/206/205（期末缺数据沿用）。
        考试回合数：期中 9；期末 Sense/Anomaly 12、Logic 11。

        终试得分 = 牌组跑考试模拟器的总分（每张牌 × 属性倍率 411%），作为
        ``eval_value`` / ``exam_score_points`` 的输入。
        """
        power = self.weighted()
        # 考试/舞台得分：用当前牌组跑考试（每张牌得分 × 属性倍率 411%）
        if index == 0:
            turns = int(self.config.exam_turns_mid)
        elif str(self.config.plan) == "logic":
            turns = int(self.config.exam_turns_final_logic)
        else:
            turns = int(self.config.exam_turns_final)
        exam_sim = LessonSim(
            list(self.deck),
            LessonConfig(
                turns=turns,
                stamina=self.config.stamina_max,
                target_clear=0,
                hand_size=3,
                attribute_coefficient=self.config.audition_coefficient,
                plan=self.config.plan,
                stance_costs=self.config.stance_costs,
                p_items=self.config.p_items,
            ),
            rng_seed=self.rng.randrange(1_000_000),
        )
        exam_sim.run(greedy_policy)
        exam_score = int(exam_sim.score)

        score_tiers = self.config.exam_npc_scores
        tier = score_tiers[min(index, len(score_tiers) - 1)] if score_tiers else ()
        if str(self.config.exam_rank_mode) == "attribute":
            # 仅 ablation：旧属性加权口径
            base = self.config.exam_base[min(index, len(self.config.exam_base) - 1)]
            opponents = [base * factor for factor in self.config.npc_factors]
            rank = 1 + sum(1 for value in opponents if value > power)
        else:
            opponents = [float(value) for value in tier]
            rank = 1 + sum(1 for value in opponents if value > exam_score)
        passed = rank <= 3
        if passed:
            self.exams_passed += 1
            self.fans += 3000
        self.last_exam = {
            "rank": rank,
            "power": round(power, 1),
            "passed": passed,
            "npc": [round(value, 1) for value in opponents],
            # 终试原始得分（已乘考试属性倍率）：官方评价公式的输入
            "score": exam_score,
            "turns": turns,
            "rank_mode": str(self.config.exam_rank_mode),
        }
        return self.last_exam

    def last_exam_score(self) -> int:
        """最近一次考试的原始得分（已乘属性倍率）；没有考试记录时用同一 proxy 兜底。"""
        for row in reversed(self.trace):
            exam = row.get("exam") or {}
            if "score" in exam:
                return int(exam["score"])
        return int(sum(self.attrs) * 2 * self.config.audition_coefficient)

    def step(self, strategy) -> None:
        cfg = self.config
        # 咨询删卡：把最弱的一张删掉（真机"咨询"就是删牌，能大幅提高循环质量）
        if self.week in cfg.remove_weeks and len(self.deck) > cfg.min_deck_size:
            worst = min(range(len(self.deck)), key=lambda i: (self.deck[i].score, self.deck[i].cost))
            removed = self.deck.pop(worst)
            self.trace.append(
                {
                    "week": self.week,
                    "action": "remove",
                    "stamina_before": self.stamina,
                    "stamina_after": self.stamina,
                    "attrs_before": list(self.attrs),
                    "attrs_after": list(self.attrs),
                    "training": {"removed": removed.name.split("#")[0]},
                    "lesson": {"removed": removed.name.split("#")[0]},
                }
            )
            self.week += 1
            return
        if self.week in cfg.exam_weeks:
            index = cfg.exam_weeks.index(self.week)
            self.exam(index)
            self.trace.append(
                {
                    "week": self.week,
                    "action": "exam",
                    "stamina_before": self.stamina,
                    "stamina_after": self.stamina,
                    "attrs_before": list(self.attrs),
                    "attrs_after": list(self.attrs),
                    "training": None,
                    "lesson": None,
                    "exam": self.last_exam,
                }
            )
            self.week += 1
            return
        action = strategy(self)
        action_kind = canonical_action(action)
        self.last_training = None
        stamina_before = self.stamina
        attrs_before = list(self.attrs)
        ok = True
        if action_kind == "class":
            ok = self.class_lesson(self.best_attribute())
        elif action_kind == "class_low":
            ok = self.class_lesson(self.lagging_attribute())
        elif action_kind == "rest":
            self.rest()
        elif action_kind == "outing":
            self.outing()
        elif action_kind == "training":
            ok = self.training()
        else:
            ok = self.class_lesson(self.best_attribute())
        row = {
            "week": self.week,
            "action": action,
            "stamina_before": stamina_before,
            "stamina_after": self.stamina,
            "attrs_before": attrs_before,
            "attrs_after": list(self.attrs),
            # 新键 + 旧键（旧可视化/外部脚本仍读 "lesson"）
            "training": self.last_training,
            "lesson": self.last_training,
        }
        if not ok:
            row["failed"] = True
        self.trace.append(row)
        self.week += 1

    def run(self, strategy) -> ProduceResult:
        while not self.done:
            self.step(strategy)
        last_rank = 3
        for row in reversed(self.trace):
            if row.get("exam"):
                last_rank = row["exam"]["rank"]
                break
        total = sum(self.attrs)
        # 终试得分：考试/舞台吃属性倍率（默认 4.11），训练仍是 1.0
        exam_score = self.last_exam_score()
        return ProduceResult(
            attrs=tuple(self.attrs),
            fans=self.fans,
            trainings=self.trainings,
            cleared=self.cleared,
            exams_passed=self.exams_passed,
            grade=grade_for(total, last_rank, exam_score),
            exam_score=exam_score,
        )


# ---------------------------------------------------------------------- 策略参数
@dataclass(frozen=True, init=False)
class StrategyParams:
    """可搜的策略参数：行动节奏 + 练哪个属性。

    新名：``training_every`` / ``training_min_stamina`` / ``min_stamina_for_class``；
    旧名 ``lesson_every`` / ``lesson_min_stamina`` / ``min_stamina_to_train``
    仍可作构造参数（新名优先），也可作为 property 读取。
    """

    rest_threshold: int = 10        # 体力低于此 → 休息
    training_every: int = 1         # 每 N 周做一次训练(レッスン)；0 = 不做
    training_min_stamina: int = 12  # 体力低于此不做训练（真机 0 体力进训练打不出牌）
    attr_choice: str = "weight"     # weight=练权重最高 / lowest=补短板 / rotate=轮转
    outing_below: int = -1          # 体力低于此且本周有外出 → 先外出（-1 关闭）
    min_stamina_for_class: int = 10  # 低于此不上课(授業)

    def __init__(
        self,
        rest_threshold: int | None = None,
        training_every: int | None = None,
        training_min_stamina: int | None = None,
        attr_choice: str | None = None,
        outing_below: int | None = None,
        min_stamina_for_class: int | None = None,
        *,
        # ---- 旧名（兼容别名，新名优先）----
        lesson_every: int | None = None,
        lesson_min_stamina: int | None = None,
        min_stamina_to_train: int | None = None,
    ) -> None:
        def pick(new, old, default):
            if new is not None:
                return new
            if old is not None:
                return old
            return default

        values = {
            "rest_threshold": pick(rest_threshold, None, 10),
            "training_every": pick(training_every, lesson_every, 1),
            "training_min_stamina": pick(training_min_stamina, lesson_min_stamina, 12),
            "attr_choice": pick(attr_choice, None, "weight"),
            "outing_below": pick(outing_below, None, -1),
            "min_stamina_for_class": pick(min_stamina_for_class, min_stamina_to_train, 10),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    # ---- 旧字段名：只读 property 别名 ----
    @property
    def lesson_every(self) -> int:
        return self.training_every

    @property
    def lesson_min_stamina(self) -> int:
        return self.training_min_stamina

    @property
    def min_stamina_to_train(self) -> int:
        return self.min_stamina_for_class

    def as_dict(self) -> dict[str, int | str]:
        """新键参数字典（写 policy_sim.json / 日志用）。"""
        return {
            "rest_threshold": self.rest_threshold,
            "training_every": self.training_every,
            "training_min_stamina": self.training_min_stamina,
            "attr_choice": self.attr_choice,
            "outing_below": self.outing_below,
            "min_stamina_for_class": self.min_stamina_for_class,
        }


def strategy_from_params(params: StrategyParams):
    """把参数变成执行函数（模拟器与真机共用的同一套节奏）。"""

    def strategy(state: ProduceSim) -> str:
        cfg = state.config
        if state.stamina < params.rest_threshold:
            return "rest"
        if params.outing_below >= 0 and state.stamina < params.outing_below and state.week in cfg.outing_weeks:
            return "outing"
        if params.training_every > 0 and state.week % params.training_every == 0:
            # 体力门：真机 0 体力进训练一张牌都打不出，只能 SKIP 白送回合。
            # 不够 training_min_stamina 就改休息，等下周有体力再训练。
            if state.stamina < params.training_min_stamina:
                return "rest"
            return "training"
        if state.stamina < params.min_stamina_for_class:
            return "rest"
        if params.attr_choice == "lowest":
            return "class_low"
        return "class"

    return strategy


# ---------------------------------------------------------------------- 策略
def strategy_class_best(state: ProduceSim) -> str:
    """总是按审查基准最高的属性上课(授業)（体力不够就休息）。"""
    if state.stamina < state.config.class_cost:
        return "rest"
    return "class"


def strategy_class_lowest(state: ProduceSim) -> str:
    """总是给最低属性上课(補短板，均衡成长)。"""
    if state.stamina < state.config.class_cost:
        return "rest"
    return "class_low"


def strategy_training_heavy(state: ProduceSim) -> str:
    """优先训练(レッスン)（拿卡+粉丝），没体力就休息。"""
    if state.stamina < state.config.training_cost:
        return "rest"
    return "training"


def strategy_smart(state: ProduceSim) -> str:
    """体力够就上课，每 3 周做一次训练(レッスン)。"""
    if state.stamina < state.config.class_cost:
        return "rest"
    return "training" if state.week % 3 == 0 else "class"


def strategy_mixed(state: ProduceSim) -> str:
    """体力 <40% 休息，否则 上课:训练 = 3:1。"""
    if state.stamina_ratio() < 0.4:
        return "rest"
    return "training" if state.week % 4 == 0 else "class"


def strategy_optimal(state: ProduceSim) -> str:
    """逐周择优：比较该周「训练收益(CLEAR+PERFECT)」与「上课收益(train_clear)」，取大的。

    依据官方排期（data/knowledge/official.json）：
    - 前期训练更赚（W1-5：65-75 vs 上课 40-73）
    - 中后期上课反超（W6-14：82-148 vs 训练 75-130）
    - 追い込み周（W15）训练暴涨（96+25 与 class 165）仍按数值比较
    """
    entry = state.official_entry()
    if entry is None:
        return "rest"
    training_gain = int(entry.get("clear") or 0) + int(entry.get("perfect") or 0)
    class_gain = int(entry.get("train_clear") or 0)
    prefer_training = training_gain >= class_gain
    if prefer_training and state.stamina >= state.config.training_cost:
        return "training"
    if not prefer_training and state.stamina >= state.config.class_cost:
        return "class"
    if state.stamina >= state.config.class_cost:
        return "class"
    if state.stamina >= state.config.training_cost:
        return "training"
    return "rest"


def strategy_official(state: ProduceSim) -> str:
    """按 official.json 的逐周排期行动；体力不足则休息。

    这是「按官方排期跑 300 局」用的策略：排期里的空周休息、考试周由 step()
    自动处理；普通周按 action 走。official.json 的 action 键沿用历史 schema：
    ``lesson`` = 旧 lesson()（现在的 training()），``train`` = 旧 train()
    （现在的 class_lesson()）——只在读取旧数据时做映射，不改数值口径。
    """
    entry = state.official_entry()
    if entry is None:
        return "rest"
    action = entry.get("action")
    if action == "lesson":
        return "training" if state.stamina >= state.config.training_cost else "rest"
    if action == "train":
        return "class" if state.stamina >= state.config.class_cost else "rest"
    return "rest"


# 旧策略函数名别名（旧脚本/外部 import 继续可用）
strategy_train_best = strategy_class_best
strategy_train_lowest = strategy_class_lowest
strategy_lesson_heavy = strategy_training_heavy

STRATEGIES = {
    # 新名
    "class_best": strategy_class_best,
    "class_lowest": strategy_class_lowest,
    "training_heavy": strategy_training_heavy,
    "mixed": strategy_mixed,
    "smart": strategy_smart,
    "official": strategy_official,
    # 旧名别名（至少保留 3 个月）
    "train_best": strategy_class_best,
    # 对比实验（训练 vs 上课）里用 pure_train 表示"只做旧 train()、体力不够就休息"
    "pure_train": strategy_class_best,
    "pure_class": strategy_class_best,
    "train_lowest": strategy_class_lowest,
    "lesson_heavy": strategy_training_heavy,
}


def random_strategy(seed: int):
    """随机打法基线（各种行动都用），用于说明"乱打"的下限。"""
    rng = random.Random(seed)

    def strategy(state: ProduceSim) -> str:
        if state.stamina < 8:
            return "rest"
        return rng.choice(["class", "class_low", "training", "rest", "outing"])

    return strategy
