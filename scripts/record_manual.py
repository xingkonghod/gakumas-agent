"""手动游玩记录器：只截图 + OCR 三维 + 落盘，不点击、不干预。

用户自己打，这个脚本每 N 秒：
1. 截一张游戏画面 → ``data/manual/<时间戳>.png``
2. 读三维（ProduceDriver.read_attrs 专用 ROI）→ 追加 ``data/attribute_log.jsonl``（tag=manual）
3. 记录屏幕类型粗判（lesson/action/result/other）→ ``data/manual/session.jsonl``

用法：
    python scripts/record_manual.py --seconds 1800 --interval 15
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

OUT_DIR = ROOT / "data" / "manual"
SESSION = OUT_DIR / "session.jsonl"


def screen_kind(text: str) -> str:
    if "剩余回合" in text or "CLEAR" in text:
        return "lesson"
    if "请选择行动" in text or "重点练习" in text:
        return "action"
    if any(word in text for word in ("评价", "审查", "名次", "合格", "不合格")):
        return "exam"
    if any(word in text for word in ("培育结束", "回忆", "保存到")):
        return "result"
    return "other"


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=1800)
    parser.add_argument("--interval", type=int, default=15)
    args = parser.parse_args(argv)

    import cv2

    from gkagent.data.calibration import record
    from gkagent.device.win32 import Win32Device, find_game_hwnd
    from gkagent.tasks.produce_ui import ProduceDriver

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    driver = ProduceDriver(ocr=None)
    started = time.time()
    count = 0
    last_attrs = None

    while time.time() - started < args.seconds:
        hwnd = find_game_hwnd()
        if not hwnd:
            print("[record] 找不到游戏窗口，等 5s")
            time.sleep(5)
            continue
        try:
            device = Win32Device(hwnd).connect()
            image = device.capture()
        except Exception as exc:  # noqa: BLE001 - 记录失败不影响用户操作
            print(f"[record] 截图失败: {exc}")
            time.sleep(args.interval)
            continue

        stamp = time.strftime("%H%M%S")
        path = OUT_DIR / f"{stamp}.png"
        cv2.imwrite(str(path), image)

        attrs = None
        try:
            attrs = driver.read_attrs(image)
        except Exception:  # noqa: BLE001
            attrs = None
        text = ""
        try:
            text = driver.text_of(driver.engine().read(image))
        except Exception:  # noqa: BLE001
            text = ""
        kind = screen_kind(text)

        if attrs and attrs != last_attrs:
            record(list(attrs), tag="manual")
            last_attrs = attrs

        row = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_s": round(time.time() - started, 1),
            "screen": kind,
            "attrs": attrs,
            "shot": str(path.name),
            "text_head": text[:80].replace("\n", " "),
        }
        with SESSION.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        count += 1
        if count % 4 == 0:
            print(f"[record] {count} 帧 | 屏幕={kind} | 三维={attrs}")

        time.sleep(args.interval)

    print(f"[record] 结束，共 {count} 帧，记录在 {SESSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
