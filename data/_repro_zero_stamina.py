"""离线复现 ep-cplus10「0 体力课程死循环」的判断链（只读截图，不连真机）。

用 data/repro_zero/step_150.png / step_166.png（原 data/auto/step_150/166.png 的备份，
同一画面、角色动画不同）。输出每一步判断结果，证明根因。

    .venv\\Scripts\\python.exe data\\_repro_zero_stamina.py
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import cv2  # noqa: E402

from gkagent.data.card_costs import CardCosts  # noqa: E402
from gkagent.data.cards_db import CardLibrary  # noqa: E402
from gkagent.data.master import MasterData  # noqa: E402
from gkagent.policy.lesson import LessonPolicy  # noqa: E402
from gkagent.tasks.produce_ui import (  # noqa: E402
    LESSON_SKIP_POINT,
    LessonPlayGuard,
    ProduceDriver,
    SameScreenGuard,
    lesson_hand_signature,
    lesson_stamina_gate,
    lesson_turn_signature,
    lowest_hand_cost,
    parse_stamina,
)
from gkagent.vision.lesson import LessonReader  # noqa: E402
from gkagent.vision.matcher import TemplateMatcher  # noqa: E402
from gkagent.vision.ocr import OcrEngine  # noqa: E402


class DummyDevice:
    clicks: list[tuple[int, int]] = []

    def click_force(self, x: int, y: int, delay: float = 0.4) -> bool:
        self.clicks.append((int(x), int(y)))
        return True


class DummyAgent:
    def __init__(self) -> None:
        self.device = DummyDevice()


def main() -> int:
    engine = OcrEngine()
    driver = ProduceDriver(ocr=engine, sleep=lambda _s: None)
    matcher = TemplateMatcher(ROOT / "templates")
    cards = CardLibrary(MasterData(ROOT / "data" / "master"))
    costs = CardCosts()
    reader = LessonReader(engine, cards=cards, costs=costs)
    LessonPolicy(buffs=reader.buffs)
    agent = DummyAgent()

    signatures = []
    timings = []
    for step in (150, 166):
        path = ROOT / "data" / "repro_zero" / f"step_{step:03d}.png"
        image = cv2.imread(str(path))
        print(f"\n===== step_{step:03d}.png =====")
        t0 = time.perf_counter()
        lines = driver.read(image)
        text = driver.text_of(lines)
        timings.append(("driver.read", time.perf_counter() - t0))
        print(f"[1] driver.read -> {len(lines)} 行, text={text!r}")
        print(
            "[2] 课程模板 produce_skip_round=%s produce_health=%s"
            % (
                matcher.find("produce_skip_round", image, threshold=0.85) is not None,
                matcher.find("produce_health", image, threshold=0.70) is not None,
            )
        )
        t0 = time.perf_counter()
        tick = driver.decide(agent, lines, image)
        timings.append(("decide", time.perf_counter() - t0))
        print(f"[3] _decide -> screen={tick.screen!r} action={tick.action!r} clicks={agent.device.clicks}")

        t0 = time.perf_counter()
        state = reader.read(image)
        timings.append(("LessonReader.read", time.perf_counter() - t0))
        print(f"[4] LessonReader.read -> {state.summary()}")
        print(
            f"    turns_left={state.turns_left!r} score={state.score!r} "
            f"stamina={state.stamina!r} 手牌={len(state.cards)}"
        )
        for card in state.cards:
            print(
                f"    card#{card.index} name={card.name!r} score={card.score!r}x{card.hits!r} "
                f"cost={card.cost!r} score_unread={card.score_unread} point={card.point}"
            )
        lowest = lowest_hand_cost(state.cards)
        print(
            f"[5] lowest_hand_cost={lowest!r}（费用读到了 {[c.cost for c in state.cards]}，取最小）"
        )
        status_stamina = parse_stamina(text)
        print(f"[6] parse_stamina(OCR 文本)={status_stamina!r}（text 里没有 'X/35'）")
        gate = lesson_stamina_gate(state, stamina=status_stamina)
        print(f"[7] lesson_stamina_gate(state, stamina={status_stamina!r})={gate!r}")
        gate_fallback = lesson_stamina_gate(state, stamina=None, last_stamina=0)
        print(f"    体力本帧读不到时用上一帧 0 兜底 -> {gate_fallback!r}")
        print(f"[8] lesson_turn_signature={lesson_turn_signature(state)!r}")
        signatures.append(lesson_turn_signature(state))
        pix = hashlib.md5(image[::17, ::17].tobytes()).hexdigest()
        print(f"[9] 像素 digest(旧 changed 判定用)={pix}  ← 每帧都不同（动画/闪光）")
        guard = LessonPlayGuard()
        print(f"[10] guard.skip_done(sig)={guard.skip_done(lesson_turn_signature(state))}")
        guard.skip_sent(lesson_turn_signature(state))
        print(
            "     guard.skip_sent(sig) 后 skip_done="
            f"{guard.skip_done(lesson_turn_signature(state))} skip_clicks={guard.skip_clicks}"
        )

    print("\n===== 同一屏兜底（同一语义签名连续喂 10 步） =====")
    same = SameScreenGuard()
    for index in range(1, 11):
        action = same.observe(signatures[0])
        print(f"step {index:02d}: observe -> {action!r} repeats={same.repeats}")
    print(f"forced_skips={same.forced_skips} stuck_exits={same.stuck_exits}")

    print("\n===== 结论 =====")
    print(f"两帧语义签名相同: {signatures[0] == signatures[1]}")
    print(f"SKIP 落点 = {LESSON_SKIP_POINT!r}")
    print("耗时: " + ", ".join(f"{name}={seconds:.1f}s" for name, seconds in timings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
