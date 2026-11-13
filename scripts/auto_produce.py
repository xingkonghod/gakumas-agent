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
import re
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
from gkagent.data.master import MasterData
from gkagent.device.win32 import USER32, Win32Device, find_game_hwnd
from gkagent.nav import Navigator
from gkagent.policy.ocr_cards import OcrCardPolicy
from gkagent.policy.search import SearchPolicy
from gkagent.runtime.metrics import EpisodeRecord, MetricsLog, StepRecord
from gkagent.runtime.replay import ReplayDB
from gkagent.sim.exam_estimate import SimCard, estimate_score
from gkagent.tasks.produce import ProduceTask
from gkagent.tasks.produce_ui import LESSON_WORDS, ProduceDriver, parse_stamina
from gkagent.vision.cards import scan_hand
from gkagent.vision.hand_names import pick_hand_card
from gkagent.vision.matcher import TemplateMatcher
from gkagent.vision.ocr import OcrEngine

LOG = ROOT / "data" / "auto_log.txt"
SHOT_DIR = ROOT / "data" / "auto"
METRICS = ROOT / "data" / "metrics.jsonl"
FAILURES = ROOT / "data" / "failures.jsonl"


def log_failure(episode: str, step: int, kind: str, detail: str, extra: dict | None = None) -> None:
    """失败日志：每出现一次失败（课程 FAILED / 局未完成 / 卡死自停）都落一条。"""
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "episode": episode,
        "step": step,
        "kind": kind,
        "detail": detail[:300],
    }
    if extra:
        record.update(extra)
    with FAILURES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

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


def build_task(episode: str, engine: OcrEngine, card_library: CardLibrary | None = None) -> ProduceTask:
    def _hand_reader(image):
        scan = scan_hand(image)
        return list(scan.cards), [tuple(card.box) for card in scan.cards]

    # 按卡名/效果文本查卡库打分（权重已改成打分优先），决定出哪张
    # 用绝对路径加载 master：进程 cwd 不一定在项目根目录（supervisor/daemon 启动时踩过坑）
    master_root = ROOT / "data" / "master"
    card_library = card_library or CardLibrary(MasterData(master_root))
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


def run_exam_estimate(agent, task, driver, image):
    """期末前估分：逐张点开手牌 → OCR 读卡名/价值 → 15 局蒙特卡洛。"""
    policy = getattr(task, "ocr_policy", None)
    if policy is None:
        return None
    hand = scan_hand(image)
    if not hand.boxes:
        return None
    cards: list[SimCard] = []
    for index, box in enumerate(hand.boxes[:4]):
        cx = box[0] + box[2] // 2
        cy = box[1] + box[3] // 2
        agent.device.click_force(cx, cy)
        time.sleep(0.35)
        detail = agent.shot()
        cost = hand.cards[index].cost if index < len(hand.cards) else None
        reading = policy.read(detail, cost)
        cards.append(SimCard(reading.name or f"card{index}", float(reading.value or 0), int(cost or 1)))
    if not cards:
        return None
    return estimate_score(cards, turns=6, trials=15, seed=11)


