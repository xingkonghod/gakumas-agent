"""按正则抓每个会话最后一个 totals（JSON 是美化格式，要容忍换行）。"""

from __future__ import annotations

import datetime
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CACHE = Path.home() / ".dsh" / "storages" / "session_projcache" / "sessions"
DS = {"cache": 0.025, "input": 3.0, "output": 6.0}
QW = {"cache": 0.5, "input": 10.0, "output": 30.0}

PAT = re.compile(
    r'"seq":\s*(\d+),\s*"val":\s*\{\s*"totals":\s*\{\s*'
    r'"uncachedInputTokens":\s*(\d+),\s*"outputTokens":\s*(\d+),\s*'
    r'"cacheReadTokens":\s*(\d+),\s*"cacheWriteTokens":\s*(\d+)'
)


def main() -> int:
    rows = []
    for path in CACHE.glob("*.json"):
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = PAT.findall(text)
        if not hits:
            continue
        _, u, o, c, _cw = max(hits, key=lambda h: int(h[0]))
        u, o, c = int(u), int(o), int(c)
        model = "qwen4-max" if "qwen4-max" in text else ("deepseek" if "deepseek" in text else "?")

        def cost(price, u=u, o=o, c=c):
            return u / 1e6 * price["input"] + c / 1e6 * price["cache"] + o / 1e6 * price["output"]

        rows.append(
            {
                "when": datetime.datetime.fromtimestamp(path.stat().st_mtime),
                "model": model,
                "u": u,
                "c": c,
                "o": o,
                "ds": cost(DS),
                "qw": cost(QW),
            }
        )

    rows.sort(key=lambda r: r["when"])
    print(f"{'时间':16}{'模型':11}{'未缓存输入':>13}{'缓存读':>15}{'输出':>11}{'DS元':>8}{'QW元':>8}")
    for r in rows[-14:]:
        print(
            f"{r['when']:%m-%d %H:%M:%S}  {r['model']:10}{r['u']:>13,}{r['c']:>15,}"
            f"{r['o']:>11,}{r['ds']:>8.2f}{r['qw']:>8.2f}"
        )

    print("\n=== 合计 ===")
    for label, price in (("DeepSeek 价", DS), ("Qwen4-Max 价", QW)):
        total = sum(
            r["u"] / 1e6 * price["input"]
            + r["c"] / 1e6 * price["cache"]
            + r["o"] / 1e6 * price["output"]
            for r in rows
        )
        print(f"{label}: {total:.2f} 元")
    tu = sum(r["u"] for r in rows)
    tc = sum(r["c"] for r in rows)
    to = sum(r["o"] for r in rows)
    print(f"token: 未缓存 {tu:,} / 缓存读 {tc:,} / 输出 {to:,}")
    print(f"缓存命中率: {tc / max(1, tc + tu) * 100:.2f}%")

    daily = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        day = r["when"].strftime("%m-%d")
        daily[day][0] += r["ds"]
        daily[day][1] += r["qw"]
    print("\n=== 按天（DS / QW）===")
    for day in sorted(daily):
        ds, qw = daily[day]
        print(f"{day}  {ds:8.2f}  {qw:9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
