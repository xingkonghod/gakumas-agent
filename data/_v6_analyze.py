"""Probe (not committed, OPENING_v6 ①): v5 per-step wall-clock composition from out/_v6_v5steps.json.

Splits every decision into pre-lock (scanning/vote/worlds) vs locked (pool search / route / tail /
fallback), gives ms distributions, budget usage (10s budget, 7s search_use), over steps, and the
idle headroom that ② can convert into more starts.

Writes out/_v6_budget.json + prints a compact table.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "out" / (sys.argv[1] if len(sys.argv) > 1 else "_v6_v5steps.json")
OUT = ROOT / "out" / (sys.argv[2] if len(sys.argv) > 2 else "_v6_budget.json")
BUDGET_MS = 10_000.0
SEARCH_MS = 7_000.0          # search_use=0.70 * budget
OVER_MS = 12_050.0


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round(p / 100.0 * (len(xs) - 1)))))
    return xs[i]


def stats(xs):
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": round(statistics.mean(xs)), "p50": round(pct(xs, 50)),
            "p90": round(pct(xs, 90)), "p95": round(pct(xs, 95)), "p99": round(pct(xs, 99)),
            "max": round(max(xs)), "sum": round(sum(xs))}


def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    games = {k: v for k, v in d.items() if v.get("steps")}
    print(f"games={len(games)}  (expect 240)")
    by_mode = defaultdict(list)
    by_mode_over = Counter()
    scan_s, lock_turn, per_game = [], [], []
    locked_steps, prelock_steps = [], []
    trunc_status = Counter()
    idle = 0.0
    over_rows = []
    headroom_by_mode = defaultdict(float)
    for k, g in games.items():
        ms = [s.get("ms") or 0 for s in g["steps"]]
        lock = next((s.get("lock_turn") for s in g["steps"] if s.get("lock_turn")), None)
        game_scan = next((s.get("scan_s") for s in g["steps"] if s.get("scan_s") is not None), None)
        lock_turn.append(lock)
        if game_scan is not None:
            scan_s.append(float(game_scan))
        for s in g["steps"]:
            m = s.get("mode")
            x = float(s.get("ms") or 0)
            by_mode[m].append(x)
            if x > OVER_MS:
                by_mode_over[m] += 1
                over_rows.append({"slot": k, "mode": m, "ms": round(x), "turn": None,
                                  "limit": g.get("limit_turn"), "lock": lock,
                                  "pool_searches": s.get("pool_searches"),
                                  "pool_status": s.get("pool_status"),
                                  "tail_status": s.get("tail_status"), "scan_s": game_scan})
            if s.get("seed_state") == "locked":
                locked_steps.append(s)
                if x < SEARCH_MS:
                    idle += SEARCH_MS - x
                    headroom_by_mode[m] += SEARCH_MS - x
            else:
                prelock_steps.append(s)
            ps = s.get("pool_status") or {}
            for st, cnt in ps.items():
                if str(st) != "0":
                    trunc_status[str(st)] += int(cnt)
        per_game.append({"slot": k, "score": g["score"], "steps": len(ms), "ms": round(sum(ms)),
                         "lock": lock, "scan_s": game_scan, "limit": g.get("limit_turn"),
                         "decisions": g.get("decisions")})
    out = {"games": len(games), "over_ms": OVER_MS,
           "by_mode": {m: stats(v) for m, v in by_mode.items()},
           "by_mode_over": dict(by_mode_over), "over_rows": over_rows,
           "scan_s": stats(scan_s), "lock_turn_dist": dict(sorted(Counter(lock_turn).items(), key=lambda x: (x[0] is None, x[0]))),
           "locked_step_ids": len(locked_steps), "prelock_step_ids": len(prelock_steps),
           "truncated_status": dict(trunc_status),
           "idle_headroom_7s_ms": round(idle), "headroom_by_mode": {m: round(v) for m, v in headroom_by_mode.items()},
           "per_game": per_game}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n--- by mode (ms) ---")
    print(f"{'mode':10s} {'n':>6s} {'mean':>7s} {'p50':>7s} {'p90':>7s} {'p95':>7s} {'p99':>7s} "
          f"{'max':>8s} {'sum_s':>9s} {'over':>4s} {'idle_s':>8s}")
    for m, v in sorted(by_mode.items(), key=lambda x: -sum(x[1])):
        st = stats(v)
        print(f"{str(m):10s} {st['n']:6d} {st['mean']:7d} {st['p50']:7d} {st['p90']:7d} {st['p95']:7d} "
              f"{st['p99']:7d} {st['max']:8d} {st['sum']/1000:9.0f} {by_mode_over[m]:4d} "
              f"{headroom_by_mode[m]/1000:8.0f}")
    print(f"\nscan_s: {out['scan_s']}")
    print(f"lock_turn: {out['lock_turn_dist']}")
    print(f"truncated statuses: {out['truncated_status']}")
    print(f"idle headroom under 7s (locked steps only): {idle/1000:.0f}s = {idle/1000/60:.1f}min "
          f"over {len(locked_steps)} steps")
    tot = sum(s.get("ms") or 0 for g in games.values() for s in g["steps"]) / 1000
    print(f"total think time: {tot:.0f}s = {tot/60:.1f}min  (n_steps={sum(len(g['steps']) for g in games.values())})")
    print(f"\n--- over rows ({len(over_rows)}) ---")
    for r in sorted(over_rows, key=lambda r: -r["ms"])[:25]:
        print(json.dumps(r, ensure_ascii=False))
    # per-game: score vs lock_turn vs time
    print("\n--- per game summary (first 15) ---")
    for r in per_game[:15]:
        print(json.dumps(r, ensure_ascii=False))
    print(f"\nsaved {OUT}")


if __name__ == "__main__":
    main()