"""自动推进培育：OCR 导航 + 出牌策略，一次跑 N 步，逐步落盘截图/日志。

用法（管理员或经 agent daemon shell 调用）：
    python scripts/auto_produce.py 40

退出条件：培育过程中回到主页 / 步数用尽 / 连续多次识别不到可执行动作。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

import cv2

from gkagent.agent import Agent
from gkagent.device.win32 import Win32Device, find_game_hwnd
from gkagent.policy.search import SearchPolicy
from gkagent.tasks.produce import ProduceTask
from gkagent.tasks.produce_ui import LESSON_WORDS, ProduceDriver
from gkagent.vision.cards import scan_hand
from gkagent.vision.matcher import TemplateMatcher
from gkagent.vision.ocr import OcrEngine

LOG = ROOT / "data" / "auto_log.txt"
SHOT_DIR = ROOT / "data" / "auto"

PRODUCE_MARKERS = (
    "定期公演",
    "请选择行动",
    "选择偶像",
    "选择支援卡",
    "选择回忆",
    "开始确认",
    "剩余回合数",
)
HOME_MARKERS = ("亲密度", "活动经费", "商店", "扭蛋")


def build_task() -> ProduceTask:
    def _hand_reader(image):
        scan = scan_hand(image)
        return list(scan.cards), [tuple(card.box) for card in scan.cards]

    return ProduceTask(
        enable_lessons=True,
        hand_reader=_hand_reader,
        card_policy=SearchPolicy(),
        ocr_policy=None,
    )


def is_home(text: str) -> bool:
    return "主页" in text and any(word in text for word in HOME_MARKERS)


def restore_window() -> None:
    """最小化/黑屏时恢复游戏窗口（本进程已是管理员）。"""
    script = ROOT / "scripts" / "force_show_game.ps1"
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            timeout=30,
            capture_output=True,
        )
    except Exception:
        pass
    time.sleep(2.0)


def main() -> int:
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window", file=sys.stderr)
        return 2
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    task = build_task()
    driver = ProduceDriver(ocr=OcrEngine())
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []
    idle = 0
    done = False
    seen_produce = False

    for step in range(1, steps + 1):
        try:
            image = agent.shot()
        except RuntimeError as exc:
            log_lines.append(f"{step:03d} [capture] {exc}; 尝试恢复窗口")
            idle += 1
            restore_window()
            continue
        cv2.imwrite(str(SHOT_DIR / f"step_{step:03d}.png"), image)
        lines = driver.read(image)
        text = driver.text_of(lines)

        if any(word in text for word in PRODUCE_MARKERS):
            seen_produce = True
        if seen_produce and is_home(text):
            log_lines.append(f"{step:03d} [home] 培育结束，已回主页")
            done = True
            break

        if any(word in text for word in LESSON_WORDS):
            screen = task.observe(agent, image)
            play = task.decide_card(agent, image, screen=screen)
            if play is not None:
                task._record(image, play)
                clicked = agent.device.click_force(*play.point)
                time.sleep(0.9)
                if clicked is False:
                    result = "[pause] 用户正在操作，暂停出牌"
                    idle = 0
                else:
                    result = f"[lesson] play card#{play.index} {play.source} at {play.point}"
                    idle = 0
            else:
                agent.device.click_force(360, 1000)
                time.sleep(0.9)
                result = "[lesson] 无可用决策，点击中位卡兜底"
                idle += 1
        else:
            tick = driver.decide(agent, lines)
            result = tick.describe()
            if tick.screen == "pause":
                time.sleep(2.0)
                idle = 0
            else:
                idle = 0 if tick.ok else idle + 1

        log_lines.append(f"{step:03d} {result}")
        if idle >= 5:
            log_lines.append(f"{step:03d} 连续 5 步无可执行动作，停止")
            break

    LOG.write_text("\n".join(log_lines), encoding="utf-8")
    print(json.dumps({"steps": len(log_lines), "done": done, "log": log_lines[-15:]}, ensure_ascii=False))
    return 0 if done or len(log_lines) >= steps else 1


if __name__ == "__main__":
    raise SystemExit(main())
