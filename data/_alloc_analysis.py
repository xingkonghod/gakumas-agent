"""Probe: v3 逐槽分数 × 题目 public_meta（step_type/limit_turn）分层 — 起点数分配依据（不提交）。"""
import json
import statistics
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "_v3_slots.json"
META = json.loads((ROOT / "data" / "_meta_probe.json").read_text(encoding="utf-8"))
meta_by_id = {m["id"]: m for m in META}

if CACHE.exists():
    data = json.loads(CACHE.read_text(encoding="utf-8"))
else:
    import httpx
    TOK = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()
    H = {"Authorization": f"Bearer {TOK}"}
    B = "https://hiro.matto.top/gkbench"
    V3RUNS = [
        "template-hif-gkagent-ex-seed-v3-xingkonghod-a478c651d4f4",
        "template-hif-gkagent-ex-seed-v3-xingkonghod-b60d6b23b475",
        "template-hif-gkagent-ex-seed-v3-xingkonghod-9ba9c00fb468",
        "template-hif-gkagent-ex-seed-v3-xingkonghod-40312fcb77a0",
    ]

    def get(path, tries=5):
        for _ in range(tries):
            try:
                return httpx.get(B + path, headers=H, timeout=90).json()
            except Exception:  # noqa: BLE001
                time.sleep(4)
        raise RuntimeError("fetch fail " + path)

    rows = get("/api/runs")
    rows = rows if isinstance(rows, list) else rows.get("runs", [])
    bk = [r["run"] for r in rows if r.get("run", "").endswith("hif-template-best-known")]
    oracle = {}
    for rn in bk:
        for e in get(f"/api/runs/{rn}").get("episodes") or []:
            k = (e.get("id"), e.get("seed_index"))
            s = e.get("score")
            if s is not None and (k not in oracle or s > oracle[k]):
                oracle[k] = s
    v3 = {}
    for rn in V3RUNS:
        for e in get(f"/api/runs/{rn}").get("episodes") or []:
            if not e.get("finished") or e.get("score") is None:
                continue
            k = (e["id"], int(e["seed_index"]))
            at = e.get("at") or ""
            prev = v3.get(k)
            if prev is None or at >= prev[0]:
                v3[k] = (at, int(e["score"]))
    data = {"v3": {f"{k[0]}/{k[1]}": v[1] for k, v in v3.items()},
            "oracle": {f"{k[0]}/{k[1]}": v for k, v in oracle.items()}}
    CACHE.write_text(json.dumps(data), encoding="utf-8")

slots = []
for key, s in data["v3"].items():
    pid, slot = key.rsplit("/", 1)
    m = meta_by_id.get(pid) or {}
    o = data["oracle"].get(key)
    slots.append({"id": pid, "slot": int(slot), "score": s, "oracle": o,
                  "step_type": m.get("step_type"), "limit_turn": m.get("limit_turn"),
                  "produce_id": m.get("produce_id")})
print(f"slots={len(slots)} sum={sum(x['score'] for x in slots):,} mean={statistics.mean(x['score'] for x in slots):,.0f}")
for field in ("step_type", "limit_turn"):
    print(f"--- by {field} ---")
    for k in sorted({str(x[field]) for x in slots}):
        rs = [x for x in slots if str(x[field]) == k]
        op = [x for x in rs if x["oracle"]]
        print(f"  {k:<18} n={len(rs):<4} sum={sum(x['score'] for x in rs):>12,} "
              f"mean={statistics.mean(x['score'] for x in rs):>10,.0f} "
              f"ratio={statistics.mean(x['score']/x['oracle'] for x in op) if op else 0:.3f}")
# 缺口按 step_type
print("--- gap share by step_type ---")
tot = sum((x["oracle"] - x["score"]) for x in slots if x["oracle"])
for k in sorted({str(x["step_type"]) for x in slots}):
    g = sum((x["oracle"] - x["score"]) for x in slots if str(x["step_type"]) == k and x["oracle"])
    print(f"  {k:<18} gap={g:>12,} share={g/tot:.1%}")