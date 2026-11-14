"""常驻管理员 agent：一次 UAC，之后通过文件收命令，不再反复弹权限。

命令文件：D:\\Games\\gakumas-agent\\data\\agent_cmd.json
结果文件：D:\\Games\\gakumas-agent\\data\\agent_result.json
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
sys.path.insert(0, str(ROOT / "src"))

CMD = ROOT / "data" / "agent_cmd.json"
RES = ROOT / "data" / "agent_result.json"


def build_agent():
    from gkagent.agent import Agent
    from gkagent.device.win32 import Win32Device, find_game_hwnd
    from gkagent.vision.matcher import TemplateMatcher

    hwnd = find_game_hwnd()
    if not hwnd:
        raise RuntimeError("game window not found")
    device = Win32Device(hwnd).connect()
    return Agent(device, TemplateMatcher(ROOT / "templates"))


def ensure_agent(agent):
    """句柄变了（游戏重启）就重建，否则沿用缓存。"""
    from gkagent.device.win32 import find_game_hwnd

    hwnd = find_game_hwnd()
    old = getattr(getattr(agent, "device", None), "hwnd", None)
    if agent is None or not hwnd or old != hwnd:
        return build_agent()
    return agent


def build_produce(ocr: bool = True):
    from gkagent.policy.search import SearchPolicy
    from gkagent.runtime.replay import ReplayDB
    from gkagent.tasks.produce import ProduceTask
    from gkagent.vision.cards import scan_hand

    def _hand_reader(image):
        scan = scan_hand(image)
        return list(scan.cards), [tuple(card.box) for card in scan.cards]

    ocr_policy = None
    if ocr:
        from gkagent.data.cards_db import CardLibrary
        from gkagent.data.items_db import ItemLibrary
        from gkagent.policy.ocr_cards import OcrCardPolicy
        from gkagent.vision.ocr import OcrEngine

        ocr_policy = OcrCardPolicy(OcrEngine(), CardLibrary(), extra_libraries=[ItemLibrary()])

    replay = ReplayDB(
        str(ROOT / "data" / "replays" / "produce.sqlite3"),
        run_id=time.strftime("produce-%Y%m%d-%H%M%S"),
    )
    return ProduceTask(
        enable_lessons=True,
        hand_reader=_hand_reader,
        card_policy=SearchPolicy(),
        replay_db=replay,
        ocr_policy=ocr_policy,
    )


def main() -> None:
    agent = None
    while True:
        if not CMD.exists():
            time.sleep(0.2)
            continue
        try:
            cmd = json.loads(CMD.read_text(encoding="utf-8"))
        except Exception:
            CMD.unlink(missing_ok=True)
            continue
        CMD.unlink(missing_ok=True)
        action = cmd.get("action", "")
        result = {"ok": False}
        try:
            if action in ("click", "force", "home"):
                agent = ensure_agent(agent)
                if action == "click":
                    agent.device.click(int(cmd["x"]), int(cmd["y"]))
                elif action == "force":
                    agent.device.click_force(int(cmd["x"]), int(cmd["y"]))
                else:
                    agent.ensure_home()
                result = {"ok": True}
            elif action == "produce":
                agent = ensure_agent(agent)
                task = build_produce(ocr=bool(cmd.get("ocr", True)))
                from gkagent.tasks.produce import ProduceStage

                image = agent.shot()
                screen = task.observe(agent, image)
                stage = task.classify(screen)
                if stage in (ProduceStage.HOME, ProduceStage.UNKNOWN):
                    outcome = task.run(agent)
                else:
                    outcome = task.resume(agent)
                result = {"ok": outcome.ok, "message": outcome.message}
            elif action == "shell":
                import subprocess

                log = ROOT / "data" / "shell.log"
                with open(log, "w", encoding="utf-8") as handle:
                    proc = subprocess.run(
                        str(cmd.get("command", "")),
                        shell=True,
                        stdout=handle,
                        stderr=subprocess.STDOUT,
                        timeout=int(cmd.get("timeout", 120)),
                        cwd=str(ROOT),
                    )
                output = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
                result = {"ok": proc.returncode == 0, "code": proc.returncode, "log": output[-2000:]}
            elif action == "quit":
                RES.write_text(json.dumps({"ok": True, "message": "bye"}, ensure_ascii=False), encoding="utf-8")
                return
            else:
                result = {"ok": False, "error": f"unknown action {action}"}
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": repr(exc), "trace": traceback.format_exc()[-800:]}
        RES.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
