"""C1 提权检查：游戏 elevated / 本进程 non-elevated → UIPI 静默丢弃点击。

DMM 版游戏以管理员身份运行；Windows UIPI 会把**低完整性级别进程**发来的窗口
消息静默丢弃（发送方拿不到任何错误），而 FramePool 截屏不受影响——症状正是
「截图读得到、点击全落空、画面一动不动」（GKMSMAA HIF-112 同根因；架构参考
其 ``winpriv.py``，AGPL 只读参考，**本文件全部自写**）。

因此 auto_produce 启动时先查两个进程的提权差：
- ``blocked`` → 拒绝起跑，写 ``elevation-blocked`` failure + 明确补救提示
  （用管理员终端跑 / 以管理员身份重启本进程），不带着「点击全落空」空转到超时；
- ``unknown`` → 只告警不拦（探测不到不等于一定丢点击）。

纯判定 :func:`tap_reach_verdict` 离线可单测；Win32 探测函数支持注入假 API
（与 ``auto_produce.ensure_window`` 的 user32 注入同一套测试约定）。
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

IS_WINDOWS = os.name == "nt"

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION = 20
ERROR_ACCESS_DENIED = 5


@dataclass(frozen=True)
class PrivilegeVerdict:
    """提权检查结论。``status`` ∈ ok/blocked/unknown。"""

    status: str
    self_elevated: bool | None
    game_elevated: bool | str | None
    reason: str
    hint: str = ""


def tap_reach_verdict(
    self_elevated: bool | None,
    game_elevated: bool | str | None,
) -> PrivilegeVerdict:
    """纯判定：本进程/游戏进程的提权状态 → 点击是否可达。

    ``game_elevated`` 取 True/False/``"denied"``（令牌读不到，通常意味着游戏
    完整性级别更高）/None（探测不到）。None 一律按 unknown 处理，不拦跑局。
    """
    if self_elevated is None:
        return PrivilegeVerdict(
            "unknown",
            None,
            game_elevated,
            "本进程提权状态未知（非 Windows 或探测失败），无法判断点击可达性",
            "若点击全部落空，先以管理员身份重试",
        )
    if self_elevated:
        return PrivilegeVerdict(
            "ok",
            True,
            game_elevated,
            "本进程已提权（管理员），点击可达游戏窗口",
        )
    if game_elevated is False:
        return PrivilegeVerdict(
            "ok",
            False,
            False,
            "游戏与本进程都未提权，消息点击可达",
        )
    if game_elevated is True:
        return PrivilegeVerdict(
            "blocked",
            False,
            True,
            "游戏以管理员运行而本进程不是：Windows UIPI 会静默丢弃点击消息"
            "（截屏仍正常，点击全落空）",
            "请在管理员终端里跑 auto_produce.py，或以管理员身份重启本进程",
        )
    if game_elevated == "denied":
        return PrivilegeVerdict(
            "blocked",
            False,
            "denied",
            "游戏进程令牌读不到（访问被拒）——通常意味着游戏完整性级别高于本进程，"
            "点击大概率被 UIPI 丢弃",
            "请在管理员终端里跑 auto_produce.py，或以管理员身份重启本进程",
        )
    return PrivilegeVerdict(
        "unknown",
        False,
        None,
        "游戏提权状态未知；若点击全部落空，先查两进程提权差",
        "若点击落空，以管理员身份重试",
    )


def is_self_elevated(shell32=None) -> bool | None:
    """本进程是否提权（UAC 管理员）。非 Windows / 探测失败 → None。"""
    if not IS_WINDOWS and shell32 is None:
        return None
    api = shell32
    if api is None:
        api = ctypes.windll.shell32  # type: ignore[attr-defined]
    try:
        return bool(api.IsUserAnAdmin())
    except Exception:  # noqa: BLE001 - 探测失败按未知处理，不拦跑局
        return None


def window_pid(hwnd: int, user32=None) -> int | None:
    """窗口所属进程 pid；拿不到返回 None。"""
    if not hwnd:
        return None
    api = user32
    if api is None:
        if not IS_WINDOWS:
            return None
        api = ctypes.windll.user32  # type: ignore[attr-defined]
    pid = wintypes.DWORD(0)
    try:
        result = api.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
    except Exception:  # noqa: BLE001
        return None
    if not result:
        return None
    value = int(pid.value)
    return value or None


def process_elevated(pid: int | None, kernel32=None, advapi32=None) -> bool | str | None:
    """进程令牌 TokenElevation：True/False；``"denied"`` = 令牌读不到
    （低完整性进程看高完整性进程的典型表现）；None = 无法判断。

    只用 PROCESS_QUERY_LIMITED_INFORMATION + TOKEN_QUERY，不需要调试权限。
    """
    if not pid:
        return None
    if kernel32 is None or advapi32 is None:
        if not IS_WINDOWS:
            return None
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        # 64 位下 HANDLE 是 64 位，默认 c_int restype 会截断句柄
        kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return "denied" if kernel32.GetLastError() == ERROR_ACCESS_DENIED else None
    try:
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(token)):
            return "denied" if kernel32.GetLastError() == ERROR_ACCESS_DENIED else None
        try:
            value = wintypes.DWORD(0)
            size = wintypes.DWORD(0)
            if not advapi32.GetTokenInformation(
                token, TOKEN_ELEVATION, ctypes.byref(value), 4, ctypes.byref(size)
            ):
                return None
            return bool(value.value)
        finally:
            kernel32.CloseHandle(token)
    finally:
        kernel32.CloseHandle(handle)


def check_tap_privilege(
    hwnd: int,
    *,
    user32=None,
    kernel32=None,
    advapi32=None,
    shell32=None,
) -> PrivilegeVerdict:
    """组合探测：本进程提权 + 游戏窗口 pid + 游戏进程提权 → 判定。"""
    self_elevated = is_self_elevated(shell32=shell32)
    pid = window_pid(hwnd, user32=user32)
    game_elevated = process_elevated(pid, kernel32=kernel32, advapi32=advapi32) if pid else None
    return tap_reach_verdict(self_elevated, game_elevated)
