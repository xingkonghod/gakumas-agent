"""真机起跑前一键自检（只读，不改游戏/不杀进程）。2026-11-26 转向真机路线新增。

承 docs/LIVE_RUN.md §0.1 清单 1-7：单进程/急停标记/daemon/窗口/接线/提权/游戏在跑。
输出 READY 或 BLOCKED+原因清单；exit 0=READY，2=BLOCKED。任何一项失败都不起跑。
用法：.venv\\Scripts\\python.exe scripts\\live_preflight.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

checks: list[dict] = []


def add(name: str, ok: bool, detail: str) -> None:
    checks.append({"check": name, "ok": bool(ok), "detail": detail})


def run(argv: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:  # pragma: no cover
        return 125, repr(e)


# 1. 游戏客户端在跑（真机前提；用户不在机前时通常 BLOCKED）
rc, out = run(["powershell", "-NoProfile", "-Command",
               "Get-Process gakumas,DMMGamePlayer -ErrorAction SilentlyContinue | "
               "Select-Object -ExpandProperty Id"])
game_ids = [x for x in out.split() if x.strip().isdigit()]
add("game-running", bool(game_ids), f"pids={game_ids or 'none'}")

# 2. 没有别的 auto_produce 在跑（一局一进程，F 双进程互抢教训）
rc, out = run(["powershell", "-NoProfile", "-Command",
               "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
               "Where-Object { $_.CommandLine -like '*auto_produce*' } | "
               "Select-Object -ExpandProperty ProcessId"])
others = [x for x in out.split() if x.strip().isdigit()]
add("single-process", not others, f"other auto_produce pids={others or 'none'}")

# 3. 急停标记已清
add("stop-flag-clear", not (ROOT / "data" / "STOP").exists(), "data/STOP absent" )

# 4. daemon  scheduled task 状态
rc, out = run(["powershell", "-NoProfile", "-Command",
               "(Get-ScheduledTask -TaskName GDEAgent -ErrorAction SilentlyContinue).State"])
add("daemon-task", "Running" in out, out.strip() or "task missing")

# 5. 配置接线 + 游戏窗口一次过（check_wiring --live）
rc, out = run([str(PY), str(ROOT / "scripts" / "check_wiring.py"), "--live"], timeout=90)
add("wiring-live", rc == 0, out.strip().splitlines()[-1] if out.strip() else f"rc={rc}")

# 6. 截帧正常（窗口尺寸/非黑屏）；游戏没跑时此项随 game-running 一起 BLOCKED
rc, out = run([str(PY), str(ROOT / "scripts" / "cap_game.py")], timeout=60)
add("capture", rc == 0 and "captured" in out, out.strip().splitlines()[-1] if out.strip() else f"rc={rc}")

# 7. 提权一致提示（C1）：本进程是否管理员；游戏若管理员而本进程非管理员=UIPI 丢点击
rc, out = run(["powershell", "-NoProfile", "-Command",
               "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::"
               "GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"])
elev = "True" in out
add("terminal-elevated", elev, f"admin={elev}（游戏以管理员跑时终端必须管理员，否则 UIPI 静默丢点击）")

blocked = [c for c in checks if not c["ok"]]
print(json.dumps({"ready": not blocked, "checks": checks}, ensure_ascii=False, indent=1))
if blocked:
    print("BLOCKED: " + "; ".join(c["check"] for c in blocked))
    print("按 docs/LIVE_RUN.md §0 开游戏/重启 daemon/换管理员终端后重跑本自检。")
    sys.exit(2)
print("READY: 可按 LIVE_RUN §1 起一局（auto_produce.py 300 <ep> --engine expectimax）。")