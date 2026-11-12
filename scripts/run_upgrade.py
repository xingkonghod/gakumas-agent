"""手动跑一次支援卡 / 偶像强化（用于验证流程）。

用法：
    python scripts/run_upgrade.py support 1 --dry
    python scripts/run_upgrade.py idol 1 --dry
    python scripts/run_upgrade.py support 2        # 真强化（会消耗素材）
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from gkagent.agent import Agent
    from gkagent.device.win32 import find_game_hwnd
    from gkagent.device.win32 import Win32Device
    from gkagent.tasks.upgrade import UpgradeTask
    from gkagent.vision.matcher import TemplateMatcher

    kind = sys.argv[1] if len(sys.argv) > 1 else "support"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    dry = "--dry" in sys.argv
    hwnd = find_game_hwnd()
    if not hwnd:
        print("no game window", file=sys.stderr)
        return 2
    agent = Agent(Win32Device(hwnd).connect(), TemplateMatcher(ROOT / "templates"))
    agent.ensure_home()
    task = UpgradeTask(kind=kind, limit=limit, dry_run=dry)
    result = task.run(agent)
    print(f"ok={result.ok} message={result.message}")
    agent.ensure_home()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
