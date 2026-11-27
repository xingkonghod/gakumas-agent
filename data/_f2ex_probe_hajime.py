"""一次性探针：拉 hajime r13 run 的 lesson/exam 局各一，看 steps 里有没有 obs。不提交。"""
import json
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tok = Path.home().joinpath(".config/gkbench/token").read_text().strip()
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": f"Bearer {tok}"}, timeout=120)
RUN = "template-hajime-gkagent-ei-r13-xingkonghod-1bf9543d4462"
our = c.get(f"/api/runs/{RUN}").json()
eps = our.get("episodes") or []
print("episodes:", len(eps), "run keys:", list(our.keys()))
if eps:
    print("episode sample keys:", list(eps[0].keys()))
    print("episode sample:", json.dumps(eps[0], ensure_ascii=False)[:600])

# 按 stage 分组找 lesson / exam 各一局
lesson = exam = None
for e in eps:
    tags = e.get("tags") or {}
    stage = str(tags.get("stage", ""))
    if "audition" in stage and exam is None:
        exam = e
    elif stage and "audition" not in stage and lesson is None:
        lesson = e
    if lesson and exam:
        break
print("lesson ep:", json.dumps(lesson, ensure_ascii=False)[:300] if lesson else None)
print("exam ep:", json.dumps(exam, ensure_ascii=False)[:300] if exam else None)

out = {}
for kind, e in (("lesson", lesson), ("exam", exam)):
    if not e:
        continue
    r = c.get(f"/api/runs/{RUN}/episodes/{e['id']}/{e['seed_index']}")
    if r.status_code != 200:
        print(kind, "fetch fail", r.status_code)
        continue
    ep = r.json()
    print(f"--- {kind} episode keys:", list(ep.keys()))
    steps = ep.get("steps") or []
    print(f"{kind} steps: {len(steps)}")
    if steps:
        print(f"{kind} step0 keys:", list(steps[0].keys()))
        print(f"{kind} step0:", json.dumps(steps[0], ensure_ascii=False)[:1500])
    out[kind] = ep
Path(r"D:\Games\gakumas-agent\data\_f2ex_hajime_eps.json").write_text(
    json.dumps(out, ensure_ascii=False), encoding="utf-8")
print("saved _f2ex_hajime_eps.json")
