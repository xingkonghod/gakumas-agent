"""偶像 / 支援卡强化任务：OCR 列表 → Tier 规划 → 自动强化。

统一逻辑：
- 导航用 Navigator（OCR 找入口，不写死每个界面）
- 优先级用 data/tier.py（网上攻略 Tier）
- 识别用 vision/ocr.py + data/cards_db/items_db
- 执行只做素材强化，遇到付费/购买直接中止
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from gkagent.agent import Agent
from gkagent.data.cards_db import CardLibrary
from gkagent.data.items_db import ItemLibrary
from gkagent.data.tier import UpgradeTarget, plan_upgrades
from gkagent.nav import Navigator
from gkagent.tasks.base import TaskResult
from gkagent.vision.ocr import OcrEngine, OcrLine

LEVEL_RE = re.compile(r"(?:Lv\.?|等级)\s*(\d{1,3})|^(\d{1,3})$")
ACTION_LABELS = ("强化", "特训", "上限解放", "才能开花")
CONFIRM_LABELS = ("执行", "确定", "确认", "强化")
FORBIDDEN = ("付费", "钻石", "购买", "购入")


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
        reached = nav.support_screen() if self.kind == "support" else nav.idol_screen()
        if not reached:
            return TaskResult(False, f"没有到达 {'支援卡' if self.kind == 'support' else '偶像'} 强化界面")

        owned = self.read_owned(nav.lines())
        if not owned:
            return TaskResult(False, "列表里没识别到卡名")

        plan = plan_upgrades([(o.name, o.level) for o in owned], limit=self.limit)
        if not plan:
            nav.home()
            return TaskResult(False, "Tier 表里没有可升级目标")

        if self.dry_run:
            nav.home()
            return TaskResult(True, "计划: " + ", ".join(f"{t.name}({t.tier})" for t in plan))

        done: list[str] = []
        for target in plan:
            try:
                if self._upgrade_one(nav, target, owned):
                    done.append(target.name)
            except Exception:  # noqa: BLE001, S112
                continue
        nav.home()
        return TaskResult(True, f"已升级 {len(done)} 个: {', '.join(done)}")

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

    # ------------------------------------------------------------------ 执行
    def _upgrade_one(self, nav: Navigator, target: UpgradeTarget, owned: list[Owned]) -> bool:
        box = next((o.box for o in owned if o.name == target.name), None)
        if box is None:
            return False
        x, y, w, h = box
        nav.agent.device.click(x + w // 2, y + h // 2)
        time.sleep(1.0)

        lines = nav.lines()
        if self._has_forbidden(lines):
            nav.home()
            return False

        for label in ACTION_LABELS:
            if nav.click_text(label, lines):
                break
        else:
            return False

        after = nav.lines()
        if self._has_forbidden(after):
            nav.home()
            return False
        for label in CONFIRM_LABELS:
            if nav.click_text(label, after):
                break
        return True
