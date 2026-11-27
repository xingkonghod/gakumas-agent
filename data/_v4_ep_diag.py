"""Probe: compare step timing/transitions for one slot (v3 vs v4) — not committed."""
import json
import statistics
import sys
import urllib.request

API = "https://hiro.matto.top/gkbench/api"


def get(path):
    with urllib.request.urlopen(API + path, timeout=90) as f:
        return json.load(f)


def episode(run_suffix, pid, slot):
    rows = get("/runs?set=hif")
    rows = rows if isinstance(rows, list) else rows.get("runs", [])
    for r in rows:
        if not str(r.get("algo", "")).endswith(run_suffix):
            continue
        d = get("/runs/" + r["run"])
        for e in d.get("episodes") or []:
            if e.get("id") == pid and int(e.get("seed_index", -1)) == slot:
                yield r["run"], e


def summarize(tag, run, e):
    steps = e.get("steps") or []
    ms = [s.get("step_ms") or 0 for s in steps]
    print(f"{tag} run={run[-12:]} score={e.get('score')} decisions={e.get('decisions')} "
          f"secs={e.get('final', {}).get('secs')} n_steps={len(steps)}")
    print(f"   step_ms mean={statistics.mean(ms):.0f} p50={statistics.median(ms):.0f} max={max(ms):.0f} "
          f"sum={sum(ms)/1000:.1f}s over={(1000*12.05) and sum(1 for x in ms if x > 12050)}")
    # 找 algo_meta（如果记录里有）
    keys = set()
    for s in steps[:3]:
        keys |= set(s)
    print("   step keys:", sorted(keys))
    metas = [s.get("algo_meta") or s.get("meta") for s in steps]
    metas = [m for m in metas if isinstance(m, dict)]
    if metas:
        for key in ("search_why", "tail_status", "votes", "target"):
            vals = [m.get(key) for m in metas if m.get(key) is not None]
            if vals:
                print(f"   {key}: sample {vals[0]!r} n={len(vals)}")
        cnt = {}
        for m in metas:
            for k, v in m.items():
                if k in ("target", "votes", "votes_n"):
                    continue
                cnt[k] = cnt.get(k, 0) + 1
        print("   meta key counts:", cnt)


pid = sys.argv[1] if len(sys.argv) > 1 else "AS-QQ6J5S39"
slot = int(sys.argv[2]) if len(sys.argv) > 2 else 0
for tag, suffix in (("v3", "gkagent-ex-seed-v3"), ("v4", "gkagent-ex-seed-v4")):
    for run, e in episode(suffix, pid, slot):
        summarize(tag, run, e)
        break