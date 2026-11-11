"""给常驻 daemon 发命令（非管理员即可运行）。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
CMD = ROOT / "data" / "agent_cmd.json"
RES = ROOT / "data" / "agent_result.json"


def send(payload: dict, timeout: float = 120.0) -> dict:
    RES.unlink(missing_ok=True)
    CMD.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if RES.exists():
            try:
                return json.loads(RES.read_text(encoding="utf-8"))
            except Exception:
                pass
        time.sleep(0.2)
    return {"ok": False, "error": "timeout waiting for daemon"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("click")
    c.add_argument("--x", type=int, required=True)
    c.add_argument("--y", type=int, required=True)
    c.add_argument("--force", action="store_true")
    sub.add_parser("home")
    p = sub.add_parser("produce")
    p.add_argument("--no-ocr", action="store_true")
    s = sub.add_parser("shell")
    s.add_argument("--command", required=True)
    s.add_argument("--timeout", type=int, default=120)
    sub.add_parser("quit")
    args = ap.parse_args()

    if args.cmd == "click":
        payload = {"action": "force" if args.force else "click", "x": args.x, "y": args.y}
    elif args.cmd == "home":
        payload = {"action": "home"}
    elif args.cmd == "produce":
        payload = {"action": "produce", "ocr": not args.no_ocr}
    elif args.cmd == "shell":
        payload = {"action": "shell", "command": args.command, "timeout": args.timeout}
    else:
        payload = {"action": "quit"}
    if args.cmd == "produce":
        wait = 600
    elif args.cmd == "shell":
        wait = args.timeout + 30
    else:
        wait = 60
    result = send(payload, timeout=wait)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
