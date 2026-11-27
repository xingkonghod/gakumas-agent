"""一次性探针③：dump 全部 StepAuditionStart（7 条）请求/响应顶层结构，
定位考试难度/回合配置字段，对比 ep-t31 与 11-20(REGULAR)/11-21(PRO) 场。不提交。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dig_traffic import decode, parse, show  # noqa: E402

TRAFFIC = Path(r"C:\GakumasLocal\GakumasUnlock\out\traffic.jsonl")


def main() -> int:
    recs = []
    for line in TRAFFIC.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    for i, r in enumerate(recs):
        if not r.get("path", "").endswith("StepAuditionStart"):
            continue
        print(f"\n{'='*70}\n#{i} {r.get('ts')}")
        for which, label in (("req_plain_hex", "请求"), ("resp_plain_hex", "响应")):
            body = decode(r, which)
            if body is None:
                print(f"  {label}: 无")
                continue
            print(f"  --- {label} {len(body)}B ---")
            show(parse(body), max_lines=45)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())