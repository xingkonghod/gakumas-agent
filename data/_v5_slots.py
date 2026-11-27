"""Probe (not committed): v4 per-slot table vs oracle; unpaired slots; dump json."""
import json
import statistics
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
API = "https://hiro.matto.top/gkbench/api"


def g(p, tries=5):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(API + p, timeout=180) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            pass
    raise RuntimeError("api fail " + p)


rows = g("/runs?set=hif")
rows = rows if isinstance(rows, list) else rows.get("runs", [])
cur, ep0 = {}, None
for r in rows:
    if str(r.get("label")) != "gkagent-ex-seed-v4":
        continue
    for e in g("/runs/" + r["run"]).get("episodes") or []:
        if not e.get("finished") or e.get("score") is None:
            continue
        if ep0 is None:
            ep0 = e
        k = f"{e['id']}/{e['seed_index']}"
        at = e.get("at") or ""
        if k not in cur or at >= cur[k][0]:
            cur[k] = (at, int(e["score"]))
ours = {k: v[1] for k, v in cur.items()}
print("episode keys:", sorted(ep0.keys()))
print("sample episode:", {k: v for k, v in ep0.items() if k not in ("at",)})
oracle = json.loads((ROOT / "data" / "_v3_slots.json").read_text(encoding="utf-8"))["oracle"]
meta = {x["id"]: x for x in json.loads((ROOT / "data" / "_meta_probe.json").read_text(encoding="utf-8"))}
unpaired = sorted(k for k in ours if not oracle.get(k))
print(f"\nunpaired slots ({len(unpaired)}):")
for k in unpaired:
    pid = k.rsplit("/", 1)[0]
    m = meta.get(pid) or {}
    print(f"  {k} score={ours[k]:,} {m.get('step_type')} limit={m.get('limit_turn')} produce={m.get('produce_id')}")
tbl = []
for k, s in ours.items():
    o = oracle.get(k)
    pid = k.rsplit("/", 1)[0]
    m = meta.get(pid) or {}
    tbl.append({"key": k, "pid": pid, "slot": int(k.rsplit("/", 1)[1]), "ours": s, "oracle": o,
                "ratio": (s / o) if o else None, "limit_turn": m.get("limit_turn"),
                "step_type": m.get("step_type"), "produce_id": m.get("produce_id")})
paired = [r for r in tbl if r["oracle"]]
print(f"\nratio buckets (paired {len(paired)}):")
for lo, hi in ((0, .3), (.3, .5), (.5, .7), (.7, .8), (.8, .9), (.9, 1.0), (1.0, 1.1), (1.1, 9)):
    n = sum(1 for r in paired if lo <= r["ratio"] < hi)
    gap = sum(r["oracle"] - r["ours"] for r in paired if lo <= r["ratio"] < hi)
    print(f"  [{lo:.1f},{hi:.1f}): n={n:3d} net_gap={gap:>12,}")
print("\nlargest deficits (net):")
for r in sorted(paired, key=lambda r: r["ours"] - r["oracle"])[:20]:
    print(f"  {r['key']:<18} {r['step_type']:<16} limit={r['limit_turn']} ratio={r['ratio']:.3f} "
          f"ours={r['ours']:>12,} oracle={r['oracle']:>12,} deficit={r['oracle']-r['ours']:>11,}")
(ROOT / "out" / "_v5_slots.json").write_text(json.dumps(tbl), encoding="utf-8")
print("\nsaved out/_v5_slots.json")