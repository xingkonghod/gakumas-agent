"""Win32 设备：截屏 + 点击。

底层复用 MaaFramework 的 Win32Controller：
- 截屏 FramePool；
- 点击默认 ``SendMessageWithCursorPos``：后台窗口消息 + 光标短暂移到目标点后还原，
  和原生 MaaGakumasu 的 PC 配置一致（``config/instances/*.json`` 的
  ``Win32ControlMouseType``），既不用抢前台，也不会一直占着鼠标。

输入方式对照（MaaFramework Python binding 的 ``MaaWin32InputMethodEnum`` 文档）：

| 方式 | 后台 | 抢鼠标 | 说明 |
|---|---|---|---|
| Seize | 否 | 是 | 真实鼠标，必须前台 |
| SendMessage / PostMessage | 是 | 否 | 本游戏不认（实测 diff≈0） |
| SendMessageWithCursorPos | 是 | 短暂 | 光标移到目标→发消息→还原（默认） |
| AnchoredTouch | 是 | 否 | 合成触摸 WM_POINTER，本游戏不认 |
| Interception | 否 | 驱动级 | 需要驱动，仍是真实输入 |
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np

USER32 = ctypes.WinDLL("user32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def user_idle_ms() -> int:
    """距离用户最后一次键盘/鼠标输入过去了多少毫秒。"""
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(_LastInputInfo)
    if not USER32.GetLastInputInfo(ctypes.byref(info)):
        return 0
    return (KERNEL32.GetTickCount() - int(info.dwTime)) & 0xFFFFFFFF




def _normalize_rows(frame):
    """将缩放取整带来的 1279/1281 行统一成 1280。"""
    import numpy as np

    rows = frame.shape[0]
    if rows == 1280:
        return frame
    if rows > 1280:
        return frame[:1280]
    pad = np.repeat(frame[-1:], 1280 - rows, axis=0)
    return np.vstack([frame, pad])

class Win32Device:
    def __init__(
        self,
        hwnd: int,
        maa_home: str | os.PathLike[str] = r"D:\Games\MaaGakumasu",
        screencap: str = "FramePool",
        input_method: str = "SendMessageWithCursorPos",
        user_idle_gate_ms: int = 800,
    ) -> None:
        self.hwnd = int(hwnd)
        self.maa_home = Path(maa_home)
        self.screencap = screencap
        self.input_method = input_method
        self.user_idle_gate_ms = int(user_idle_gate_ms)
        self._ctrl = None
        self._overlay: int | None = None

    def connect(self) -> Win32Device:
        os.chdir(self.maa_home)
        site = self.maa_home / "python" / "Lib" / "site-packages"
        if site.exists() and str(site) not in sys.path:
            # 追加而不是插到最前面：MaaGakumasu 的 site-packages 里有别的 Python
            # 编译的 C 扩展（onnxruntime 等），插到最前会把本项目 venv 里的同名包顶掉，
            # 表现为 "DLL load failed while importing onnxruntime_pybind11_state"。
            sys.path.append(str(site))

        from maa.controller import Win32Controller
        from maa.define import MaaWin32InputMethodEnum as InputMethod
        from maa.define import MaaWin32ScreencapMethodEnum as ScreencapMethod

        self._overlay = find_window("player-assist")
        if self._overlay:
            USER32.ShowWindow(self._overlay, 0)
        cap = getattr(ScreencapMethod, self.screencap)
        inp = getattr(InputMethod, self.input_method)
        self._ctrl = Win32Controller(self.hwnd, cap, inp, inp)
        self._ctrl.post_connection().wait()
        return self

    @property
    def controller(self):
        if self._ctrl is None:
            raise RuntimeError("device not connected; call connect() first")
        return self._ctrl

    def _prepare_input(self) -> None:
        # 不再移动光标/抢焦点；PostMessage 直接投递窗口消息。
        return

    def capture(self, attempts: int = 8) -> np.ndarray:
        """截屏；窗口最小化或拿到黑帧/异常尺寸时重试几次再报错。

        游戏实际渲染高度可能是 1279 或 1280（差 1px），两者都接受。
        """
        if USER32.IsIconic(self.hwnd):
            raise RuntimeError("game window is minimized; restore it first")
        frame = None
        for _ in range(max(1, attempts)):
            frame = np.asarray(self.controller.post_screencap().wait().get())
            shape = getattr(frame, "shape", ())
            if (
                frame.ndim == 3
                and shape[0] in (1279, 1280, 1281)
                and shape[1] == 720
                and float(frame.mean()) > 3.0
            ):
                return _normalize_rows(frame)
            # 窗口被拉成横屏（720x1280）时转回竖屏
            if (
                frame.ndim == 3
                and shape[0] == 720
                and shape[1] in (1279, 1280, 1281)
                and float(frame.mean()) > 3.0
            ):
                return _normalize_rows(frame.transpose(1, 0, 2))
            time.sleep(0.35)
        shape = getattr(frame, "shape", None)
        mean = float(frame.mean()) if frame is not None else -1.0
        raise RuntimeError(f"invalid screenshot shape={shape} mean={mean:.1f}")

    def click(self, x: int, y: int, delay: float = 0.35, respect_user: bool = True) -> bool:
        """点击：默认 SendMessageWithCursorPos（后台消息，光标短暂移到目标再还原）。

        坐标约定：**直接传 720x1280 设计坐标，不要预缩放**。
        ``Win32Controller.post_click`` 的坐标系是截图/识别坐标系（720x1280），
        原生代码内部会按窗口客户区大小换算到客户区像素/屏幕像素再发送
        （实测：post_click(360,1090) 会把光标移到客户区 (270,819) = 360*540/720）。

        2026-11-21 真机踩坑（TROUBLESHOOTING 2.1 的复发变种）：窗口客户区是
        540x960 时，这里曾把设计坐标**先**缩放成客户区像素再交给 controller，
        被原生代码**再**缩放一次（0.75×0.75），点击实际落在设计坐标 ×0.75 处
        ——主页点「プロデュース」全落空、bot 连点 60 步画面不动。7e58b4b 的
        预缩放是误诊（当时窗口尺寸/坐标空间没对齐），现已撤销。

        ``respect_user``：用户正在用键鼠时不点（等待最多 ~1.2s 后返回 False）。
        返回是否真的点下去了。
        """
        if respect_user:
            deadline = time.monotonic() + 1.2
            while user_idle_ms() < self.user_idle_gate_ms:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.12)
        self.controller.post_click(int(x), int(y)).wait()
        if delay:
            time.sleep(delay)
        return True

    def click_force(self, x: int, y: int, delay: float = 0.4) -> bool:
        """强制点击：不受「用户正在操作」门限影响。

        之前这里透传给 click()，而 click() 默认 respect_user=True，
        结果机器自己刚点完一下就会被自己的输入判成"用户在动"，
        下一帧的点击被静默跳过 —— 领卡弹窗那种连续点两下的流程会卡死。
        """
        return self.click(x, y, delay=delay, respect_user=False)

    def click_bg(self, x: int, y: int, delay: float = 0.3) -> None:
        """原生 PostMessage 点击：不移动系统光标，不抢前台焦点（本游戏无效，留作他用）。"""
        rect = wintypes.RECT()
        USER32.GetClientRect(self.hwnd, ctypes.byref(rect))
        cw, ch = rect.right, rect.bottom
        cx = round(int(x) * cw / 720.0)
        cy = round(int(y) * ch / 1280.0)
        lp = (cy << 16) | (cx & 0xFFFF)
        USER32.PostMessageW(self.hwnd, 0x0201, 0x0001, lp)  # WM_LBUTTONDOWN
        time.sleep(0.03)
        USER32.PostMessageW(self.hwnd, 0x0202, 0, lp)  # WM_LBUTTONUP
        if delay:
            time.sleep(delay)

    def click_raw(self, x: int, y: int, delay: float = 0.4) -> None:
        """真实鼠标点击（Seize 等价）：设计坐标 → 客户区像素 → 屏幕坐标，自己算。

        和 ``click`` 的区别：这里绕过 MaaFramework，直接用 SetCursorPos + mouse_event
        发真实输入，所以**必须自己把 720x1280 设计坐标缩放到客户区像素**（这一步对
        原生 post_click 是多余的，对真实鼠标输入是必需的）。用于 SendMessage 点击
        不生效的兜底（例如某些需要真实输入状态的界面），会短暂抢前台/移动光标，
        点完恢复光标位置。
        """
        rect = wintypes.RECT()
        USER32.GetClientRect(self.hwnd, ctypes.byref(rect))
        cw, ch = rect.right, rect.bottom
        origin = wintypes.POINT(0, 0)
        USER32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        sx = origin.x + round(int(x) * cw / 720.0)
        sy = origin.y + round(int(y) * ch / 1280.0)

        saved = wintypes.POINT()
        USER32.GetCursorPos(ctypes.byref(saved))
        # 用 AttachThreadInput 绕过前台锁，把游戏拉到最前（不最小化）
        fg = USER32.GetForegroundWindow()
        if fg and fg != self.hwnd:
            fg_tid = USER32.GetWindowThreadProcessId(fg, None)
            cur_tid = KERNEL32.GetCurrentThreadId()
            USER32.AttachThreadInput(cur_tid, fg_tid, True)
            USER32.ShowWindow(self.hwnd, 9)
            USER32.SetForegroundWindow(self.hwnd)
            USER32.BringWindowToTop(self.hwnd)
            USER32.AttachThreadInput(cur_tid, fg_tid, False)
        else:
            USER32.ShowWindow(self.hwnd, 9)
            USER32.SetForegroundWindow(self.hwnd)
        time.sleep(0.15)
        USER32.SetCursorPos(sx, sy)
        time.sleep(0.05)
        USER32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)
        USER32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.06)
        USER32.SetCursorPos(saved.x, saved.y)
        if delay:
            time.sleep(delay)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._prepare_input()
        self.controller.post_swipe(int(x1), int(y1), int(x2), int(y2), int(duration_ms)).wait()

    def key(self, keycode: int) -> None:
        self.controller.post_click_key(int(keycode)).wait()


def find_window(title: str) -> int | None:
    """按标题精确查找可见窗口。"""
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []

    def _cb(hwnd, _lparam):
        length = USER32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            USER32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value == title and USER32.IsWindowVisible(hwnd):
                found.append(int(hwnd))
                return False
        return True

    USER32.EnumWindows(proc_type(_cb), 0)
    return found[0] if found else None


def find_game_hwnd(title_substr: str = "gakumas", class_name: str = "UnityWndClass") -> int | None:
    """按窗口类查找游戏窗口。

    历史坑：daemon 的控制台窗口标题里带 ``gakumas-agent`` 路径，早先按标题子串匹配会
    误把控制台当成游戏（截到 720x1396 黑图、点击也打到控制台）。这里只认
    ``UnityWndClass``，标题匹配必须完全相等；并优先返回未最小化的窗口。
    """
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[tuple[int, int, int]] = []  # (优先级, hwnd, 是否最小化)

    def _cb(hwnd, _lparam):
        if not USER32.IsWindowVisible(hwnd):
            return True
        cbuf = ctypes.create_unicode_buffer(256)
        USER32.GetClassNameW(hwnd, cbuf, 256)
        cls = cbuf.value
        length = USER32.GetWindowTextLengthW(hwnd)
        title = ""
        if length:
            tbuf = ctypes.create_unicode_buffer(length + 1)
            USER32.GetWindowTextW(hwnd, tbuf, length + 1)
            title = tbuf.value.strip()
        iconic = int(bool(USER32.IsIconic(hwnd)))
        if cls == class_name:
            priority = 0 + iconic
        elif title.lower() == title_substr.strip().lower():
            priority = 2 + iconic
        else:
            return True
        found.append((priority, int(hwnd), iconic))
        return True

    USER32.EnumWindows(proc_type(_cb), 0)
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    for _, hwnd, iconic in found:
        if not iconic:
            return hwnd
    return found[0][1]
