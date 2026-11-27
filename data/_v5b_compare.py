"""Probe (not committed): v5b full-240 analysis vs v4 and vs v5 (same-slot)."""
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
API = "https://hiro.matto.top/gkbench/api"
V4 = {f"{r['pid']}/{r['slot']}": r for r in json.loads((ROOT / "out/_v5_slots.json").read_text(encoding="utf-8"))}
V5 = json.loads((ROOT / "out/_v5_final.json").read_text(encoding="utf-8"))["scores"]


def g(p, tries=6):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(API + p, timeout=180) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            time.sleep(5)
    raise RuntimeError("api fail " + p)


def slots_of(label):
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
                cur[k] = (at, int(e["score"]))
    return {k: v[1] for k, v in cur.items()}


def stat(tag, base_name, base, cand_name, cand):
    ks = sorted(set(base) & set(cand))
    d = [cand[k] - base[k] for k in ks]
    m = statistics.mean(d)
    sd = statistics.stdev(d) if len(d) > 1 else 0.0
    se = sd / len(d) ** 0.5 if d else 0.0
    print(f"{cand_name} vs {base_name}: n={len(ks)} {base_name}_mean={statistics.mean(base[k] for k in ks):,.0f} "
          f"{cand_name}_mean={statistics.mean(cand[k] for k in ks):,.0f} "
          f"螖mean={m:+,.0f} sd={sd:,.0f} CI鈮圼{m - 2 * se:+,.0f},{m + 2 * se:+,.0f}] "
          f"win={sum(1 for x in d if x > 0)} lose={sum(1 for x in d if x < 0)} tie={sum(1 for x in d if x == 0)}")
    return d


label = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v5b"
cur = slots_of(label)
print(f"{label}: slots={len(cur)} mean={statistics.mean(cur.values()):,.0f}")
v4 = {k: r["ours"] for k, r in V4.items()}
stat("v4", "v4", v4, label, cur)
stat("v5", "v5", V5, label, cur)

paired = [(k, cur[k], V4[k]["ours"]) for k in sorted(cur) if k in V4]
print(f"\nvs v4 paired n={len(paired)}")
deltas = [s - o for _k, s, o in paired]
m = statistics.mean(deltas)
sd = statistics.stdev(deltas)
se = sd / len(deltas) ** 0.5
print(f"  螖mean={m:+,.0f} sd={sd:,.0f} CI鈮圼{m - 2 * se:+,.0f},{m + 2 * se:+,.0f}]")
rat5 = statistics.mean(s / V4[_k]["oracle"] for _k, s, _o in paired if V4[_k].get("oracle"))
rat4 = statistics.mean(o / V4[_k]["oracle"] for _k, _s, o in paired if V4[_k].get("oracle"))
print(f"  ratio vs oracle: v4={rat4:.4f} {label}={rat5:.4f}")
for lim_name, cond in (("FINAL", lambda r: int(r.get("limit_turn") or 0) >= 12),
                       ("MID", lambda r: 0 < int(r.get("limit_turn") or 0) < 12)):
    sub = [(k, s, o) for k, s, o in paired if cond(V4[k])]
    d = [s - o for _k, s, o in sub]
    print(f"  {lim_name}: n={len(sub)} 螖sum={sum(d):+,} 螖mean={statistics.mean(d):+,.0f} "
          f"win={sum(1 for x in d if x > 0)} lose={sum(1 for x in d if x < 0)}")
print("\ntop gains:")
for k, s, o in sorted(paired, key=lambda x: -(x[1] - x[2]))[:6]:
    print(f"  {k:<18} v4={o:>12,} {label}={s:>12,} 螖={s - o:>+12,}")
print("top losses:")
for k, s, o in sorted(paired, key=lambda x: (x[1] - x[2]))[:6]:
    print(f"  {k:<18} v4={o:>12,} {label}={s:>12,} 螖={s - o:>+12,}")
print("\n--- leaderboard rows for label ---")
try:
    lb = g("/leaderboard?set=hif&kind=template")
    if isinstance(lb, dict):
        lb = lb.get("rows") or []
    for r in lb:
        if str(r.get("label")) == label:
            print(json.dumps({k: r.get(k) for k in ("mean", "n", "over", "errors", "p95_ms",
                                                   "max_ms", "ep_think_s")}, ensure_ascii=False))
except Exception as e:  # noqa: BLE001
    print("leaderboard fail", e)
json.dump(cur, open(ROOT / f"out/_{label.replace('gkagent-ex-seed-', '')}_scores.json", "w"))
