"""一次性探针：列 traffic 里 Produce/* 记录 + 解码 Produce/Start 与 Produce/Result 字段结构。

调查 ep-t31 C+ 疑问①：最终评价点 + produce 难度/类型（初pro/regular/pro）。不提交。
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
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
    print(f"总记录 {len(recs)}")
    paths = Counter(r.get("path", "") for r in recs)
    print("\n== Produce/* 与 Audition/* 路径计数 ==")
    for p, n in sorted(paths.items()):
        if "Produce" in p or "Audition" in p:
            print(f"  {n:4d}  {p}")

    print("\n== 2026-11-24 21:00 之后的 Produce/Start 与 Produce/Result ==")
    for i, r in enumerate(recs):
        p = r.get("path", "")
        ts = str(r.get("ts", ""))
        if ts >= "2026-11-24T21:" and (p.endswith("Produce/Start") or p.endswith("Produce/Result")):
            print(f"\n--- record#{i} {ts} {p} note={r.get('note','')} ---")
            for which, label in (("req_plain_hex", "请求"), ("resp_plain_hex", "响应")):
                body = decode(r, which)
                if body is None:
                    print(f"  {label}: 无")
                    continue
                print(f"  --- {label} {len(body)}B ---")
                show(parse(body), max_lines=120)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())