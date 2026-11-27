"""f2-exv2 托管逐局对比：v2 vs ex-seed / seedlock（服务器 runs API，同 (id, seed_index) 配对）。
报均值 / 分布 min/p10/p25/med/max / 崩局(<50%配对max) / 胜负平 / bootstrap CI / 锁定率 / over_steps。
轻量网络探针（不加载引擎），可在托管跑中/跑后使用。探针不提交。

用法：.venv\\Scripts\\python.exe data\\_f2exv2_compare.py [v2_run_substring]
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

import httpx  # noqa: E402
from gkbench.client import SERVER, _client  # noqa: E402


def dist(xs):
    xs = sorted(xs)
    n = len(xs)
    q = lambda p: xs[min(n - 1, int(p * n))]  # noqa: E731
    return {"n": n, "min": xs[0], "p10": q(0.10), "p25": q(0.25), "med": q(0.50),
            "max": xs[-1], "mean": round(sum(xs) / n, 1)}


def boot_ci(deltas, iters=10000, seed=20261125):
    rng = random.Random(seed)
    n = len(deltas)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def episodes(c, run):
    j = c.get(f"/api/runs/{run}", timeout=120).raise_for_status().json()
    eps = j["episodes"] if isinstance(j, dict) else j
    out = {}
    for e in eps:
        if not e.get("finished"):
            continue
        k = (e["id"], int(e["seed_index"]))
        # 服务器紧凑结构：over_steps/decisions 在 episode 级；无 steps.meta（锁定率从 stderr 报告统计）
        out[k] = {"score": int(e["score"]), "over": int(e.get("over_steps") or 0),
                  "decisions": int(e.get("decisions") or 0),
                  "secs": e.get("secs"), "err": e.get("err")}
    return out


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v2"
    with _client() as c:
        sets = httpx.get(f"{SERVER}/api/sets", timeout=60).raise_for_status().json()
        hif = next(x for x in sets if x.get("set") == "hif")
        core = hif.get("core") or []
        print(f"hif core: {len(core)} problems; core_seeds={hif.get('core_seeds')}", flush=True)
        runs = c.get("/api/runs", timeout=120).raise_for_status().json()
        cand = [r for r in runs if r.get("set") == "hif" and r.get("kind") == "template"]
        by_label = {}
        for r in cand:
            lab = r.get("label") or ""
            if lab in ("gkagent-ex-seed-v2", "gkagent-ex-seed", "gkagent-seedlock"):
                by_label.setdefault(lab, []).append(r)
        picks = {}
        for lab, rs in by_label.items():
            rs.sort(key=lambda r: r.get("finished") or r.get("started") or "", reverse=True)
            picks[lab] = rs[0]
            print(f"{lab}: run {rs[0]['run']} (n runs={len(rs)})", flush=True)
        if want not in picks:
            raise SystemExit(f"no run for {want}")
        data = {lab: episodes(c, r["run"]) for lab, r in picks.items()}
    v2 = data[want]
    print(f"\nv2 episodes finished: {len(v2)}", flush=True)
    print("v2 dist:", json.dumps(dist([x["score"] for x in v2.values()])), flush=True)
    print(f"v2 over_steps total: {sum(x['over'] for x in v2.values())}; "
          f"episodes with over>0: {sum(1 for x in v2.values() if x['over'])}; "
          f"errors: {sum(1 for x in v2.values() if x['err'])}", flush=True)
    out = {"core_n": len(core), "v2_run": picks[want]["run"], "v2_n": len(v2),
           "v2_dist": dist([x["score"] for x in v2.values()]), "pairs": {}}
    for lab, other in data.items():
        if lab == want:
            continue
        common = sorted(set(v2) & set(other))
        if not common:
            continue
        deltas = [v2[k]["score"] - other[k]["score"] for k in common]
        lo, hi = boot_ci(deltas)
        collapse_v2 = sum(1 for k in common if v2[k]["score"] < 0.5 * max(v2[k]["score"], other[k]["score"]))
        collapse_ot = sum(1 for k in common if other[k]["score"] < 0.5 * max(v2[k]["score"], other[k]["score"]))
        rep = {"n_paired": len(common), "mean_delta": round(sum(deltas) / len(deltas), 1),
               "ci95": [lo, hi],
               "win": sum(1 for d in deltas if d > 0), "loss": sum(1 for d in deltas if d < 0),
               "tie": sum(1 for d in deltas if d == 0),
               "collapse_v2": collapse_v2, "collapse_other": collapse_ot,
               "v2_mean_paired": round(sum(v2[k]["score"] for k in common) / len(common), 1),
               "other_mean_paired": round(sum(other[k]["score"] for k in common) / len(common), 1),
               "v2_over_steps": sum(v2[k]["over"] for k in common),
               "other_over_steps": sum(other[k]["over"] for k in common),
               "worst5": sorted(((v2[k]["score"] - other[k]["score"], k[0], k[1]) for k in common))[:5],
               "best5": sorted(((v2[k]["score"] - other[k]["score"], k[0], k[1]) for k in common), reverse=True)[:5]}
        out["pairs"][lab] = rep
        print(f"\nvs {lab} (paired n={len(common)}):", json.dumps(rep, ensure_ascii=False), flush=True)
    p = ROOT / "data" / "_f2exv2_compare.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", p, flush=True)


if __name__ == "__main__":
    main()
