import ctypes, sys, time
sys.path.insert(0, r"D:\Games\gakumas-agent\src")
from gkagent.device.win32 import find_game_hwnd
u = ctypes.windll.user32
hwnd = find_game_hwnd()
print("hwnd", hwnd, "iconic", bool(u.IsIconic(hwnd)))
u.ShowWindow(hwnd, 9)   # SW_RESTORE
time.sleep(0.5)
u.SetForegroundWindow(hwnd)
time.sleep(0.5)
from ctypes import wintypes
r = wintypes.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r))
c = wintypes.RECT(); u.GetClientRect(hwnd, ctypes.byref(c))
print(f"restored: client {c.right}x{c.bottom} pos ({r.left},{r.top}) iconic={bool(u.IsIconic(hwnd))}")
