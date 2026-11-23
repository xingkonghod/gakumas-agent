"""C1 执行层可靠性：tap 确认/重试 + 动作前预算下一帧 + picker 选牌（失败场景单测）。

DoD 场景（WORKPLAN C1）：
- tap 丢失：同屏未生效 → 限时重试 → lost 上报（绝不静默 SKIP）；
- 对话未开：饮料槽位点了对话没开 → 重试槽位 → 失败留痕（attempt_drink）；
- picker 选牌：卡位/领取分级重试，选中后只重试领取不重点卡位；
- 同屏循环：画面已推进不重试（rev254）；加载/暂停帧不判（rev135）；
- 动作前预算下一帧：decide() 给每个 tap 登记期望（hiro 原则 3）。

参考 GKMSMAA follow.py 架构（AGPL 只读参考），状态机全部自写、时钟注入、离线可测。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from gkagent.runtime.tapguard import (
    KIND_CHANGE,
    KIND_DIALOG_GONE,
    PickerGuard,
    TapGuard,
    expect_any,
    expect_change,
    expect_dialog_gone,
    expect_dialog_open,
    expect_overlay,
)
from gkagent.tasks.produce_ui import ProduceDriver, TickResult
from gkagent.vision.ocr import OcrLine


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _lines(*texts: str) -> list[OcrLine]:
    return [OcrLine(text, 0.95, (40, 40 + index * 60, 200, 40)) for index, text in enumerate(texts)]


@dataclass
class FakeDevice:
    clicks: list[tuple[int, int]] = field(default_factory=list)
    refuse: bool = False

    def click_force(self, x: int, y: int) -> bool:
        self.clicks.append((int(x), int(y)))
        return not self.refuse


@dataclass
class FakeAgent:
    device: FakeDevice = field(default_factory=FakeDevice)
    frames: list[list[OcrLine]] = field(default_factory=list)

    def shot(self):
        return None


def _driver() -> ProduceDriver:
    return ProduceDriver(sleep=lambda _seconds: None)


# ---------------------------------------------------------------- TapGuard


def test_tap_lost_retries_then_reports_never_skips() -> None:
    """tap 丢失：弹窗确认点了没消失 → 等动画 → 重试 2 次 → lost（没有 skip 语义）。"""
    clock = FakeClock()
    guard = TapGuard(retry_after=1.0, max_retries=2, clock=clock)
    guard.budget("confirm", (360, 1150), expect_dialog_gone(("取消",), "sig-dialog"), now=clock())
    text = "跳过确认 取消 确定"
    # 动画未 settle：不判
    assert guard.observe(text, "sig-dialog", now=clock()).outcome == "wait"
    clock.advance(1.5)
    first = guard.observe(text, "sig-dialog", now=clock())
    assert first.outcome == "retap" and first.point == (360, 1150) and first.tries == 1
    clock.advance(1.5)
    second = guard.observe(text, "sig-dialog", now=clock())
    assert second.outcome == "retap" and second.tries == 2
    clock.advance(1.5)
    lost = guard.observe(text, "sig-dialog", now=clock())
    assert lost.outcome == "lost"
    assert "tap 丢失" in lost.reason
    assert guard.pending is None
    assert (guard.retaps, guard.lost, guard.confirmed) == (2, 1, 0)
    # 绝不静默 SKIP：verdict 里没有 skip 语义，升级交给调用方
    assert "skip" not in lost.outcome
    assert guard.observe(text, "sig-dialog", now=clock()).outcome == "none"


def test_tap_confirmed_after_animation_settles() -> None:
    clock = FakeClock()
    guard = TapGuard(clock=clock)
    guard.budget("confirm", (360, 1150), expect_dialog_gone(("取消",), "sig-dialog"), now=clock())
    assert guard.observe("取消 确定", "sig-dialog", now=clock()).outcome == "wait"
    clock.advance(1.2)
    verdict = guard.observe("培育主界面 请选择行动", "sig-action", now=clock())
    assert verdict.outcome == "confirmed"
    assert guard.confirmed == 1 and guard.pending is None


def test_screen_moved_on_is_not_retried() -> None:
    """rev254：画面已推进到别的屏（期望没满足）→ moved，重新决策，绝不重试。"""
    clock = FakeClock()
    guard = TapGuard(clock=clock)
    guard.budget("confirm", (360, 1150), expect_dialog_gone(("取消",), "sig-dialog"), now=clock())
    clock.advance(5.0)
    # 另一个弹窗（仍含「取消」）：签名变了 = 游戏响应了别的东西
    verdict = guard.observe("休息确认 取消 休息", "sig-rest", now=clock())
    assert verdict.outcome == "moved"
    assert guard.retaps == 0 and guard.moved == 1
    assert guard.pending is None


def test_generic_change_expectation_budgets_before_signature() -> None:
    clock = FakeClock()
    guard = TapGuard(clock=clock)
    guard.budget("enter-produce", (359, 1006), expect_change("sig-home"), now=clock())
    clock.advance(1.5)
    assert guard.observe("主页 プロデュース", "sig-home", now=clock()).outcome == "retap"
    clock.advance(1.5)
    assert guard.observe("选择偶像", "sig-idol", now=clock()).outcome == "confirmed"


def test_loading_frame_postpones_retry_clock() -> None:
    """rev135：加载/暂停不是游戏的沉默——postpone 后重试时钟重新起算。"""
    clock = FakeClock()
    guard = TapGuard(retry_after=1.0, clock=clock)
    guard.budget("confirm", (360, 1150), expect_dialog_gone(("取消",), "sig"), now=clock())
    clock.advance(2.0)
    guard.postpone(now=clock())  # 这一帧是 LOADING
    clock.advance(0.5)
    assert guard.observe("取消 确定", "sig", now=clock()).outcome == "wait"
    clock.advance(1.0)
    assert guard.observe("取消 确定", "sig", now=clock()).outcome == "retap"


def test_cancel_and_new_budget_supersede() -> None:
    guard = TapGuard(clock=FakeClock())
    guard.budget("a", (1, 2), expect_any("sig"))
    guard.cancel()
    assert guard.observe("x", "sig").outcome == "none"
    guard.budget("a", (1, 2), expect_dialog_gone(("取消",), "sig"))
    guard.budget("b", (3, 4), expect_dialog_gone(("结束回合",), "sig"))
    assert guard.pending is not None and guard.pending.action == "b"


def test_dialog_open_expectation_drink_dialog() -> None:
    """对话未开（饮料）：期望「使用」出现；一直不出现 → retap → lost。"""
    clock = FakeClock()
    guard = TapGuard(retry_after=1.0, max_retries=1, clock=clock)
    guard.budget("drink", (75, 1182), expect_dialog_open(("使用",), "sig-lesson"), now=clock())
    clock.advance(1.5)
    assert guard.observe("剩余回合", "sig-lesson", now=clock()).outcome == "retap"
    clock.advance(1.5)
    assert guard.observe("剩余回合", "sig-lesson", now=clock()).outcome == "lost"
    # 对话开了就 confirmed
    guard.budget("drink", (75, 1182), expect_dialog_open(("使用",), "sig-lesson"), now=clock())
    clock.advance(1.5)
    assert guard.observe("饮料 使用 取消", "sig-drink", now=clock()).outcome == "confirmed"


def test_overlay_expectations_use_overlay_flag() -> None:
    guard = TapGuard(clock=FakeClock())
    guard.budget("pick", (230, 918), expect_overlay(True, "sig"))
    assert guard.observe("t", "sig", overlay_open=False).outcome == "wait"
    assert guard.observe("t", "sig", overlay_open=True).outcome == "confirmed"
    guard.budget("close", (360, 260), expect_overlay(False, "sig"))
    assert guard.observe("t", "sig", overlay_open=True).outcome == "wait"
    assert guard.observe("t", "sig", overlay_open=False).outcome == "confirmed"


def test_any_expectation_confirms_but_still_records() -> None:
    guard = TapGuard(clock=FakeClock())
    guard.budget("tap", (360, 1000), expect_any("sig"))
    assert guard.observe("anything", "sig").outcome == "confirmed"
    assert guard.summary() == "confirmed=1 retaps=0 lost=0 moved=0"


# ---------------------------------------------------------------- PickerGuard


def test_picker_slot_lost_retries_slot_then_fails() -> None:
    clock = FakeClock()
    picker = PickerGuard(max_retries=2, retry_after=1.0, clock=clock)
    picker.start((230, 918), (360, 1095), signature="sig-reward", now=clock())
    picker.slot_tapped(now=clock())
    assert picker.observe(selected=False, screen_gone=False, now=clock()).outcome == "wait"
    clock.advance(1.5)
    first = picker.observe(selected=False, screen_gone=False, now=clock())
    assert first.outcome == "retap-slot" and first.point == (230, 918)
    clock.advance(1.5)
    assert picker.observe(selected=False, screen_gone=False, now=clock()).outcome == "retap-slot"
    clock.advance(1.5)
    failed = picker.observe(selected=False, screen_gone=False, now=clock())
    assert failed.outcome == "failed" and "未选中" in failed.reason
    assert not picker.active


def test_picker_selected_then_confirm_only_retries() -> None:
    """选中后只重试确认，绝不回头重点卡位（重点可能取消选中）。"""
    clock = FakeClock()
    picker = PickerGuard(max_retries=2, retry_after=1.0, clock=clock)
    picker.start((230, 918), (360, 1095), now=clock())
    picker.slot_tapped(now=clock())
    clock.advance(1.5)
    verdict = picker.observe(selected=True, screen_gone=False, now=clock())
    assert verdict.outcome == "tap-confirm" and verdict.point == (360, 1095)
    picker.confirm_tapped(now=clock())
    clock.advance(1.5)
    again = picker.observe(selected=True, screen_gone=False, now=clock())
    assert again.outcome == "retap-confirm" and again.point == (360, 1095)
    assert "不重点卡位" in again.reason
    clock.advance(1.5)
    assert picker.observe(selected=True, screen_gone=False, now=clock()).outcome == "retap-confirm"
    clock.advance(1.5)
    assert picker.observe(selected=True, screen_gone=False, now=clock()).outcome == "failed"


def test_picker_unknown_selection_conservative_after_confirm() -> None:
    """selected=None（读不到选中态）：第一次确认发出后按已选中，只重试确认。"""
    clock = FakeClock()
    picker = PickerGuard(max_retries=1, retry_after=1.0, clock=clock)
    picker.start((230, 918), (360, 1095), now=clock())
    picker.slot_tapped(now=clock())
    picker.confirm_tapped(now=clock())  # pick+claim 同一 tick 发出
    clock.advance(1.5)
    verdict = picker.observe(selected=None, screen_gone=False, now=clock())
    assert verdict.outcome == "retap-confirm"
    clock.advance(1.5)
    assert picker.observe(selected=None, screen_gone=False, now=clock()).outcome == "failed"


def test_picker_done_when_screen_gone_and_selection_lost_goes_back_to_slot() -> None:
    picker = PickerGuard(clock=FakeClock())
    picker.start((230, 918), (360, 1095))
    assert picker.observe(selected=None, screen_gone=True).outcome == "done"
    assert not picker.active
    picker.start((230, 918), (360, 1095))
    picker.confirm_tapped()
    verdict = picker.observe(selected=False, screen_gone=False)
    # 选中态丢了 → 回卡位阶段（wait/retap-slot），不会继续 retap-confirm
    assert verdict.outcome in ("wait", "retap-slot")
    assert picker.stage == "slot"


# ---------------------------------------------------------------- attempt_drink


def _auto_produce():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import auto_produce

    return auto_produce


class FakeDrinkDriver:
    """read() 按脚本返回 OCR 行；find/center 用 ProduceDriver 的静态语义。"""

    def __init__(self, frames: list[list[OcrLine]]) -> None:
        self.frames = frames
        self.reads = 0

    def read(self, image):
        lines = self.frames[min(self.reads, len(self.frames) - 1)]
        self.reads += 1
        return lines

    @staticmethod
    def find(lines, needle):
        for line in lines:
            if needle in line.text:
                return line
        return None

    @staticmethod
    def center(line):
        x, y, w, h = line.box
        return x + w // 2, y + h // 2


def test_drink_dialog_never_open_retries_slot_and_reports() -> None:
    """对话未开（GKMSMAA HIF-112 同类）：重试槽位 max_tries 次，失败留痕，不点「使用」。"""
    ap = _auto_produce()
    device = FakeDevice()
    agent = FakeAgent(device=device)
    driver = FakeDrinkDriver([_lines("剩余回合", "SKIP")])  # 对话始终没开
    ok, reason = ap.attempt_drink(agent, driver, sleep=lambda _s: None, max_tries=2)
    assert ok is False
    assert "对话仍未打开" in reason
    assert device.clicks == [ap.DRINK_SLOT, ap.DRINK_SLOT]
    assert driver.reads == 2


def test_drink_dialog_opens_on_second_try() -> None:
    ap = _auto_produce()
    device = FakeDevice()
    agent = FakeAgent(device=device)
    use_line = _lines("饮料", "使用", "取消")[1]
    driver = FakeDrinkDriver([_lines("剩余回合"), _lines("饮料", "使用", "取消")])
    ok, reason = ap.attempt_drink(agent, driver, sleep=lambda _s: None, max_tries=2)
    assert ok is True and "第 2 次" in reason
    assert device.clicks == [ap.DRINK_SLOT, ap.DRINK_SLOT, (140, 120)]
    assert device.clicks[-1] == FakeDrinkDriver.center(use_line)


def test_drink_dialog_opens_first_try() -> None:
    ap = _auto_produce()
    device = FakeDevice()
    agent = FakeAgent(device=device)
    driver = FakeDrinkDriver([_lines("饮料", "使用")])
    ok, reason = ap.attempt_drink(agent, driver, sleep=lambda _s: None)
    assert ok is True and "第 1 次" in reason
    assert device.clicks[0] == ap.DRINK_SLOT
    assert len(device.clicks) == 2


# ---------------------------------------------------------------- decide() 预算


def test_decide_budgets_dialog_gone_for_confirm() -> None:
    """动作前预算下一帧：弹窗确认 → 期望「取消」消失 + 落点。"""
    driver = _driver()
    agent = FakeAgent()
    tick = driver.decide(agent, _lines("跳过确认", "未读的交流", "取消", "确定"))
    assert tick.screen == "dialog" and tick.action == "confirm"
    assert tick.point == (140, 240)
    assert tick.expect is not None
    assert tick.expect.kind == KIND_DIALOG_GONE
    assert "取消" in tick.expect.words
    assert tick.reason and "弹窗确认" in tick.reason


def test_decide_budgets_end_turn_yes_dialog_gone() -> None:
    driver = _driver()
    tick = driver.decide(
        FakeAgent(), _lines("回合结束", "尚可使用技能卡", "确定要结束回合吗", "是", "否")
    )
    assert tick.action == "end-turn-yes"
    assert tick.expect is not None and tick.expect.kind == KIND_DIALOG_GONE
    assert "结束回合" in tick.expect.words
    assert tick.point is not None


def test_decide_budgets_net_error_dialog_gone() -> None:
    driver = _driver()
    tick = driver.decide(
        FakeAgent(), _lines("通信错误", "获取资产失败", "返回标题", "重试")
    )
    assert tick.screen == "net-error"
    assert tick.expect is not None and tick.expect.kind == KIND_DIALOG_GONE
    assert "通信错误" in tick.expect.words


def test_decide_generic_tap_budgets_screen_change() -> None:
    driver = _driver()
    agent = FakeAgent()
    lines = _lines("美铃", "哎呀……这可真是麻烦了呢。")
    tick = driver.decide(agent, lines)
    assert tick.screen == "story"
    assert tick.expect is not None and tick.expect.kind == KIND_CHANGE
    assert tick.expect.before == driver._frame_signature(driver.text_of(lines))
    assert tick.point == (360, 1000)


def test_decide_user_busy_has_no_budget() -> None:
    driver = _driver()
    agent = FakeAgent(device=FakeDevice(refuse=True))
    tick = driver.decide(agent, _lines("取消", "确定"))
    assert tick.screen == "pause"
    assert tick.point is None and tick.expect is None


def test_decide_loading_has_no_budget() -> None:
    driver = _driver()
    tick = driver.decide(FakeAgent(), _lines("NOW LOADING..."))
    assert tick.screen == "loading"
    assert tick.expect is None


def test_action_confirm_keeps_last_point_across_calls() -> None:
    """last_point 跨调用保留（action-confirm 用上一次的落点），预算不破坏它。"""
    driver = _driver()
    agent = FakeAgent()
    driver.decide(agent, _lines("请选择行动", "授课", "活动奖励"))
    tick = driver.decide(agent, _lines("根据选项会发生各种效果。", "SELECT"))
    assert tick.screen == "action-confirm"
    assert tick.point == (140, 120)
    assert tick.expect is not None and tick.expect.kind == KIND_CHANGE


# ---------------------------------------------------------------- card-reward picker 接线


def test_card_reward_first_tick_picks_then_claims() -> None:
    driver = _driver()
    agent = FakeAgent()
    lines = _lines("请选择要领取的技能卡", "卡A", "卡B", "领取")
    tick = driver.decide(agent, lines)
    assert tick.screen == "card-reward" and tick.action == "pick+claim"
    # 卡位一击 + 领取两击（点亮动画兜底），picker 已登记
    assert len(agent.device.clicks) == 3
    assert driver.reward_picker.active
    assert driver.reward_picker.stage == "confirm"
    assert tick.expect is not None and tick.expect.kind == KIND_CHANGE


def test_card_reward_same_screen_retries_claim_not_slot() -> None:
    """picker 选牌失败场景：同一奖励屏没关 → 只重试「领取」，不重点卡位。"""
    driver = _driver()
    agent = FakeAgent()
    lines = _lines("请选择要领取的技能卡", "卡A", "卡B", "领取")
    driver.decide(agent, lines)
    first_clicks = list(agent.device.clicks)
    slot = first_clicks[0]
    claim = first_clicks[1]
    driver.reward_picker._last_tap_at -= 5.0  # 模拟下一帧（时钟已走过 retry_after）
    tick = driver.decide(agent, lines)
    assert tick.action == "claim-retry"
    assert agent.device.clicks[len(first_clicks) :] == [claim]
    assert slot not in agent.device.clicks[len(first_clicks) :]
    assert "不重点卡位" in tick.reason


def test_card_reward_retry_budget_exhausted_resets_to_full_pick() -> None:
    driver = _driver()
    agent = FakeAgent()
    lines = _lines("请选择要领取的技能卡", "卡A", "卡B", "领取")
    driver.decide(agent, lines)
    for _ in range(2):
        driver.reward_picker._last_tap_at -= 5.0
        tick = driver.decide(agent, lines)
        assert tick.action == "claim-retry"
    driver.reward_picker._last_tap_at -= 5.0
    tick = driver.decide(agent, lines)
    # failed → 重置 → 重新完整选卡+领取（既有同屏兜底仍封顶）
    assert tick.action == "pick+claim"
    assert driver.reward_picker.active


def test_card_reward_new_screen_starts_new_picker() -> None:
    driver = _driver()
    agent = FakeAgent()
    driver.decide(agent, _lines("请选择要领取的技能卡", "卡A", "领取"))
    assert driver.reward_picker.active
    # 换了一屏（签名不同）→ 重新登记 picker，不走重试
    tick = driver.decide(agent, _lines("请选择要领取的饮料", "饮料X", "领取"))
    assert tick.action == "pick+claim"


def test_tick_result_backward_compatible_positional() -> None:
    tick = TickResult("dialog", "confirm", True, "确定")
    assert tick.point is None and tick.reason == "" and tick.expect is None
    assert tick.describe() == "[dialog] confirm 确定"
