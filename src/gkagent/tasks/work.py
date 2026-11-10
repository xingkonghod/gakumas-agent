"""安排工作：主页 → 左侧「工作」→ 选类型/偶像/时长 → 开始 → 领取 → 回主页。

MAA 在中文 UI 下用 OCR 找「お仕事」/「4時間」，但汉化后入口是「工作」、时长是
「*小时」，所以 WorkHomeFlag / WorkClick / WorkChoose*Time 会卡住。这里不复用
MAA pipeline，只用自己的模板匹配推进状态机，决策逻辑集中在本类，方便 GDE 以后
直接调用或移植。
"""

from __future__ import annotations

import time

import numpy as np

from gkagent.agent import Agent
from gkagent.tasks.base import TaskResult
from gkagent.vision.matcher import Match


class WorkTask:
    name = "work"

    # 中文主页左侧「工作」入口（在 720x1280 截图里约 x=49..93, y=722..744）。
    work_entry_roi = (0, 620, 200, 220)
    work_entry_threshold = 0.65
    button_threshold = 0.85

    max_steps = 12
    after_entry_delay = 1.2
    after_click_delay = 0.9
    after_start_delay = 1.5

    def run(self, agent: Agent) -> TaskResult:
        if not agent.ensure_home():
            return TaskResult(False, "不在主页，无法找到左侧工作入口")

        entry = self._find_work_entry(agent)
        for _ in range(2):
            # 主页可能压着活动/公告弹窗，关掉后再找。
            if entry is not None or not agent.close_popup():
                break
            entry = self._find_work_entry(agent)
        if entry is None:
            return TaskResult(False, "卡在工作入口：主页左侧未识别到 work_entry.png")

        agent.click(entry)
        time.sleep(self.after_entry_delay)

        stage = "工作选择页"
        started = False
        rewarded = False
        popup_closed = False

        for _ in range(self.max_steps):
            image = agent.shot()

            # 1) 已完成的工作：反复领取奖励（MAA 的 WorkFinished 也会循环）。
            reward = agent.find("work_finish", image=image, threshold=self.button_threshold)
            if reward is not None:
                agent.click(reward)
                rewarded = True
                stage = "领取奖励"
                time.sleep(self.after_click_delay)
                continue

            # 2) 还没开始工作：按 类型 → 偶像 → 时长 → 开始 的顺序推进。
            if not started and not rewarded:
                kind = self._find_best(
                    agent,
                    ("work_choose_show", "work_choose_live"),
                    image,
                )
                if kind is not None:
                    agent.click(kind)
                    stage = "选择工作类型"
                    time.sleep(self.after_click_delay)
                    continue

                idol = agent.find("work_choose_idol", image=image, threshold=self.button_threshold)
                if idol is not None:
                    agent.click(idol)
                    stage = "选择偶像"
                    time.sleep(self.after_click_delay)
                    continue

                sure = agent.find("work_sure", image=image, threshold=self.button_threshold)
                if sure is not None:
                    agent.click(sure)
                    stage = "确认时长"
                    time.sleep(self.after_click_delay)
                    continue

                decide = agent.find("decide", image=image, threshold=self.button_threshold)
                if decide is not None:
                    agent.click(decide)
                    stage = "确认选择"
                    time.sleep(self.after_click_delay)
                    continue

                start = agent.find("work_start", image=image, threshold=self.button_threshold)
                if start is not None:
                    agent.click(start)
                    started = True
                    stage = "开始工作"
                    time.sleep(self.after_start_delay)
                    continue

            # 3) 已开始/已领取：只处理「确定」类收尾弹窗，避免重复开一份工作。
            else:
                finish_confirm = agent.find(
                    "work_sure", image=image, threshold=self.button_threshold
                )
                if finish_confirm is None:
                    finish_confirm = agent.find(
                        "decide", image=image, threshold=self.button_threshold
                    )
                if finish_confirm is not None:
                    agent.click(finish_confirm)
                    stage = "确认收尾"
                    time.sleep(self.after_click_delay)
                    continue

            # 4) 未识别的弹窗/工作页：最多关一次，避免卡死，也避免把已有工作当成新工作。
            if not popup_closed:
                close = agent.find("close", image=image, threshold=self.button_threshold)
                if close is not None:
                    agent.click(close)
                    popup_closed = True
                    time.sleep(self.after_click_delay)
                    continue

            # 5) 回到主页才算收尾成功。
            if self._is_home(agent, image):
                if rewarded:
                    return TaskResult(True, "工作奖励已领取，已回到主页")
                if started:
                    return TaskResult(True, "工作已开始，已回到主页")
                if popup_closed:
                    return TaskResult(False, f"卡在{stage}：没有可用的下一步按钮，已关闭工作页")
                return TaskResult(False, "回到主页，但没有识别到开始/领取动作")

            # 6) 工作页可能还留着底部 tab：已经点过开始/领取时，直接回主页收尾。
            if (started or rewarded) and agent.ensure_home(attempts=2):
                if rewarded:
                    return TaskResult(True, "工作奖励已领取，已回到主页")
                return TaskResult(True, "工作已开始，已回到主页")

            return TaskResult(
                False,
                f"卡在{stage}：未识别到下一步按钮"
                "（work_finish/work_choose_*/work_sure/decide/work_start）",
            )

        if (started or rewarded) and agent.ensure_home(attempts=2):
            if rewarded:
                return TaskResult(True, "工作奖励已领取，已回到主页")
            return TaskResult(True, "工作已开始，已回到主页")
        return TaskResult(False, f"超过 {self.max_steps} 步仍未完成，卡在{stage}")

    def _find_work_entry(self, agent: Agent) -> Match | None:
        image = agent.shot()
        match = agent.find(
            "work_entry",
            image=image,
            roi=self.work_entry_roi,
            threshold=self.work_entry_threshold,
        )
        if match is not None:
            return match
        # 少部分窗口高度是 1279，文字会被压 1px；放大搜索范围再试一次。
        return agent.find(
            "work_entry",
            image=image,
            roi=(0, 600, 240, 260),
            threshold=0.62,
        )

    def _find_best(
        self,
        agent: Agent,
        names: tuple[str, ...],
        image: np.ndarray,
    ) -> Match | None:
        best: Match | None = None
        for name in names:
            match = agent.find(name, image=image, threshold=self.button_threshold)
            # 分数非常接近时保留先列出的模板，避免浮点误差让「演出/直播」随机切换。
            if match is not None and (best is None or match.score > best.score + 0.001):
                best = match
        return best

    @staticmethod
    def _is_home(agent: Agent, image: np.ndarray) -> bool:
        return agent.find("home", image=image, threshold=0.85) is not None
