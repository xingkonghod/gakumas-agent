"""Probe (not committed): mid-run check of the v6 full eval (scores only, /runs/{run}).

Usage: .venv\\Scripts\\python.exe data\\_v6_midcheck.py <run>
Compares finished v6 slots with v5 (out/_v5_final.json) and prints mean/median/win/lose + over.
"""
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
v5 = json.loads((ROOT / "out/_v5_final.json").read_text(encoding="utf-8"))["scores"]
slots = {s["key"]: s for s in json.loads((ROOT / "out/_v5_slots.json").read_text(encoding="utf-8"))}


def g(p, tries=6, timeout=120):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(API + p, headers=H), timeout=timeout) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4)
    raise RuntimeError(f"api fail {p}: {last}")


def main():
    run = sys.argv[1]
    d = g("/runs/" + run)
    eps = {f"{e['id']}/{int(e['seed_index'])}": e for e in d.get("episodes") or [] if e.get("finished")}
    print(f"run={run} finished={len(eps)}")
    keys = sorted(eps)
    pair = [k for k in keys if k in v5]
    ds = [int(eps[k]["score"]) - v5[k] for k in pair]
    if pair:
        sd = statistics.stdev(ds) if len(ds) > 1 else 0
        se = sd / max(1, len(ds)) ** 0.5
        print(f"paired={len(pair)} v5mean={statistics.mean(v5[k] for k in pair):,.0f} "
              f"v6mean={statistics.mean(int(eps[k]['score']) for k in pair):,.0f}")
        print(f"meanΔ={statistics.mean(ds):+,.0f} medianΔ={statistics.median(ds):+,.0f} "
              f"se={se:,.0f} win={sum(1 for x in ds if x>0)} lose={sum(1 for x in ds if x<0)} "
              f"tie={sum(1 for x in ds if x==0)}")
        orc = [(k, slots[k]["oracle"]) for k in pair if slots.get(k, {}).get("oracle")]
        if orc:
            print(f"oracle ratio: v5={statistics.mean(v5[k]/o for k,o in orc):.4f} "
                  f"v6={statistics.mean(int(eps[k]['score'])/o for k,o in orc):.4f}")
        over = sum(int(e.get("over_steps") or 0) for e in eps.values())
        print(f"over steps total={over}")
        for nm, cond in (("FINAL", lambda r: int(r.get("limit_turn") or 0) >= 12),
                         ("MID", lambda r: 0 < int(r.get("limit_turn") or 0) < 12)):
            sub = [k for k in pair if cond(slots[k])]
            if sub:
                dd = [int(eps[k]["score"]) - v5[k] for k in sub]
                print(f"  {nm}: n={len(sub)} meanΔ={statistics.mean(dd):+,.0f}")
    # per-problem biggest deltas so far
    best = sorted(pair, key=lambda k: -(int(eps[k]["score"]) - v5[k]))[:5]
    worst = sorted(pair, key=lambda k: (int(eps[k]["score"]) - v5[k]))[:5]
    print("best:", [(k, int(eps[k]["score"]) - v5[k]) for k in best])
    print("worst:", [(k, int(eps[k]["score"]) - v5[k]) for k in worst])


if __name__ == "__main__":
    main()