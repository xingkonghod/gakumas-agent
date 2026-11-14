import ctypes
from ctypes import wintypes

from PIL import ImageGrab

user32 = ctypes.WinDLL("user32", use_last_error=True)


def find(title_sub: str):
    found = []

    def cb(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if title_sub.lower() in buf.value.lower() and user32.IsWindowVisible(hwnd):
            found.append((int(hwnd), buf.value))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found


cands = find("マイゲーム") or find("DMM")
print("windows:", cands)
if not cands:
    raise SystemExit("no DMM window")
hwnd, title = cands[0]
user32.ShowWindow(hwnd, 9)
user32.SetForegroundWindow(hwnd)
rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
print("rect", rect.left, rect.top, rect.right, rect.bottom)
img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
img.save(r"D:\Games\gakumas-agent\data\dmm.png")
print("saved", img.size)
