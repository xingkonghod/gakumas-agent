"""按天汇总 DSH token 用量与估算花费。"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CACHE = Path.home() / ".dsh" / "storages" / "session_projcache" / "sessions"
P = {"cache": 0.025, "input": 3.0, "output": 6.0}


def find_totals(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        if "uncachedInputTokens" in obj and "outputTokens" in obj:
            out.append(obj)
        for value in obj.values():
            find_totals(value, out)
    elif isinstance(obj, list):
        for value in obj:
            find_totals(value, out)
    return out


def main() -> int:
    daily = defaultdict(lambda: {"u": 0, "c": 0, "o": 0, "cost": 0.0, "n": 0})
    for path in CACHE.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        blocks = find_totals(data)
        if not blocks:
            continue
        best = max(blocks, key=lambda b: b.get("outputTokens", 0))
        day = datetime.fromtimestamp(path.stat().st_mtime).strftime("%m-%d")
        u = int(best.get("uncachedInputTokens", 0))
        c = int(best.get("cacheReadTokens", 0))
        o = int(best.get("outputTokens", 0))
        bucket = daily[day]
        bucket["u"] += u
        bucket["c"] += c
        bucket["o"] += o
        bucket["n"] += 1
        bucket["cost"] += u / 1e6 * P["input"] + c / 1e6 * P["cache"] + o / 1e6 * P["output"]

    print(f"{'日期':<7}{'会话':>4}{'未缓存输入':>15}{'缓存读':>17}{'输出':>12}{'估算元':>9}")
    total = 0.0
    for day in sorted(daily):
        r = daily[day]
        total += r["cost"]
        print(f"{day:<7}{r['n']:>4}{r['u']:>15,}{r['c']:>17,}{r['o']:>12,}{r['cost']:>9.2f}")
    print("-" * 66)
    print(f"{'合计':<7}{'':>4}{'':>15}{'':>17}{'':>12}{total:>9.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
