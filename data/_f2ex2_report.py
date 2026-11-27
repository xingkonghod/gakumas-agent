"""两版跑分汇总：配对比较 + seed-lock 统计 + 榜单上下文。探针不提交。链跑完后执行。"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

import httpx

ROOT = Path(r"D:\Games\gakumas-agent")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERVER = "https://hiro.matto.top/gkbench"
TOK = (Path.home() / ".config/gkbench/token").read_text().strip()
C = httpx.Client(base_url=SERVER, headers={"Authorization": f"Bearer {TOK}"}, timeout=120)

STAGES = ["a_hif", "a_hajime", "b_hif", "b_hajime"]
evs, locklines = {}, {}
for s in STAGES:
    log = ROOT / "data" / f"_f2ex2_eval_{s}.log"
    if not log.is_file():
        continue
    text = log.read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(r"评测 ([0-9a-f]{12})", text)
    if m:
        evs[s] = m.group(1)
    locklines[s] = re.findall(r"\[ex-seed\] game \d+: (.+)", text)

done = {}
for s, ev in evs.items():
    j = C.get(f"/api/evals/{ev}").json()
    done[s] = {(d["id"], d["slot"]): d["score"] for d in j.get("done") or []}
    print(f"{s}: eval {ev}  {len(done[s])}/{j.get('total')} 局")

out = ["# f2-ex2 两版跑分汇总", ""]
for setname in ("hif", "hajime"):
    a, b = done.get(f"a_{setname}", {}), done.get(f"b_{setname}", {})
    if not a and not b:
        continue
    out.append(f"## {setname}（模板核心题 × 前 2 保密种子，托管）")
    if a:
        out.append(f"- A gkagent-expectimax（GKMS PIMC eval, worlds=6）: n={len(a)} 均分 {statistics.mean(a.values()):,.0f}")
    if b:
        out.append(f"- B gkagent-ex-seed（自锁种子+全知GNRPA/tail）: n={len(b)} 均分 {statistics.mean(b.values()):,.0f}")
    pairs = sorted(set(a) & set(b))
    if pairs:
        da = statistics.mean([a[k] for k in pairs])
        db = statistics.mean([b[k] for k in pairs])
        deltas = [b[k] - a[k] for k in pairs]
        wins = sum(1 for d in deltas if d > 0)
        out.append(f"- 配对 {len(pairs)} 局：A {da:,.0f} / B {db:,.0f}，B−A 平均 {statistics.mean(deltas):+,.0f}，"
                   f"B 胜 {wins}/{len(pairs)}（{wins / len(pairs):.0%}）")
    out.append("")

out.append("## B seed-lock 统计（stderr 每局一行）")
for s in ("b_hif", "b_hajime"):
    lines = locklines.get(s, [])
    if not lines:
        continue
    locked = [l for l in lines if l.startswith("locked turn")]
    turns = [int(re.match(r"locked turn (\d+)", l).group(1)) for l in locked]
    scans = [float(x) for l in lines for x in re.findall(r"scan ([\d.]+)s", l)]
    lost = [l for l in lines if "lost turn" in l]
    out.append(f"- {s}: {len(locked)}/{len(lines)} 局锁定"
               + (f"，锁定回合分布 {dict(sorted(((t, turns.count(t)) for t in set(turns))))}" if turns else "")
               + (f"，失锁 {len(lost)}" if lost else "")
               + (f"，扫描耗时中位 {statistics.median(scans):.2f}s" if scans else ""))
out.append("")

out.append("## 错误 / 超时（服务器 episode 记录）")
runs_all = C.get("/api/runs").json()
for s, ev in evs.items():
    rr = next((r for r in runs_all if ev in str(r.get("run"))), None)
    if not rr:
        continue
    eps = C.get(f"/api/runs/{rr['run']}").json().get("episodes") or []
    errs = [e for e in eps if e.get("err")]
    over = sum(int(e.get("over_steps") or 0) for e in eps)
    unf = sum(1 for e in eps if not e.get("finished"))
    mx = max((max(e.get("step_ms") or [0]) for e in eps), default=0)
    mean = statistics.mean([e["score"] for e in eps]) if eps else 0
    out.append(f"- {s}: n={len(eps)} 均分 {mean:,.0f} 错误 {len(errs)} 超时步 {over} 未走完 {unf} 最大步 {mx:.0f}ms")
    for e in errs[:3]:
        out.append(f"  - {e.get('id')}#{e.get('seed_index')}: {str(e.get('err'))[:120]}")
out.append("")

out.append("## 榜单上下文（/api/runs，同集合最近运行）")
runs = C.get("/api/runs").json()
want = ("gkagent-expectimax", "gkagent-ex-seed", "gkagent-ei-r13", "gkagent-seedlock", "uihorizon", "pimc", "best-known")
best = {}
for r in runs:
    lab = str(r.get("label") or "")
    if r.get("set") not in ("hif", "hajime") or r.get("kind") != "template":
        continue
    if not any(w in lab.lower() for w in want):
        continue
    key = (r.get("set"), lab)
    n = r.get("episodes") or 0
    if key not in best or n > (best[key].get("episodes") or 0):
        best[key] = r
for (setname, lab), r in sorted(best.items()):
    out.append(f"- {setname} | {lab} | n={r.get('episodes')} | mean={r.get('mean_score'):,.0f} | run={r.get('run')}")

text = "\n".join(out)
(ROOT / "data" / "_f2ex2_report.md").write_text(text, encoding="utf-8")
print(text)