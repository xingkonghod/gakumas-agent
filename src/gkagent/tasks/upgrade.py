"""偶像 / 支援卡强化任务：固定流程 + OCR 守卫。

实测（2026-11-12）：
- 支援卡：偶像菜单「支援卡」→ 卡牌网格 → 点第一张 → 详情「Lv强化」→ 确认页「Lv强化」
  （支援卡详情页不显示卡名，OCR 无法按名字选，因此按列表顺序练）
- 偶像：偶像菜单「培养/ P偶像」→ 偶像详情（名字可见）→「特训」→「进行特训」

统一逻辑：
- 导航用 Navigator（OCR 找入口）
- 执行前检查付费/购买字样，出现就中止
- dry_run 只走到确认页，不点最后的强化/特训
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from gkagent.agent import Agent
from gkagent.data.cards_db import CardLibrary
from gkagent.data.items_db import ItemLibrary
from gkagent.nav import Navigator
from gkagent.tasks.base import TaskResult
from gkagent.vision.ocr import OcrEngine, OcrLine

LEVEL_RE = re.compile(r"(?:Lv\.?|等级)\s*(\d{1,3})|^(\d{1,3})$")
FORBIDDEN = ("付费", "钻石", "购买", "购入")

BACK_POINT = (283, 1192)
SUPPORT_GRID_CARD = (120, 530)
SUPPORT_DETAIL_LV = (196, 1070)
SUPPORT_CONFIRM = (455, 1155)
IDOL_TRAIN = (180, 792)
IDOL_PAGE_CONFIRM = (526, 1212)
IDOL_DIALOG_CONFIRM = (522, 1160)
IDOL_DIALOG_CANCEL = (240, 1160)


@dataclass(frozen=True)
class Owned:
    name: str
    level: int
    box: tuple[int, int, int, int]


class UpgradeTask:
    name = "upgrade"

    def __init__(
        self,
        kind: str = "support",
        limit: int = 3,
        *,
        ocr: OcrEngine | None = None,
        cards: CardLibrary | None = None,
        items: ItemLibrary | None = None,
        dry_run: bool = False,
    ) -> None:
        self.kind = kind
        self.limit = limit
        self.ocr = ocr or OcrEngine()
        self.cards = cards or CardLibrary()
        self.items = items or ItemLibrary()
        self.dry_run = dry_run

    # ------------------------------------------------------------------ 入口
    def run(self, agent: Agent) -> TaskResult:
        nav = Navigator(agent, self.ocr)
        nav.ensure_home()
        if self.kind == "support":
            if not nav.support_screen():
                return TaskResult(False, "没有到达支援卡界面")
            return self._run_support(nav, agent)
        if not nav.idol_screen():
            return TaskResult(False, "没有到达偶像界面")
        return self._run_idol(nav, agent)

    # ------------------------------------------------------------------ 执行
    @staticmethod
    def _text(nav: Navigator) -> str:
        return " ".join(line.text for line in nav.lines())

    @classmethod
    def _back(cls, nav: Navigator, times: int = 1) -> None:
        for _ in range(times):
            nav.agent.device.click(*BACK_POINT)
            time.sleep(0.8)

    def _run_support(self, nav: Navigator, agent: Agent) -> TaskResult:
        """支援卡列表 → 第一张 → 详情「Lv强化」→ 确认页「Lv强化」，反复 limit 次。"""
        done = 0
        for _ in range(self.limit):
            text = self._text(nav)
            if not any(marker in text for marker in ("查看详情", "支援卡加成", "支援卡变换")):
                break
            agent.device.click(*SUPPORT_GRID_CARD)
            time.sleep(2.0)
            text = self._text(nav)
            if "Lv强化" not in text or any(token in text for token in FORBIDDEN):
                break
            if not nav.click_exact("Lv强化"):  # 详情 → 强化确认页
                break
            time.sleep(1.2)
            text = self._text(nav)
            if "取消" not in text:
                nav.click_exact("取消")
                self._back(nav)
                break
            if self.dry_run:
                nav.click_exact("取消")
            elif nav.click_exact("Lv强化"):  # 确认页 → 真正强化
                time.sleep(1.5)
            else:
                nav.click_exact("取消")
                self._back(nav)
                break
            done += 1
            self._back(nav, 2)  # 详情 → 列表
        if done == 0:
            return TaskResult(False, "没有可强化的支援卡")
        mode = "（试运行未消耗）" if self.dry_run else ""
        return TaskResult(True, f"支援卡 Lv强化 {done} 次{mode}")

    def _run_idol(self, nav: Navigator, agent: Agent) -> TaskResult:
        """偶像详情 → 「特训」→ 特训页「进行特训」→ 确认弹窗「进行特训」。"""
        text = self._text(nav)
        if "特训" not in text and "才能开花" not in text:
            return TaskResult(False, "偶像页没有特训/才能开花按钮")
        done = 0
        for _ in range(self.limit):
            if not nav.click_exact("特训"):  # 详情 → 特训页
                break
            time.sleep(1.2)
            text = self._text(nav)
            if "进行特训" not in text:
                self._back(nav)
                break
            if not nav.click_exact("进行特训"):  # 特训页 → 确认弹窗
                self._back(nav)
                break
            time.sleep(1.2)
            text = self._text(nav)
            if "特训阶段确认" in text and any(token in text for token in FORBIDDEN):
                nav.click_exact("取消")
                self._back(nav)
                break
            if self.dry_run:
                if "特训阶段确认" in text:
                    nav.click_exact("取消")  # 关掉确认弹窗，不消耗
                    time.sleep(0.8)
                self._back(nav)
                done += 1
                continue
            if "特训阶段确认" not in text:
                # 没有确认弹窗：素材不足/按钮不可用
                self._back(nav)
                break
            if not nav.click_exact("进行特训"):  # 弹窗 → 真正特训
                self._back(nav)
                break
            time.sleep(2.2)
            done += 1
            self._back(nav)
        if done == 0:
            return TaskResult(False, "没有可特训的偶像")
        mode = "（试运行未消耗）" if self.dry_run else ""
        return TaskResult(True, f"偶像特训 {done} 次{mode}")

    # ------------------------------------------------------------------ 识别
    def read_owned(self, lines: list[OcrLine]) -> list[Owned]:
        owned: list[Owned] = []
        for line in lines:
            info = self.cards.find(line.text) or self.items.find(line.text)
            if info is None:
                continue
            owned.append(Owned(info.name, self._level_near(line, lines), line.box))
        # 同名去重
        seen: set[str] = set()
        unique: list[Owned] = []
        for item in owned:
            if item.name in seen:
                continue
            seen.add(item.name)
            unique.append(item)
        return unique

    @staticmethod
    def _level_near(line: OcrLine, lines: list[OcrLine]) -> int:
        x, y, _w, _h = line.box
        best: int | None = None
        for other in lines:
            if other is line:
                continue
            ox, oy, _ow, _oh = other.box
            if abs(oy - y) > 60 or abs(ox - x) > 500:
                continue
            match = LEVEL_RE.search(other.text)
            if match:
                value = match.group(1) or match.group(2)
                best = max(best or 0, int(value))
        return best or 0

    @staticmethod
    def _has_forbidden(lines: list[OcrLine]) -> bool:
        return any(token in line.text for line in lines for token in FORBIDDEN)
