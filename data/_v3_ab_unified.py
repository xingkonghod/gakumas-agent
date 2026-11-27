"""v3 A/B 统一报告（探针不提交）：跨所有碎片 run 按 params.vote_sec_cap 归臂，
同题同种子取最新，配对 Δ+CI+覆盖度。服务器 eval 被清不影响 episodes 落盘。"""
import json
import random
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tok = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": "Bearer " + tok}, timeout=90)


def get(p, tries=5):
    for i in range(tries):
        try:
            return c.get(p).raise_for_status().json()
        except Exception:
            time.sleep(4)
    raise SystemExit("fail " + p)


runs = get("/api/runs")
rows = runs if isinstance(runs, list) else runs.get("runs", [])
v3 = [r for r in rows if r.get("label") == "gkagent-ex-seed-v3" and r.get("set") == "hif"]
arms = {0.8: {}, 2.0: {}}
for r in v3:
    cap = (r.get("params") or {}).get("vote_sec_cap")
    if cap not in arms:
        continue
    fin = r.get("finished") or ""
    for e in get("/api/runs/" + r["run"]).get("episodes") or []:
        if not e.get("finished"):
            continue
        k = (e["id"], int(e["seed_index"]))
        prev = arms[cap].get(k)
        if prev is None or fin >= prev[1]:
            arms[cap][k] = (int(e["score"]), fin)
a, b = arms[0.8], arms[2.0]
keys = sorted(set(a) & set(b))
d = [b[k][0] - a[k][0] for k in keys]


def ci(xs, iters=10000, seed=20261126):
    rng = random.Random(seed)
    n = len(xs)
    ms = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return ms[int(0.025 * iters)], ms[int(0.975 * iters)]


lo, hi = ci(d) if d else (0, 0)
out = {
    "armA_vote0.8_slots": len(a), "armB_vote2.0_slots": len(b), "paired_n": len(keys),
    "armA_mean_paired": sum(a[k][0] for k in keys) / len(keys) if keys else None,
    "armB_mean_paired": sum(b[k][0] for k in keys) / len(keys) if keys else None,
    "mean_delta": sum(d) / len(d) if d else None, "ci95": [lo, hi],
    "wins": sum(x > 0 for x in d), "loss": sum(x < 0 for x in d), "ties": sum(x == 0 for x in d),
}
print(json.dumps(out, ensure_ascii=False, indent=1))
json.dump(out, open("out/_v3_ab_unified.json", "w"), ensure_ascii=False, indent=1)