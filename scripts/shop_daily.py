"""每日兑换所按需购买：把当天能买的道具（每日限购）全部买下。

用法：``python scripts/shop_daily.py``（在游戏处于主页或商店内都可以，会先回主页）
规则：只花金币/AP 类货币；出现「付费/钻石/购买」字样立即取消退出（安全约束）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# 每日兑换所 4 列 x 3 行 的道具格子中心
SLOTS = [
    (95, 417),
    (270, 417),
    (430, 417),
    (610, 417),
    (95, 740),
    (270, 740),
    (430, 740),
    (610, 740),
    (95, 945),
    (270, 945),
    (430, 945),
    (610, 945),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from gkagent.agent import Agent
    from gkagent.device.win32 import Win32Device, find_game_hwnd
    from gkagent.nav import Navigator
    from gkagent.vision.matcher import TemplateMatcher
    from gkagent.vision.ocr import OcrEngine

    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window", file=sys.stderr)
        return 2
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    engine = OcrEngine()
    nav = Navigator(agent, engine)
    nav.ensure_home()

    # 主页 → 商店 → 每日兑换所
    agent.device.click(634, 993)
    time.sleep(2.5)
    agent.device.click(226, 948)
    time.sleep(2.5)
    text = " ".join(line.text for line in nav.lines())
    if "每日兑换所" not in text:
        print("no daily exchange screen:", text[:120])
        return 1

    bought = 0
    for slot in SLOTS:
        agent.device.click(*slot)
        time.sleep(1.6)
        lines = nav.lines()
        text = " ".join(line.text for line in lines)
        if "付费" in text or "钻石" in text or "购买" in text:
            # 安全：付费类不碰
            for line in lines:
                if line.text.strip() == "取消":
                    agent.device.click(line.box[0] + line.box[2] // 2, line.box[1] + line.box[3] // 2)
                    break
            print(f"skip paid slot {slot}")
            time.sleep(1.2)
            continue
        if "兑换确认" in text:
            confirm = next((line for line in lines if line.text.strip() == "确定"), None)
            if confirm is not None:
                agent.device.click(
                    confirm.box[0] + confirm.box[2] // 2, confirm.box[1] + confirm.box[3] // 2
                )
                bought += 1
                print(f"bought slot {slot}")
                time.sleep(1.6)
                continue
        # 没弹窗（已售罄/不可买）：关掉可能的详情页
        close = next((line for line in lines if line.text.strip() in ("关闭", "取消")), None)
        if close is not None and "兑换确认" not in text:
            agent.device.click(close.box[0] + close.box[2] // 2, close.box[1] + close.box[3] // 2)
            time.sleep(1.0)
    print(f"done, bought={bought}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
