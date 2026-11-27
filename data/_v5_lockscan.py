"""Probe (not committed): fetch every v4 hosted episode's steps (token) -> lock/lost/mode summary.

Answers: how much of the 240-slot deficit sits in games we never locked (worlds-only fallback)
vs games we locked (pure search quality)? Also over/time profile per slot.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
API = "https://hiro.matto.top/gkbench/api"
TOK = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()
H = {"Authorization": f"Bearer {TOK}"}
OUT = ROOT / "out" / "_v5_lockscan.json"


def g(p, tries=6, auth=True):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(API + p, headers=H if auth else {})
            with urllib.request.urlopen(req, timeout=600) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5)
    raise RuntimeError(f"api fail {p}: {last}")


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v4"
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rows = g("/runs?set=hif", auth=False)
    rows = rows if isinstance(rows, list) else rows.get("runs", [])
    slots = {}
    for r in [x for x in rows if str(x.get("label")) == label]:
        for e in g("/runs/" + r["run"], auth=False).get("episodes") or []:
            key = f"{e['id']}/{int(e['seed_index'])}"
            at = e.get("at") or ""
            if key not in slots or at >= slots[key][0]:
                slots[key] = (at, r["run"], int(e["score"]))
    print(f"{label}: {len(slots)} slots, {len(res)} already fetched", flush=True)
    for n, (key, (at, run, score)) in enumerate(sorted(slots.items())):
        if key in res:
            continue
        pid, si = key.rsplit("/", 1)
        t0 = time.time()
        try:
            d = g(f"/runs/{run}/episodes/{pid}/{si}")
        except Exception as e:  # noqa: BLE001
            print(f"  {key} FETCH FAIL {e}", flush=True)
            continue
        steps = d.get("steps") or []
        ms = [s.get("step_ms") or 0 for s in steps]
        metas = [s.get("algo_meta") or {} for s in steps]
        modes, lock = {}, None
        for m in metas:
            modes[m.get("mode")] = modes.get(m.get("mode"), 0) + 1
            if m.get("lock_turn") and lock is None:
                lock = int(m["lock_turn"])
        res[key] = {"pid": pid, "slot": int(si), "score": score, "run": run,
                    "decisions": len(steps), "lock_turn": lock, "modes": modes,
                    "secs": round(sum(ms) / 1000, 1), "max_ms": round(max(ms)) if ms else 0,
                    "over": sum(1 for x in ms if x > 12050),
                    "rescan": any(m.get("rescan_used") for m in metas),
                    "graph_clean": next((m.get("graph_clean") for m in metas
                                         if m.get("graph_clean") is not None), None)}
        if n % 10 == 0:
            OUT.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(f"  [{n+1}/{len(slots)}] {key} score={score:,} lock={lock} "
              f"modes={modes} secs={res[key]['secs']} max_ms={res[key]['max_ms']} "
              f"fetch={time.time()-t0:.0f}s", flush=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    locked = [v for v in res.values() if v["lock_turn"]]
    print(f"\nfetched={len(res)} locked={len(locked)} unlocked={len(res)-len(locked)}")
    print(f"locked: mean={sum(v['score'] for v in locked)/max(1,len(locked)):,.0f} "
          f"secs={sum(v['secs'] for v in locked)/max(1,len(locked)):.0f}")
    unl = [v for v in res.values() if not v["lock_turn"]]
    print(f"unlocked: mean={sum(v['score'] for v in unl)/max(1,len(unl)):,.0f} n={len(unl)}")
    print(f"total over steps={sum(v['over'] for v in res.values())}")


if __name__ == "__main__":
    main()