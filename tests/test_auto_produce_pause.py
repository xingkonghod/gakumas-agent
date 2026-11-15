"""auto_produce 暂停门：排除 bot 自身输入 + 30s 画面无变化强制继续。

真机症状：bot 用 SendMessageWithCursorPos 点击（光标短暂移动再还原）会刷新
``GetLastInputInfo``，下一次点击的 user_idle 门误判"用户正在操作"而返回 False，
日志出现 ``[pause] 用户正在操作，暂停出牌``，出牌空转。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _auto_produce():
    """按 scripts 目录导入 auto_produce（scripts 不是包，避免污染 sys.path 到顶层）。"""
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import auto_produce

    return auto_produce


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeInput:
    """模拟 GetLastInputInfo：idle = 当前时刻 - 最后一次输入时刻。"""

    def __init__(self, clock: FakeClock, idle_s: float = 5.0) -> None:
        self.clock = clock
        self.last_input_ts = clock.now - idle_s

    def mark_input(self) -> None:
        self.last_input_ts = self.clock.now

    def idle_ms(self) -> int:
        return max(0, round((self.clock.now - self.last_input_ts) * 1000))


class FakeDevice:
    """只记录注入了什么，不真碰 Win32。"""

    def __init__(self, clock: FakeClock, input_state: FakeInput) -> None:
        self.clock = clock
        self.input = input_state
        self.calls: list[tuple[int, int, float, bool]] = []

    def click(self, x, y, delay: float = 0.35, respect_user: bool = True) -> bool:
        self.calls.append((x, y, delay, respect_user))
        # SendMessageWithCursorPos 会移动/还原光标，Windows 视为一次输入
        self.input.mark_input()
        return True


def _gate(ap, clock: FakeClock, input_state: FakeInput, sleeps: list[float] | None = None):
    return ap.PauseGate(
        idle_ms=input_state.idle_ms,
        clock=clock,
        sleep=(sleeps if sleeps is not None else []).append,
    )


def test_bot_own_click_is_not_user_input() -> None:
    """bot 点击后 0.1s 内 idle 只有 100ms，但那是自己注入的，不能触发暂停。"""
    ap = _auto_produce()
    clock = FakeClock()
    input_state = FakeInput(clock)
    sleeps: list[float] = []
    gate = _gate(ap, clock, input_state, sleeps)
    device = FakeDevice(clock, input_state)
    ap.SelfInputClickGuard(device, gate).install()

    assert gate.user_operating() is False
    assert device.click_force(360, 1000) is True  # 第一次点击放行
    assert device.calls[-1][3] is False  # 绕开设备内置 respect_user 等待

    clock.advance(0.1)
    assert input_state.idle_ms() == 100  # GetLastInputInfo 认为"刚有输入"
    assert gate.user_operating() is False  # 但时间戳落在 bot 自己的 0.6s 窗口内
    assert device.click_force(360, 1000) is True
    assert sleeps == []
    assert len(device.calls) == 2


def test_real_user_input_still_pauses() -> None:
    """bot 点击完成 0.7s 后用户又动鼠标：超出排除窗口，必须继续暂停。"""
    ap = _auto_produce()
    clock = FakeClock()
    input_state = FakeInput(clock)
    input_state.last_input_ts = clock.now - 0.5  # bot 点击过程中的注入
    sleeps: list[float] = []
    gate = _gate(ap, clock, input_state, sleeps)
    device = FakeDevice(clock, input_state)
    ap.SelfInputClickGuard(device, gate).install()

    gate.note_self_input()  # 假设刚点完
    clock.advance(0.7)
    input_state.mark_input()  # 真实用户输入
    clock.advance(0.05)
    assert input_state.idle_ms() == 50
    assert gate.user_operating() is True

    assert device.click_force(360, 1000) is False
    assert device.calls == []  # 真实用户操作时绝不抢点击
    assert sleeps == [gate.refusal_backoff_s]  # 返回 False 前有退避，避免空转

    # 用户停手超过 gate_ms 就不再算操作
    clock.advance(0.8)
    assert gate.user_operating() is False


def test_pause_gate_forces_continue_after_30s_without_screen_change() -> None:
    """连续判定用户在操作但画面 30s 没变 → 兜底放行，不再无限暂停。"""
    ap = _auto_produce()
    clock = FakeClock()
    gate = ap.PauseGate(idle_ms=lambda: 100, clock=clock, sleep=lambda _s: None)

    assert gate.user_operating() is True
    assert gate.observe("same-frame") is False  # 开始计时
    clock.advance(29.0)
    assert gate.observe("same-frame") is False  # 还不到 30s
    clock.advance(1.5)
    assert gate.observe("same-frame") is True  # 30.5s 无变化 → 强制继续
    assert gate.forced_continues == 1

    # 放行后重新计时，不会每一步都刷"强制继续"
    clock.advance(5.0)
    assert gate.observe("same-frame") is False


def test_screen_change_resets_force_timer() -> None:
    """用户真的在玩（画面在变）时计时清零，不会 30s 后误放行。"""
    ap = _auto_produce()
    clock = FakeClock()
    gate = ap.PauseGate(idle_ms=lambda: 100, clock=clock, sleep=lambda _s: None)

    assert gate.observe("frame-A") is False
    clock.advance(20.0)
    assert gate.observe("frame-B") is False  # 画面变了 → 重新计时
    clock.advance(20.0)
    assert gate.observe("frame-B") is False  # 连续没变只有 20s
    clock.advance(10.5)
    assert gate.observe("frame-B") is True
    assert gate.forced_continues == 1


def test_force_flag_lets_click_through_then_self_input_clears_it() -> None:
    """30s 兜底放行的那一步点击照常执行，点击后立刻记账，不会下一步又判用户操作。"""
    ap = _auto_produce()
    clock = FakeClock()
    input_state = FakeInput(clock)
    gate = _gate(ap, clock, input_state)
    device = FakeDevice(clock, input_state)
    guard = ap.SelfInputClickGuard(device, gate).install()

    input_state.mark_input()
    assert gate.user_operating() is True
    clock.advance(0.05)

    guard.force = True
    assert device.click_force(360, 1000) is True
    assert len(device.calls) == 1

    guard.force = False
    clock.advance(0.1)
    assert gate.user_operating() is False  # 刚才那次是 bot 自己点的
