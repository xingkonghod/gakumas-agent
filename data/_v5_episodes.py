"""Probe (not committed): fetch episode steps (token) and summarize per-step meta/timing."""
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


def g(p, tries=5, auth=True):
    for _ in range(tries):
        try:
            req = urllib.request.Request(API + p, headers=H if auth else {})
            with urllib.request.urlopen(req, timeout=300) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4)
    raise RuntimeError(f"api fail {p}: {last}")


rows = g("/runs?set=hif", auth=False)
rows = rows if isinstance(rows, list) else rows.get("runs", [])
# build slot -> (run, at) for our label
want_slots = [("AS-AXME8QK2", 1), ("AS-WDKWQYW5", 1), ("AS-BZXB28YJ", 1),
              ("AS-QQ6J5S39", 1), ("AS-YSNBNDV4", 0), ("AS-3EW6E6HV", 1)]
label = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v4"
slots = {}
for r in [x for x in rows if str(x.get("label")) == label]:
    for e in g("/runs/" + r["run"], auth=False).get("episodes") or []:
        slots.setdefault((e["id"], int(e["seed_index"])), (r["run"], e.get("at")))

for pid, si in want_slots:
    hit = slots.get((pid, si))
    if not hit:
        print(pid, si, "no run")
        continue
    run, at = hit
    t0 = time.time()
    try:
        d = g(f"/runs/{run}/episodes/{pid}/{si}")
    except Exception as e:  # noqa: BLE001
        print(pid, si, "fetch fail", e)
        continue
    steps = d.get("steps") or []
    ms = [s.get("step_ms") or 0 for s in steps]
    metas = [s.get("algo_meta") or {} for s in steps]
    modes, locks = {}, set()
    for m in metas:
        modes[m.get("mode")] = modes.get(m.get("mode"), 0) + 1
        if m.get("lock_turn"):
            locks.add(m["lock_turn"])
    trans = sum(m.get("transitions") or 0 for m in metas if isinstance(m.get("transitions"), int))
    print(f"\n{pid}/{si} score={d.get('score')} run={run[-16:]} episodes_n={len(steps)} "
          f"fetch={time.time()-t0:.0f}s")
    print(f"  step_ms mean={statistics.mean(ms):.0f} p50={statistics.median(ms):.0f} max={max(ms):.0f} "
          f"sum={sum(ms)/1000:.1f}s over={sum(1 for x in ms if x > 12050)}")
    print(f"  modes={modes} locks={sorted(locks)} decisions={d.get('decisions')} meta_keys="
          f"{sorted({k for m in metas for k in m})}")
    for i, (m, s) in enumerate(zip(metas, steps)):
        if i < 4 or (m.get("mode") in ("tail", "search", "vote", "worlds")):
            print(f"   step{i:02d} t={s.get('turn')} ms={s.get('step_ms')} action={s.get('action')} "
                  f"meta={ {k: v for k, v in m.items() if k in ('mode','target','lock_turn','scan_s','adopted','bad_routes','tail_status','search_why','votes','worlds')} }")