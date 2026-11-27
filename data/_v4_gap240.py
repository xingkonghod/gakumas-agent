"""v4 托管 240 槽逐题缺口（probe，不提交）：oracle=best-known farm per-(id,slot) max。"""
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
API = "https://hiro.matto.top/gkbench/api"
ALGO = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v4"
v3 = json.loads((ROOT / "data" / "_v3_slots.json").read_text(encoding="utf-8"))
meta = {x["id"]: x for x in json.loads((ROOT / "data" / "_meta_probe.json").read_text(encoding="utf-8"))}


def get(path, tries=6):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(API + path, timeout=60) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            time.sleep(5)
    raise RuntimeError("api fail " + path)


rows = get("/runs?set=hif")
rows = rows if isinstance(rows, list) else rows.get("runs", [])
cur = {}
for r in rows:
    if not str(r.get("algo", "")).endswith(ALGO):
        continue
    d = get("/runs/" + r["run"])
    for e in d.get("episodes") or []:
        if not e.get("finished") or e.get("score") is None:
            continue
        k = f"{e['id']}/{e['seed_index']}"
        at = e.get("at") or ""
        if k not in cur or at >= cur[k][0]:
            cur[k] = (at, int(e["score"]))
pairs = [(k, int(s), v3["oracle"].get(k)) for k, (_a, s) in sorted(cur.items()) if v3["oracle"].get(k)]
ratios = [s / o for _k, s, o in pairs]
print(f"{ALGO} slots={len(cur)} paired={len(pairs)} mean={sum(s for _k,s,_o in pairs)/len(pairs):,.0f} "
      f"ratio mean={statistics.mean(ratios):.3f} median={statistics.median(ratios):.3f}")
byid = {}
for k, s, o in pairs:
    i = k.rsplit("/", 1)[0]
    d = byid.setdefault(i, {"s": 0, "o": 0, "n": 0})
    d["s"] += s
    d["o"] += o
    d["n"] += 1
drag = sorted(byid.items(), key=lambda kv: kv[1]["o"] - kv[1]["s"], reverse=True)
tot = sum(d["o"] - d["s"] for _i, d in drag)
print(f"total gap={tot:,}")
for i, d in drag[:18]:
    m = meta.get(i) or {}
    lim = int(m.get("limit_turn") or 0)
    print(f"  {i}: {d['s']/d['o']*100:5.1f}% gap {d['o']-d['s']:>10,} "
          f"{'FINAL' if lim>=12 else 'MID  '} limit={lim} v4={d['s']:>10,}/{d['o']:>10,}")
print(f"top10 share {sum(d['o']-d['s'] for _i, d in drag[:10])/tot:.1%}")