"""抓取初星攻略站（gkbench）公开数据，落成本地知识库。

数据源（全部公开只读）：
- /api/catalog?lang=zh  技能卡目录（中文名/稀有度/方案/类别/费用/数值）
- /api/usage/hif        排行榜前 100 名的卡片使用率（"主流配装"）
- /api/leaderboard      算法排行（greedy / PIMC / UINet / 官方 AI 的分数基线）

用法：python scripts/bench_ingest.py [--base https://hiro.matto.top/gkbench]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
OUT_DIR = ROOT / "data" / "knowledge" / "bench"


def fetch(url: str, timeout: float = 30.0) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "gakumas-agent/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - 固定 https 白名单域名
        payload = resp.read()
    return json.loads(payload.decode("utf-8"))


def ingest(base: str) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    catalog = fetch(f"{base}/api/catalog?lang=zh")
    cards = catalog.get("cards") or {}
    drinks = catalog.get("drinks") or {}
    items = catalog.get("items") or {}
    (OUT_DIR / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    report["catalog"] = {"cards": len(cards), "drinks": len(drinks), "items": len(items)}

    usage = fetch(f"{base}/api/usage/hif")
    (OUT_DIR / "usage_hif.json").write_text(json.dumps(usage, ensure_ascii=False), encoding="utf-8")
    report["usage"] = {"format": usage.get("format")}

    board = fetch(f"{base}/api/leaderboard?set=hif-live&kind=fixed")
    rows = [
        {
            "family": row.get("family") or row.get("algo"),
            "label": row.get("label"),
            "mean": row.get("mean"),
            "vs_oracle": (row.get("vs_oracle") or {}).get("geo"),
            "p50_ms": row.get("p50_ms"),
            "sees": (row.get("about") or {}).get("sees"),
        }
        for row in board
        if row.get("mean")
    ]
    rows.sort(key=lambda r: r["mean"], reverse=True)
    (OUT_DIR / "leaderboard.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    report["leaderboard"] = rows[:8]
    return report


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://hiro.matto.top/gkbench")
    args = parser.parse_args(argv)
    report = ingest(args.base)
    print(json.dumps(report, ensure_ascii=False, indent=1)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
