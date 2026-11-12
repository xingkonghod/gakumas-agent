"""清点支援卡（重点是 SSR），评估并给出训练优先级。

- 逐张开详情页读：稀有度 / 等级 / 支援能力效果
- 按攻略向规则打分（SSR 优先、SP 训练、能力值加成、低等级优先）
- 输出 data/survey.json，不消耗资源
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

GRID_X = (140, 390, 615)
GRID_Y = (522, 700, 880, 1060)
BACK = (283, 1192)
IDOL_MENU = (198, 1158)
SUPPORT_ENTRY = (368, 930)
GRID_MARKERS = ("查看详情", "支援卡加成", "支援卡变换")


def parse_card(lines: list) -> dict:
    text = " ".join(line.text for line in lines)
    rarity = next((r for r in ("SSR", "SR", "R") if f" {r}" in f" {text}" or text.startswith(r)), "?")
    level = None
    match = re.search(r"Lv\.?\s*(\d{1,3})\s*/\s*(\d{1,3})", text)
    if match:
        level = int(match.group(1))
    effects = [
        line.text
        for line in lines
        if any(key in line.text for key in ("能力值加成", "概率", "能力值上升", "SP", "打分", "支援", "训练"))
        and len(line.text) <= 40
    ]
    return {"rarity": rarity, "level": level, "effects": effects, "text": text[:300]}


def score_card(card: dict) -> float:
    text = " ".join(card["effects"])
    score = {"SSR": 4.0, "SR": 2.5, "R": 1.0}.get(card["rarity"], 0.5)
    if "SP" in text and "概率" in text:
        score += 2.0
    if "能力值加成" in text:
        score += 1.5
    if "训练" in text and "上升" in text:
        score += 1.0
    if "打分" in text:
        score += 1.0
    level = card.get("level")
    if level is not None and level < 20:
        score += 0.5  # 低等级升级收益高
    return score


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from gkagent.agent import Agent
    from gkagent.device.win32 import Win32Device, find_game_hwnd
    from gkagent.nav import Navigator
    from gkagent.vision.matcher import TemplateMatcher
    from gkagent.vision.ocr import OcrEngine

    hwnd = find_game_hwnd()
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    nav = Navigator(agent, OcrEngine())

    def nav_text() -> str:
        return " ".join(line.text for line in nav.lines())

    def ensure_grid(attempts: int = 3) -> bool:
        for _ in range(attempts):
            text = nav_text()
            if any(marker in text for marker in GRID_MARKERS):
                return True
            agent.device.click(*BACK)
            time.sleep(1.2)
        return any(marker in nav_text() for marker in GRID_MARKERS)

    nav.ensure_home()
    agent.device.click(*IDOL_MENU)
    time.sleep(1.5)
    agent.device.click(*SUPPORT_ENTRY)
    time.sleep(2.0)

    cards: list[dict] = []
    for y in GRID_Y:
        for x in GRID_X:
            if not ensure_grid():
                break
            agent.device.click(x, y)  # 选中卡片
            time.sleep(0.8)
            agent.device.click(360, 1105)  # 「查看详情」
            time.sleep(2.0)
            text = nav_text()
            if "Lv强化" not in text:
                agent.device.click(*BACK)
                time.sleep(1.2)
                continue
            card = parse_card(nav.lines())
            card["pos"] = [x, y]
            cards.append(card)
            agent.device.click(*BACK)
            time.sleep(1.4)

    ranking = sorted(
        ({"card": card, "score": score_card(card)} for card in cards),
        key=lambda item: -item["score"],
    )
    report = {"count": len(cards), "cards": cards, "ranking": ranking}
    out = ROOT / "data" / "survey.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:5000])
    print(f"\nsaved: {out}")
    nav.ensure_home()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
