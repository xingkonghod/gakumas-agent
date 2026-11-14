import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202


def find_game() -> int:
    found = []

    def cb(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if "gakumas" in buf.value.lower() and user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return found[0] if found else 0


def click(hwnd: int, x: int, y: int) -> None:
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    cw, ch = rect.right, rect.bottom
    cx = round(x * cw / 720)
    cy = round(y * ch / 1280)
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    sx, sy = origin.x + cx, origin.y + cy
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    user32.SetCursorPos(sx, sy)
    time.sleep(0.05)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def main() -> None:
    hwnd = find_game()
    if not hwnd:
        raise SystemExit("no game window")
    args = [int(v) for v in sys.argv[1:]]
    pairs = list(zip(args[0::2], args[1::2]))
    for x, y in pairs:
        click(hwnd, x, y)
        time.sleep(1.5)
    print("clicked", pairs)


if __name__ == "__main__":
    main()
