"""培育（produce）级模拟器：从开培育到最终评价，纯数值、无画面。

用途：在几十万局里比较**训练/休息/上课/外出**的行动策略，看哪种能把三维属性推得更高。

建模（有意简化，只保留对"属性成长"有影响的量）：
- 一周一个行动：训练(某属性) / 上课 / 休息 / 外出
- 训练：属性 +N(随机)，体力 -cost；支持卡加成用倍率近似
- 上课：跑课程模拟器(LessonSim)，CLEAR 则按课程的属性给成长 + 抽卡奖励；
  课程内部已建模：每回合 3 张手牌、体力、元气（ExamBlock）优先抵牌费、
  SKIP 换手牌、饮料（LessonSim.use_drink，每回合 1 瓶）
- 休息：体力 +24；外出：体力 +24 且不消耗周数（近似）
- 期中/期末：按"属性×审查基准权重"和一个门槛比较，估算名次
- 最终评价：用三维总和映射到 S/A/B/C/E（回归到真机观测：总和 ~630 = E/不合格）

只依赖 `gkagent.sim.lesson`，不依赖真机、不联网、可多进程。

**校准锚点（2026-11-15 真机实测，唯一可信基准）：**

- 玩家手动打完一局：**评价 C / 4135 评价点 / 三维约 1000-1200**
  （有村麻央，支援卡 Lv10/10/10/20/10/60，起始三维 209/85/75）；
- 扫描 ``lesson_gain_ratio``：1.00 → 三维 2219 / 评价点 7309；0.60 → 1330 / 4739；
  **0.50 → 1108 / 4097（与真机 4135 误差 0.9%）**；0.40 → 886 / 3454；
- 所以默认取 **0.5**：机制上课程得分 1:1 转属性（1.0 是对的），但模拟器"奖励选最强"
  后的牌组约为真机牌组的 **2 倍强**（模拟课程均分 ~245，真机只有 90-120），
  1.0 会把总分放大约 2 倍；0.5 是吸收"牌组强度差"后的有效系数；
- 支援卡加成同步改成 **1.2**：真机 6 张卡均值 Lv20（Lv10/10/10/20/10/60）属 SR 档，
  旧的 1.35 假设 Lv40，会把训练收益再抬高一档。

**考试属性倍率（2026-11-15 19:06 真机 C+/5577 反推）：**

- 真机手动那局：**C+ / 5577 评价点**，考试原始得分约 **1.7 万**；按卡面公式
  37 分 + 集中 10 + 好调 × 屏幕「歌唱 411%」≈ 290 分/张——考试里每张牌都吃
  属性倍率，而课程里倍率 ≈ 1.0；
- 旧模拟器的终试得分 proxy 是 ``2 × 三维总和``（典型局 ~2480），完全没乘属性
  倍率，所以官方评价公式算出 ~4092（C），与真机 5577（C+）差一个档；
- 新增 ``audition_coefficient = 4.11``：``exam()`` 里
  ``终试得分 ≈ 2 × 三维总和 × 4.11``（典型局三维 1245 → ~10200 分），再喂给
  ``eval_value`` / ``exam_score_points``，典型局评价点回到 ~5600，与真机 5577
  对齐；课程仍用 1.0，课程分数不受影响。

**未建模（真机有、本层没有；影响已写明）：**

- P 道具 / 角色被动（真机部分角色每回合开始触发加分、元气、集中等）：不进课程
  与属性。影响：依赖 P 道具的卡组成长/得分被低估；
- 饮料/道具的配装与使用：``LessonSim`` 已支持 ``DrinkSpec`` + ``use_drink``，
  但 ``ProduceSim`` 没有饮料配置，``lesson_policy`` 也不会主动喝。影响：培育级
  模拟默认无饮料收益；要测饮料需直接构造 ``LessonConfig.drinks``；
- 支援卡技能（技能卡追加、事件卡、P 饮料获得等）：只按 ``support_bonus`` 的
  训练倍率近似。影响：支援卡越强、模拟越低估；
- 课程奖励三选一之外的奖励（P 道具、饮料、金钱/粉丝商店）：只看技能卡；
- 考试中对手伤害、元气挡伤害、追击等考试专属规则：考试只按三维加权比大小；
- 体力上限成长、课程/训练的具体随机分布：用固定参数 + 高斯近似。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim

ATTRIBUTES = ("Vo", "Da", "Vi")


@dataclass(frozen=True)
class ProduceConfig:
    """一局培育的数值配置（默认值 = 真机实测校准后的口径）。

    校准依据：真机手动一局 **评价 C / 4135 评价点 / 三维约 1000-1200**
    （起始 209/85/75，支援卡 Lv10/10/10/20/10/60）。

    - ``lesson_gain_ratio=0.5``：机制值本是 1.0（课程得分 1:1 转属性），但模拟器
      奖励选牌后的牌组强度约为真机的 2 倍（课程均分 ~245 vs 真机 90-120），
      1.0 会把总分放大约 2 倍；0.5 时模拟三维 1108 / 评价点 4097，与真机 4135
      误差 0.9%（扫描 1.0/0.6/0.5/0.4 见模块 docstring）。
    - ``support_bonus=1.2``：真机支援卡均值 Lv20、SR 档 → 1.2；旧默认 1.35
      是"假设 Lv40"的口径，训练/课程收益会偏高。
    - ``audition_coefficient=4.11``：考试/舞台的属性倍率（屏幕「歌唱 411%」），
      真机实测值；课程里倍率 1.0（课程得分/评价校准不受影响）。
    """

    weeks: int = 12
    stamina_max: int = 35
    start_stamina: int = 35
    weights: tuple[float, float, float] = (0.40, 0.33, 0.27)  # 审查基准比例
    train_cost: int = 10
    train_gain: int = 75
    train_sigma: float = 6.0
    lesson_cost: int = 10
    rest_gain: int = 24
    outing_weeks: tuple[int, ...] = (3, 5, 8, 10)  # 这几周有外出可选
    exam_weeks: tuple[int, ...] = (6, 12)
    lesson_targets: tuple[int, ...] = (100, 150, 200, 250, 300)
    support_levels: tuple[int, ...] = (10, 10, 10, 20, 10, 60)  # 真机实测支援卡等级
    support_bonus: float = 1.2      # 训练收益倍率：均值 Lv20 / SR 档（旧 1.35 假设 Lv40）
    lesson_gain_ratio: float = 0.5  # 课程得分→属性；机制 1:1，但模拟牌组强 2 倍，取 0.5
    reward_pick: str = "best"       # best=选最强卡 / random=随机 / none=不拿
    # 考试：6 人里进前 3 才算合格。基准分按真机标定：
    # 实拍期末 1st 589 / 2nd 406 / 3rd 203 / 4th 201 / 5th 195，我们 632 属性 = 6th（不合格）
    exam_base: tuple[float, ...] = (85.0, 205.0)     # 期中/期末第3名基准（期中真机能过，设为100）
    npc_factors: tuple[float, ...] = (2.9, 2.0, 1.0, 0.99, 0.95)  # 5 个对手相对第 3 名的倍数
    fans_per_clear: int = 800
    remove_weeks: tuple[int, ...] = ()       # 咨询删卡（默认关：占一周去删 1 张，模型里是负收益）
    min_deck_size: int = 8                   # 牌组不低于此张数才删
    # 考试/舞台属性倍率（真机屏幕「歌唱 411%」= 4.11，实测校准 C+/5577）。
    # 课程里倍率 ≈ 1.0：LessonConfig 默认 1.0，课程得分不受影响。
    audition_coefficient: float = 4.11


@dataclass
class ProduceResult:
    attrs: tuple[int, int, int]
    fans: int
    lessons: int
    cleared: int
    exams_passed: int
    grade: str
    # 终试原始得分（已乘考试属性倍率），喂 eval_value / exam_score_points 用
    exam_score: int = 0

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


def lesson_policy(sim) -> int | None:
    """课程内策略：分数/体力最高，没有就换最便宜的（与真机策略同构的简化版）。"""
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
        return min(legal, key=lambda i: (sim.hand[i].cost, i))
    scored.sort(key=lambda item: (item[1] / max(sim.hand[item[0]].cost, 1), item[1]), reverse=True)
    return scored[0][0]


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
        self.lessons = 0
        self.cleared = 0
        self.exams_passed = 0
        self.log: list[str] = []
        self.reward_pool: list[CardSpec] = []
        self.reward_picks = 0
        self.trace: list[dict] = []       # 每周快照，给前端回放用
        self.lesson_policy_fn = lesson_policy  # 可注入真机 LessonPolicy 适配器
        self.last_lesson: dict | None = None
        self.last_exam: dict | None = None

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
    def train(self, index: int) -> bool:
        """训练：属性 +N、体力 -cost；体力不足则**不发生**并返回 False。

        真机体力不够时训练不成立（不是扣成负数），所以这里先查体力再扣，
        只有成功的训练才给属性。
        """
        cost = self.config.train_cost
        if self.stamina < cost:
            self.log.append(f"W{self.week} train{ATTRIBUTES[index]} failed stamina{self.stamina}<{cost}")
            return False
        self.stamina = max(0, self.stamina - cost)
        base = self.config.train_gain * self.config.support_bonus
        gain = max(1, int(self.rng.gauss(base, self.config.train_sigma)))
        self.attrs[index] += gain
        self.log.append(f"W{self.week} train{ATTRIBUTES[index]}+{gain}")
        return True

    def rest(self) -> None:
        self.stamina = min(self.config.stamina_max, self.stamina + self.config.rest_gain)
        self.log.append(f"W{self.week} rest")

    def outing(self) -> None:
        self.stamina = min(self.config.stamina_max, self.stamina + self.config.rest_gain)
        reward = self.pick_reward()
        if reward is not None:
            self.deck.append(reward)
            self.reward_picks += 1
        self.log.append(f"W{self.week} outing" + (f" +card:{reward.name.split('#')[0]}" if reward else ""))

    def pick_reward(self) -> CardSpec | None:
        """课程奖励三选一：按 分数/体力 选最强的一张进牌组。"""
        if not self.reward_pool or self.config.reward_pick == "none":
            return None
        if self.config.reward_pick == "random":
            return self.rng.choice(self.reward_pool)
        best = max(
            self.reward_pool,
            key=lambda card: (card.score / max(card.cost, 1), card.score),
        )
        return best

    def lesson(self) -> bool:
        """上课：跑课程模拟器；体力不足时**打不出牌**，返回 False。

        真机在体力不足时进课只能一直 SKIP（不会把体力扣成负数）。这里直接
        判定失败：不跑课程、不加属性、不拿奖励，只记一次失败课（grade=FAILED），
        让调用方/策略知道该休息。
        """
        cost = self.config.lesson_cost
        if self.stamina < cost:
            self.lessons += 1
            self.last_lesson = {
                "target": None,
                "score": 0,
                "grade": "FAILED",
                "plays": [],
                "reward": None,
                "reason": f"stamina {self.stamina} < {cost}",
            }
            self.log.append(f"W{self.week} lesson failed stamina{self.stamina}<{cost}")
            return False
        self.stamina = max(0, self.stamina - cost)
        # 审查基准随进度抬升：前半段偏易，后半段偏难
        stage = min(len(self.config.lesson_targets) - 1, (self.week - 1) * len(self.config.lesson_targets) // max(self.config.weeks, 1))
        target = self.config.lesson_targets[stage]
        plays: list[dict] = []

        base_policy = getattr(self, "lesson_policy_fn", None) or lesson_policy

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
                stamina=self.config.stamina_max,
                target_clear=target,
                target_perfect=int(target * 1.5),
                hand_size=3,
            ),
            rng_seed=self.rng.randrange(1 << 30),
        )
        score, grade = sim.run(traced_policy)
        self.lessons += 1
        if grade in ("CLEAR", "PERFECT"):
            self.cleared += 1
            self.fans += self.config.fans_per_clear
        # 课程的属性成长 ≈ 这节课的总得分（游戏里 パラメータ上昇 就是属性增长），
        # 之前按 30+score/20 估会低估 5-10 倍，已按机制修正。
        order = sorted(range(3), key=lambda i: self.config.weights[i], reverse=True)
        target_attr = order[self.lessons % 3]
        # 支援卡也提升课程成长（真机支援卡给属性加成/技能卡；这里只建模属性加成那一路）
        support_factor = 0.85 + 0.15 * self.config.support_bonus
        self.attrs[target_attr] += int(score * self.config.lesson_gain_ratio * support_factor)
        # 课程奖励：真机每节课后都有三选一，所以不管 CLEAR 都给（这才是牌组变强的来源）
        reward = self.pick_reward()
        if reward is not None:
            self.deck.append(reward)
            self.reward_picks += 1
        self.last_lesson = {
            "target": target,
            "score": score,
            "grade": grade,
            "plays": plays,
            "reward": reward.name.split("#")[0] if reward else None,
            # 课程逐回合 trace（SKIP 会记 skipped=True，剩余手牌弃掉且不回复体力）
            "turns": [dict(row) for row in sim.trace],
            "skipped": any(row.get("skipped") for row in sim.trace),
        }
        self.log.append(f"W{self.week} lesson target{target} score{score} {grade}")
        return True

    # ------------------------------------------------------------------ 学期
    def exam(self, index: int) -> dict:
        """6 人考试：属性加权 = 实力，和第 3 名基准比，进前 3 才合格。

        终试得分 = ``2 × 三维总和 × audition_coefficient``：考试/舞台里每张牌的
        分数都吃屏幕上的属性倍率（「歌唱 411%」= 4.11），课程里倍率 ≈ 1.0。
        旧口径的 ``2 × 三维总和`` 只是"终试得分 ≈ 2×属性"的 proxy；乘上倍率后
        再喂 ``eval_value`` / ``exam_score_points``，典型局评价点才落回真机 C+/5577
        的区间。
        """
        power = self.weighted()
        base = self.config.exam_base[min(index, len(self.config.exam_base) - 1)]
        opponents = [base * factor for factor in self.config.npc_factors]
        rank = 1 + sum(1 for value in opponents if value > power)
        passed = rank <= 3
        if passed:
            self.exams_passed += 1
            self.fans += 3000
        # 考试/舞台得分：沿用“终试 ≈ 2×三维总和”的 proxy，再乘属性倍率（411%）
        exam_score = int(sum(self.attrs) * 2 * self.config.audition_coefficient)
        self.last_exam = {
            "rank": rank,
            "power": round(power, 1),
            "passed": passed,
            "npc": [round(value, 1) for value in opponents],
            # 终试原始得分（已乘考试属性倍率）：官方评价公式的输入
            "score": exam_score,
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
                    "lesson": None,
                    "exam": self.last_exam,
                }
            )
            self.week += 1
            return
        action = strategy(self)
        self.last_lesson = None
        stamina_before = self.stamina
        attrs_before = list(self.attrs)
        ok = True
        if action == "train":
            ok = self.train(self.best_attribute())
        elif action == "train_low":
            ok = self.train(self.lagging_attribute())
        elif action == "rest":
            self.rest()
        elif action == "outing":
            self.outing()
        elif action == "lesson":
            ok = self.lesson()
        else:
            ok = self.train(self.best_attribute())
        row = {
            "week": self.week,
            "action": action,
            "stamina_before": stamina_before,
            "stamina_after": self.stamina,
            "attrs_before": attrs_before,
            "attrs_after": list(self.attrs),
            "lesson": self.last_lesson,
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
        # 终试得分：考试/舞台吃属性倍率（默认 4.11），课程仍是 1.0
        exam_score = self.last_exam_score()
        return ProduceResult(
            attrs=tuple(self.attrs),
            fans=self.fans,
            lessons=self.lessons,
            cleared=self.cleared,
            exams_passed=self.exams_passed,
            grade=grade_for(total, last_rank, exam_score),
            exam_score=exam_score,
        )


# ---------------------------------------------------------------------- 策略参数
@dataclass(frozen=True)
class StrategyParams:
    """可搜的策略参数：行动节奏 + 练哪个属性。"""

    rest_threshold: int = 10        # 体力低于此 → 休息
    lesson_every: int = 1           # 每 N 周上一次课（1 = 能上就上）
    lesson_min_stamina: int = 12    # 体力低于此不上课（真机 0 体力进课打不出牌）
    attr_choice: str = "weight"     # weight=练权重最高 / lowest=补短板 / rotate=轮转
    outing_below: int = -1          # 体力低于此且本周有外出 → 先外出（-1 关闭）
    min_stamina_to_train: int = 10  # 低于此不硬练


def strategy_from_params(params: StrategyParams):
    """把参数变成执行函数（模拟器与真机共用的同一套节奏）。"""

    def strategy(state: ProduceSim) -> str:
        cfg = state.config
        if state.stamina < params.rest_threshold:
            return "rest"
        if params.outing_below >= 0 and state.stamina < params.outing_below and state.week in cfg.outing_weeks:
            return "outing"
        if params.lesson_every > 0 and state.week % params.lesson_every == 0:
            # 体力门：真机 0 体力进课一张牌都打不出，只能 SKIP 白送回合。
            # 不够 lesson_min_stamina 就改休息，等下周有体力再上课。
            if state.stamina < params.lesson_min_stamina:
                return "rest"
            return "lesson"
        if state.stamina < params.min_stamina_to_train:
            return "rest"
        if params.attr_choice == "lowest":
            return "train_low"
        return "train"

    return strategy


# ---------------------------------------------------------------------- 策略
def strategy_train_best(state: ProduceSim) -> str:
    """总是练审查基准最高的属性（体力不够就休息）。"""
    if state.stamina < state.config.train_cost:
        return "rest"
    return "train"


def strategy_train_lowest(state: ProduceSim) -> str:
    """总是补最低属性（均衡成长）。"""
    if state.stamina < state.config.train_cost:
        return "rest"
    return "train_low"


def strategy_lesson_heavy(state: ProduceSim) -> str:
    """优先上课（拿卡+粉丝），没体力就休息。"""
    if state.stamina < state.config.lesson_cost:
        return "rest"
    return "lesson"


def strategy_smart(state: ProduceSim) -> str:
    """能明显打不过就不上课：体力够就先训练，每 3 周上一次课。"""
    if state.stamina < state.config.train_cost:
        return "rest"
    return "lesson" if state.week % 3 == 0 else "train"


def strategy_mixed(state: ProduceSim) -> str:
    """体力 <40% 休息，否则 训练:上课 = 3:1。"""
    if state.stamina_ratio() < 0.4:
        return "rest"
    return "lesson" if state.week % 4 == 0 else "train"


STRATEGIES = {
    "train_best": strategy_train_best,
    # 别名：对比实验（训练 vs 上课）里用 pure_train 表示"只训练、体力不够就休息"
    "pure_train": strategy_train_best,
    "train_lowest": strategy_train_lowest,
    "lesson_heavy": strategy_lesson_heavy,
    "mixed": strategy_mixed,
    "smart": strategy_smart,
}


def random_strategy(seed: int):
    """随机打法基线（各种训练都用），用于说明"乱打"的下限。"""
    rng = random.Random(seed)

    def strategy(state: ProduceSim) -> str:
        if state.stamina < 8:
            return "rest"
        return rng.choice(["train", "train_low", "lesson", "rest", "outing"])

    return strategy
