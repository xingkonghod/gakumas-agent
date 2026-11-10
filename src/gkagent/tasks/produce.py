"""培育（produce）状态机：主页 → プロデュース → SSR 偶像 → 场景 → 支援卡 → 主界面。

只使用 ``Agent`` 已有的截屏/模板匹配/点击能力，不依赖 MAA pipeline：

1. 主页点「プロデュース」进入培育；
2. SSR/培育偶像选择页：识别标题「SSRプロデュースアイドルを選んでください」和
   「获取」按钮；也可以按配置改成点「变换」或「取消」（``selection_action``）；
3. 场景选择、难度/开始、支援卡选择按屏幕自适应推进；
4. 培育主界面：出牌优先委托 ``gkagent.policy.router.RuleCardPolicy``（需要注入
   ``hand_reader`` 提供手牌/费用），没有卡牌识别时回退到模板「推荐」；事件点第一个；
   结算点「关闭/下一步/完成」，最后回主页。

所有等待都有 deadline；失败返回 ``TaskResult(False, "卡在<阶段>：...")``。
``observe`` / ``classify`` / ``decide_card`` / ``read_hand`` 是纯识别/决策入口，GDE 以后
可以把 MAA 的截图直接喂进来复用，不必启动 MAA。

模板来自 MaaGakumasu ``resource/base/image``（统一 ``produce_`` 前缀）；MAA 没有中文
SSR 选择页模板，``produce_ssr_title.png`` / ``produce_get.png`` 是从真实截图裁出来的。
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import ClassVar, Protocol

import cv2
import numpy as np

from gkagent.agent import Agent
from gkagent.contract.models import Card, Observation, Phase
from gkagent.policy.router import Recommendation, RuleCardPolicy
from gkagent.runtime.replay import ReplayDB
from gkagent.tasks.base import TaskResult
from gkagent.vision.matcher import Match


class ProduceStage(str, Enum):
    """当前截图属于培育的哪个阶段。"""

    HOME = "home"
    SSR_SELECT = "ssr_select"
    SCENARIO = "scenario"
    SUPPORT = "support"
    MAIN = "main"
    CARD_PLAY = "card_play"
    EVENT = "event"
    RESULT = "result"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProduceScreen:
    """一帧里所有关心的命中结果；classify/decide 只依赖这个结构。"""

    stage: ProduceStage = ProduceStage.UNKNOWN
    home: Match | None = None
    produce_entry: Match | None = None
    ssr_title: Match | None = None
    get: Match | None = None
    exchange: Match | None = None
    cancel: Match | None = None
    decide: Match | None = None
    close: Match | None = None
    next_step: Match | None = None
    finished: Match | None = None
    continue_: Match | None = None
    start: Match | None = None
    recommend: Match | None = None
    event: Match | None = None
    event_recommend: Match | None = None
    auto_support: Match | None = None
    checkbox: Match | None = None
    support_replace: Match | None = None
    main_page: Match | None = None
    scenario: Match | None = None
    health: Match | None = None
    skip_round: Match | None = None
    round_close: Match | None = None
    cards_get: Match | None = None


@dataclass(frozen=True)
class HandState:
    """手牌识别结果：``cards`` 与 ``boxes`` 一一对应。"""

    cards: tuple[Card, ...] = ()
    boxes: tuple[tuple[int, int, int, int], ...] = ()

    def __bool__(self) -> bool:
        return bool(self.cards or self.boxes)


@dataclass(frozen=True)
class CardPlay:
    """一次出牌决策：点哪里、来自策略还是模板。"""

    point: tuple[int, int]
    source: str
    index: int | None = None


class TextReader(Protocol):
    """OCR 适配器：返回 ROI 内的文本行；没有 OCR 时传 None。"""

    def __call__(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> list[str]: ...


class HandReader(Protocol):
    """手牌识别适配器：返回 HandState 或 (cards, boxes)。"""

    def __call__(
        self,
        image: np.ndarray,
    ) -> HandState | tuple[list[Card], list[tuple[int, int, int, int]]]: ...


class CardRecommender(Protocol):
    """与 ``gkagent.policy.router.RuleCardPolicy`` 兼容的出牌建议接口。"""

    def recommend(self, obs: Observation) -> Recommendation | None: ...


class ProduceTask:
    name = "produce"

    # 模板名（全部在 templates/ 下，produce_ 前缀）。
    ENTRY = "produce_entry"  # MAA home.png：主页「プロデュース」
    SSR_TITLE = "produce_ssr_title"  # 真实截图裁切：SSR 选择页标题
    GET = "produce_get"  # 真实截图裁切：中文「获取」按钮
    EXCHANGE = "produce_exchange"  # MAA exchange.png：变换/チェンジ
    CANCEL = "produce_cancel"  # MAA produce/cancel.png：日文「キャンセル」
    CANCEL_CN = "produce_cancel_cn"  # MAA cancel.png：中文「取消」
    DECIDE = "produce_decide"  # MAA decide.png：決定（日文兜底）
    CLOSE = "produce_close"  # MAA close.png：閉じる（日文兜底）
    NEXT = "produce_next"  # MAA next.png：下一步
    FINISHED = "produce_finished"  # MAA finished.png：完了する
    CONTINUE = "produce_continue"  # MAA continue.png：再開する
    START = "produce_start"  # MAA start.png：開始する
    RECOMMEND = "produce_recommend"  # MAA recommend.png：おすすめ
    EVENT = "produce_event"  # MAA event.png：事件卡
    EVENT_RECOMMEND = "produce_event_recommend"  # MAA event_recommend.png
    AUTO_SUPPORT = "produce_auto_support"  # MAA auto_support.png：おまかせ
    CHECKBOX = "produce_checkbox"  # MAA checkbox.png
    SUPPORT_REPLACE = "produce_support_replace"  # MAA support_card_replacement.png
    MAIN_PAGE = "produce_mainpage_ranking"  # MAA produce_mainpage_ranking.png
    HEALTH = "produce_health"  # MAA health.png：出牌界面的体力图标
    SKIP_ROUND = "produce_skip_round"  # MAA skip_round.png
    ROUND_CLOSE = "produce_round_close"  # MAA round_close_button.png
    CARDS_GET = "produce_cards_get"  # MAA cards_get.png：受け取る

    SCENARIO_TEMPLATES: ClassVar[dict[str, str]] = {
        "hajime": "produce_scenario_hajime",
        "hif": "produce_scenario_hif",
        "nia": "produce_scenario_nia",
    }

    # 720x1279/1280 中文 UI 的固定位置。ROI 会被裁到截图内，1279/1280 都能用。
    ssr_title_roi = (0, 0, 720, 100)
    get_roi = (0, 1000, 720, 279)
    recommend_roi = (54, 476, 614, 620)
    event_roi = (0, 640, 720, 639)
    auto_support_roi = (510, 948, 210, 100)
    checkbox_roi = (470, 940, 240, 160)
    main_page_roi = (500, 1050, 200, 80)
    health_roi = (512, 125, 168, 130)
    skip_round_roi = (590, 720, 130, 120)
    hand_roi = (0, 900, 720, 379)

    get_point = (360, 1100)  # 获取按钮中心（真实截图在 y≈1100）
    next_point = (360, 1140)  # 中文「下一步」大按钮中心（new_account 截图）
    scenario_point = (360, 360)  # MAA 场景选择 ROI (120,120,480,480) 的中心
    first_option_point = (222, 886)  # MAA ProduceChooseFirst target 的中心
    home_tab_point = (360, 1150)

    min_card_width = 60
    min_card_height = 100
    max_card_width = 220
    max_card_height = 280
    max_hand_cards = 8
    max_scenario_clicks = 2

    default_threshold = 0.85
    thresholds: ClassVar[dict[str, float]] = {
        "home": 0.85,
        "produce_entry": 0.85,
        "produce_ssr_title": 0.62,
        "produce_get": 0.80,
        "produce_exchange": 0.85,
        "produce_cancel": 0.85,
        "produce_cancel_cn": 0.85,
        "decide": 0.85,
        "produce_decide": 0.85,
        "close": 0.85,
        "produce_close": 0.80,
        "produce_next": 0.80,
        "produce_finished": 0.80,
        "produce_continue": 0.85,
        "produce_start": 0.85,
        "produce_recommend": 0.75,
        "produce_event": 0.85,
        "produce_event_recommend": 0.85,
        "produce_auto_support": 0.85,
        "produce_checkbox": 0.90,
        "produce_support_replace": 0.90,
        "produce_mainpage_ranking": 0.80,
        "produce_scenario_hajime": 0.80,
        "produce_scenario_hif": 0.80,
        "produce_scenario_nia": 0.80,
        "produce_health": 0.70,
        "produce_skip_round": 0.85,
        "produce_round_close": 0.85,
        "produce_cards_get": 0.85,
    }

    def __init__(
        self,
        *,
        selection_action: str = "get",
        confirm_get: bool = True,
        scenario: str = "any",
        card_policy: CardRecommender | None = None,
        hand_reader: HandReader | None = None,
        text_reader: TextReader | None = None,
        sleep: Callable[[float], None] | None = None,
        poll_interval: float | None = None,
        click_delay: float | None = None,
        entry_timeout: float | None = None,
        selector_timeout: float | None = None,
        prepare_timeout: float | None = None,
        main_timeout: float | None = None,
        max_steps: int | None = None,
        max_panel_steps: int | None = None,
        max_repeat: int | None = None,
        max_get_clicks: int | None = None,
        get_retry: float | None = None,
        finish_attempts: int | None = None,
        enable_lessons: bool = False,
        replay_db: ReplayDB | None = None,
    ) -> None:
        if selection_action not in ("get", "exchange", "cancel"):
            raise ValueError(f"unsupported selection_action: {selection_action}")
        if scenario not in (*self.SCENARIO_TEMPLATES, "any"):
            raise ValueError(f"unsupported scenario: {scenario}")

        self.selection_action = selection_action
        self.confirm_get = confirm_get
        self.scenario = scenario
        self.hand_reader = hand_reader
        self.text_reader = text_reader
        # 有手牌识别才启用 L1 规则策略；否则回退到模板「推荐」。
        self.card_policy: CardRecommender | None = card_policy
        if self.card_policy is None and hand_reader is not None:
            self.card_policy = RuleCardPolicy()

        self._sleep = time.sleep if sleep is None else sleep
        self.poll_interval = 0.5 if poll_interval is None else poll_interval
        self.click_delay = 0.8 if click_delay is None else click_delay
        self.entry_timeout = 12.0 if entry_timeout is None else entry_timeout
        self.selector_timeout = 10.0 if selector_timeout is None else selector_timeout
        self.prepare_timeout = 20.0 if prepare_timeout is None else prepare_timeout
        self.main_timeout = 1800.0 if main_timeout is None else main_timeout
        self.max_steps = 400 if max_steps is None else max_steps
        self.max_panel_steps = 12 if max_panel_steps is None else max_panel_steps
        self.max_repeat = 6 if max_repeat is None else max_repeat
        self.max_get_clicks = 2 if max_get_clicks is None else max_get_clicks
        self.get_retry = 2.0 if get_retry is None else get_retry
        self.finish_attempts = 3 if finish_attempts is None else finish_attempts
        self.enable_lessons = enable_lessons
        self.lesson_point: tuple[int, int] = (360, 1010)
        self.lesson_template = "produce_lesson_row"
        self.replay_db = replay_db

    # ------------------------------------------------------------------ 识别
    def observe(self, agent: Agent, image: np.ndarray | None = None) -> ProduceScreen:
        """在截图上找齐本任务关心的所有元素；不点击，可离线复用。"""
        img = agent.shot() if image is None else image

        def find(name: str, roi: tuple[int, int, int, int] | None = None) -> Match | None:
            return agent.find(
                name,
                image=img,
                roi=self._clip_roi(roi, img),
                threshold=self.thresholds.get(name, self.default_threshold),
            )

        home = find("home")
        produce_entry = find(self.ENTRY)
        ssr_title = find(self.SSR_TITLE, self.ssr_title_roi)
        if ssr_title is None and self.text_reader is not None and home is None:
            title_texts = self._ocr(img, self.ssr_title_roi)
            if self._has_any(title_texts, ("プロデュースアイドル", "培育偶像", "SSRプロデュース")):
                ssr_title = self._synthetic_match(self.SSR_TITLE, self.ssr_title_roi, img)
        # 获取按钮只在 SSR 选择页语义明确；先认标题，避免主界面的青色按钮误匹配。
        get = find(self.GET, self.get_roi) if ssr_title is not None else None
        exchange = find(self.EXCHANGE)
        cancel = self._find_best(agent, (self.CANCEL, self.CANCEL_CN), img)
        decide = self._find_best(agent, ("decide", self.DECIDE), img)
        close = self._find_best(agent, ("close", self.CLOSE), img)
        next_step = find(self.NEXT)
        finished = find(self.FINISHED)
        continue_ = find(self.CONTINUE)
        start = find(self.START)
        recommend = find(self.RECOMMEND, self.recommend_roi)
        event = find(self.EVENT, self.event_roi)
        event_recommend = find(self.EVENT_RECOMMEND, self.event_roi)
        auto_support = find(self.AUTO_SUPPORT, self.auto_support_roi)
        checkbox = find(self.CHECKBOX, self.checkbox_roi)
        support_replace = find(self.SUPPORT_REPLACE)
        main_page = find(self.MAIN_PAGE, self.main_page_roi)
        scenario = self._find_scenario(agent, img)
        health = find(self.HEALTH, self.health_roi)
        skip_round = find(self.SKIP_ROUND, self.skip_round_roi)
        round_close = find(self.ROUND_CLOSE)
        cards_get = find(self.CARDS_GET)

        # 模板缺失时再用 OCR 兜底；没有 text_reader 就不付这份成本。
        if self.text_reader is not None:
            if (
                get is None
                or cards_get is None
                or finished is None
                or next_step is None
            ):
                bottom_texts = self._ocr(img, self.get_roi)
                if get is None and ssr_title is not None and self._has_any(
                    bottom_texts, ("获取", "獲得", "获得", "受け取る")
                ):
                    get = self._synthetic_point(self.GET, self.get_point)
                if cards_get is None and self._has_any(
                    bottom_texts, ("获取", "领取", "受け取る", "受け取")
                ):
                    cards_get = self._synthetic_point(self.CARDS_GET, self.get_point)
                if next_step is None and self._has_any(
                    bottom_texts, ("下一步", "次へ", "继续", "繼續")
                ):
                    next_step = self._synthetic_point(self.NEXT, self.next_point)
                if (
                    finished is None
                    and ssr_title is None
                    and home is None
                    and self._has_any(bottom_texts, ("完了", "完成", "结束"))
                ):
                    finished = self._synthetic_point(self.FINISHED, self.get_point)

            if (
                auto_support is None
                and home is None
                and ssr_title is None
                and recommend is None
                and event is None
                and main_page is None
                and finished is None
                and close is None
                and cards_get is None
            ):
                support_texts = self._ocr(img, self.auto_support_roi)
                if self._has_any(
                    support_texts, ("おまかせ", "自动编成", "自动选择", "推荐编成", "おすすめ")
                ):
                    auto_support = self._synthetic_match(
                        self.AUTO_SUPPORT, self.auto_support_roi, img
                    )

        screen = ProduceScreen(
            home=home,
            produce_entry=produce_entry,
            ssr_title=ssr_title,
            get=get,
            exchange=exchange,
            cancel=cancel,
            decide=decide,
            close=close,
            next_step=next_step,
            finished=finished,
            continue_=continue_,
            start=start,
            recommend=recommend,
            event=event,
            event_recommend=event_recommend,
            auto_support=auto_support,
            checkbox=checkbox,
            support_replace=support_replace,
            main_page=main_page,
            scenario=scenario,
            health=health,
            skip_round=skip_round,
            round_close=round_close,
            cards_get=cards_get,
        )
        return replace(screen, stage=self.classify(screen))

    @staticmethod
    def classify(screen: ProduceScreen) -> ProduceStage:
        """纯规则：给定一帧识别结果，判断当前阶段（GDE 复用点）。"""
        if screen.home is not None:
            return ProduceStage.HOME
        if screen.ssr_title is not None:
            return ProduceStage.SSR_SELECT
        if screen.recommend is not None or screen.health is not None:
            return ProduceStage.CARD_PLAY
        if screen.skip_round is not None:
            return ProduceStage.CARD_PLAY
        if screen.event_recommend is not None or screen.event is not None:
            return ProduceStage.EVENT
        if (
            screen.auto_support is not None
            or screen.checkbox is not None
            or screen.support_replace is not None
        ):
            return ProduceStage.SUPPORT
        if screen.scenario is not None:
            return ProduceStage.SCENARIO
        if screen.main_page is not None:
            return ProduceStage.MAIN
        if (
            screen.finished is not None
            or screen.continue_ is not None
            or screen.cards_get is not None
            or screen.get is not None
            or screen.next_step is not None
            or screen.start is not None
            or screen.decide is not None
            or screen.close is not None
            or screen.round_close is not None
        ):
            return ProduceStage.RESULT
        return ProduceStage.UNKNOWN

    # ------------------------------------------------------------------ 任务入口
    def resume(self, agent: Agent) -> TaskResult:
        """从当前培育界面继续，不重新进入培育。"""
        image = agent.shot()
        screen = self.observe(agent, image)
        stage = self.classify(screen)
        if (
            stage == ProduceStage.UNKNOWN
            and agent.matcher.find(self.lesson_template, image, threshold=0.8) is not None
        ):
            stage = ProduceStage.MAIN
        if (
            stage == ProduceStage.UNKNOWN
            and agent.matcher.find("produce_dialogue_box", image, threshold=0.8) is not None
        ):
            stage = ProduceStage.MAIN
        if stage == ProduceStage.UNKNOWN:
            home_icon = agent.matcher.find("produce_home_icon", image, threshold=0.8)
            if home_icon is not None:
                agent.click(home_icon)
                self._pause(1.5)
                return self.run(agent)
            return self._play_main(agent)
        if stage in (
            ProduceStage.MAIN,
            ProduceStage.CARD_PLAY,
            ProduceStage.EVENT,
            ProduceStage.RESULT,
            ProduceStage.SUPPORT,
            ProduceStage.SCENARIO,
        ):
            return self._play_main(agent)
        if stage == ProduceStage.HOME:
            return self.run(agent)
        return TaskResult(False, f"当前不在培育流程中：{stage.value}")

    def run(self, agent: Agent) -> TaskResult:
        screen = self.observe(agent)
        if screen.stage in (ProduceStage.HOME, ProduceStage.UNKNOWN):
            if not self._go_home(agent):
                return TaskResult(False, "不在主页，也回不到主页，无法开始培育")
            if not self._enter_produce(agent):
                return TaskResult(
                    False,
                    "进入培育失败：主页未识别到「プロデュース」入口，或点击后未进入培育页面",
                )
            screen = self.observe(agent)

        if screen.ssr_title is not None:
            selection = self._select_ssr(agent)
            if not selection.ok:
                return selection
            if self.selection_action != "get":
                return selection

        prepare = self._prepare(agent)
        if not prepare.ok:
            return prepare

        main = self._play_main(agent)
        if not main.ok:
            return main

        if self._go_home(agent, allow_tab=True):
            return TaskResult(True, "培育完成，已回到主页")
        return TaskResult(False, "培育已结束，但未能回到主页")

    # ------------------------------------------------------------------ 关卡推进
    def _enter_produce(self, agent: Agent) -> bool:
        """主页点「プロデュース」，等待进入 SSR 选择/培育页面。"""
        deadline = time.monotonic() + self.entry_timeout
        while True:
            screen = self.observe(agent)
            if screen.stage in (
                ProduceStage.SSR_SELECT,
                ProduceStage.SCENARIO,
                ProduceStage.SUPPORT,
                ProduceStage.MAIN,
                ProduceStage.CARD_PLAY,
                ProduceStage.EVENT,
            ):
                return True
            if screen.continue_ is not None:
                agent.click(screen.continue_)
                self._pause(self.click_delay)
                continue
            # 主页可能压着公告/登录奖励弹窗；先关弹窗，避免点「プロデュース」时
            # 点穿到弹窗上。
            if (screen.close is not None or screen.decide is not None) and agent.close_popup():
                self._pause(self.click_delay)
                continue
            if screen.produce_entry is not None:
                agent.click(screen.produce_entry)
                self._pause(self.click_delay)
                continue
            if agent.close_popup():
                self._pause(self.click_delay)
                continue
            if time.monotonic() >= deadline:
                return False
            self._pause(self.poll_interval)

    def _select_ssr(self, agent: Agent) -> TaskResult:
        """SSR 偶像选择：默认点「获取」并确认；可配置成变换/取消。"""
        label = self._selection_label()
        if self.selection_action != "get":
            screen = self.observe(agent)
            target: Match | None = screen.exchange
            if self.selection_action == "cancel":
                target = screen.cancel or screen.close
            if target is None:
                return TaskResult(False, f"卡在SSR偶像选择：未识别到{label}按钮")
            agent.click(target)
            self._pause(self.click_delay)
            return TaskResult(True, f"SSR偶像选择：已按配置点击{label}，未获取")

        deadline = time.monotonic() + self.selector_timeout
        get_clicks = 0
        confirm_clicks = 0
        last_get = 0.0
        while True:
            screen = self.observe(agent)
            if screen.stage in (
                ProduceStage.SCENARIO,
                ProduceStage.SUPPORT,
                ProduceStage.MAIN,
                ProduceStage.CARD_PLAY,
                ProduceStage.EVENT,
            ):
                return TaskResult(True, "SSR偶像已获取")
            if screen.stage == ProduceStage.HOME:
                return TaskResult(False, "卡在SSR偶像选择：回到主页，未获取SSR偶像")

            if screen.ssr_title is not None:
                now = time.monotonic()
                ready = get_clicks == 0 or now - last_get >= self.get_retry
                if ready and get_clicks < self.max_get_clicks:
                    target = screen.get or screen.cards_get or screen.decide
                    if target is None:
                        agent.device.click(*self.get_point)
                    else:
                        agent.click(target)
                    get_clicks += 1
                    last_get = now
                    self._pause(self.click_delay)
                    continue
                if now >= deadline:
                    if get_clicks == 0:
                        return TaskResult(False, "卡在SSR偶像选择：未识别到获取按钮")
                    if get_clicks >= self.max_get_clicks:
                        return TaskResult(False, "卡在SSR偶像选择：多次点击获取后仍在选择页")
                    return TaskResult(False, "卡在SSR偶像选择：点击获取后仍在选择页")
                self._pause(self.poll_interval)
                continue

            if self.confirm_get and screen.stage == ProduceStage.RESULT:
                target = screen.decide or screen.cards_get or screen.next_step or screen.close
                if target is not None and confirm_clicks < self.max_get_clicks + 1:
                    agent.click(target)
                    confirm_clicks += 1
                    self._pause(self.click_delay)
                    continue

            if time.monotonic() >= deadline:
                return TaskResult(False, "卡在SSR偶像选择：点击获取后未进入场景选择")
            self._pause(self.poll_interval)

    def _prepare(self, agent: Agent) -> TaskResult:
        """SSR 之后、主界面之前：场景/难度/开始/支援卡自适应推进。"""
        deadline = time.monotonic() + self.prepare_timeout
        stage = "场景选择"
        scenario_clicks = 0
        steps = 0
        while True:
            screen = self.observe(agent)
            if screen.stage in (ProduceStage.CARD_PLAY, ProduceStage.EVENT, ProduceStage.RESULT):
                return TaskResult(True, "已进入培育主界面")
            if screen.stage == ProduceStage.HOME:
                return TaskResult(False, f"卡在{stage}：回到主页，未进入培育主界面")
            if screen.ssr_title is not None:
                return TaskResult(False, "卡在SSR偶像选择：仍未获取SSR偶像")

            handled = False
            if screen.scenario is not None:
                stage = "场景选择"
                if scenario_clicks < self.max_scenario_clicks:
                    agent.click(screen.scenario)
                    scenario_clicks += 1
                    handled = True
            elif screen.main_page is not None:
                stage = "场景选择"
                if scenario_clicks == 0 and self.scenario == "any":
                    agent.device.click(*self.scenario_point)
                    scenario_clicks += 1
                    handled = True
                elif screen.start is not None:
                    agent.click(screen.start)
                    handled = True
                elif screen.decide is not None:
                    agent.click(screen.decide)
                    handled = True
                elif screen.next_step is not None:
                    agent.click(screen.next_step)
                    handled = True

            if not handled and screen.support_replace is not None:
                stage = "支援卡选择"
                cancel = screen.cancel or screen.decide or screen.close
                if cancel is not None:
                    agent.click(cancel)
                    handled = True
            if not handled and screen.auto_support is not None:
                stage = "支援卡选择"
                agent.click(screen.auto_support)
                handled = True
            if not handled and screen.checkbox is not None:
                stage = "支援卡选择"
                agent.click(screen.checkbox)
                handled = True
            if not handled and screen.continue_ is not None:
                stage = "继续培育"
                agent.click(screen.continue_)
                handled = True
            if not handled and screen.start is not None:
                stage = "开始培育"
                agent.click(screen.start)
                handled = True
            if not handled and screen.next_step is not None:
                stage = "支援卡选择"
                agent.click(screen.next_step)
                handled = True
            if not handled and screen.decide is not None:
                agent.click(screen.decide)
                handled = True
            if not handled and screen.close is not None:
                agent.click(screen.close)
                handled = True

            if handled:
                steps += 1
                self._pause(self.click_delay)
                if steps >= self.max_panel_steps:
                    return TaskResult(
                        False, f"卡在{stage}：超过 {self.max_panel_steps} 次点击仍未进入培育主界面"
                    )
                continue
            if agent.close_popup():
                steps += 1
                self._pause(self.click_delay)
                continue
            if time.monotonic() >= deadline:
                return TaskResult(False, f"卡在{stage}：等待超时，未进入培育主界面")
            self._pause(self.poll_interval)

    # ------------------------------------------------------------------ 主循环
    def _play_main(self, agent: Agent) -> TaskResult:
        """培育主界面：出牌 → 事件 → 结算，直到回到主页。"""
        deadline = time.monotonic() + self.main_timeout
        steps = 0
        finished_clicks = 0
        last_digest: str | None = None
        repeats = 0
        stage = "培育主界面"
        stage_since = time.monotonic()
        last_stage = stage
        stuck_actions = 0

        while steps < self.max_steps:
            image = agent.shot()
            screen = self.observe(agent, image)
            digest = self._digest(image)
            if digest == last_digest:
                repeats += 1
            else:
                last_digest = digest
                repeats = 0

            # 下载/加载：只等待，不点击
            if (
                self.enable_lessons
                and agent.matcher.find("produce_loading", image, threshold=0.9) is not None
            ):
                stage_since = time.monotonic()
                self._pause(1.0)
                steps += 1
                continue

            if screen.home is not None:
                return TaskResult(True, "培育已结束，已回到主页")

            now = time.monotonic()
            if stage != last_stage:
                last_stage = stage
                stage_since = now
            if now - stage_since > 15.0:
                stage = "卡住兜底"
                last_stage = stage
                stage_since = now
                stuck_actions += 1
                self._stuck_advance(agent, image, stuck_actions)
                self._pause(self.click_delay)
                steps += 1
                continue

            handled = False
            if screen.finished is not None:
                stage = "结算"
                finished_clicks += 1
                if finished_clicks > self.finish_attempts:
                    if self._go_home(agent, allow_tab=True):
                        return TaskResult(True, "培育已结束，已回到主页")
                    return TaskResult(False, "卡在结算：已点完成但回不到主页")
                agent.click(screen.finished)
                handled = True

            if not handled and screen.stage == ProduceStage.CARD_PLAY:
                stage = "出牌"
                card_play = self.decide_card(agent, image, screen=screen)
                if card_play is not None:
                    self._record(image, card_play)
                    agent.device.click(*card_play.point)
                    handled = True
            if not handled and screen.event_recommend is not None:
                stage = "事件选项"
                agent.click(screen.event_recommend)
                handled = True
            if not handled and screen.event is not None:
                stage = "事件选项"
                agent.device.click(*self.first_option_point)
                handled = True
            if not handled and screen.cards_get is not None:
                stage = "领取奖励"
                agent.click(screen.cards_get)
                handled = True
            if not handled and screen.get is not None:
                stage = "领取奖励"
                agent.click(screen.get)
                handled = True
            if not handled and screen.skip_round is not None:
                stage = "跳过回合"
                agent.click(screen.skip_round)
                handled = True
            if not handled and screen.round_close is not None:
                stage = "回合结算"
                agent.click(screen.round_close)
                handled = True
            if not handled and screen.next_step is not None:
                stage = "结算"
                agent.click(screen.next_step)
                handled = True
            if not handled and screen.decide is not None:
                stage = "确认"
                agent.click(screen.decide)
                handled = True
            if not handled and screen.close is not None:
                stage = "关闭弹窗"
                agent.click(screen.close)
                handled = True
            if not handled and screen.start is not None:
                stage = "开始"
                agent.click(screen.start)
                handled = True
            if not handled and screen.continue_ is not None:
                stage = "继续培育"
                agent.click(screen.continue_)
                handled = True
            if not handled and screen.support_replace is not None:
                stage = "支援卡选择"
                cancel = screen.cancel or screen.decide or screen.close
                if cancel is not None:
                    agent.click(cancel)
                    handled = True
            if not handled and (screen.auto_support is not None or screen.checkbox is not None):
                stage = "支援卡选择"
                support = screen.auto_support or screen.checkbox
                if support is not None:
                    agent.click(support)
                handled = True
            if not handled and screen.scenario is not None:
                stage = "场景选择"
                agent.click(screen.scenario)
                handled = True
            if not handled and screen.main_page is not None:
                stage = "场景选择"
                agent.device.click(*self.scenario_point)
                handled = True
            if (
                not handled
                and self.enable_lessons
                and agent.matcher.find(self.lesson_template, image, threshold=0.8) is not None
            ):
                stage = "课程选择"
                agent.device.click(*self.lesson_point)
                handled = True
            if not handled and self.enable_lessons:
                for action_template in ("produce_class", "produce_reward", "produce_rest"):
                    action = agent.matcher.find(action_template, image, threshold=0.8)
                    if action is not None:
                        stage = "主界面行动"
                        agent.click(action)
                        handled = True
                        break
            if not handled and self.enable_lessons:
                get_btn = agent.matcher.find_any(
                    ["produce_claim", "produce_claim2"],
                    image,
                    threshold=0.8,
                )
                if get_btn is not None:
                    stage = "领取奖励"
                    agent.device.click(360, 900)
                    self._pause(self.click_delay)
                    agent.device.click(*get_btn.center)
                    handled = True
            if (
                not handled
                and self.enable_lessons
                and agent.matcher.find("produce_dialogue_box", image, threshold=0.8) is not None
            ):
                stage = "剧情"
                agent.device.click(360, 1000)
                handled = True
            if not handled and self.enable_lessons and self._looks_like_dialogue(image):
                stage = "剧情"
                agent.device.click(360, 1000)
                handled = True
            if not handled and self.enable_lessons:
                hand = self.read_hand(image)
                if hand.boxes:
                    stage = "出牌"
                    card_play = self.decide_card(agent, image, screen=screen)
                    if card_play is not None:
                        self._record(image, card_play)
                        agent.device.click(*card_play.point)
                        handled = True

            if handled:
                repeats = 0
                steps += 1
                self._pause(self.click_delay)
                continue
            if agent.close_popup(image):
                stage = "关闭弹窗"
                steps += 1
                self._pause(self.click_delay)
                continue
            if time.monotonic() >= deadline:
                return TaskResult(False, f"卡在{stage}：等待超过 {self.main_timeout:.1f}s")
            self._pause(self.poll_interval)
            steps += 1

        return TaskResult(False, f"超过 {self.max_steps} 步仍未完成，卡在{stage}")

    # ------------------------------------------------------------------ 出牌
    def decide_card(
        self,
        agent: Agent,
        image: np.ndarray | None = None,
        screen: ProduceScreen | None = None,
    ) -> CardPlay | None:
        """出牌决策：手牌 + gkagent.policy 优先，其次模板「推荐」。"""
        img = agent.shot() if image is None else image
        current = self.observe(agent, img) if screen is None else screen
        # 始终识别手牌/费用：即使暂时没有策略，也能把状态留给后续 GDE 复用。
        hand = self.read_hand(img)
        for index, card in enumerate(hand.cards):
            if getattr(card, "suggested", False) and index < len(hand.boxes):
                return CardPlay(self._box_center(hand.boxes[index]), "suggested", index)
        if hand.cards and self.card_policy is not None:
            recommendation = self.card_policy.recommend(self._observation(hand))
            if (
                recommendation is not None
                and 0 <= recommendation.index < len(hand.boxes)
            ):
                return CardPlay(
                    self._box_center(hand.boxes[recommendation.index]),
                    f"policy:{recommendation.reason}",
                    recommendation.index,
                )
        if current.recommend is not None:
            return CardPlay(current.recommend.center, "template:recommend")
        if current.event_recommend is not None:
            return CardPlay(current.event_recommend.center, "template:event_recommend")
        if hand.boxes:
            return CardPlay(self._box_center(hand.boxes[0]), "first_hand_card", 0)
        if current.cards_get is not None:
            return CardPlay(current.cards_get.center, "template:cards_get")
        return None

    def read_hand(self, image: np.ndarray) -> HandState:
        """识别手牌与费用。

        默认用轮廓找底部手牌框，费用由可选的 ``text_reader`` OCR 读；注入
        ``hand_reader`` 时完全交给外部识别（例如 ONNX 检测器）。
        """
        if self.hand_reader is not None:
            result = self.hand_reader(image)
            if isinstance(result, HandState):
                return result
            cards, boxes = result
            card_list = list(cards)
            box_list = [tuple(int(v) for v in box) for box in boxes]
            while len(card_list) < len(box_list):
                card_list.append(Card(card_id=f"hand_{len(card_list)}"))
            return HandState(tuple(card_list[: len(box_list)]), tuple(box_list))

        boxes = self._detect_hand_boxes(image)
        cards = tuple(
            Card(
                card_id=f"hand_{index}",
                cost=self._read_cost(image, box),
                playable=True,
            )
            for index, box in enumerate(boxes)
        )
        return HandState(cards, tuple(boxes))

    def _detect_hand_boxes(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        roi = self._clip_roi(self.hand_roi, image)
        if roi is None:
            return []
        ox, oy, rw, rh = roi
        crop = image[oy : oy + rh, ox : ox + rw]
        if crop.size == 0:
            return []
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 180)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes: list[tuple[int, int, int, int]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < self.min_card_width or h < self.min_card_height:
                continue
            if w > self.max_card_width or h > self.max_card_height:
                continue
            if h / w < 1.1 or h / w > 2.4:
                continue
            if w * h < 6000:
                continue
            boxes.append((ox + x, oy + y, w, h))
        return self._dedupe_boxes(boxes)[: self.max_hand_cards]

    def _read_cost(self, image: np.ndarray, box: tuple[int, int, int, int]) -> int | None:
        if self.text_reader is None:
            return None
        x, y, w, h = box
        roi = self._clip_roi((x, y, max(16, w // 4), max(16, h // 5)), image)
        if roi is None:
            return None
        for text in self._ocr(image, roi):
            match = re.search(r"\d{1,2}", text)
            if match is not None:
                return int(match.group(0))
        return None

    @staticmethod
    def _observation(hand: HandState) -> Observation:
        return Observation(
            frame_id=0,
            ts_ms=0,
            screen="produce_card",
            phase=Phase.PRODUCE,
            hand=list(hand.cards),
            confidence=1.0 if hand.cards else 0.0,
            raw={
                "boxes": [list(box) for box in hand.boxes],
                "scores": [1.0] * len(hand.boxes),
            },
        )

    # ------------------------------------------------------------------ 收尾
    def _go_home(self, agent: Agent, allow_tab: bool = True) -> bool:
        if agent.ensure_home(attempts=2):
            return True
        agent.close_popup()
        if agent.ensure_home(attempts=2):
            return True
        if not allow_tab:
            return False
        image = agent.shot()
        tab = agent.find("home_tab", image=image, threshold=0.9)
        if tab is not None:
            agent.click(tab)
        else:
            agent.device.click(*self.home_tab_point)
        self._pause(self.click_delay)
        return agent.ensure_home(attempts=2)

    # ------------------------------------------------------------------ 工具
    def _selection_label(self) -> str:
        return {"get": "获取", "exchange": "变换", "cancel": "取消"}[self.selection_action]

    def _find_scenario(self, agent: Agent, image: np.ndarray) -> Match | None:
        if self.scenario == "any":
            names = list(self.SCENARIO_TEMPLATES.values())
        else:
            names = [self.SCENARIO_TEMPLATES[self.scenario]]
        return self._find_best(agent, names, image)

    def _find_best(
        self,
        agent: Agent,
        names: tuple[str, ...] | list[str],
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> Match | None:
        best: Match | None = None
        for name in names:
            match = agent.find(
                name,
                image=image,
                roi=self._clip_roi(roi, image),
                threshold=self.thresholds.get(name, self.default_threshold),
            )
            if match is not None and (best is None or match.score > best.score + 0.001):
                best = match
        return best

    def _ocr(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None,
    ) -> tuple[str, ...]:
        if self.text_reader is None:
            return ()
        try:
            texts = self.text_reader(image, roi)
        except Exception:  # noqa: BLE001 - OCR 适配器失败时只跳过兜底，不中断状态机
            return ()
        return tuple(str(text) for text in texts if str(text).strip())

    @staticmethod
    def _has_any(texts: tuple[str, ...], needles: tuple[str, ...]) -> bool:
        return any(needle in text for text in texts for needle in needles)

    @staticmethod
    def _synthetic_match(
        name: str,
        roi: tuple[int, int, int, int],
        image: np.ndarray,
    ) -> Match:
        clipped = ProduceTask._clip_roi(roi, image) or roi
        x, y, w, h = clipped
        return Match(name, x, y, w, h, 0.5)

    @staticmethod
    def _synthetic_point(name: str, point: tuple[int, int]) -> Match:
        x, y = point
        return Match(name, x - 40, y - 20, 80, 40, 0.5)

    @staticmethod
    def _clip_roi(
        roi: tuple[int, int, int, int] | None,
        image: np.ndarray,
    ) -> tuple[int, int, int, int] | None:
        if roi is None:
            return None
        height, width = image.shape[:2]
        x, y, w, h = roi
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))
        return x, y, w, h

    @staticmethod
    def _box_center(box: tuple[int, int, int, int]) -> tuple[int, int]:
        x, y, w, h = box
        return x + w // 2, y + h // 2

    @classmethod
    def _dedupe_boxes(
        cls,
        boxes: list[tuple[int, int, int, int]],
    ) -> list[tuple[int, int, int, int]]:
        kept: list[tuple[int, int, int, int]] = []
        for box in sorted(boxes, key=lambda item: item[2] * item[3], reverse=True):
            if all(cls._iou(box, other) < 0.4 for other in kept):
                kept.append(box)
        return sorted(kept, key=lambda item: item[0])

    @staticmethod
    def _iou(
        left: tuple[int, int, int, int],
        right: tuple[int, int, int, int],
    ) -> float:
        lx, ly, lw, lh = left
        rx, ry, rw, rh = right
        x1 = max(lx, rx)
        y1 = max(ly, ry)
        x2 = min(lx + lw, rx + rw)
        y2 = min(ly + lh, ry + rh)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        intersection = (x2 - x1) * (y2 - y1)
        union = lw * lh + rw * rh - intersection
        return intersection / union if union else 0.0

    def _record(self, image: np.ndarray, card_play: CardPlay) -> None:
        """把一次出牌决策写入回放库，供 BC/搜索训练。"""
        if self.replay_db is None or card_play.index is None:
            return
        hand = self.read_hand(image)
        if not hand.cards:
            return
        self.replay_db.record(
            frame_hash=self._digest(image),
            state_json=self._observation(hand),
            action_json={
                "index": card_play.index,
                "point": list(card_play.point),
                "source": card_play.source,
            },
            reward=0.0,
        )

    def _stuck_advance(self, agent: Agent, image: np.ndarray, index: int) -> None:
        """卡住超过 15s：按顺序尝试下一步。"""
        home_icon = None
        try:
            home_icon = agent.matcher.find("produce_home_icon", image, threshold=0.8)
        except FileNotFoundError:
            home_icon = None
        if home_icon is not None:
            agent.click(home_icon)
            return
        for template in (
            "produce_retry",
            "produce_claim",
            "produce_claim2",
            "produce_get",
            "decide",
            "close",
        ):
            try:
                match = agent.matcher.find(template, image, threshold=0.8)
            except FileNotFoundError:
                continue
            if match is not None:
                agent.click(match)
                return
        points = [
            (360, 1000),
            (360, 900),
            (150, 860),
            (500, 860),
            (630, 700),
            (630, 795),
            (630, 890),
            (360, 1100),
            (620, 1195),
            (380, 1130),
            (95, 1200),
            (60, 80),
        ]
        x, y = points[(index - 1) % len(points)]
        agent.device.click(x, y)

    @staticmethod
    def _looks_like_dialogue(image: np.ndarray) -> bool:
        roi = image[950:1140, 40:680]
        return bool(roi.size) and float(roi.mean()) > 190.0

    @staticmethod
    def _digest(image: np.ndarray) -> str:
        if image.size == 0:
            return ""
        small = cv2.resize(image, (48, 48), interpolation=cv2.INTER_AREA)
        return hashlib.sha1(small.tobytes()).hexdigest()

    def _pause(self, seconds: float) -> None:
        if seconds > 0:
            self._sleep(seconds)
