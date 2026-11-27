"""一次性收尾：增强版逐机制/轮次均分 + 投稿目录清单。"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tok = Path.home().joinpath(".config/gkbench/token").read_text().strip()
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": f"Bearer {tok}"}, timeout=120)
RUN = "template-hif-gkagent-ei-r13-cgaug-xingkonghod-d20fda5881ec"
j = c.get(f"/api/runs/{RUN}").json()
eps = j.get("episodes") or []
by_mech = defaultdict(list)
by_stage = defaultdict(list)
by_plan = defaultdict(list)
for e in eps:
    t = e.get("tags") or {}
    by_mech[t.get("mechanic")].append(e["score"])
    by_stage[t.get("stage")].append(e["score"])
print("by mechanic:")
for k, v in sorted(by_mech.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
    print(f"  {str(k):18s} n={len(v):3d} mean {sum(v)/len(v):>10,.0f}")
print("by stage:")
for k, v in sorted(by_stage.items()):
    print(f"  {str(k):18s} n={len(v):3d} mean {sum(v)/len(v):>10,.0f}")

sub = Path(r"D:\Games\gakumas-agent\data\bench_repo\submissions\gkagent-ei-r13")
print("\nsubmission dir:")
for p in sorted(sub.rglob("*")):
    if p.is_file():
        print(f"  {p.relative_to(sub)}  {p.stat().st_size/1e6:.3f} MB")
print("\nsubmission.json:", (sub / "submission.json").read_text(encoding="utf-8"))