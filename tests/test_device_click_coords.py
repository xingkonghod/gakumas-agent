"""设备层点击坐标契约回归测试（真机踩坑：预缩放 × 原生缩放 = 点击落空）。

背景（2026-11-21 真机）：
- 游戏窗口客户区 540x960，截图/识别坐标系是 720x1280（Unity 渲染分辨率）。
- MaaFramework ``Win32Controller.post_click`` 的入参就是**截图坐标系**，
  原生代码内部按客户区大小换算（post_click(360,1090) → 客户区 (270,819)）。
- 7e58b4b 曾在 ``Win32Device.click`` 里把设计坐标先缩放到客户区（×0.75），
  原生再缩放一次 → 实际点击落在设计坐标 ×0.75 处，主页「プロデュース」
  连点 60 步全落空（用户看得到光标点在错误位置）。

这里用假的 controller 断言：``click`` 必须把收到的 720x1280 设计坐标
**原样**交给 ``post_click``（不做任何缩放），且 ``click_force`` 走同一路径。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gkagent.device.win32 import Win32Device


class _Job:
    def wait(self) -> _Job:
        return self


class _FakeController:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def post_click(self, x: int, y: int) -> _Job:
        self.clicks.append((int(x), int(y)))
        return _Job()


def _device_with_fake_controller() -> tuple[Win32Device, _FakeController]:
    device = Win32Device(1)
    fake = _FakeController()
    device._ctrl = fake
    return device, fake


def test_click_passes_design_coords_unscaled() -> None:
    device, fake = _device_with_fake_controller()
    assert device.click(359, 1006, delay=0, respect_user=False) is True
    # 设计坐标必须原样透传：任何缩放（如 540/720=0.75 → 269,754）都是回归
    assert fake.clicks == [(359, 1006)]


def test_click_force_passes_design_coords_unscaled() -> None:
    device, fake = _device_with_fake_controller()
    assert device.click_force(360, 1090, delay=0) is True
    assert fake.clicks == [(360, 1090)]


def test_click_keeps_coords_when_window_is_small() -> None:
    """窗口被缩到更小（如 540x960）时，设备层也不能再乘一次比例。"""
    device, fake = _device_with_fake_controller()
    for point in ((0, 0), (719, 1279), (359, 1006), (360, 1090)):
        device.click(*point, delay=0, respect_user=False)
    assert fake.clicks == [(0, 0), (719, 1279), (359, 1006), (360, 1090)]
