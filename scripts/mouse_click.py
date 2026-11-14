import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"D:\Games\gakumas-agent\src")

from gkagent.device.win32 import find_game_hwnd

user32 = ctypes.WinDLL("user32", use_last_error=True)

hwnd = find_game_hwnd()
if not hwnd:
    raise SystemExit("game window not found")

rect = wintypes.RECT()
user32.GetClientRect(hwnd, ctypes.byref(rect))
cw, ch = rect.right, rect.bottom

origin = wintypes.POINT(0, 0)
user32.ClientToScreen(hwnd, ctypes.byref(origin))

x = int(sys.argv[1])
y = int(sys.argv[2])
sx = origin.x + int(x * cw / 720)
sy = origin.y + int(y * ch / 1280)

user32.SetCursorPos(sx, sy)
time.sleep(0.15)
user32.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.05)
user32.mouse_event(0x0004, 0, 0, 0, 0)
print(f"mouse click client=({x},{y}) screen=({sx},{sy}) client_size={cw}x{ch} origin=({origin.x},{origin.y})")
