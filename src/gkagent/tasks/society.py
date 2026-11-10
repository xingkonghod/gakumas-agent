"""社团活动：主页 → 菜单 → 社团 → 捐赠（捐赠/已捐赠）→ 募集（可选）→ 回主页。

MAA（MaaGakumasu）在中文 UI 下的失败点：

- ``SocietyCommitAlready`` 用 RGBCount + 0.95 阈值，中文 UI 的「已捐赠」实测只有
  ~0.80，认不出来后就反复点 CloseButton / ReturnHome，最后停在社团页；
- ``SocietyRequestAuto`` 依赖 OCR + Custom Recognition，中文 UI 下 OCR 失败时
  ``best_result`` 为 None，请求弹窗里直接异常，流程出不去。

这里不复用 MAA pipeline，只用 Agent 的截屏/模板匹配/点击推进状态机：

1. 主页点右下角菜单（society_menu.png），再点「社团」（society_entry.png）；
2. 社团页优先认「已捐赠」（society_commit_already.png），认到就跳过捐赠；
   否则点「捐赠」（society_commit.png），用 society_next.png 翻页、decide.png 确认；
3. 再找「募集」（society_requests.png）：找到就点开，只处理「募集领取」
   （society_requests_get.png）和「关闭」，不选物品、不点决定，因此不会触发
   SocietyRequestAuto；已经是「募集中」（society_requests_already.png）就不重复募集；
4. 最后尽力回主页；菜单打开时主页 tab 会被压暗，ensure_home 认不出，所以先用
   society_close_menu.png 关掉菜单再回。

``classify`` / ``donation_state`` / ``request_state`` 是纯决策方法（只读截图，
不点击），GDE 以后可以把 MAA 的截图或自己的识别结果喂进来复用。
"""

from __future__ import annotations

import time

import numpy as np

from gkagent.agent import Agent
from gkagent.tasks.base import TaskResult


