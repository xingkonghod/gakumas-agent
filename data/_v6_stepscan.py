"""Probe (not committed): pull v5's 240 episodes with full per-step algo_meta -> out/_v6_v5steps.json.

Purpose (OPENING_v6 ①): per-step wall-clock composition (pre-lock scan / pool / tail / worlds),
over steps location, budget usage. Read-only; no param changes.

Robustness: server is flaky (hangs / SYN drops) -> short per-request timeout, threaded fetch, retry,
per-episode checkpoint.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
API = "https://hiro.matto.top/gkbench/api"
TOK = (Path.home() / ".config" / "gkbench" / "token").read_text().strip()
H = {"Authorization": f"Bearer {TOK}"}
LABEL = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v5"
OUT = ROOT / "out" / (sys.argv[2] if len(sys.argv) > 2 else "_v6_v5steps.json")
RUNS_CACHE = ROOT / "out" / "_v6_runs_cache.json"
WORKERS = int(sys.argv[3]) if len(sys.argv) > 3 else 5
STEP_KEYS = ("mode", "ms", "seed_state", "scan_s", "scan_hits", "scan_draws", "lock_turn",
             "pool_searches", "pool_waves", "pool_threads", "pool_status", "pool_adopted",
             "pool_bad", "pool_err", "pool_full", "pool_partial", "pool_expect_ms", "tail_status", "tail_why", "target", "adopted", "bad_routes",
             "pool_lane_ms", "pool_main_ms", "tail_probe", "tail3_failed", "late_worlds", "late_vote",
             "candidates", "worlds", "vote_worlds", "votes", "rescan_used", "graph_clean",
             "error", "why", "differs", "search_why", "route_illegal", "hard_rule", "root_scan_n")


def g(path, tries=14, timeout=25):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(API + path, headers=H)
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(8, 1 + k))
    raise RuntimeError(f"api fail {path}: {last}")


def runs_doc():
    if RUNS_CACHE.exists():
        age = time.time() - RUNS_CACHE.stat().st_mtime
        if age < 3600:
            return json.loads(RUNS_CACHE.read_text(encoding="utf-8"))
    rows = g("/runs?set=hif", timeout=180)
    RUNS_CACHE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def one(key, run, pid, si, score):
    d = g(f"/runs/{run}/episodes/{pid}/{si}", timeout=60)
    raw_steps = d.get("steps") or []
    steps = []
    for s in raw_steps:
        m = s.get("algo_meta") or {}
        r = {k: m[k] for k in STEP_KEYS if k in m}
        r["ms"] = s.get("step_ms", m.get("ms"))
        steps.append(r)
    return key, {"pid": pid, "slot": int(si), "score": score, "run": run,
                 "decisions": len(steps), "steps": steps,
                 "limit_turn": (raw_steps[-1].get("algo_meta") or {}).get("limit_turn") if raw_steps else None}


def main():
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rows = runs_doc()
    rows = rows if isinstance(rows, list) else rows.get("runs", [])
    want = [r for r in rows if str(r.get("label")) == LABEL]
    print(f"{LABEL}: {len(want)} runs", flush=True)
    slots = {}
    for r in want:
        try:
            d = g("/runs/" + r["run"], timeout=60)
        except Exception as e:  # noqa: BLE001
            print("run fail", r["run"], e, flush=True)
            continue
        for e in d.get("episodes") or []:
            if not e.get("finished") or e.get("score") is None:
                continue
            key = f"{e['id']}/{int(e['seed_index'])}"
            at = e.get("at") or ""
            if key not in slots or at >= slots[key][0]:
                slots[key] = (at, r["run"], int(e["score"]))
    todo = [(k, v[1], k.rsplit("/", 1)[0], int(k.rsplit("/", 1)[1]), v[2])
            for k, v in sorted(slots.items()) if k not in res]
    print(f"slots={len(slots)} done={len(res)} todo={len(todo)}", flush=True)
    t00, done = time.time(), 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(one, *t): t[0] for t in todo}
        for f in as_completed(futs):
            k = futs[f]
            try:
                key, val = f.result()
                res[key] = val
                done += 1
                if done % 10 == 0 or done == len(todo):
                    OUT.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
                print(f"  [{done}/{len(todo)}] {key} score={val['score']:,} steps={val['decisions']} "
                      f"elapsed={time.time()-t00:.0f}s", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  {k} FAIL {e}", flush=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print(f"saved {OUT} n={len(res)}", flush=True)


if __name__ == "__main__":
    main()