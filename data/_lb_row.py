"""Read-only probe: dump one leaderboard row raw (not committed)."""
import json
import urllib.request

BASE = "https://hiro.matto.top/gkbench/api"

with urllib.request.urlopen(BASE + "/leaderboard?set=hif&kind=template", timeout=60) as f:
    rows = json.load(f)
for r in rows:
    if str(r.get("algo", "")).endswith(("gkagent-ex-seed-v3", "gkagent-ex-seed-v2")):
        print(json.dumps(r, ensure_ascii=False, indent=1)[:4000])
        print("---")