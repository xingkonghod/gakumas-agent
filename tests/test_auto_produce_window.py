"""auto_produce.ensure_window：每步前置恢复窗口（F#9）。

真机 ep-cplus13：跑局中途窗口被最小化 / 拉成 720x1280，所有点击都落到不存在的地方，
日志只有 ``[capture] invalid screenshot shape=(720, 1280, 3) mean=0.0``——等截图报错
再补救已经空转 12 次。这里在每步决策之前检查并恢复，尺寸固定回 540x960
（720x1280 是截图内部缩放后的尺寸，改窗口反而会多出 1 行，见 F#10）。
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


class FakeUser32:
    """最小 Win32 桩：只实现 ensure_window 用到的 5 个函数，不碰真窗口。"""

    def __init__(
        self,
        iconic: bool = False,
        client: tuple[int, int] = (540, 960),
        frame: tuple[int, int] = (16, 39),
        restore_works: bool = True,
        resize_works: bool = True,
    ) -> None:
        self.iconic = iconic
        self.client = client
        self.frame = frame
        self.restore_works = restore_works
        self.resize_works = resize_works
        self.show_window: list[tuple[int, int]] = []
        self.set_window_pos: list[tuple[int, int, int, int]] = []

    @staticmethod
    def _fill(ref, left: int, top: int, width: int, height: int) -> None:
        rect = ref._obj  # ctypes.byref(...) 的 CArgObject 指向调用方传进来的 RECT
        rect.left = int(left)
        rect.top = int(top)
        rect.right = int(left) + int(width)
        rect.bottom = int(top) + int(height)

    def IsIconic(self, hwnd: int) -> int:
        return int(self.iconic)

    def ShowWindow(self, hwnd: int, cmd: int) -> int:
        self.show_window.append((int(hwnd), int(cmd)))
        if self.restore_works:
            self.iconic = False
        return 1

    def GetClientRect(self, hwnd: int, ref) -> int:
        # client 坐标从 (0,0) 开始：只有宽高有意义
        self._fill(ref, 0, 0, *self.client)
        return 1

    def GetWindowRect(self, hwnd: int, ref) -> int:
        # 外框 = client + 边框/标题栏，左上角在屏幕上的偏移（100,50）不影响差值
        self._fill(ref, 100, 50, self.client[0] + self.frame[0], self.client[1] + self.frame[1])
        return 1

    def SetWindowPos(
        self, hwnd: int, after: int, x: int, y: int, cx: int, cy: int, flags: int
    ) -> int:
        self.set_window_pos.append((int(hwnd), int(cx), int(cy), int(flags)))
        if self.resize_works:
            self.client = (int(cx) - self.frame[0], int(cy) - self.frame[1])
        return 1


def test_ensure_window_restores_minimized_window() -> None:
    """最小化 → ShowWindow(SW_RESTORE)，并报告 restored（主循环据此打 [window] 日志）。"""
    ap = _auto_produce()
    api = FakeUser32(iconic=True)
    state = ap.ensure_window(1234, user32=api, sleep=lambda _s: None)
    assert state == "restored"
    assert api.show_window == [(1234, ap.SW_RESTORE)]
    assert api.set_window_pos == []


def test_ensure_window_resizes_client_back_to_540x960() -> None:
    """client 变成 720x1280（真机故障态）→ SetWindowPos 把 client 改回 540x960。

    注意 SetWindowPos 设的是含边框的外框，这里按 frame=(16,39) 换算成 556x999。
    """
    ap = _auto_produce()
    api = FakeUser32(client=(720, 1280))
    state = ap.ensure_window(1234, user32=api, sleep=lambda _s: None)
    assert state == "restored"
    expected_flags = ap.SWP_NOMOVE | ap.SWP_NOZORDER | ap.SWP_NOACTIVATE
    assert api.set_window_pos == [(1234, 540 + 16, 960 + 39, expected_flags)]
    assert api.client == (540, 960)


def test_ensure_window_never_resizes_to_720x1280() -> None:
    """只允许 540x960（F#10：720x1280 会多出 1 行，反而截不出图）。"""
    ap = _auto_produce()
    assert ap.PRODUCE_CLIENT_SIZE == (540, 960)
    api = FakeUser32(client=(720, 1280))
    ap.ensure_window(1234, user32=api, sleep=lambda _s: None)
    _, width, height, _ = api.set_window_pos[0]
    assert (width - api.frame[0], height - api.frame[1]) == (540, 960)


def test_ensure_window_noop_when_window_is_normal() -> None:
    """窗口本来就正常：不做任何 Win32 调用，返回 ok。"""
    ap = _auto_produce()
    api = FakeUser32()
    assert ap.ensure_window(1234, user32=api, sleep=lambda _s: None) == "ok"
    assert api.show_window == []
    assert api.set_window_pos == []


def test_ensure_window_reports_failed_when_still_minimized() -> None:
    """ShowWindow 不生效（还在最小化）→ failed，主循环等待而不是继续点击。"""
    ap = _auto_produce()
    api = FakeUser32(iconic=True, restore_works=False)
    state = ap.ensure_window(1234, user32=api, sleep=lambda _s: None)
    assert state == "failed"
    assert len(api.show_window) == ap.WINDOW_RESTORE_ATTEMPTS


def test_ensure_window_reports_failed_when_size_never_sticks() -> None:
    """SetWindowPos 不生效（尺寸改不回来）→ failed。"""
    ap = _auto_produce()
    api = FakeUser32(client=(720, 1280), resize_works=False)
    state = ap.ensure_window(1234, user32=api, sleep=lambda _s: None)
    assert state == "failed"
    assert len(api.set_window_pos) == ap.WINDOW_RESTORE_ATTEMPTS
