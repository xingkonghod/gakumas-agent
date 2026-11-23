"""C1 提权检查：游戏 elevated / 本进程 non-elevated → UIPI 静默丢点击。

纯判定矩阵 + Win32 探测（注入假 API，与 ensure_window 的 user32 注入同约定）。
架构参考 GKMSMAA winpriv.py（AGPL 只读参考），实现全部自写。
"""

from __future__ import annotations

import ctypes

import pytest

from gkagent.device import privilege
from gkagent.device.privilege import (
    check_tap_privilege,
    is_self_elevated,
    process_elevated,
    tap_reach_verdict,
    window_pid,
)

# ---------------------------------------------------------------- 纯判定矩阵


def test_self_elevated_always_ok() -> None:
    for game in (True, False, None, "denied"):
        verdict = tap_reach_verdict(True, game)
        assert verdict.status == "ok"


def test_both_non_elevated_ok() -> None:
    verdict = tap_reach_verdict(False, False)
    assert verdict.status == "ok"


def test_game_elevated_self_not_blocks_with_hint() -> None:
    verdict = tap_reach_verdict(False, True)
    assert verdict.status == "blocked"
    assert "UIPI" in verdict.reason
    assert "管理员" in verdict.hint


def test_token_denied_blocks() -> None:
    """低完整性进程读高完整性进程令牌 = 访问被拒 → 按 blocked 处理。"""
    verdict = tap_reach_verdict(False, "denied")
    assert verdict.status == "blocked"
    assert "管理员" in verdict.hint


def test_unknown_never_blocks() -> None:
    assert tap_reach_verdict(False, None).status == "unknown"
    assert tap_reach_verdict(None, True).status == "unknown"
    assert tap_reach_verdict(None, None).status == "unknown"


# ---------------------------------------------------------------- 探测（假 API）


class FakeShell32:
    def __init__(self, admin: int = 0, raises: bool = False) -> None:
        self.admin = admin
        self.raises = raises

    def IsUserAnAdmin(self):
        if self.raises:
            raise OSError("probe failed")
        return self.admin


class FakeUser32:
    def __init__(self, pid: int = 777, result: int = 1) -> None:
        self.pid = pid
        self.result = result

    def GetWindowThreadProcessId(self, hwnd, pid_ptr):
        pid_ptr._obj.value = self.pid
        return self.result


class FakeKernel32:
    def __init__(self, handle: int = 123, error: int = 0) -> None:
        self.handle = handle
        self.error = error
        self.closed: list[int] = []
        self.opened: list[tuple[int, int]] = []

    def OpenProcess(self, access, inherit, pid):
        self.opened.append((access, pid))
        return self.handle

    def GetLastError(self):
        return self.error

    def CloseHandle(self, handle):
        value = getattr(handle, "value", handle)
        self.closed.append(int(value or 0))
        return 1


class FakeAdvapi32:
    def __init__(
        self,
        token_ok: bool = True,
        token_handle: int = 456,
        info_ok: bool = True,
        elevation: int = 1,
    ) -> None:
        self.token_ok = token_ok
        self.token_handle = token_handle
        self.info_ok = info_ok
        self.elevation = elevation

    def OpenProcessToken(self, handle, access, token_ptr):
        if not self.token_ok:
            return 0
        token_ptr._obj.value = self.token_handle
        return 1

    def GetTokenInformation(self, token, info_class, value_ptr, size, size_ptr):
        if not self.info_ok:
            return 0
        value_ptr._obj.value = self.elevation
        return 1


def test_is_self_elevated_probe() -> None:
    assert is_self_elevated(shell32=FakeShell32(admin=1)) is True
    assert is_self_elevated(shell32=FakeShell32(admin=0)) is False
    assert is_self_elevated(shell32=FakeShell32(raises=True)) is None


def test_window_pid_probe() -> None:
    assert window_pid(42, user32=FakeUser32(pid=777)) == 777
    assert window_pid(42, user32=FakeUser32(result=0)) is None
    assert window_pid(0) is None


def test_process_elevated_true_and_closes_handles() -> None:
    kernel32 = FakeKernel32()
    advapi32 = FakeAdvapi32(elevation=1)
    assert process_elevated(777, kernel32=kernel32, advapi32=advapi32) is True
    assert kernel32.opened == [(privilege.PROCESS_QUERY_LIMITED_INFORMATION, 777)]
    # 进程句柄 + 令牌句柄都要关
    assert sorted(kernel32.closed) == [123, 456]


def test_process_elevated_false() -> None:
    assert (
        process_elevated(777, kernel32=FakeKernel32(), advapi32=FakeAdvapi32(elevation=0))
        is False
    )


def test_process_open_denied() -> None:
    kernel32 = FakeKernel32(handle=0, error=privilege.ERROR_ACCESS_DENIED)
    assert process_elevated(777, kernel32=kernel32, advapi32=FakeAdvapi32()) == "denied"


def test_process_open_other_error_is_unknown() -> None:
    kernel32 = FakeKernel32(handle=0, error=87)
    assert process_elevated(777, kernel32=kernel32, advapi32=FakeAdvapi32()) is None


def test_token_open_denied_closes_process_handle() -> None:
    kernel32 = FakeKernel32(error=privilege.ERROR_ACCESS_DENIED)
    advapi32 = FakeAdvapi32(token_ok=False)
    assert process_elevated(777, kernel32=kernel32, advapi32=advapi32) == "denied"
    assert kernel32.closed == [123]


def test_token_info_failure_is_unknown() -> None:
    kernel32 = FakeKernel32()
    advapi32 = FakeAdvapi32(info_ok=False)
    assert process_elevated(777, kernel32=kernel32, advapi32=advapi32) is None
    assert sorted(kernel32.closed) == [123, 456]


def test_process_elevated_no_pid() -> None:
    assert process_elevated(None) is None
    assert process_elevated(0) is None


def test_check_tap_privilege_combines_probes() -> None:
    verdict = check_tap_privilege(
        42,
        user32=FakeUser32(pid=777),
        shell32=FakeShell32(admin=0),
        kernel32=FakeKernel32(),
        advapi32=FakeAdvapi32(elevation=1),
    )
    assert verdict.status == "blocked"
    assert verdict.self_elevated is False
    assert verdict.game_elevated is True


def test_check_tap_privilege_no_window_is_unknown() -> None:
    verdict = check_tap_privilege(
        42,
        user32=FakeUser32(result=0),
        shell32=FakeShell32(admin=0),
        kernel32=FakeKernel32(),
        advapi32=FakeAdvapi32(),
    )
    assert verdict.status == "unknown"


def test_non_windows_probes_return_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(privilege, "IS_WINDOWS", False)
    assert is_self_elevated() is None
    assert window_pid(42) is None
    assert process_elevated(777) is None
    assert check_tap_privilege(42).status == "unknown"


def test_byref_contract_matches_ctypes() -> None:
    """假 API 用 ._obj.value 写回——与真 ctypes.byref 的契约一致（防探针写错指针）。"""
    value = ctypes.c_ulong(0)
    ptr = ctypes.byref(value)
    ptr._obj.value = 9
    assert value.value == 9