class SocietyTask:
    name = "society"

    # 模板（全部复制自 MaaGakumasu resource/base/image，见 templates/）。
    HOME = "home"
    ENTRY = "society_entry"  # MAA society.png：菜单里的「社团」
    MENU = "society_menu"  # MAA menu.png：主页右下角菜单
    CLOSE_MENU = "society_close_menu"  # MAA close_menu.png：菜单的 X
    COMMIT = "society_commit"  # 「捐赠」
    COMMIT_ALREADY = "society_commit_already"  # 「已捐赠」
    REQUESTS = "society_requests"  # 黄色「募集」
    REQUESTS_ALREADY = "society_requests_already"  # 橙色「募集中」
    REQUESTS_GET = "society_requests_get"  # 「募集领取」
    NEXT = "society_next"  # 捐赠物品列表的翻页箭头
    CLOSE = "close"
    CLOSE_ICON = "society_close_icon"  # MAA close_icon.png：弹窗右上角的圆 X
    DECIDE = "decide"

    # 坐标来自 MAA Society.json；社团页的捐赠/已捐赠按钮都在这个 ROI 里。
    donation_roi = (26, 750, 666, 250)
    # 底部 tab 栏：成员 / 募集 / 募集列表。
    requests_roi = (0, 1000, 720, 280)
    # 主页右下角菜单、菜单的关闭 X。
    menu_roi = (500, 1080, 220, 200)
    # MAA CloseRoundButton 的 ROI：弹窗右上角圆 X 一般在下半屏。
    close_icon_roi = (0, 780, 720, 500)

    button_threshold = 0.85
    entry_threshold = 0.85
    # menu.png 在白天/夜晚主页背景上只有 0.71~0.81，但社团页只有 0.24，0.60 足够区分。
    menu_threshold = 0.60
    close_menu_threshold = 0.60
    close_icon_threshold = 0.80
    # MAA 对 society_next.png 用默认的 0.70；它是白底浅色箭头，阈值高了容易漏。
    next_threshold = 0.70

    # 等待页面切换的最长时间；测试里传 0 就只检查一次当前截图。
    settle_timeout = 4.0
    poll_interval = 0.4
    click_delay = 0.8
    max_panel_steps = 6

    def __init__(
        self,
        *,
        settle_timeout: float | None = None,
        poll_interval: float | None = None,
        click_delay: float | None = None,
        max_panel_steps: int | None = None,
    ) -> None:
        if settle_timeout is not None:
            self.settle_timeout = settle_timeout
        if poll_interval is not None:
            self.poll_interval = poll_interval
        if click_delay is not None:
            self.click_delay = click_delay
        if max_panel_steps is not None:
            self.max_panel_steps = max_panel_steps

    # ------------------------------------------------------------------ run

    def run(self, agent: Agent) -> TaskResult:
        started_on_society = self.classify(agent, agent.shot()) == "society"

        if not started_on_society:
            if not self._return_home(agent):
                return TaskResult(False, "不在主页，也回不到主页，无法开始社团活动")
            if not self._open_society(agent):
                return TaskResult(False, "从主页菜单进入社团失败")

        donation = self._donate(agent)
        request = self._request(agent)
        home = self._return_home(agent)

        return TaskResult(
            donation in ("donated", "already") and home,
            self._message(donation, request, home),
        )

    # ------------------------------------------------------- 决策逻辑（GDE 可复用）

    def classify(self, agent: Agent, image: np.ndarray) -> str:
        """判断当前截图：home / menu / society / unknown。"""
        if agent.find(self.HOME, image=image, threshold=0.85) is not None:
            return "home"
        if agent.find(self.ENTRY, image=image, threshold=self.entry_threshold) is not None:
            return "menu"
        if self.donation_state(agent, image) != "unknown":
            return "society"
        if self.request_state(agent, image) != "unknown":
            return "society"
        return "unknown"

    def donation_state(self, agent: Agent, image: np.ndarray) -> str:
        """判断捐赠状态：already（已捐赠）/ ready（可捐赠）/ unknown。"""
        if (
            agent.find(
                self.COMMIT_ALREADY,
                image=image,
                roi=self.donation_roi,
                threshold=self.button_threshold,
            )
            is not None
        ):
            return "already"
        if (
            agent.find(
                self.COMMIT,
                image=image,
                roi=self.donation_roi,
                threshold=self.button_threshold,
            )
            is not None
        ):
            return "ready"
        return "unknown"

    def request_state(self, agent: Agent, image: np.ndarray) -> str:
        """判断募集状态：open（可募集）/ already（募集中）/ unknown。"""
        if (
            agent.find(
                self.REQUESTS,
                image=image,
                roi=self.requests_roi,
                threshold=self.button_threshold,
            )
            is not None
        ):
            return "open"
        if (
            agent.find(
                self.REQUESTS_ALREADY,
                image=image,
                roi=self.requests_roi,
                threshold=self.button_threshold,
            )
            is not None
        ):
            return "already"
        return "unknown"

    # ------------------------------------------------------------- 页面导航

    def _open_society(self, agent: Agent) -> bool:
        image = agent.shot()
        screen = self.classify(agent, image)
        if screen == "society":
            return True

        if screen != "home" and not self._return_home(agent):
            return False

        image = agent.shot()
        menu = agent.find(
            self.MENU,
            image=image,
            roi=self.menu_roi,
            threshold=self.menu_threshold,
        )
        if menu is None and self._close_only(agent):
            # 主页可能压着公告/活动弹窗，挡住右下角菜单；关掉后再找一次。
            image = agent.shot()
            menu = agent.find(
                self.MENU,
                image=image,
                roi=self.menu_roi,
                threshold=self.menu_threshold,
            )
        if menu is None:
            return False
        agent.click(menu)
        self._pause(self.click_delay)

        entry = self._wait_for(
            agent,
            lambda img: agent.find(self.ENTRY, image=img, threshold=self.entry_threshold),
        )
        if entry is None:
            # 菜单开了但没找到社团入口：先关菜单，避免留在菜单里。
            self._close_menu(agent)
            return False

        agent.click(entry)
        self._pause(self.click_delay)

        if self._wait_for(agent, lambda img: self.classify(agent, img) == "society") is None:
            # 进社团后可能先弹公告/登录奖励，关掉后再等社团页。
            if not self._close_only(agent):
                self._return_home(agent)
                return False
            if self._wait_for(agent, lambda img: self.classify(agent, img) == "society") is None:
                self._return_home(agent)
                return False
        return True

    def _return_home(self, agent: Agent) -> bool:
        image = agent.shot()
        if self.classify(agent, image) == "home":
            return True
        if agent.ensure_home(attempts=2):
            return True

        # 菜单打开时底部主页 tab 被压暗（home_tab 只有 ~0.80），ensure_home 不会点；
        # 先点菜单的 X 关掉菜单。
        if self._close_menu(agent) and agent.ensure_home(attempts=2):
            return True

        # 社团/请求页上的「关闭」；这里只点 close，不点 decide，避免误确认。
        if self._close_only(agent) and agent.ensure_home(attempts=2):
            return True

        return self.classify(agent, agent.shot()) == "home"

    def _close_menu(self, agent: Agent) -> bool:
        image = agent.shot()
        close = agent.find(
            self.CLOSE_MENU,
            image=image,
            roi=self.menu_roi,
            threshold=self.close_menu_threshold,
        )
        if close is None:
            return False
        agent.click(close)
        self._pause(self.click_delay)
        return True

    def _close_only(self, agent: Agent) -> bool:
        image = agent.shot()
        close = agent.find(self.CLOSE, image=image, threshold=self.button_threshold)
        if close is None:
            # 有些弹窗只有右上角的圆 X，没有「关闭」文字按钮。
            close = agent.find(
                self.CLOSE_ICON,
                image=image,
                roi=self.close_icon_roi,
                threshold=self.close_icon_threshold,
            )
        if close is None:
            return False
        agent.click(close)
        self._pause(self.click_delay)
        return True

    # --------------------------------------------------------------- 捐赠

    def _donate(self, agent: Agent) -> str:
        image = agent.shot()
        # 先清掉可能压在社团页上的公告/登录奖励弹窗（只点 close）。
        for _ in range(2):
            if self.donation_state(agent, image) != "unknown":
                break
            if not self._close_only(agent):
                break
            image = agent.shot()

        state = self.donation_state(agent, image)
        if state == "already":
            return "already"
        if state != "ready":
            return "failed"

        commit = agent.find(
            self.COMMIT,
            image=image,
            roi=self.donation_roi,
            threshold=self.button_threshold,
        )
        if commit is None:  # pragma: no cover - donation_state 已确认
            return "failed"

        agent.click(commit)
        self._pause(self.click_delay)
        return "donated" if self._confirm_donation(agent) else "failed"

    def _confirm_donation(self, agent: Agent) -> bool:
        for _ in range(self.max_panel_steps):
            image = agent.shot()
            if self.donation_state(agent, image) == "already":
                return True

            # 物品列表有多页时，MAA 是左右滑动翻页，再点决定。
            nxt = agent.find(self.NEXT, image=image, threshold=self.next_threshold)
            if nxt is not None:
                agent.device.swipe(490, 855, 182, 855, 300)
                self._pause(self.click_delay)
                continue

            decide = agent.find(self.DECIDE, image=image, threshold=self.button_threshold)
            if decide is not None:
                agent.click(decide)
                self._pause(self.click_delay)
                continue

            self._close_only(agent)
            break

        if (
            self._wait_for(
                agent,
                lambda img: self.donation_state(agent, img) == "already",
            )
            is not None
        ):
            return True
        # 捐赠完成弹窗可能压着「已捐赠」；关掉后再确认一次。
        if self._close_only(agent):
            return (
                self._wait_for(
                    agent,
                    lambda img: self.donation_state(agent, img) == "already",
                )
                is not None
            )
        return False

    # --------------------------------------------------------------- 募集

    def _request(self, agent: Agent) -> str:
        image = agent.shot()
        state = self.request_state(agent, image)
        if state == "unknown" and self._close_only(agent):
            image = agent.shot()
            state = self.request_state(agent, image)
        if state == "unknown":
            return "skipped"

        name = self.REQUESTS if state == "open" else self.REQUESTS_ALREADY
        button = agent.find(
            name,
            image=image,
            roi=self.requests_roi,
            threshold=self.button_threshold,
        )
        if button is None:  # pragma: no cover - request_state 已确认
            return "skipped"

        agent.click(button)
        self._pause(self.click_delay)
        self._finish_request_page(agent)
        return "opened" if state == "open" else "already"

    def _finish_request_page(self, agent: Agent) -> None:
        """请求页只做两件事：领已完成的募集、关闭。绝不选物品/点决定。"""
        for _ in range(self.max_panel_steps):
            image = agent.shot()

            get = agent.find(
                self.REQUESTS_GET,
                image=image,
                threshold=self.button_threshold,
            )
            if get is not None:
                agent.click(get)
                self._pause(self.click_delay)
                continue

            self._close_only(agent)
            return

    # --------------------------------------------------------------- 工具

    def _wait_for(self, agent: Agent, probe):
        deadline = time.monotonic() + self.settle_timeout
        while True:
            value = probe(agent.shot())
            if value:
                return value
            if time.monotonic() >= deadline:
                return None
            self._pause(self.poll_interval)

    @staticmethod
    def _pause(seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    @staticmethod
    def _message(donation: str, request: str, home: bool) -> str:
        head = {
            "donated": "社团捐赠已完成",
            "already": "社团今日已捐赠，已跳过捐赠",
        }.get(donation, "社团捐赠未完成")
        mid = {
            "opened": "已打开并关闭募集页" if home else "已打开募集页",
            "already": "募集已在处理中",
        }.get(request, "未找到募集入口")
        tail = "已回到主页" if home else "回主页未确认（可能仍在社团页）"
        return f"{head}；{mid}；{tail}"
