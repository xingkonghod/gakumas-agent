"""Read-only probe: per-run params/counts for our v3 runs (not committed)."""
import json
import urllib.request

BASE = "https://hiro.matto.top/gkbench/api"
RUNS = [
    "template-hif-gkagent-ex-seed-v3-xingkonghod-a478c651d4f4",
    "template-hif-gkagent-ex-seed-v3-xingkonghod-b60d6b23b475",
    "template-hif-gkagent-ex-seed-v3-xingkonghod-9ba9c00fb468",
    "template-hif-gkagent-ex-seed-v3-xingkonghod-40312fcb77a0",
]


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=90) as f:
        return json.load(f)


for rid in RUNS:
    try:
        d = get("/runs/" + rid)
    except Exception as e:  # noqa: BLE001
        print(rid, "ERR", e)
        continue
    eps = d.get("episodes") or d.get("rows") or []
    print(rid.split("-")[-1], "keys:", list(d)[:12], "n_eps:", len(eps), "params:", d.get("params"))
    if eps:
        print("   sample ep keys:", list(eps[0])[:20])