"""无人值守 supervisor：反复跑 auto_produce，处理卡死/最小化/体力不足，写监督日志。

用法（管理员）：
    python scripts/supervisor.py [max_episodes] [steps_per_batch]

停止：
- 按 F12
- 创建 data/STOP 文件
- 达到 max_episodes

日志：
- data/supervisor.log   人类可读
- data/metrics.jsonl    auto_produce 写入的每步指标
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
PY = r"D:\Games\MaaGakumasu\python\python.exe"
AUTO = str(ROOT / "scripts" / "auto_produce.py")
LOG = ROOT / "data" / "supervisor.log"
STOP = ROOT / "data" / "STOP"


def log(message: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def stop_requested() -> bool:
    return STOP.exists()


def game_window_state() -> str:
    """返回 up / minimized / missing。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = user32.FindWindowW("UnityWndClass", "gakumas")
    if not hwnd:
        return "missing"
    if user32.IsIconic(hwnd):
        return "minimized"
    return "up"


def ensure_window() -> bool:
    state = game_window_state()
    if state == "up":
        return True
    if state == "missing":
        log("game window missing; waiting 60s")
        time.sleep(60)
        return False
    log("game window minimized; restoring")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(ROOT / "scripts" / "force_show_game.ps1")],
        timeout=30,
        capture_output=True,
    )
    time.sleep(2)
    return game_window_state() == "up"


def run_batch(episode: str, steps: int, timeout_s: int = 2400) -> dict:
    started = time.time()
    # 先按初星课题开一局挑战培育（失败/不在主页时脚本自己退出，不影响后续）
    try:
        launcher = subprocess.run(
            [PY, str(ROOT / "scripts" / "challenge_launcher.py")],
            capture_output=True,
            timeout=180,
            cwd=str(ROOT),
        )
        launch_text = (launcher.stdout or b"").decode("utf-8", "replace").strip()
        if launch_text:
            log(f"{episode} challenge: {launch_text.splitlines()[-1][:120]}")
    except subprocess.TimeoutExpired:
        log(f"{episode} challenge launcher timeout")
    except Exception as exc:  # noqa: BLE001
        log(f"{episode} challenge launcher error: {exc!r}")
    try:
        proc = subprocess.run(
            [PY, AUTO, str(steps), episode],
            capture_output=True,
            timeout=timeout_s,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        log(f"{episode} batch timeout after {timeout_s}s")
        return {"steps": 0, "done": False, "timeout": True}
    text = (proc.stdout or b"").decode("utf-8", "replace")
    match = re.search(r"\{.*\}\s*$", text, re.S)
    payload: dict = {}
    if match:
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            payload = {}
    payload["elapsed_s"] = round(time.time() - started, 1)
    payload["code"] = proc.returncode
    stderr_text = (proc.stderr or b"").decode("utf-8", "replace").strip()
    if stderr_text:
        log(f"{episode} stderr: {stderr_text[-500:]}")
    if proc.returncode not in (0, 1):
        log(f"{episode} batch exit={proc.returncode}")
    return payload


def main() -> int:
    max_episodes = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    log(f"supervisor start max_episodes={max_episodes} steps={steps}")
    STOP.unlink(missing_ok=True)
    episode_no = 0
    consecutive_failures = 0

    while episode_no < max_episodes and not stop_requested():
        if not ensure_window():
            continue
        episode_no += 1
        episode = f"ep-{time.strftime('%Y%m%d-%H%M%S')}"
        log(f"episode {episode_no}/{max_episodes} start ({episode})")
        payload = run_batch(episode, steps)
        summary = {
            "episode": episode,
            "steps": payload.get("steps"),
            "done": payload.get("done"),
            "duration_s": payload.get("duration_s"),
            "avg_total_ms": payload.get("avg_total_ms"),
            "changed_rate": payload.get("changed_rate"),
            "elapsed_s": payload.get("elapsed_s"),
        }
        log("episode result " + json.dumps(summary, ensure_ascii=False))
        if payload.get("done"):
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                log("3 consecutive unfinished episodes; wait 10 min (stamina or stuck)")
                time.sleep(600)
                consecutive_failures = 0
        time.sleep(2)

    log(f"supervisor exit after {episode_no} episodes (stop={stop_requested()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