def should_retry(score: float | None, mean: float) -> bool:
    """第一把打完：分数不到期望的 90% 就免费重开。"""
    if score is None or mean <= 0:
        return False
    return score < mean * 0.9


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
    crash_log = ROOT / "data" / "crash.log"

    def _hook(exc_type, exc_value, exc_tb):
        import traceback

        with crash_log.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] crash\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=handle)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
    steps = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    episode = sys.argv[2] if len(sys.argv) > 2 else time.strftime("ep-%Y%m%d-%H%M%S")
    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window", file=sys.stderr)
        return 2
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    engine = OcrEngine()
    card_lib = CardLibrary(MasterData(ROOT / "data" / "master"))
    task = build_task(episode, engine, card_lib)
    driver = ProduceDriver(ocr=engine)
    # 开局先回主页：上一轮可能停在支援卡/偶像/强化页面，否则前 8 步全是 unknown-tap
    try:
        Navigator(agent, engine).ensure_home()
    except Exception:  # noqa: BLE001
        pass
    metrics = MetricsLog(METRICS)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []
    idle = 0
    pause_streak = 0
    last_stamina: int | None = None
    done = False
    seen_produce = False
    produce_end_seen = False
    started_at = time.time()
    prev_digest: str | None = None
    pending: StepRecord | None = None
    markers: list[str] = []
    unknown_streak = 0
    ocr_cache: dict[str, tuple[list, str]] = {}
    last_signature: tuple[str, str, str] | None = None
    same_action_count = 0
    lesson_pending: tuple[tuple[int, int], tuple] | None = None
    drink_used = False
    exam_estimate_done = False

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
        # 失败画面（课程/考试 FAILED、不合格）：落失败日志 + 截图
        if "FAILED" in text or "不合格" in text:
            fail_path = SHOT_DIR / f"fail_{episode}_{step:03d}.png"
            cv2.imwrite(str(fail_path), image)
            log_failure(
                episode,
                step,
                "lesson-failed" if "FAILED" in text else "exam-failed",
                text,
                {
                    "attribute": driver.lesson_attribute,
                    "stamina": last_stamina,
                    "screenshot": str(fail_path),
                },
            )
            log_lines.append(f"{step:03d} [fail] FAILED/不合格 已记录 {fail_path}")
        # 最终评价画面单独存档（轮转 step_NNN 会覆盖）
        if "最终培育评价" in text:
            final_path = SHOT_DIR / f"final_eval_{episode}.png"
            if not final_path.exists():
                cv2.imwrite(str(final_path), image)
                log_lines.append(f"{step:03d} [final] 最终培育评价截图已存 {final_path}")
        # 培育结束的强信号：最终评价 / 结算后成就页（粉丝数）
        if "最终培育评价" in text or ("粉丝" in text and "成就" in text):
            produce_end_seen = True
        if produce_end_seen and (
            is_home(text) or "定期公演" in text or "プロデュース" in text
        ):
            log_lines.append(f"{step:03d} [home] 培育结束，回到入口/主页")
            done = True
            break
        if seen_produce and is_home(text):
            log_lines.append(f"{step:03d} [home] 培育结束，已回主页")
            done = True
            break

        status_text = text
        if lesson_fast:
            # 课程 frame 跳过整屏 OCR，但左上角状态条仍需读（体力/最终考试截止）
            status_lines = driver.engine().read(image, driver.corner_roi)
            status_text = driver.text_of(status_lines)

        t_decide = time.perf_counter()
        clicked: bool | None = None
        if lesson_fast or any(word in text for word in LESSON_WORDS):
            action_name, screen_name = "card", "lesson"
            unknown_streak = 0
            last_signature = None
            same_action_count = 0
            # 期末前估分：拿当前手牌跑 15 局蒙特卡洛
            if not exam_estimate_done and ("最终考试" in status_text or "期末考试" in status_text):
                exam_estimate_done = True
                estimate = run_exam_estimate(agent, task, driver, image)
                if estimate is not None:
                    record = {
                        "episode": episode,
                        "step": step,
                        "estimate": str(estimate),
                        "mean": round(estimate.mean, 1),
                        "p10": round(estimate.p10, 1),
                        "p90": round(estimate.p90, 1),
                        "ts": time.time(),
                    }
                    with (ROOT / "data" / "exam_estimates.jsonl").open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log_lines.append(f"{step:03d} [exam] estimate {estimate}")
            # 体力管理：低于 8 且还有回合，用一次饮料（每节课最多一次）
            stamina = parse_stamina(status_text or text)
            if stamina is not None:
                last_stamina = stamina
            turns_match = re.search(r"剩余回合数\s*(\d+)", text)
            turns = int(turns_match.group(1)) if turns_match else None
            if (
                stamina is not None
                and stamina <= 8
                and not drink_used
                and (turns is None or turns > 1)
                and lesson_pending is None
            ):
                drink_used = True
                agent.device.click_force(75, 1182)
                time.sleep(1.0)
                shot2 = agent.shot()
                lines2 = driver.read(shot2)
                use = driver.find(lines2, "使用")
                if use is not None:
                    agent.device.click_force(*driver.center(use))
                time.sleep(0.8)
                result = f"[lesson] drink at stamina={stamina}"
                clicked = True
                action_name = "drink"
                hand = scan_hand(image)
                boxes = tuple(tuple(card.box) for card in hand.cards)
                lesson_pending = None
            else:
                hand = scan_hand(image)
                boxes = tuple(tuple(card.box) for card in hand.cards)
            # 两段式出牌：第一次点卡只是选中，下一步点同一点确认（不再依赖手牌框是否变化）
            if action_name != "drink" and lesson_pending is not None:
                point = lesson_pending[0]
                clicked = agent.device.click_force(*point)
                time.sleep(0.9)
                lesson_pending = None
                result = f"[lesson] confirm card at {point}"
                idle = 0 if clicked is not False else idle
            elif action_name != "drink":
                lesson_pending = None
                # 快路径：手牌上直接读卡名 → 卡库估值，选最值的一张（不逐张点开）
                # 课程 fastpath 跳过了整屏 OCR，这里补一块手牌区 ROI（比逐张点开读便宜）
                if not lines:
                    lines = driver.engine().read(image, (0, 780, 720, 420))
                costs = [card.cost for card in hand.cards] if hand.cards else None
                name_pick = pick_hand_card(
                    lines,
                    boxes,
                    card_lib,
                    stamina=stamina,
                    costs=costs,
                    attribute=driver.lesson_attribute,
                )
                if name_pick is not None:
                    clicked = agent.device.click_force(*name_pick.point)
                    time.sleep(0.9)
                    if clicked is False:
                        result = "[pause] 用户正在操作，暂停出牌"
                        idle = 0
                    else:
                        lesson_pending = (name_pick.point, boxes)
                        result = (
                            f"[lesson] name-pick {name_pick.name} "
                            f"({name_pick.value:.1f}) at {name_pick.point}"
                        )
                        idle = 0
                    action_name = "name-pick"
                else:
                    with (ROOT / "data" / "pick_debug.log").open("a", encoding="utf-8") as handle:
                        detail = []
                        for box in boxes:
                            bx, by, bw, bh = box
                            candidates = []
                            for line in lines:
                                lx, ly, lw, _lh = line.box
                                cx = lx + lw // 2
                                in_y = by + bh * 0.5 <= ly <= by + bh + 50
                                in_x = bx - 10 <= cx <= bx + bw + 10
                                if in_y or in_x:
                                    candidates.append(
                                        {
                                            "text": line.text,
                                            "cx": cx,
                                            "ly": ly,
                                            "in_y": in_y,
                                            "in_x": in_x,
                                            "known": card_lib.find(line.text.strip()) is not None,
                                        }
                                    )
                            detail.append({"box": list(box), "candidates": candidates[:8]})
                        handle.write(
                            json.dumps(
                                {
                                    "episode": episode,
                                    "step": step,
                                    "boxes": [list(box) for box in boxes],
                                    "detail": detail,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    screen = task.observe(agent, image)
                    play = task.decide_card(agent, image, screen=screen, stamina=stamina)
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
            drink_used = False
            tick = driver.decide(agent, lines, image)
            result = tick.describe()
            screen_name, action_name = tick.screen, tick.action
            clicked = None if screen_name in ("pause", "loading", "blank") else True
            if tick.screen == "pause":
                pause_streak += 1
                # 用户在操作时逐步拉长退避，避免每 2s 空烧一步
                time.sleep(min(2.0 + pause_streak * 0.5, 6.0))
                idle = 0
                if pause_streak >= 30:
                    log_lines.append(f"{step:03d} 用户持续操作 {pause_streak} 步，暂停本局")
                    break
            else:
                pause_streak = 0
                idle = 0 if tick.ok and tick.screen not in ("unknown", "unknown-tap") else idle + 1
                unknown_streak = (
                    0
                    if tick.ok and tick.screen not in ("unknown", "unknown-tap")
                    else unknown_streak + 1
                )
                # 防死循环：同一 (screen, action, 文本) 连续出现才计数；
                # 数字全部归一化（P/体力/回合每步都在变，否则签名永远不同）；
                # 剧情「快进」每步台词都变，仍不会误杀。
                signature = (
                    tick.screen,
                    tick.action,
                    re.sub(r"\d+", "#", text[:80]),
                )
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
    # 每局单独留一份，避免被下一局/手工测试覆盖
    (SHOT_DIR / f"auto_log_{episode}.log").write_text("\n".join(log_lines), encoding="utf-8")
    if not done:
        log_failure(
            episode,
            len(log_lines),
            "episode-not-done",
            log_lines[-1] if log_lines else "no log",
            {"steps": len(log_lines), "attribute": driver.lesson_attribute},
        )
    summary = metrics.summary(episode)
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
