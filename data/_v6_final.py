"""Probe (not committed): full-run analysis v6 vs v5 (240 slots) + leaderboard row."""
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
API = "https://hiro.matto.top/gkbench/api"
TOK = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()
H = {"Authorization": f"Bearer {TOK}"}
SLOTS = json.loads((ROOT / "out/_v5_slots.json").read_text(encoding="utf-8"))
v4 = {s["key"]: s for s in SLOTS}
V5F = json.loads((ROOT / "out/_v5_final.json").read_text(encoding="utf-8"))
v5 = V5F["scores"]


def g(p, tries=8, timeout=180):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + p, headers=H), timeout=timeout) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4)
    raise RuntimeError(f"api fail {p}: {last}")


def boot_ci(deltas, iters=10000, seed=20261127):
    import random
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def collect(label):
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
    return {k: v[1] for k, v in cur.items()}


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v6"
    scores = collect(label)
    print(f"{label}: slots={len(scores)} mean={statistics.mean(scores.values()):,.0f}")
    keys = sorted(scores)
    paired = [k for k in keys if k in v5]
    print(f"paired with v5: {len(paired)}")
    if paired:
        d = [scores[k] - v5[k] for k in paired]
        lo, hi = boot_ci(d)
        print(f"v5 mean on these slots={statistics.mean(v5[k] for k in paired):,.0f}")
        print(f"meanΔ={statistics.mean(d):+,.0f} sd={statistics.stdev(d) if len(d)>1 else 0:,.0f} "
              f"CI95=[{lo:+,.0f},{hi:+,.0f}] win={sum(1 for x in d if x>0)} "
              f"lose={sum(1 for x in d if x<0)} tie={sum(1 for x in d if x==0)}")
        for nm, cond in (("FINAL(12T)", lambda r: int(r.get("limit_turn") or 0) >= 12),
                         ("MID(9T)", lambda r: 0 < int(r.get("limit_turn") or 0) < 12)):
            sub = [(k, scores[k], v5[k]) for k in paired if cond(v4[k])]
            if sub:
                dd = [a - b for _k, a, b in sub]
                print(f"  {nm}: n={len(sub)} v5sum={sum(b for _k,_a,b in sub):,} "
                      f"v6sum={sum(a for _k,a,_b in sub):,} Δ={sum(dd):+,} meanΔ={statistics.mean(dd):+,.0f}")
        orc = [(k, v4[k]["oracle"]) for k in paired if v4[k].get("oracle")]
        if orc:
            r5 = statistics.mean(v5[k] / o for k, o in orc)
            r6 = statistics.mean(scores[k] / o for k, o in orc)
            print(f"  oracle ratio: v5={r5:.4f} v6={r6:.4f}")
    print("\ntop gains:")
    for k in sorted(keys, key=lambda k: -(scores[k] - v5.get(k, 0)))[:8]:
        print(f"  {k:<18} v5={v5.get(k,0):>12,} v6={scores[k]:>12,} Δ={scores[k]-v5.get(k,0):>+12,}")
    print("top losses:")
    for k in sorted(keys, key=lambda k: (scores[k] - v5.get(k, 0)))[:8]:
        print(f"  {k:<18} v5={v5.get(k,0):>12,} v6={scores[k]:>12,} Δ={scores[k]-v5.get(k,0):>+12,}")
    try:
        lb = g("/leaderboard?set=hif&kind=template")
        rows = lb if isinstance(lb, list) else lb.get("rows") or []
        print("\n--- leaderboard rows (v6 / v5) ---")
        for r in rows:
            if str(r.get("label")) in (label, "gkagent-ex-seed-v5", "gkagent-ex-seed-v5b"):
                print(json.dumps({k: r.get(k) for k in ("label", "n", "mean", "over", "errors",
                                                       "p50_ms", "p95_ms", "max_ms", "step_seconds")},
                                 ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        print("leaderboard fail", e)
    out = ROOT / "out" / f"_{label}_final.json"
    out.write_text(json.dumps({"scores": scores}, ensure_ascii=False), encoding="utf-8")
    print("\nsaved", out)


if __name__ == "__main__":
    main()