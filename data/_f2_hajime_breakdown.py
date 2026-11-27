"""一次性：拉 hajime r13 run 逐局摘要，按课程/考试拆分均分。不提交。"""
from __future__ import annotations
import json, sys, urllib.request
from collections import defaultdict

RUN = "template-hajime-gkagent-ei-r13-xingkonghod-1bf9543d4462"
URL = f"https://hiro.matto.top/gkbench/api/runs/{RUN}"

def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "gkagent-probe"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    # find episodes list
    eps = data.get("episodes") or data.get("rows") or data
    if isinstance(eps, dict):
        for k in ("episodes", "rows", "items", "results"):
            if k in eps: eps = eps[k]; break
    print("top keys:", list(data.keys()) if isinstance(data, dict) else type(data))
    if not isinstance(eps, list):
        print("no episode list; sample:", json.dumps(data, ensure_ascii=False)[:500]); return
    groups = defaultdict(list)
    for e in eps:
        score = e.get("score")
        tags = e.get("tags") or {}
        stage = tags.get("stage", "") if isinstance(tags, dict) else ""
        kind = "exam" if "audition" in stage else ("lesson" if stage else "unknown")
        if isinstance(score, (int, float)):
            groups[kind].append(score)
            groups["all"].append(score)
    for k, v in sorted(groups.items()):
        if v: print(f"  {k:8s} n={len(v):3d} mean={sum(v)/len(v):10.1f} min={min(v):8.0f} max={max(v):9.0f}")

if __name__ == "__main__":
    main()