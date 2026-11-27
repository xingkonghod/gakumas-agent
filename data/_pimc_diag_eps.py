"""pimc-opt 探针③：240 局逐局 over 分布 + 平均步时相关性 + evals 列表。只读。"""
from __future__ import annotations
import json, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path
import httpx

ROOT = Path(r"D:\Games\gakumas-agent")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERVER = "https://hiro.matto.top/gkbench"
TOK = (Path.home() / ".config/gkbench/token").read_text().strip()
C = httpx.Client(base_url=SERVER, headers={"Authorization": f"Bearer {TOK}"}, timeout=120)

try:
    evs = C.get("/api/evals").json()
    print("evals type:", type(evs).__name__, "len:", len(evs) if hasattr(evs, "__len__") else "?")
    if isinstance(evs, list):
        for e in evs[:40]:
            print("EV:", json.dumps(e, ensure_ascii=False)[:300])
    else:
        print(json.dumps(evs, ensure_ascii=False)[:800])
except Exception as ex:
    print("evals err:", ex)

j = C.get("/api/runs/template-hif-gkagent-expectimax-xingkonghod-3671171720ab").json()
print("summary:", json.dumps(j.get("summary"), ensure_ascii=False)[:500])
print("detail:", json.dumps(j.get("detail"), ensure_ascii=False)[:500])
print("params:", json.dumps(j.get("params"), ensure_ascii=False))
eps = j["episodes"]
rows = []
for e in eps:
    dec = e.get("decisions") or 0
    secs = e.get("secs") or 0
    rows.append({"pid": e["id"], "slot": e["seed_index"], "score": e["score"], "over": e.get("over_steps") or 0,
                 "dec": dec, "secs": secs, "mean_ms": round(secs * 1000 / dec) if dec else 0,
                 "mechanic": (e.get("tags") or {}).get("mechanic"), "round": (e.get("tags") or {}).get("round")})
over_dist = Counter(r["over"] for r in rows)
print("over_steps per-game dist:", dict(sorted(over_dist.items())))
print("total over:", sum(r["over"] for r in rows), "games with over:", sum(1 for r in rows if r["over"]))
mm = [r["mean_ms"] for r in rows if r["dec"]]
print(f"mean step ms: mean={statistics.mean(mm):.0f} med={statistics.median(mm):.0f} "
      f"p90={sorted(mm)[int(0.9*len(mm))]} max={max(mm)}")
# 均步时 vs over 率
buckets = defaultdict(lambda: [0, 0, 0])
for r in rows:
    b = "<3000" if r["mean_ms"] < 3000 else "3000-4000" if r["mean_ms"] < 4000 else "4000-4500" if r["mean_ms"] < 4500 else "4500-5000" if r["mean_ms"] < 5000 else ">=5000"
    buckets[b][0] += 1; buckets[b][1] += r["dec"]; buckets[b][2] += r["over"]
print("mean_ms bucket -> [games, steps, over, over_rate]:")
for b, (g, s, o) in sorted(buckets.items()):
    print(f"  {b}: {g} games {s} steps {o} over ({o/max(1,s):.1%})")
by_pid = defaultdict(lambda: [0, 0, 0, 0])
for r in rows:
    by_pid[r["pid"]][0] += 1; by_pid[r["pid"]][1] += r["dec"]; by_pid[r["pid"]][2] += r["over"]; by_pid[r["pid"]][3] += r["score"]
top = sorted(by_pid.items(), key=lambda kv: -kv[1][2])
print("top 25 over problems: pid games steps over score_sum")
for p, (g, s, o, sc) in top[:25]:
    print(f"  {p}  g={g} dec={s} over={o} mean_score={sc//g}")
by_mech = defaultdict(lambda: [0, 0, 0])
for r in rows:
    by_mech[r["mechanic"]][0] += 1; by_mech[r["mechanic"]][1] += r["dec"]; by_mech[r["mechanic"]][2] += r["over"]
print("by mechanic:", {k: f"{v[2]}/{v[1]} ({v[2]/max(1,v[1]):.1%})" for k, v in sorted(by_mech.items(), key=lambda kv: -kv[1][2])})
(ROOT / "data" / "_pimc_diag_eps.json").write_text(json.dumps({"rows": rows, "top_over": [p for p, _ in top[:30]]},
                                                            ensure_ascii=False, indent=1), encoding="utf-8")
print("saved data/_pimc_diag_eps.json")