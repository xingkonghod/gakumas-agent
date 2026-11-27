"""f2-norm 结果分析（不提交）：从各模式日志提取 run 名，拉 /api/runs 逐局统计。

均分 / 超时步(over_steps) / 错误局 / 决策数；hajime 按 tags.stage 拆考试/课程。
    .venv\\Scripts\\python.exe data\\_f2norm_analyze.py [mode ...]
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import httpx

ROOT = Path(r"D:\Games\gakumas-agent")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
tok = Path.home().joinpath(".config/gkbench/token").read_text().strip()
c = httpx.Client(base_url="https://hiro.matto.top/gkbench",
                 headers={"Authorization": f"Bearer {tok}"}, timeout=120)
RUN_RE = re.compile(r"template-[a-z]+-gkagent-ei-r13-norm-[a-z0-9]+-xingkonghod-[0-9a-f]{12}")


def run_from_log(mode):
    p = ROOT / "data" / f"_f2norm_run_{mode}.log"
    if not p.is_file():
        return None
    txt = p.read_text(encoding="utf-16", errors="replace")
    m = RUN_RE.search(txt)
    return m.group(0) if m else None


def stats(run):
    r = c.get(f"/api/runs/{run}")
    if r.status_code >= 400:
        return {"error": f"HTTP {r.status_code}"}
    j = r.json()
    eps = j.get("episodes") or j.get("rows") or j.get("summaries") or []
    scores, over, errs, decisions, zero = [], 0, 0, [], 0
    stages = {}
    for e in eps:
        fin = e.get("final") or e
        sc = fin.get("score")
        if isinstance(sc, (int, float)):
            scores.append(sc)
            if sc == 0: zero += 1
        over += int(fin.get("over_steps") or e.get("over_steps") or 0)
        if e.get("err") or fin.get("err"): errs += 1
        if isinstance(fin.get("decisions"), (int, float)): decisions.append(fin["decisions"])
        tags = e.get("tags") or fin.get("tags") or {}
        stage = tags.get("stage", "") if isinstance(tags, dict) else ""
        kind = "exam" if "audition" in stage else ("lesson" if stage else "unknown")
        stages.setdefault(kind, []).append(sc if isinstance(sc, (int, float)) else 0)
    n = len(scores)
    out = {"n": n, "mean": sum(scores) / n if n else 0, "min": min(scores) if n else 0,
           "max": max(scores) if n else 0, "over_steps": over, "err_eps": errs, "zero": zero,
           "decisions": sum(decisions), "stages": {k: (len(v), sum(v) / len(v) if v else 0) for k, v in stages.items()}}
    return out


def main():
    modes = sys.argv[1:] or ["off", "clip2", "clip3", "clip4", "rescale", "both"]
    print(f"{'mode':16s} {'n':>4s} {'mean':>10s} {'min':>8s} {'max':>9s} {'over':>5s} {'err':>4s} {'zero':>5s} {'dec':>6s}  run")
    results = {}
    for mode in modes:
        run = run_from_log(mode)
        if not run:
            print(f"{mode:16s}  (no run name in log)")
            continue
        s = stats(run)
        results[mode] = {"run": run, **s}
        if "error" in s:
            print(f"{mode:16s}  {s['error']}  {run}")
            continue
        print(f"{mode:16s} {s['n']:4d} {s['mean']:10.0f} {s['min']:8.0f} {s['max']:9.0f} "
              f"{s['over_steps']:5d} {s['err_eps']:4d} {s['zero']:5d} {s['decisions']:6d}  {run}")
        if s["stages"] and set(s["stages"]) != {"unknown"}:
            for k, (nn, mm) in sorted(s["stages"].items()):
                print(f"    stage {k:8s} n={nn:3d} mean={mm:10.1f}")
    (ROOT / "data" / "_f2norm_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nsaved -> data/_f2norm_results.json")


if __name__ == "__main__":
    main()