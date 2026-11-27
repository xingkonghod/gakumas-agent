"""列出最近 N 分钟内活动的会话：用的模型、token、估算花费。"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CACHE = Path.home() / ".dsh" / "storages" / "session_projcache" / "sessions"
MINUTES = int(sys.argv[1]) if len(sys.argv) > 1 else 40
P = {"cache": 0.025, "input": 3.0, "output": 6.0}


def walk(obj, keys, out):
    if isinstance(obj, dict):
        if all(k in obj for k in keys):
            out.append({k: obj.get(k) for k in keys})
        for value in obj.values():
            walk(value, keys, out)
    elif isinstance(obj, list):
        for value in obj:
            walk(value, keys, out)


def main() -> int:
    cutoff = time.time() - MINUTES * 60
    rows = []
    for path in CACHE.glob("*.json"):
        mtime = path.stat().st_mtime
        if mtime < cutoff:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            continue
        totals = []
        walk(data, ("uncachedInputTokens", "outputTokens"), totals)
        models = []
        walk(data, ("model",), models)
        model_names = sorted({str(m.get("model")) for m in models if m.get("model")})
        best = max(totals, key=lambda b: b.get("outputTokens", 0)) if totals else {}
        u = int(best.get("uncachedInputTokens", 0))
        c = int(best.get("cacheReadTokens", 0))
        o = int(best.get("outputTokens", 0))
        cost = u / 1e6 * P["input"] + c / 1e6 * P["cache"] + o / 1e6 * P["output"]
        rows.append(
            {
                "file": path.stem,
                "when": datetime.fromtimestamp(mtime),
                "models": model_names[-3:],
                "u": u,
                "c": c,
                "o": o,
                "cost": cost,
            }
        )
    rows.sort(key=lambda r: r["when"], reverse=True)
    for r in rows:
        print(f"{r['when']:%H:%M:%S}  {r['file'][:8]}  models={r['models']}")
        print(f"   未缓存输入 {r['u']:,}  缓存读 {r['c']:,}  输出 {r['o']:,}  → {r['cost']:.2f} 元")
    if not rows:
        print(f"最近 {MINUTES} 分钟内没有会话活动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
