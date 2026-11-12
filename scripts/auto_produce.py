"""自动推进培育：OCR 导航 + 出牌策略 + 指标记录，一次跑 N 步。

用法（管理员或经 agent daemon shell 调用）：
    python scripts/auto_produce.py 40 [episode_id]

产物：
- data/auto/step_NNN.png        每步截图
- data/auto_log.txt             人类可读日志
- data/metrics.jsonl            每步指标（时延/点击回执）
- data/replays/produce.sqlite3  出牌回放（训练数据）

退出条件：回到主页 / 步数用尽 / 连续 5 步无动作 / F12 / data/STOP。
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
from gkagent.data.cards_db import CardLibrary
from gkagent.data.items_db import ItemLibrary
from gkagent.device.win32 import USER32, Win32Device, find_game_hwnd
from gkagent.policy.ocr_cards import OcrCardPolicy
from gkagent.policy.search import SearchPolicy
from gkagent.runtime.metrics import EpisodeRecord, MetricsLog, StepRecord
from gkagent.runtime.replay import ReplayDB
from gkagent.tasks.produce import ProduceTask
from gkagent.tasks.produce_ui import LESSON_WORDS, ProduceDriver
from gkagent.vision.cards import scan_hand
from gkagent.vision.matcher import TemplateMatcher
from gkagent.vision.ocr import OcrEngine

LOG = ROOT / "data" / "auto_log.txt"
SHOT_DIR = ROOT / "data" / "auto"
METRICS = ROOT / "data" / "metrics.jsonl"

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


def build_task(episode: str, engine: OcrEngine) -> ProduceTask:
    def _hand_reader(image):
        scan = scan_hand(image)
        return list(scan.cards), [tuple(card.box) for card in scan.cards]

    # 按卡名/效果文本查卡库打分（权重已改成打分优先），决定出哪张
    card_library = CardLibrary()
    item_library = ItemLibrary()
    ocr_policy = OcrCardPolicy(
        engine,
        card_library,
        detail_roi=(0, 480, 720, 400),
        extra_libraries=[item_library],
    )
    replay = ReplayDB(str(ROOT / "data" / "replays" / "produce.sqlite3"), run_id=episode)
    return ProduceTask(
        enable_lessons=True,
        hand_reader=_hand_reader,
        card_policy=SearchPolicy(),
        replay_db=replay,
        ocr_policy=ocr_policy,
    )


def is_home(text: str) -> bool:
    return "主页" in text and any(word in text for word in HOME_MARKERS)


def stop_requested() -> bool:
    """F12 是急停键；data/STOP 文件也能停。"""
    if (ROOT / "data" / "STOP").exists():
        return True
    return bool(USER32.GetAsyncKeyState(0x7B) & 0x8000)


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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    episode = sys.argv[2] if len(sys.argv) > 2 else time.strftime("ep-%Y%m%d-%H%M%S")
    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window", file=sys.stderr)
        return 2
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    engine = OcrEngine()
    task = build_task(episode, engine)
    driver = ProduceDriver(ocr=engine)
    metrics = MetricsLog(METRICS)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []
    idle = 0
    done = False
    seen_produce = False
    started_at = time.time()
    prev_digest: str | None = None
    pending: StepRecord | None = None
    markers: list[str] = []
    unknown_streak = 0
    ocr_cache: dict[str, tuple[list, str]] = {}
    last_signature: tuple[str, str, str] | None = None
    same_action_count = 0
    lesson_pending: tuple[tuple[int, int], tuple] | None = None

    def flush_pending(changed: bool | None) -> None:
        nonlocal pending
        if pending is not None:
            pending.changed = changed
            metrics.write(pending)
            pending = None

    for step in range(1, steps + 1):
        if stop_requested():
            log_lines.append(f"{step:03d} [stop] 急停触发")
            break
        try:
            t_start = time.perf_counter()
            image = agent.shot()
            capture_ms = (time.perf_counter() - t_start) * 1000
        except RuntimeError as exc:
            log_lines.append(f"{step:03d} [capture] {exc}; 尝试恢复窗口")
            idle += 1
            restore_window()
            continue
        digest = str(hash(image[::17, ::17].tobytes()))
        flush_pending(prev_digest is not None and digest != prev_digest)
        prev_digest = digest
        cv2.imwrite(str(SHOT_DIR / f"step_{step:03d}.png"), image)

        t_ocr = time.perf_counter()
        # 快速路径 1：模板命中「跳过回合/体力」→ 课程帧，省掉整屏 OCR（2-5s）
        lesson_fast = (
            agent.matcher.find("produce_skip_round", image, threshold=0.85) is not None
            or agent.matcher.find("produce_health", image, threshold=0.70) is not None
        )
        # 快速路径 2：加载帧模板命中 → 直接当 loading 等待，不 OCR
        loading_fast = (not lesson_fast) and (
            agent.matcher.find("produce_loading", image, threshold=0.90) is not None
        )
        if lesson_fast:
            lines = []
            text = ""
            ocr_ms = 0.0
        elif loading_fast:
            lines = []
            text = "LOADING"
            ocr_ms = 0.0
        elif digest in ocr_cache:
            lines, text = ocr_cache[digest]
            ocr_ms = 0.0
        elif unknown_streak >= 3:
            # 连续认不出时，用整屏 OCR 兜底一次，排除 ROI 漏读
            lines = driver.engine().read(image)
            text = driver.text_of(lines)
            ocr_ms = (time.perf_counter() - t_ocr) * 1000
        else:
            lines = driver.read(image)
            ocr_ms = (time.perf_counter() - t_ocr) * 1000
            text = driver.text_of(lines)
            if len(ocr_cache) < 256:
                ocr_cache[digest] = (lines, text)

        if any(word in text for word in PRODUCE_MARKERS):
            seen_produce = True
            markers.append(text[:40])
        if seen_produce and is_home(text):
            log_lines.append(f"{step:03d} [home] 培育结束，已回主页")
            done = True
            break

        t_decide = time.perf_counter()
        clicked: bool | None = None
        if lesson_fast or any(word in text for word in LESSON_WORDS):
            action_name, screen_name = "card", "lesson"
            unknown_streak = 0
            last_signature = None
            same_action_count = 0
            hand = scan_hand(image)
            boxes = tuple(tuple(card.box) for card in hand.cards)
            # 两段式出牌：第一次点卡只是选中，下一步点同一点确认（不再依赖手牌框是否变化）
            if lesson_pending is not None:
                point = lesson_pending[0]
                clicked = agent.device.click_force(*point)
                time.sleep(0.9)
                lesson_pending = None
                result = f"[lesson] confirm card at {point}"
                idle = 0 if clicked is not False else idle
            else:
                lesson_pending = None
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
                        lesson_pending = (play.point, boxes)
                        result = f"[lesson] play card#{play.index} {play.source} at {play.point}"
                        idle = 0
                else:
                    clicked = agent.device.click_force(360, 1000)
                    time.sleep(0.9)
                    result = "[lesson] 无可用决策，点击中位卡兜底"
                    idle += 1
        else:
            lesson_pending = None
            tick = driver.decide(agent, lines)
            result = tick.describe()
            screen_name, action_name = tick.screen, tick.action
            clicked = None if screen_name in ("pause", "loading", "blank") else True
            if tick.screen == "pause":
                time.sleep(2.0)
                idle = 0
            else:
                idle = 0 if tick.ok and tick.screen not in ("unknown", "unknown-tap") else idle + 1
                unknown_streak = (
                    0
                    if tick.ok and tick.screen not in ("unknown", "unknown-tap")
                    else unknown_streak + 1
                )
                # 防死循环：同一 (screen, action, 文本) 连续出现才计数；
                # 剧情「快进」每步台词都变，不会误杀。
                signature = (tick.screen, tick.action, text[:80])
                if signature == last_signature:
                    same_action_count += 1
                else:
                    last_signature = signature
                    same_action_count = 1
                if (
                    same_action_count >= 10
                    and tick.screen not in ("loading", "blank", "pause")
                ):
                    log_lines.append(
                        f"{step:03d} 同一动作 {tick.screen}/{tick.action} 连续 {same_action_count} 次，停止"
                    )
                    break

        decide_ms = (time.perf_counter() - t_decide) * 1000
        total_ms = capture_ms + ocr_ms + decide_ms
        pending = StepRecord(
            episode=episode,
            step=step,
            screen=screen_name,
            action=action_name,
            capture_ms=round(capture_ms, 1),
            ocr_ms=round(ocr_ms, 1),
            decide_ms=round(decide_ms, 1),
            total_ms=round(total_ms, 1),
            clicked=clicked,
        )
        log_lines.append(f"{step:03d} {result}")
        if idle >= 8:
            log_lines.append(f"{step:03d} 连续 8 步无可执行动作，停止")
            break

    flush_pending(None)
    ended_at = time.time()
    metrics.write(
        EpisodeRecord(
            episode=episode,
            started_at=started_at,
            ended_at=ended_at,
            steps=len(log_lines),
            done=done,
            progress_markers=markers[:10],
        )
    )
    LOG.write_text("\n".join(log_lines), encoding="utf-8")
    summary = metrics.summary()
    print(
        json.dumps(
            {
                "episode": episode,
                "steps": len(log_lines),
                "done": done,
                "duration_s": round(ended_at - started_at, 1),
                "avg_total_ms": summary.get("avg_total_ms"),
                "changed_rate": summary.get("changed_rate"),
                "log": log_lines[-12:],
            },
            ensure_ascii=False,
        )
    )
    return 0 if done or len(log_lines) >= steps else 1


if __name__ == "__main__":
    raise SystemExit(main())
