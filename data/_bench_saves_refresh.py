# -*- coding: utf-8 -*-
"""对比 gkbench 当前 hif 题模板 vs 本地 11-22 快照（matto 11-22 重爬补技能卡定制）。探针不提交。"""
import hashlib
import json
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"D:\Games\gakumas-agent")
TOK = (Path.home() / ".config/gkbench/token").read_text().strip()
LOCAL = ROOT / "data/bench_local/gkbench_dl/hif/saves.jsonl"
FRESH = ROOT / "data/_bench_refresh_saves.jsonl"

r = httpx.get("https://hiro.matto.top/gkbench/api/sets/hif/saves?answers=1",
              headers={"Authorization": f"Bearer {TOK}"}, timeout=120)
r.raise_for_status()
FRESH.write_bytes(r.content)
print(f"fetched {len(r.content)} bytes -> {FRESH.name}")


def load(p):
    d = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            d[row["id"]] = row
    return d


old, new = load(LOCAL), load(FRESH)
print(f"local {len(old)} ids, fresh {len(new)} ids")
added = set(new) - set(old)
removed = set(old) - set(new)
print(f"added {len(added)}: {sorted(added)[:10]}")
print(f"removed {len(removed)}: {sorted(removed)[:10]}")
changed = []
for i in sorted(set(old) & set(new)):
    if json.dumps(old[i].get("loadout"), sort_keys=True) != json.dumps(new[i].get("loadout"), sort_keys=True):
        changed.append(i)
print(f"loadout changed: {len(changed)}")
for i in changed[:15]:
    print("  ", i)
check_changed = [i for i in sorted(set(old) & set(new))
                 if json.dumps(old[i].get("check"), sort_keys=True) != json.dumps(new[i].get("check"), sort_keys=True)]
print(f"check changed: {len(check_changed)}")
if not added and not removed and not changed:
    print("VERDICT: loadout 逐位一致（本地快照已是重爬后版本）")
else:
    print("VERDICT: 有差异，需更新本地快照")
