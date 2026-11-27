"""一次性：扫描托管运行每步 algo_meta.error（推理回退）+ 与 uinet 同种子配对对比。"""
import json
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tok = Path.home().joinpath(".config/gkbench/token").read_text().strip()
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": f"Bearer {tok}"}, timeout=120)
OUR = sys.argv[1] if len(sys.argv) > 1 else "template-hif-gkagent-ei-r13-xingkonghod-7b0da3c354fd"
UINET = "20261112-040508-hif-template-uinet-matto"

our = c.get(f"/api/runs/{OUR}").json()
eps = our.get("episodes") or []
print("our episodes:", len(eps))

# 1) 逐步扫描 algo_meta.error / why 回退
n_steps = n_err = n_fallback = 0
err_examples = []
why_counter = {}
cg_applied = cg_ignored = 0
over_steps = 0
scores = []
for i, e in enumerate(eps):
    r = c.get(f"/api/runs/{OUR}/episodes/{e['id']}/{e['seed_index']}")
    if r.status_code != 200:
        print("episode fetch fail", e["id"], e["seed_index"], r.status_code)
        continue
    ep = r.json()
    fin = ep.get("final") or {}
    over_steps += int(fin.get("over_steps") or 0)
    if isinstance(fin.get("score"), (int, float)):
        scores.append(fin["score"])
    for s in ep.get("steps") or []:
        n_steps += 1
        m = s.get("algo_meta") or {}
        cg = m.get("cg_aug")
        if isinstance(cg, list) and len(cg) == 2:
            cg_applied = max(cg_applied, int(cg[0]))
            cg_ignored = max(cg_ignored, int(cg[1]))
        why = str(m.get("why", ""))
        why_counter[why] = why_counter.get(why, 0) + 1
        if "error" in m:
            n_err += 1
            if len(err_examples) < 5:
                err_examples.append((e["id"], e["seed_index"], s.get("i"), m.get("error")))
        if "退回" in why or "异常" in why:
            n_fallback += 1
    if (i + 1) % 60 == 0:
        print(f"  scanned {i+1}/{len(eps)} episodes, steps={n_steps}, errors={n_err}")
print(f"steps scanned: {n_steps}, algo_meta.error: {n_err}, fallback why: {n_fallback}")
print(f"over_steps: {over_steps}, episodes with score: {len(scores)}, "
      f"mean {sum(scores)/max(len(scores),1):,.0f}, zero-score {sum(1 for s in scores if s==0)}")
print(f"cg_aug max per-episode [applied, ignored]: [{cg_applied}, {cg_ignored}]")
print("why distribution:", json.dumps(why_counter, ensure_ascii=False))
print("error examples:", err_examples)

# 2) 与 uinet 同 (题, 种子) 配对
ui = c.get(f"/api/runs/{UINET}").json()
ueps = ui.get("episodes") or []
umap = {(e["id"], e["seed_index"]): e["score"] for e in ueps}
pairs = [(e["score"], umap[(e["id"], e["seed_index"])]) for e in eps
         if (e["id"], e["seed_index"]) in umap]
if pairs:
    import math
    n = len(pairs)
    ours_mean = sum(a for a, b in pairs) / n
    ui_mean = sum(b for a, b in pairs) / n
    wins = sum(1 for a, b in pairs if a > b)
    logratios = [math.log(max(a, 1) / max(b, 1)) for a, b in pairs]
    geomean = math.exp(sum(logratios) / n)
    print(f"paired on {n} (problem,seed): ours mean {ours_mean:,.0f} vs uinet {ui_mean:,.0f}; "
          f"win rate {wins}/{n} = {wins/n:.3f}; geomean ratio ours/uinet = {geomean:.3f}")
else:
    print("no paired episodes found")