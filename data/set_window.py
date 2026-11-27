import ctypes, sys
from ctypes import wintypes
sys.path.insert(0, r"D:\Games\gakumas-agent\src")
from gkagent.device.win32 import find_game_hwnd
user32 = ctypes.windll.user32
hwnd = find_game_hwnd()
W, H, X, Y = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
r = wintypes.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r))
c = wintypes.RECT(); user32.GetClientRect(hwnd, ctypes.byref(c))
dw = (r.right - r.left) - c.right
dh = (r.bottom - r.top) - c.bottom
user32.SetWindowPos(hwnd, 0, X, Y, W + dw, H + dh, 0x0004 | 0x0010)
import time; time.sleep(0.4)
c2 = wintypes.RECT(); user32.GetClientRect(hwnd, ctypes.byref(c2))
r2 = wintypes.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r2))
print(f"client {c2.right}x{c2.bottom} pos ({r2.left},{r2.top})")
