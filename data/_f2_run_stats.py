"""一次性：拉取托管评测运行详情，统计超时步/错误/决策数/步时。"""
import json
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tok = Path.home().joinpath(".config/gkbench/token").read_text().strip()
RUN = "template-hif-gkagent-ei-r13-xingkonghod-7b0da3c354fd"
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": f"Bearer {tok}"}, timeout=120)
r = c.get(f"/api/runs/{RUN}")
print("run status:", r.status_code)
j = r.json()
if isinstance(j, dict):
    print("keys:", list(j.keys()))
    for k in ("algo", "label", "set", "kind", "episodes", "mean", "score", "ok", "failed",
              "step_seconds", "budget", "seeds_per_problem", "template_seeds", "engine", "rules"):
        if k in j:
            print(f"  {k}: {j[k]}")
    eps = j.get("episodes") or j.get("rows") or j.get("summaries") or []
    if isinstance(eps, list) and eps and isinstance(eps[0], dict):
        print("episode rows:", len(eps), "sample keys:", list(eps[0].keys()))
        scores, over, errs, decisions, step_ms, wall = [], 0, 0, [], [], []
        for e in eps:
            fin = e.get("final") or e
            if isinstance(fin.get("score"), (int, float)):
                scores.append(fin["score"])
            over += int(fin.get("over_steps") or e.get("over_steps") or 0)
            if e.get("err") or fin.get("err"):
                errs += 1
            if isinstance(fin.get("decisions"), (int, float)):
                decisions.append(fin["decisions"])
            for s in e.get("steps") or []:
                if isinstance(s.get("step_ms"), (int, float)):
                    step_ms.append(s["step_ms"])
        if scores:
            scores.sort()
            n = len(scores)
            print(f"episodes with score: {n}, mean {sum(scores)/n:,.0f}, "
                  f"min {scores[0]:,}, p50 {scores[n//2]:,}, max {scores[-1]:,}")
            print(f"zero-score episodes: {sum(1 for s in scores if s == 0)}")
        print(f"over_steps total: {over}, err episodes: {errs}")
        if decisions:
            print(f"decisions: total {sum(decisions)}, mean {sum(decisions)/len(decisions):.1f}")
        if step_ms:
            step_ms.sort()
            n = len(step_ms)
            print(f"step_ms: n={n} mean {sum(step_ms)/n:.1f} p50 {step_ms[n//2]:.1f} "
                  f"p95 {step_ms[int(n*0.95)]:.1f} max {step_ms[-1]:.1f}")
    else:
        print(json.dumps(j, ensure_ascii=False)[:3000])
else:
    print(str(j)[:2000])