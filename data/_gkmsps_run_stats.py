"""gkmsps pilot 托管运行统计 glue（我们的代码，探针不提交）：GET /api/runs/<run> 拉均分/errors/over_steps。

令牌读 ~/.config/gkbench/token（gkbench.client 同口径），**不打印令牌**。
用法：.venv\\Scripts\\python.exe -B data\\_gkmsps_run_stats.py <RUN_ID> [--set hif]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--set", default="hif")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    from gkbench.client import _client
    with _client() as c:
        r = c.get(f"/api/runs/{a.run}")
        r.raise_for_status()
        doc = r.json()
    # 只打印统计相关字段，避免巨大逐局列表刷屏
    slim = {k: v for k, v in doc.items() if not isinstance(v, (list, dict))}
    eps = doc.get("episodes") or doc.get("rows") or []
    if isinstance(eps, list) and eps:
        scores = [e.get("score") or (e.get("final") or {}).get("score") for e in eps if isinstance(e, dict)]
        scores = [s for s in scores if isinstance(s, (int, float))]
        if scores:
            slim["episodes_n"] = len(scores)
            slim["mean_score"] = sum(scores) / len(scores)
    for k in ("errors", "over_steps", "unfinished", "n", "mean", "algo", "label", "rules", "mode", "kind"):
        if k in doc and k not in slim:
            slim[k] = doc[k]
    print(json.dumps(slim, ensure_ascii=False, indent=1))
    print("TOP-LEVEL KEYS:", sorted(doc.keys()))
    if a.out:
        a.out.resolve().write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
