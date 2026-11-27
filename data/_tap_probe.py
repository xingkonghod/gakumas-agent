# -*- coding: utf-8 -*-
"""一次性：实证开场二选一的确认机制——点橙色选项气泡中心，看画面是否推进。"""
import sys
import time
from gkagent.device.win32 import find_game_hwnd, Win32Device

x, y = int(sys.argv[1]), int(sys.argv[2])
hwnd = find_game_hwnd()
d = Win32Device(hwnd).connect()
d.click(x, y)
print(f"clicked ({x},{y})")
time.sleep(2.5)