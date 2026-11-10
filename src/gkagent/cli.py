"""命令行：capture / find / home / task。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _templates(args) -> Path:
    return Path(args.templates).resolve()


def cmd_find(args) -> int:
    from gkagent.vision.matcher import TemplateMatcher

    img = cv2.imread(args.image)
    if img is None:
        print(f"cannot read image: {args.image}", file=sys.stderr)
        return 2
    matcher = TemplateMatcher(_templates(args))
    roi = tuple(int(v) for v in args.roi.split(",")) if args.roi else None
    m = matcher.find(args.template, img, roi=roi, threshold=args.threshold)
    if m is None:
        _print({"found": False, "template": args.template})
        return 1
    _print({"found": True, "template": m.name, "box": m.box, "center": m.center, "score": round(m.score, 4)})
    return 0


def _agent(args):
    from gkagent.agent import build_agent

    return build_agent(templates_dir=_templates(args), hwnd=args.hwnd)


def cmd_capture(args) -> int:
    agent = _agent(args)
    img = agent.shot()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(args.out, img)
    _print({"saved": args.out, "shape": list(img.shape)})
    return 0


def cmd_home(args) -> int:
    agent = _agent(args)
    ok = agent.ensure_home()
    _print({"ok": ok})
    return 0 if ok else 1


def cmd_click(args) -> int:
    agent = _agent(args)
    if getattr(args, "force", False):
        agent.device.click_force(args.x, args.y)
    else:
        agent.device.click(args.x, args.y)
    _print({"clicked": [args.x, args.y], "force": bool(getattr(args, "force", False))})
    return 0


def cmd_task(args) -> int:
    from gkagent.tasks import (
        ActivityFeeTask,
        ChallengeTask,
        DailyTask,
        ProduceTask,
        SocietyTask,
        WorkTask,
    )

    agent = _agent(args)
    tasks = {
        "activity_fee": ActivityFeeTask,
        "challenge": ChallengeTask,
        "daily": DailyTask,
        "produce": ProduceTask,
        "society": SocietyTask,
        "work": WorkTask,
    }
    task = tasks[args.name]()
    if args.name == "produce":
        from gkagent.policy.search import SearchPolicy
        from gkagent.runtime.replay import ReplayDB
        from gkagent.vision.cards import scan_hand

        def _hand_reader(image):
            scan = scan_hand(image)
            return list(scan.cards), [tuple(card.box) for card in scan.cards]

        replay = ReplayDB(
            r"D:\Games\gakumas-agent\data\replays\produce.sqlite3",
            run_id=time.strftime("produce-%Y%m%d-%H%M%S"),
        )
        task = ProduceTask(
            enable_lessons=True,
            hand_reader=_hand_reader,
            card_policy=SearchPolicy(),
            replay_db=replay,
        )
    if getattr(args, "resume", False) and hasattr(task, "resume"):
        result = task.resume(agent)
    else:
        result = task.run(agent)
    _print({"task": task.name, "ok": result.ok, "message": result.message})
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gkagent")
    parser.add_argument("--templates", default="templates", help="template directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("capture", help="capture the game window")
    p.add_argument("--out", default="shot.png")
    p.add_argument("--hwnd", type=int, default=None)
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("find", help="offline template match on an image")
    p.add_argument("--image", required=True)
    p.add_argument("--template", required=True)
    p.add_argument("--roi", default=None, help="x,y,w,h")
    p.add_argument("--threshold", type=float, default=0.85)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("home", help="ensure the game is on the home screen")
    p.add_argument("--hwnd", type=int, default=None)
    p.set_defaults(func=cmd_home)

    p = sub.add_parser("click", help="click in the game window")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)
    p.add_argument("--hwnd", type=int, default=None)
    p.add_argument("--force", action="store_true", help="physical click fallback")
    p.set_defaults(func=cmd_click)

    p = sub.add_parser("task", help="run a task")
    p.add_argument(
        "name",
        choices=["activity_fee", "work", "challenge", "society", "daily", "produce"],
    )
    p.add_argument("--hwnd", type=int, default=None)
    p.add_argument("--resume", action="store_true", help="continue current produce")
    p.set_defaults(func=cmd_task)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
