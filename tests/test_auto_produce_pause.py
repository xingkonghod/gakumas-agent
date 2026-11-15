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
        self.swipes: list[tuple[int, int, int, int, int]] = []

    def click(self, x, y, delay: float = 0.35, respect_user: bool = True) -> bool:
        self.calls.append((x, y, delay, respect_user))
        # SendMessageWithCursorPos 会移动/还原光标，Windows 视为一次输入
        self.input.mark_input()
        return True

    def swipe(self, x1, y1, x2, y2, duration_ms: int = 300) -> bool:
        self.swipes.append((x1, y1, x2, y2, duration_ms))
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
    """bot 点击完成 3s 后用户又动鼠标：超出排除窗口，必须继续暂停。"""
    ap = _auto_produce()
    clock = FakeClock()
    input_state = FakeInput(clock)
    input_state.last_input_ts = clock.now - 2.5  # bot 点击过程中的注入
    sleeps: list[float] = []
    gate = _gate(ap, clock, input_state, sleeps)
    device = FakeDevice(clock, input_state)
    ap.SelfInputClickGuard(device, gate).install()

    gate.note_self_input()  # 假设刚点完
    clock.advance(3.2)  # 超出 bot 自身 3s 排除窗口
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


def test_queued_cursor_input_within_3s_after_click_is_still_self() -> None:
    """真机 ep-sup1：MAA「还原光标」的输入晚于 note_self_input 落盘，3s 内都算 bot 自己。

    旧窗口 0.6s：奖励屏领奖（连点多次）后下一步必然误判 `[pause] user-active`，
    实测 3 次、每次 8.5-30.2s 空转。这里模拟"点击后 2.5s 才落盘的注入输入"。
    """
    ap = _auto_produce()
    clock = FakeClock()
    input_state = FakeInput(clock)
    gate = _gate(ap, clock, input_state)
    device = FakeDevice(clock, input_state)
    ap.SelfInputClickGuard(device, gate).install()

    assert device.click_force(360, 1000) is True
    clock.advance(2.5)
    input_state.mark_input()  # 排队中的光标还原输入（晚于记账落盘）
    clock.advance(0.05)
    assert input_state.idle_ms() == 50
    assert gate.user_operating() is False  # 3s 窗口内 → bot 自己
    assert device.click_force(360, 1000) is True

    # 距 bot 点击超过 3s 之后的输入才算用户操作
    clock.advance(3.6)
    input_state.mark_input()
    clock.advance(0.05)
    assert gate.user_operating() is True
    assert device.click_force(360, 1000) is False


def test_same_digest_passes_through_instead_of_waiting_30s() -> None:
    """F#11 兜底：判定"用户在操作"但画面 digest 与上一步完全相同 → 直接放行。

    真机 ep-cplus13 在结算页连刷 `[pause] user-active`，旧实现要等 30s 才强制继续，
    结果是整局空转停机；真实用户操作一定伴随画面变化（翻页/选牌/换镜头），
    所以"画面一模一样"只可能是 bot 自己注入的光标移动被算成用户输入。
    """
    ap = _auto_produce()
    gate = ap.PauseGate(idle_ms=lambda: 100, clock=lambda: 0.0, sleep=lambda _s: None)

    assert gate.user_operating() is True
    assert gate.observe("same-frame") is False  # 第一步没有"上一步"可比，先暂停
    assert gate.last_reason == "user-operating"
    assert gate.observe("same-frame") is True  # 同一画面 → 直接放行
    assert gate.same_digest_passes == 1
    assert gate.last_reason == "same-digest"
    # 放行后每步继续放行（画面仍然没变），不会退回空转
    assert gate.observe("same-frame") is True
    assert gate.same_digest_passes == 2


def test_screen_change_keeps_pause_and_resets_digest_pass() -> None:
    """画面真的在变（用户翻页/选牌）时继续保持暂停；换屏不能触发"直接放行"。"""
    ap = _auto_produce()
    gate = ap.PauseGate(idle_ms=lambda: 100, clock=lambda: 0.0, sleep=lambda _s: None)

    assert gate.observe("frame-A") is False
    assert gate.observe("frame-B") is False  # 换屏 → 仍判用户操作，不抢点击
    assert gate.last_reason == "user-operating"
    assert gate.observe("frame-C") is False
    assert gate.same_digest_passes == 0


def test_same_digest_pass_lets_the_click_through() -> None:
    """放行那一步的点击必须真的执行（否则"放行"没有意义）。"""
    ap = _auto_produce()
    clock = FakeClock()
    input_state = FakeInput(clock)
    gate = _gate(ap, clock, input_state)
    device = FakeDevice(clock, input_state)
    guard = ap.SelfInputClickGuard(device, gate).install()

    input_state.mark_input()  # bot 自己注入的光标移动被当成"用户刚有输入"
    assert gate.user_operating() is True
    assert gate.observe("frame-A") is False  # 第一步：暂停
    guard.force = gate.observe("frame-A")  # 第二步：同一画面 → 放行
    assert guard.force is True
    assert device.click_force(360, 1000) is True
    assert len(device.calls) == 1
    assert gate.same_digest_passes == 1


def test_guard_takes_over_click_and_click_force_and_swipe() -> None:
    """F#11 真因之一：只有 click_force 走门，device.click / device.swipe 仍走原生。

    ProduceTask/Navigator 用 ``device.click(...)``（自带 respect_user 门），滚动用
    ``device.swipe(...)``；这两条路径不记账，下一步就误判"用户正在操作"。install()
    必须把三个入口都换成 guard 的绑定方法（不是把 click_force 缓存成局部引用）。
    """
    ap = _auto_produce()
    clock = FakeClock()
    input_state = FakeInput(clock)
    gate = _gate(ap, clock, input_state)
    device = FakeDevice(clock, input_state)
    guard = ap.SelfInputClickGuard(device, gate).install()

    assert device.click.__self__ is guard
    assert device.click_force.__self__ is guard
    assert device.swipe.__self__ is guard

    assert device.click(360, 1000) is True
    assert device.click_force(360, 1000) is True
    assert device.swipe(360, 1020, 360, 760) is True
    assert len(device.calls) == 2
    assert device.swipes == [(360, 1020, 360, 760, 300)]
    # 三次注入都记成 bot 自己：紧接着的一步不会被误判成用户操作
    clock.advance(0.05)
    assert input_state.idle_ms() == 50
    assert gate.user_operating() is False


def test_swipe_respects_pause_gate() -> None:
    """真实用户操作时滑动也不能抢（滚动饮料列表会移动光标）。"""
    ap = _auto_produce()
    clock = FakeClock()
    input_state = FakeInput(clock)
    sleeps: list[float] = []
    gate = _gate(ap, clock, input_state, sleeps)
    device = FakeDevice(clock, input_state)
    ap.SelfInputClickGuard(device, gate).install()

    clock.advance(0.7)
    input_state.mark_input()  # 真实用户输入（已超出 bot 自身 0.6s 窗口）
    assert gate.user_operating() is True
    assert device.swipe(360, 1020, 360, 760) is False
    assert device.swipes == []
    assert sleeps == [gate.refusal_backoff_s]


def test_force_flag_lets_click_through_then_self_input_clears_it() -> None:
    """放行的那一步点击照常执行，点击后立刻记账，不会下一步又判用户操作。"""
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
