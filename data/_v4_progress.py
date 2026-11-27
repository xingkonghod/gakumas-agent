"""Probe: v4 chunk scores vs v3 per-slot (probe, not committed)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
v3 = json.loads((ROOT / "data" / "_v3_slots.json").read_text(encoding="utf-8"))
meta = {x["id"]: x for x in json.loads((ROOT / "data" / "_meta_probe.json").read_text(encoding="utf-8"))}
import sys
import urllib.request

def get(path):
    with urllib.request.urlopen("https://hiro.matto.top/gkbench/api" + path, timeout=60) as f:
        return json.load(f)

rows = get("/runs?set=hif")
rows = rows if isinstance(rows, list) else rows.get("runs", [])
v4 = {}
for r in rows:
    if not str(r.get("algo", "")).endswith("gkagent-ex-seed-v4"):
        continue
    d = get("/runs/" + r["run"])
    for e in d.get("episodes") or []:
        if not e.get("finished") or e.get("score") is None:
            continue
        k = f"{e['id']}/{e['seed_index']}"
        at = e.get("at") or ""
        if k not in v4 or at >= v4[k][0]:
            v4[k] = (at, int(e["score"]))
print(f"v4 slots={len(v4)}")
tot_old = tot_new = 0
for k in sorted(v4):
    pid = k.rsplit("/", 1)[0]
    old = v3["v3"].get(k)
    new = v4[k][1]
    orc = v3["oracle"].get(k)
    if old is None:
        continue
    tot_old += old
    tot_new += new
    m = meta.get(pid) or {}
    flag = "FINAL" if int(m.get("limit_turn") or 0) >= 12 else "MID"
    print(f"{k:<22} {flag:<5} limit={m.get('limit_turn')} v3={old:>9,} v4={new:>9,} d={new-old:>+9,}"
          f" ({(new-old)/max(1,old)*100:+.1f}%) ratio={new/orc*100 if orc else 0:.1f}%")
if tot_old:
    print(f"paired sum v3={tot_old:,} v4={tot_new:,} delta={tot_new-tot_old:+,} ({(tot_new-tot_old)/tot_old*100:+.2f}%)")