"""Probe: v4 vs v3 per-slot group summary (probe, not committed)."""
import json
import statistics
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://hiro.matto.top/gkbench/api"
v3 = json.loads((ROOT / "data" / "_v3_slots.json").read_text(encoding="utf-8"))
meta = {x["id"]: x for x in json.loads((ROOT / "data" / "_meta_probe.json").read_text(encoding="utf-8"))}


def get(path, tries=6):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(API + path, timeout=60) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            import time
            time.sleep(5)
    raise RuntimeError("api fail " + path)


def collect(algo_suffix):
    rows = get("/runs?set=hif")
    rows = rows if isinstance(rows, list) else rows.get("runs", [])
    out = {}
    for r in rows:
        if not str(r.get("algo", "")).endswith(algo_suffix):
            continue
        d = get("/runs/" + r["run"])
        for e in d.get("episodes") or []:
            if not e.get("finished") or e.get("score") is None:
                continue
            k = f"{e['id']}/{e['seed_index']}"
            at = e.get("at") or ""
            if k not in out or at >= out[k][0]:
                out[k] = (at, int(e["score"]), e.get("decisions"), e.get("secs"))
    return out


algo = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v4"
v4 = collect(algo)
print(f"{algo} slots={len(v4)}")
groups = {"FINAL": [], "MID": []}
for k, (at, new, dec, secs) in sorted(v4.items()):
    old = v3["v3"].get(k)
    if old is None:
        continue
    pid = k.rsplit("/", 1)[0]
    lim = int((meta.get(pid) or {}).get("limit_turn") or 0)
    g = "FINAL" if lim >= 12 else "MID"
    groups[g].append((k, old, new))
for g, rows in groups.items():
    if not rows:
        continue
    ds = [n - o for _k, o, n in rows]
    ps = [(n - o) / max(1, o) for _k, o, n in rows]
    print(f"{g}: n={len(rows)} sum v3={sum(o for _k,o,_n in rows):,} v4={sum(n for _k,_o,n in rows):,} "
          f"delta={sum(ds):+,} ({sum(ds)/max(1,sum(o for _k,o,_n in rows))*100:+.2f}%) "
          f"median%={statistics.median(ps)*100:+.1f}% win={sum(1 for d in ds if d>0)}/{sum(1 for d in ds if d<0)}")
    for k, o, n in sorted(rows, key=lambda x: x[2] - x[1])[:8]:
        print(f"   {k:<20} v3={o:>9,} v4={n:>9,} d={n-o:>+9,} ({(n-o)/max(1,o)*100:+.1f}%)")
    print("   -- top + --")
    for k, o, n in sorted(rows, key=lambda x: x[2] - x[1])[-8:]:
        print(f"   {k:<20} v3={o:>9,} v4={n:>9,} d={n-o:>+9,} ({(n-o)/max(1,o)*100:+.1f}%)")