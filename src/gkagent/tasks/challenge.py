"""每日挑战（challenge）：主页 → 竞技场 → 选对手 → 开始 → 跳过 → 下一步 → 结束。

MAA 的 Challenge 流程在中文 UI 下有两个问题：
1. 打完一次后 ChallengeFinish / ReturnHome 不返回主页；
2. 今日次数用完时「已耗尽今天的挑战权」弹窗压在主页上，后续任务全部卡住。

这里不复用 MAA pipeline，只用现有 Agent API + 模板匹配推进状态机。识别（observe）
和决策（decide）都放在本类里：GDE 可以只调用这两个方法拿到「当前该点哪里」，
不用启动 MAA，也不用关心计时/循环。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from gkagent.agent import Agent
from gkagent.tasks.base import TaskResult
from gkagent.vision.matcher import Match


class ChallengeAction(Enum):
    """一步决策：点哪个按钮、回主页，还是等待。"""

    DISMISS_RUNOUT = "dismiss_runout"
    SKIP = "skip"
    NEXT = "next"
    AWARD = "award"
    FINISH = "finish"
    START = "start"
    OPPONENT = "opponent"
    ENTRY = "entry"
    GO_HOME = "go_home"
    WAIT = "wait"


@dataclass(frozen=True)
class ChallengeScreen:
    """一帧里所有关心的命中结果；decide() 只依赖这个结构，方便 GDE 复用。"""

    runout: Match | None = None
    home: Match | None = None
    entry: Match | None = None
    opponent: Match | None = None
    start: Match | None = None
    ready: Match | None = None
    ready_period: Match | None = None
    skip: Match | None = None
    next_step: Match | None = None
    finish: Match | None = None
    award: Match | None = None
    decide: Match | None = None
    close: Match | None = None

    @property
    def in_selector(self) -> bool:
        return self.start is not None or self.opponent is not None


class _Outcome(Enum):
    """一次阶段推进的结果，供 run() 决定下一步。"""

    SELECTOR = "selector"
    RUNOUT = "runout"
    READY_PERIOD = "ready_period"
    HOME = "home"
    FAILED = "failed"


class ChallengeTask:
    name = "challenge"

    # 720x1280 中文 UI 的固定坐标。
    # 竞技场入口页上的「评价Pt / 竞技场」卡片（MAA 日志点击点 534,896 附近）。
    arena_entry_point = (500, 880)
    # 底部「主页」tab；和 MAA BackHome 的 homeflag_black 匹配点一致。
    home_tab_point = (360, 1150)

    home_flag_roi = (0, 1050, 720, 230)
    # 对手列表固定三张卡：中间那张的「总综合实力」在 y=797 附近。
    opponent_roi = (54, 740, 190, 140)

    default_threshold = 0.85
    thresholds: ClassVar[dict[str, float]] = {
        "home": 0.85,
        "challenge": 0.85,
        "challenge_homeflag_black": 0.85,
        "challenge_battle_total": 0.85,
        "challenge_start": 0.75,
        "challenge_ready": 0.75,
        "challenge_ready_period": 0.85,
        "challenge_skip": 0.75,
        "challenge_next": 0.75,
        "challenge_finish": 0.75,
        "challenge_award": 0.75,
        "challenge_runout": 0.85,
        "decide": 0.85,
        "close": 0.85,
    }

    max_rounds = 10
    poll_interval = 0.5
    entry_timeout = 15.0
    selector_timeout = 10.0
    battle_timeout = 120.0
    result_timeout = 25.0

    # 同一按钮的重复点击间隔：防止动画期间连点，也防止点击没生效时干等。
    entry_retry = 4.0
    arena_retry = 3.0
    opponent_retry = 2.0
    start_retry = 4.0

    def __init__(
        self,
        *,
        sleep: Callable[[float], None] | None = None,
        poll_interval: float | None = None,
        entry_timeout: float | None = None,
        selector_timeout: float | None = None,
        battle_timeout: float | None = None,
        result_timeout: float | None = None,
        max_rounds: int | None = None,
    ) -> None:
        self._sleep = time.sleep if sleep is None else sleep
        self.poll_interval = self.poll_interval if poll_interval is None else poll_interval
        self.entry_timeout = self.entry_timeout if entry_timeout is None else entry_timeout
        self.selector_timeout = (
            self.selector_timeout if selector_timeout is None else selector_timeout
        )
        self.battle_timeout = self.battle_timeout if battle_timeout is None else battle_timeout
        self.result_timeout = self.result_timeout if result_timeout is None else result_timeout
        self.max_rounds = self.max_rounds if max_rounds is None else max_rounds

    # ------------------------------------------------------------------ 识别/决策
    def observe(self, agent: Agent, image=None) -> ChallengeScreen:
        """在截图上找齐本任务关心的所有元素；GDE 可以直接复用。"""
        img = agent.shot() if image is None else image

        def find(name: str, roi: tuple[int, int, int, int] | None = None) -> Match | None:
            return agent.find(
                name,
                image=img,
                roi=roi,
                threshold=self.thresholds.get(name, self.default_threshold),
            )

        opponent = find("challenge_battle_total", roi=self.opponent_roi)
        if opponent is None:
            opponent = find("challenge_battle_total")
        return ChallengeScreen(
            runout=find("challenge_runout"),
            home=find("home"),
            entry=find("challenge"),
            opponent=opponent,
            start=find("challenge_start"),
            ready=find("challenge_ready"),
            ready_period=find("challenge_ready_period"),
            skip=find("challenge_skip"),
            next_step=find("challenge_next"),
            finish=find("challenge_finish"),
            award=find("challenge_award"),
            decide=find("decide"),
            close=find("close"),
        )

    def decide(self, screen: ChallengeScreen) -> tuple[ChallengeAction, Match | None]:
        """纯决策：给定一帧识别结果，返回动作和要点的位置（GDE 复用点）。"""
        if screen.runout is not None:
            target = screen.decide or screen.close or screen.runout
            return ChallengeAction.DISMISS_RUNOUT, target
        for action, match in (
            (ChallengeAction.SKIP, screen.skip),
            (ChallengeAction.NEXT, screen.next_step),
            (ChallengeAction.AWARD, screen.award),
            (ChallengeAction.FINISH, screen.finish),
            (ChallengeAction.START, screen.start),
            (ChallengeAction.OPPONENT, screen.opponent),
            (ChallengeAction.ENTRY, screen.entry),
        ):
            if match is not None:
                return action, match
        if screen.ready_period is not None:
            return ChallengeAction.GO_HOME, None
        return ChallengeAction.WAIT, None

    # ------------------------------------------------------------------ 任务入口
    def run(self, agent: Agent) -> TaskResult:
        screen = self.observe(agent)
        if screen.runout is not None:
            return self._close_runout(agent, rounds=0)
        if screen.ready_period is not None:
            self._go_home(agent)
            return TaskResult(True, "今日挑战处于活动准备期")

        if not self._go_home(agent):
            return TaskResult(False, "不在主页，无法进入竞技场")

        state = self._enter_selector(agent)
        if state is _Outcome.RUNOUT:
            return self._close_runout(agent, rounds=0)
        if state is _Outcome.READY_PERIOD:
            self._go_home(agent)
            return TaskResult(True, "今日挑战处于活动准备期")
        if state is not _Outcome.SELECTOR:
            return TaskResult(False, "进入竞技场失败：未识别到挑战入口或对手列表")

        rounds = 0
        while rounds < self.max_rounds:
            outcome, completed = self._play_round(agent)
            if outcome is _Outcome.RUNOUT:
                if completed:
                    rounds += 1
                return self._close_runout(agent, rounds)
            if outcome is _Outcome.READY_PERIOD:
                self._go_home(agent)
                return TaskResult(True, "今日挑战处于活动准备期")
            if outcome is _Outcome.FAILED:
                return TaskResult(False, f"第 {rounds + 1} 次挑战中断：未识别到开始/跳过/下一步")

            if completed:
                rounds += 1
            if outcome is _Outcome.HOME:
                # MAA 就是在这里回不到竞技场；显式重新进入，而不是等 ReturnHome。
                state = self._enter_selector(agent)
                if state is _Outcome.RUNOUT:
                    return self._close_runout(agent, rounds)
                if state is _Outcome.READY_PERIOD:
                    self._go_home(agent)
                    return TaskResult(True, "今日挑战处于活动准备期")
                if state is not _Outcome.SELECTOR:
                    return TaskResult(False, "挑战结束后无法重新进入竞技场")

        self._go_home(agent)
        return TaskResult(True, f"完成 {rounds} 次挑战（未检测到次数用完弹窗）")

    # ------------------------------------------------------------------ 阶段推进
    def _enter_selector(self, agent: Agent) -> _Outcome:
        """主页 → 竞技场入口页 → 对手选择页。"""
        deadline = time.monotonic() + self.entry_timeout
        entry_clicks = 0
        arena_clicks = 0
        last_entry = 0.0
        last_arena = 0.0
        while time.monotonic() < deadline:
            screen = self.observe(agent)
            if screen.runout is not None:
                return _Outcome.RUNOUT
            if screen.ready_period is not None:
                return _Outcome.READY_PERIOD
            if screen.in_selector:
                return _Outcome.SELECTOR

            now = time.monotonic()
            if (
                screen.entry is not None
                and entry_clicks < 2
                and now - last_entry >= self.entry_retry
            ):
                agent.click(screen.entry)
                entry_clicks += 1
                last_entry = now
                self._sleep(1.0)
                continue
            # 点完底部「竞技场」后：主页 banner 消失、底部图标变成选中态，
            # challenge.png 匹配不到，此时点入口页中间的「竞技场」卡片。
            if (
                entry_clicks > 0
                and screen.home is None
                and screen.entry is None
                and arena_clicks < 2
                and now - last_arena >= self.arena_retry
            ):
                agent.device.click(*self.arena_entry_point)
                arena_clicks += 1
                last_arena = now
                self._sleep(1.2)
                continue
            self._sleep(self.poll_interval)
        return _Outcome.FAILED

    def _play_round(self, agent: Agent) -> tuple[_Outcome, bool]:
        """选对手 → 开始 → 跳过战斗 → 结算 → 回到选择页/主页。

        返回 (结果, 本轮战斗是否已打完)；只有打完的轮次才计入 total。
        """
        start: Match | None = None
        opponent_clicks = 0
        last_opponent = 0.0
        deadline = time.monotonic() + self.selector_timeout
        while time.monotonic() < deadline:
            screen = self.observe(agent)
            if screen.runout is not None:
                return _Outcome.RUNOUT, False
            if screen.ready_period is not None:
                return _Outcome.READY_PERIOD, False

            now = time.monotonic()
            # 先选对手（中间的「总综合实力」卡），再点「挑战开始」。
            if (
                screen.opponent is not None
                and opponent_clicks < 2
                and now - last_opponent >= self.opponent_retry
            ):
                agent.click(screen.opponent)
                opponent_clicks += 1
                last_opponent = now
                self._sleep(0.8)
                continue
            if screen.start is not None:
                start = screen.start
                break
            self._sleep(self.poll_interval)
        if start is None:
            return _Outcome.FAILED, False

        agent.click(start)
        self._sleep(1.0)

        deadline = time.monotonic() + self.battle_timeout
        start_clicks = 1
        last_start = time.monotonic()
        result_ready = False
        while time.monotonic() < deadline:
            screen = self.observe(agent)
            if screen.runout is not None:
                return _Outcome.RUNOUT, False
            if screen.next_step is not None or screen.finish is not None or screen.award is not None:
                result_ready = True
                break
            if screen.skip is not None:
                agent.click(screen.skip)
                self._sleep(0.4)
                continue
            now = time.monotonic()
            if screen.start is not None and start_clicks < 2 and now - last_start >= self.start_retry:
                # 点了开始却还停在选择页：再点一次，避免动画吃掉点击。
                agent.click(screen.start)
                start_clicks += 1
                last_start = now
                self._sleep(1.0)
                continue
            self._sleep(self.poll_interval)
        if not result_ready:
            return _Outcome.FAILED, False

        return self._settle(agent), True

    def _settle(self, agent: Agent) -> _Outcome:
        """下一步 → 关闭奖励弹窗 → 结束，直到回到选择页或主页。"""
        deadline = time.monotonic() + self.result_timeout
        finish_clicks = 0
        while time.monotonic() < deadline:
            screen = self.observe(agent)
            if screen.runout is not None:
                return _Outcome.RUNOUT
            if screen.in_selector:
                return _Outcome.SELECTOR
            if screen.home is not None:
                return _Outcome.HOME
            if screen.next_step is not None:
                agent.click(screen.next_step)
                self._sleep(0.8)
                continue
            if screen.award is not None:
                agent.click(screen.award)
                self._sleep(0.8)
                continue
            if screen.finish is not None and finish_clicks < 3:
                agent.click(screen.finish)
                finish_clicks += 1
                self._sleep(1.0)
                continue
            if screen.skip is not None:
                # 结算界面偶尔会残留「跳过」：先点掉，避免卡在战斗中。
                agent.click(screen.skip)
                self._sleep(0.4)
                continue
            self._sleep(self.poll_interval)
        return _Outcome.FAILED

    # ------------------------------------------------------------------ 收尾
    def _dismiss_runout(self, agent: Agent) -> bool:
        """点「确定/关闭」关掉「已耗尽今天的挑战权」弹窗。"""
        for _ in range(4):
            screen = self.observe(agent)
            if screen.runout is None:
                return True
            action, target = self.decide(screen)
            if action is not ChallengeAction.DISMISS_RUNOUT or target is None:
                return False
            agent.click(target)
            self._sleep(1.0)
        return self.observe(agent).runout is None

    def _close_runout(self, agent: Agent, rounds: int) -> TaskResult:
        self._dismiss_runout(agent)
        if not self._go_home(agent):
            return TaskResult(False, "今日挑战次数已用完，但未能回到主页")
        if rounds:
            return TaskResult(True, f"今日挑战次数已用完，完成 {rounds} 次挑战，已回到主页")
        return TaskResult(True, "今日挑战次数已用完，已回到主页")

    def _go_home(self, agent: Agent) -> bool:
        """回主页；ensure_home 在非主页页面上认不出灰色「主页」tab，这里补两条退路。"""
        if agent.ensure_home():
            return True
        agent.close_popup()
        if agent.ensure_home():
            return True

        # MAA ReturnHome 用的 homeflag_black：未选中态的「主页」图标。
        flag = agent.find(
            "challenge_homeflag_black",
            image=agent.shot(),
            roi=self.home_flag_roi,
            threshold=self.thresholds["challenge_homeflag_black"],
        )
        if flag is not None:
            agent.click(flag)
            self._sleep(1.2)
            if agent.ensure_home():
                return True

        # 最后退路：底部主页 tab 的固定坐标（720x1280）。
        agent.device.click(*self.home_tab_point)
        self._sleep(1.2)
        return agent.ensure_home()
