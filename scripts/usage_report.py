"""汇总 DSH 各会话的 token 用量，按 DeepSeek 价格估算花费。"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CACHE = Path.home() / ".dsh" / "storages" / "session_projcache" / "sessions"

# DeepSeek v4-pro 永久 2.5 折价格（元/百万 token）
PRICE = {"cache": 0.025, "input": 3.0, "output": 6.0}


def find_totals(obj, out=None):
    """递归找所有 totals 块。"""
    if out is None:
        out = []
    if isinstance(obj, dict):
        if "uncachedInputTokens" in obj and "outputTokens" in obj:
            out.append(obj)
        for v in obj.values():
            find_totals(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_totals(v, out)
    return out


def main() -> int:
    rows = []
    for path in CACHE.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        blocks = find_totals(data)
        if not blocks:
            continue
        # 取最大的那组（通常是会话累计）
        best = max(blocks, key=lambda b: b.get("outputTokens", 0))
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        rows.append(
            {
                "file": path.stem[:8],
                "mtime": mtime,
                "uncached": int(best.get("uncachedInputTokens", 0)),
                "cache_read": int(best.get("cacheReadTokens", 0)),
                "cache_write": int(best.get("cacheWriteTokens", 0)),
                "output": int(best.get("outputTokens", 0)),
            }
        )

    rows.sort(key=lambda r: r["mtime"])
    print(f"{'会话':10s} {'最后活动':16s} {'未缓存输入':>12s} {'缓存读':>12s} {'输出':>10s} {'估算元':>8s}")
    total_cost = 0.0
    tot = {"uncached": 0, "cache_read": 0, "output": 0}
    for r in rows:
        cost = (
            r["uncached"] / 1e6 * PRICE["input"]
            + r["cache_read"] / 1e6 * PRICE["cache"]
            + r["output"] / 1e6 * PRICE["output"]
        )
        total_cost += cost
        for k in tot:
            tot[k] += r[k]
        print(
            f"{r['file']:10s} {r['mtime']:%m-%d %H:%M}   "
            f"{r['uncached']:12,d} {r['cache_read']:12,d} {r['output']:10,d} {cost:8.2f}"
        )

    print("-" * 76)
    print(
        f"{'合计':10s} {'':16s} {tot['uncached']:12,d} {tot['cache_read']:12,d} "
        f"{tot['output']:10,d} {total_cost:8.2f}"
    )
    total_tokens = tot["uncached"] + tot["cache_read"] + tot["output"]
    print(f"\n总 token: {total_tokens:,}  缓存命中率: "
          f"{tot['cache_read'] / max(1, tot['cache_read'] + tot['uncached']) * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
