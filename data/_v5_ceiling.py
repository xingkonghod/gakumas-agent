"""Probe (not committed): feasibility math for the v4 -> best-known gap.

Iterates ALL hosted chunk runs of one label (leaderboard merges per-slot latest),
builds per-slot latest scores, then compares against the best-known farm oracle and
against best-known's own seed_index{0,1} subset (the same games we play).
"""
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


def slots_of(label, min_eps=4):
    rows = g("/runs?set=hif")
    rows = rows if isinstance(rows, list) else rows.get("runs", [])
    cur, runs = {}, []
    for r in rows:
        if str(r.get("label")) != label or (r.get("episodes") or 0) < min_eps:
            continue
        runs.append(r["run"])
        for e in g("/runs/" + r["run"]).get("episodes") or []:
            if not e.get("finished") or e.get("score") is None:
                continue
            k = f"{e['id']}/{e['seed_index']}"
            at = e.get("at") or ""
            if k not in cur or at >= cur[k][0]:
                cur[k] = (at, int(e["score"]))
    return {k: v[1] for k, v in cur.items()}, runs


label = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v4"
ours, our_runs = slots_of(label, min_eps=4)
print(f"{label}: runs={len(our_runs)} slots={len(ours)} mean={statistics.mean(ours.values()):,.0f}")
cache = json.loads((ROOT / "data" / "_v3_slots.json").read_text(encoding="utf-8"))
oracle = cache["oracle"]
meta = {x["id"]: x for x in json.loads((ROOT / "data" / "_meta_probe.json").read_text(encoding="utf-8"))}
paired = {k: (s, oracle[k]) for k, s in ours.items() if oracle.get(k)}
ratios = [s / o for s, o in paired.values()]
above = sum(1 for s, o in paired.values() if s > o)
print(f"paired={len(paired)} ratio mean={statistics.mean(ratios):.3f} median={statistics.median(ratios):.3f} "
      f">1.0: {above} ({above/len(paired):.1%})")
gap = sum(o - s for s, o in paired.values() if o > s)
ceil_all = sum(max(s, o) for s, o in paired.values())
print(f"positive gap={gap:,}; ours_sum={sum(s for s,_ in paired.values()):,} oracle_sum={sum(o for _,o in paired.values()):,}")
print(f"ceiling (match oracle where below, keep above) mean over paired={ceil_all/len(paired):,.0f}; "
      f"over 240 slots={ceil_all/240:,.0f}")

bk, bk_runs = slots_of("best-known", min_eps=800)
print(f"\nbest-known: runs={len(bk_runs)} slots={len(bk)} mean={statistics.mean(bk.values()):,.0f}")
for slot in (0, 1):
    sub = {k: v for k, v in bk.items() if k.endswith("/%d" % slot)}
    print(f"  best-known seed_index={slot}: n={len(sub)} mean={statistics.mean(sub.values()):,.0f}")
common = [k for k in ours if k in bk]
dlt = [ours[k] - bk[k] for k in common]
print(f"  paired vs best-known on {len(common)} common slots: meanΔ={statistics.mean(dlt):,.0f} "
      f"win={sum(1 for x in dlt if x>0)} lose={sum(1 for x in dlt if x<0)}")

byid = {}
for k, (s, o) in paired.items():
    pid = k.rsplit("/", 1)[0]
    d = byid.setdefault(pid, [0, 0, 0])
    d[0] += s
    d[1] += o
    d[2] += 1
rows_p = []
for pid, (s, o, n) in byid.items():
    m = meta.get(pid) or {}
    rows_p.append((o - s, pid, s / o, s, o, n, int(m.get("limit_turn") or 0), m.get("step_type")))
rows_p.sort(reverse=True)
print("\nper-problem headroom (top 15):")
for hp, pid, rt, s, o, n, lim, st in rows_p[:15]:
    print(f"  {pid} {st} limit={lim} n={n} ratio={rt:.3f} ours={s:,} oracle={o:,} headroom={hp:,}")
tail = sum(x[0] for x in rows_p[10:])
print(f"headroom beyond top10 = {tail:,} ({tail/gap:.1%}); below 1.0 count={sum(1 for x in rows_p if x[2]<1)}")