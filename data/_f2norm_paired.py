"""f2-norm 配对分析（不提交）：各模式 vs off 逐题逐种子配对差，去题目难度方差。

报告：配对 n / 平均差 / 胜负平 / 配对 t / bootstrap 95% CI。
    .venv\\Scripts\\python.exe data\\_f2norm_paired.py
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import numpy as np
import httpx

ROOT = Path(r"D:\Games\gakumas-agent")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tok = Path.home().joinpath(".config/gkbench/token").read_text().strip()
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": f"Bearer {tok}"}, timeout=120)
RUN_RE = re.compile(r"template-[a-z]+-gkagent-ei-r13-norm-[a-z0-9]+-xingkonghod-[0-9a-f]{12}")


def run_from_log(mode):
    p = ROOT / "data" / f"_f2norm_run_{mode}.log"
    txt = p.read_text(encoding="utf-16", errors="replace") if p.is_file() else ""
    m = RUN_RE.search(txt)
    return m.group(0) if m else None


def scores_by_key(run):
    j = c.get(f"/api/runs/{run}").json()
    out = {}
    for e in j.get("episodes") or []:
        sc = e.get("score")
        if isinstance(sc, (int, float)):
            out[(e.get("id"), e.get("seed_index"))] = sc
    return out


def main():
    modes = ["off", "clip2", "clip3", "clip4", "rescale", "both"]
    data = {}
    for m in modes:
        run = run_from_log(m)
        if run:
            data[m] = scores_by_key(run)
            print(f"loaded {m:10s} n={len(data[m])} run={run}")
    if "off" not in data:
        print("no off baseline"); return
    off = data["off"]
    rng = np.random.default_rng(42)
    print(f"\n{'mode':10s} {'npair':>5s} {'meanΔ':>9s} {'win':>4s} {'loss':>4s} {'tie':>4s} {'t':>7s} {'boot95%CI':>22s}")
    summary = {}
    for m in modes:
        if m == "off" or m not in data:
            continue
        common = sorted(set(off) & set(data[m]))
        d = np.array([data[m][k] - off[k] for k in common], dtype=float)
        n = len(d)
        if n == 0:
            continue
        mean = d.mean()
        win = int((d > 0).sum()); loss = int((d < 0).sum()); tie = int((d == 0).sum())
        sd = d.std(ddof=1) if n > 1 else 0.0
        t = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
        boots = rng.choice(d, size=(4000, n), replace=True).mean(axis=1)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        summary[m] = dict(npair=n, mean_diff=float(mean), win=win, loss=loss, tie=tie,
                          t=float(t), ci=[float(lo), float(hi)])
        print(f"{m:10s} {n:5d} {mean:9.0f} {win:4d} {loss:4d} {tie:4d} {t:7.2f}   [{lo:8.0f}, {hi:8.0f}]")
    (ROOT / "data" / "_f2norm_paired.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved -> data/_f2norm_paired.json")


if __name__ == "__main__":
    main()