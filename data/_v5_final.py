"""Probe (not committed): final v5 vs v4 analysis (240 slots) + leaderboard row."""
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
API = "https://hiro.matto.top/gkbench/api"
V4 = json.loads((ROOT / "out/_v5_slots.json").read_text(encoding="utf-8"))
v4 = {f"{r['pid']}/{r['slot']}": r for r in V4}
STALE = json.loads((ROOT / "out/_v5_stale.json").read_text(encoding="utf-8"))
stale_keys = {k for k, _s, _r in STALE["stale"]}


def g(p, tries=6):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(API + p, timeout=180) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            time.sleep(5)
    raise RuntimeError("api fail " + p)


label = "gkagent-ex-seed-v5"
rows = g("/runs?set=hif")
rows = rows if isinstance(rows, list) else rows.get("runs", [])
cur = {}
for r in rows:
    if str(r.get("label")) != label:
        continue
    for e in g("/runs/" + r["run"]).get("episodes") or []:
        if not e.get("finished") or e.get("score") is None:
            continue
        k = f"{e['id']}/{int(e['seed_index'])}"
        at = e.get("at") or ""
        if k not in cur or at >= cur[k][0]:
            cur[k] = (at, int(e["score"]), r["run"])
scores = {k: v[1] for k, v in cur.items()}
print(f"{label}: slots={len(scores)} mean={statistics.mean(scores.values()):,.0f}")

paired = [(k, s, v4[k]["ours"]) for k, s in sorted(scores.items()) if k in v4]
print(f"paired vs v4: n={len(paired)}")
deltas = [s - o for _k, s, o in paired]
mean = statistics.mean(deltas)
sd = statistics.stdev(deltas) if len(deltas) > 1 else 0
se = sd / len(deltas) ** 0.5
print(f"  v4 mean={statistics.mean(o for _k, _s, o in paired):,.0f} "
      f"v5 mean={statistics.mean(s for _k, s, _o in paired):,.0f}")
print(f"  meanΔ={mean:+,.0f} sd={sd:,.0f} se={se:,.0f} ~95%CI=[{mean - 2 * se:+,.0f},{mean + 2 * se:+,.0f}]")
print(f"  win={sum(1 for d in deltas if d > 0)} lose={sum(1 for d in deltas if d < 0)} "
      f"tie={sum(1 for d in deltas if d == 0)}")
ratios4 = [o / v4[k]["oracle"] for k, _s, o in paired if v4[k].get("oracle")]
ratios5 = [s / v4[k]["oracle"] for k, s, _o in paired if v4[k].get("oracle")]
print(f"  ratio vs oracle: v4={statistics.mean(ratios4):.4f} v5={statistics.mean(ratios5):.4f}")

pure = [(k, s, o) for k, s, o in paired if k not in stale_keys]
if pure:
    d2 = [s - o for _k, s, o in pure]
    print(f"  [non-stale config only] n={len(pure)} meanΔ={statistics.mean(d2):+,.0f} "
          f"win={sum(1 for d in d2 if d > 0)} lose={sum(1 for d in d2 if d < 0)}")

for lim_name, cond in (("FINAL(12T)", lambda r: int(r.get("limit_turn") or 0) >= 12),
                       ("MID(9T)", lambda r: 0 < int(r.get("limit_turn") or 0) < 12)):
    sub = [(k, s, o) for k, s, o in paired if cond(v4[k])]
    if sub:
        d = [s - o for _k, s, o in sub]
        print(f"  {lim_name}: n={len(sub)} v4sum={sum(o for _k,_s,o in sub):,} "
              f"Δsum={sum(d):+,} meanΔ={statistics.mean(d):+,.0f} "
              f"win={sum(1 for x in d if x>0)} lose={sum(1 for x in d if x<0)}")

print("\ntop gains:")
for k, s, o in sorted(paired, key=lambda x: -(x[1] - x[2]))[:8]:
    print(f"  {k:<18} v4={o:>12,} v5={s:>12,} Δ={s - o:>+12,} ({s / o * 100:5.1f}%)"
          + (" [stale]" if k in stale_keys else ""))
print("top losses:")
for k, s, o in sorted(paired, key=lambda x: (x[1] - x[2]))[:8]:
    print(f"  {k:<18} v4={o:>12,} v5={s:>12,} Δ={s - o:>+12,} ({s / o * 100:5.1f}%)"
          + (" [stale]" if k in stale_keys else ""))

print("\n--- leaderboard row ---")
try:
    lb = g("/leaderboard?set=hif&kind=template")
    if isinstance(lb, dict):
        lb = lb.get("rows") or []
    for r in lb:
        if str(r.get("label")) == label:
            print(json.dumps({k: r.get(k) for k in ("mean", "n", "seeds_per_problem", "step_seconds",
                                                   "over", "errors", "unfinished", "p50_ms", "p95_ms",
                                                   "max_ms", "ep_think_s")}, ensure_ascii=False))
except Exception as e:  # noqa: BLE001
    print("leaderboard fail", e)
print("\nsaved out/_v5_final.json")
json.dump({"scores": scores, "paired": [[k, s, o] for k, s, o in paired],
           "stale": sorted(stale_keys)}, open(ROOT / "out/_v5_final.json", "w"), ensure_ascii=False)