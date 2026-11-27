"""Probe (not committed): v5 hosted (subset) vs v4 hosted per-slot paired comparison."""
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
v4 = {f"{r['pid']}/{r['slot']}": r["ours"] for r in V4}
oracle = {f"{r['pid']}/{r['slot']}": r["oracle"] for r in V4}


def g(p, tries=6):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(API + p, timeout=120) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            time.sleep(5)
    raise RuntimeError("api fail " + p)


label = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v5"
rows = g("/runs?set=hif")
rows = rows if isinstance(rows, list) else rows.get("runs", [])
cur = {}
n_ep = 0
for r in rows:
    if str(r.get("label")) != label:
        continue
    n_ep += r.get("episodes") or 0
    for e in g("/runs/" + r["run"]).get("episodes") or []:
        if not e.get("finished") or e.get("score") is None:
            continue
        k = f"{e['id']}/{int(e['seed_index'])}"
        at = e.get("at") or ""
        if k not in cur or at >= cur[k][0]:
            cur[k] = (at, int(e["score"]))
print(f"{label}: runs episodes={n_ep} slots={len(cur)}")
deltas, rows_out = [], []
for k in sorted(cur):
    s5 = cur[k][1]
    s4 = v4.get(k)
    o = oracle.get(k)
    if s4 is None:
        print(f"  {k}: v5={s5:,} (no v4 row)")
        continue
    d = s5 - s4
    deltas.append(d)
    rows_out.append((k, s5, s4, o, d))
if deltas:
    n = len(deltas)
    mean = sum(deltas) / n
    sd = statistics.stdev(deltas) if n > 1 else 0
    se = sd / (n ** 0.5) if n > 1 else 0
    print(f"\npaired n={n} meanΔ={mean:,.0f} sd={sd:,.0f} se={se:,.0f} "
          f"~95%CI=[{mean - 2 * se:,.0f},{mean + 2 * se:,.0f}]")
    print(f"win={sum(1 for d in deltas if d > 0)} lose={sum(1 for d in deltas if d < 0)} "
          f"tie={sum(1 for d in deltas if d == 0)}")
    print(f"v4 mean={statistics.mean(r[2] for r in rows_out):,.0f} "
          f"v5 mean={statistics.mean(r[1] for r in rows_out):,.0f} "
          f"ratio_v4={statistics.mean(r[2] / r[3] for r in rows_out) if all(r[3] for r in rows_out) else 0:.3f} "
          f"ratio_v5={statistics.mean(r[1] / r[3] for r in rows_out) if all(r[3] for r in rows_out) else 0:.3f}")
    print("\nper slot:")
    for k, s5, s4, o, d in sorted(rows_out, key=lambda r: -r[4]):
        print(f"  {k:<18} v4={s4:>12,} v5={s5:>12,} Δ={d:>+12,} "
              f"({(d / s4 * 100) if s4 else 0:+.1f}%) oracle={o}")