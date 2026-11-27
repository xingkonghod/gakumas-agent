# -*- coding: utf-8 -*-
"""一次性：点标题 TAP TO START（设计坐标 360,1035）。"""
from gkagent.device.win32 import find_game_hwnd, Win32Device

hwnd = find_game_hwnd()
print("hwnd:", hwnd)
d = Win32Device(hwnd).connect()
d.click(360, 1035)
print("tapped title")