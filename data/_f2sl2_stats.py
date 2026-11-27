"""f2-sl2：从服务器拉 hif 评测全部 episode（含逐步 algo_meta），统计锁定率/硬规矩/错误/超时。不提交。"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUN = sys.argv[1] if len(sys.argv) > 1 else "template-hif-gkagent-seedlock-xingkonghod-c060df94acad"
OUT = ROOT / "data" / ("_f2sl2_hif_stats.json" if "hif" in RUN else "_f2sl2_hajime_stats.json")

c = httpx.Client(base_url="https://hiro.matto.top/gkbench", timeout=120)
j = c.get(f"/api/runs/{RUN}").raise_for_status().json()
eps = j["episodes"]
print(f"run {RUN}: {len(eps)} episodes, mean {j.get('mean_score')}", flush=True)

rows = []
for i, e in enumerate(eps):
    d = c.get(f"/api/runs/{RUN}/episodes/{e['id']}/{e['seed_index']}").raise_for_status().json()
    steps = d.get("steps") or []
    metas = [s.get("algo_meta") or {} for s in steps]
    last = metas[-1] if metas else {}
    state = last.get("seed")
    lock_turn = next((m.get("lock_turn") for m in metas if m.get("lock_turn") is not None), None)
    hard = sum(1 for m in metas if m.get("hard_rule"))
    errs = sum(1 for m in metas if m.get("error"))
    modes = Counter(m.get("mode") for m in metas)
    ms = [s.get("step_ms") or 0 for s in steps]
    rows.append({"id": e["id"], "seed_index": e["seed_index"], "score": e["score"],
                 "finished": e.get("finished"), "state": state, "lock_turn": lock_turn,
                 "hard_rule": hard, "meta_errors": errs, "modes": dict(modes),
                 "over": e.get("over_steps", 0), "max_ms": max(ms) if ms else 0,
                 "decisions": e.get("decisions"), "why": last.get("why")})
    if (i + 1) % 60 == 0:
        print(f"  fetched {i + 1}/{len(eps)}", flush=True)

n = len(rows)
locked = [r for r in rows if r["state"] == "locked"]
lost = [r for r in rows if r["state"] == "lost"]
failed = [r for r in rows if r["state"] == "failed"]
other = [r for r in rows if r["state"] not in ("locked", "lost", "failed")]
mean = lambda rs: round(sum(r["score"] for r in rs) / len(rs)) if rs else None  # noqa: E731
out = {
    "run": RUN, "n": n, "mean_score": j.get("mean_score"),
    "locked": len(locked), "lost": len(lost), "failed": len(failed), "other": len(other),
    "lock_rate": len(locked) / n if n else None,
    "mean_locked": mean(locked), "mean_lost": mean(lost), "mean_failed": mean(failed),
    "lock_turn_dist": dict(sorted(Counter(r["lock_turn"] for r in locked).items())),
    "hard_rule_total": sum(r["hard_rule"] for r in rows),
    "hard_rule_games": sum(1 for r in rows if r["hard_rule"]),
    "meta_errors_total": sum(r["meta_errors"] for r in rows),
    "over_steps_total": sum(r["over"] for r in rows),
    "unfinished": sum(1 for r in rows if not r["finished"]),
    "failed_rows": [{k: r[k] for k in ("id", "seed_index", "score", "state", "why", "decisions")} for r in lost + failed + other],
    "rows": rows,
}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: out[k] for k in ("n", "mean_score", "locked", "lost", "failed", "other", "lock_rate",
                                      "mean_locked", "mean_failed", "lock_turn_dist", "hard_rule_total",
                                      "meta_errors_total", "over_steps_total", "unfinished")}, ensure_ascii=False), flush=True)
print("failed/lost rows:", json.dumps(out["failed_rows"], ensure_ascii=False)[:1500], flush=True)
print("written", OUT, flush=True)