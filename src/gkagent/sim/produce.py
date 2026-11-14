"""培育（produce）级模拟器：从开培育到最终评价，纯数值、无画面。

用途：在几十万局里比较**训练/休息/上课/外出**的行动策略，看哪种能把三维属性推得更高。

建模（有意简化，只保留对"属性成长"有影响的量）：
- 一周一个行动：训练(某属性) / 上课 / 休息 / 外出
- 训练：属性 +N(随机)，体力 -cost；支持卡加成用倍率近似
- 上课：跑课程模拟器(LessonSim)，CLEAR 则按课程的属性给成长 + 抽卡奖励
- 休息：体力 +24；外出：体力 +24 且不消耗周数（近似）
- 期中/期末：按"属性×审查基准权重"和一个门槛比较，估算名次
- 最终评价：用三维总和映射到 S/A/B/C/E（回归到真机观测：总和 ~630 = E/不合格）

只依赖 `gkagent.sim.lesson`，不依赖真机、不联网、可多进程。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from gkagent.sim.lesson import CardSpec, LessonConfig, LessonSim

ATTRIBUTES = ("Vo", "Da", "Vi")


@dataclass(frozen=True)
class ProduceConfig:
    weeks: int = 12
    stamina_max: int = 35
    start_stamina: int = 35
    weights: tuple[float, float, float] = (0.40, 0.33, 0.27)  # 审查基准比例
    train_cost: int = 10
    train_gain: int = 75
    train_sigma: float = 6.0
    lesson_cost: int = 10
    rest_gain: int = 24
    outing_weeks: tuple[int, ...] = (3, 8)  # 这几天有外出
    exam_weeks: tuple[int, ...] = (6, 12)
    lesson_targets: tuple[int, ...] = (100, 150, 200, 250, 300)
    support_bonus: float = 1.0      # 支援卡对训练收益的倍率（近似）
    lesson_gain_ratio: float = 0.6  # 课程得分 → 属性成长（按真机一局 ~632 标定）
    reward_pick: str = "best"       # best=选最强卡 / random=随机 / none=不拿
    # 考试：6 人里进前 3 才算合格。基准分按真机标定：
    # 实拍期末 1st 589 / 2nd 406 / 3rd 203 / 4th 201 / 5th 195，我们 632 属性 = 6th（不合格）
    exam_base: tuple[float, ...] = (150.0, 205.0)     # 期中/期末「第 3 名」的实力基准
    npc_factors: tuple[float, ...] = (2.9, 2.0, 1.0, 0.99, 0.95)  # 5 个对手相对第 3 名的倍数
    fans_per_clear: int = 800


@dataclass
class ProduceResult:
    attrs: tuple[int, int, int]
    fans: int
    lessons: int
    cleared: int
    exams_passed: int
    grade: str

    @property
    def total(self) -> int:
        return sum(self.attrs)


def grade_for(total: int) -> str:
    """三维总和 → 评价（按真机观测标定：总和 ~630 = E）。"""
    for limit, grade in ((700, "E"), (900, "D"), (1100, "C"), (1300, "C+"), (1600, "B"), (1900, "B+"), (2200, "A")):
        if total < limit:
            return grade
    return "S"


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
    def train(self, index: int) -> None:
        self.stamina = max(0, self.stamina - self.config.train_cost)
        base = self.config.train_gain * self.config.support_bonus
        gain = max(1, int(self.rng.gauss(base, self.config.train_sigma)))
        self.attrs[index] += gain
        self.log.append(f"W{self.week} train{ATTRIBUTES[index]}+{gain}")

    def rest(self) -> None:
        self.stamina = min(self.config.stamina_max, self.stamina + self.config.rest_gain)
        self.log.append(f"W{self.week} rest")

    def outing(self) -> None:
        self.stamina = min(self.config.stamina_max, self.stamina + self.config.rest_gain)
        self.log.append(f"W{self.week} outing")

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

    def lesson(self) -> None:
        self.stamina = max(0, self.stamina - self.config.lesson_cost)
        # 审查基准随进度抬升：前半段偏易，后半段偏难
        stage = min(len(self.config.lesson_targets) - 1, (self.week - 1) * len(self.config.lesson_targets) // max(self.config.weeks, 1))
        target = self.config.lesson_targets[stage]
        plays: list[dict] = []

        def traced_policy(inner):
            action = lesson_policy(inner)
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
        self.attrs[target_attr] += int(score * self.config.lesson_gain_ratio)
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
        }
        self.log.append(f"W{self.week} lesson target{target} score{score} {grade}")

    # ------------------------------------------------------------------ 学期
    def exam(self, index: int) -> dict:
        """6 人考试：属性加权 = 实力，和第 3 名基准比，进前 3 才合格。"""
        power = self.weighted()
        base = self.config.exam_base[min(index, len(self.config.exam_base) - 1)]
        opponents = [base * factor for factor in self.config.npc_factors]
        rank = 1 + sum(1 for value in opponents if value > power)
        passed = rank <= 3
        if passed:
            self.exams_passed += 1
            self.fans += 3000
        self.last_exam = {
            "rank": rank,
            "power": round(power, 1),
            "passed": passed,
            "npc": [round(value, 1) for value in opponents],
        }
        return self.last_exam

    def step(self, strategy) -> None:
        cfg = self.config
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
        if action == "train":
            self.train(self.best_attribute())
        elif action == "train_low":
            self.train(self.lagging_attribute())
        elif action == "rest":
            self.rest()
        elif action == "outing":
            self.outing()
        elif action == "lesson":
            self.lesson()
        else:
            self.train(self.best_attribute())
        self.trace.append(
            {
                "week": self.week,
                "action": action,
                "stamina_before": stamina_before,
                "stamina_after": self.stamina,
                "attrs_before": attrs_before,
                "attrs_after": list(self.attrs),
                "lesson": self.last_lesson,
            }
        )
        self.week += 1

    def run(self, strategy) -> ProduceResult:
        while not self.done:
            self.step(strategy)
        return ProduceResult(
            attrs=tuple(self.attrs),
            fans=self.fans,
            lessons=self.lessons,
            cleared=self.cleared,
            exams_passed=self.exams_passed,
            grade=grade_for(sum(self.attrs)),
        )


# ---------------------------------------------------------------------- 策略参数
@dataclass(frozen=True)
class StrategyParams:
    """可搜的策略参数：行动节奏 + 练哪个属性。"""

    rest_threshold: int = 10        # 体力低于此 → 休息
    lesson_every: int = 1           # 每 N 周上一次课（1 = 能上就上）
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
