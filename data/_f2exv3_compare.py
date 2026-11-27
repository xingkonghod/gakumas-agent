"""f2-exv3 托管逐局对比：v3 vs v2（服务器 runs API，同 (id, seed_index) 配对）+ **oracle 比例分层**。
报均值 / 分布 / 崩局(<50%配对max) / 胜负平 / bootstrap CI / over_steps；并按 v2 相对 best-known oracle
比例分层（[0,.2)/[.2,.4)/...）报每层 mean Δ，重点看最低比例题（最大提升空间）是否被 v3 抬升。
轻量网络探针（不加载引擎），可在托管跑中/跑后使用。探针不提交。

用法：.venv\\Scripts\\python.exe data\\_f2exv3_compare.py [v3_run_substring]
"""
from __future__ import annotations

import json
import random
import statistics
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
    if n == 0:
        return (0.0, 0.0)
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
        out[k] = {"score": int(e["score"]), "over": int(e.get("over_steps") or 0),
                  "decisions": int(e.get("decisions") or 0), "secs": e.get("secs"), "err": e.get("err")}
    return out


def fetch_oracle(c):
    runs = c.get("/api/runs", timeout=120).raise_for_status().json()
    rows = runs if isinstance(runs, list) else runs.get("runs", [])
    bk = [r["run"] for r in rows if r.get("run", "").endswith("hif-template-best-known")]
    oracle = {}
    for rn in bk:
        for e in c.get(f"/api/runs/{rn}", timeout=120).raise_for_status().json().get("episodes") or []:
            k = (e.get("id"), int(e.get("seed_index")))
            s = e.get("score")
            if s is not None and (k not in oracle or s > oracle[k]):
                oracle[k] = s
    return oracle, len(bk)


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else "gkagent-ex-seed-v3"
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
            if lab in ("gkagent-ex-seed-v3", "gkagent-ex-seed-v2", "gkagent-ex-seed", "gkagent-seedlock"):
                by_label.setdefault(lab, []).append(r)
        picks = {}
        for lab, rs in by_label.items():
            rs.sort(key=lambda r: r.get("finished") or r.get("started") or "", reverse=True)
            picks[lab] = rs[0]
            print(f"{lab}: run {rs[0]['run']} (n runs={len(rs)})", flush=True)
        if want not in picks:
            raise SystemExit(f"no run for {want}")
        data = {lab: episodes(c, r["run"]) for lab, r in picks.items()}
        oracle, n_bk = fetch_oracle(c)
    print(f"oracle pairs: {len(oracle)} (from {n_bk} best-known farm runs)", flush=True)
    v3 = data[want]
    print(f"\n{want} episodes finished: {len(v3)}", flush=True)
    print("v3 dist:", json.dumps(dist([x["score"] for x in v3.values()])), flush=True)
    print(f"v3 over_steps total: {sum(x['over'] for x in v3.values())}; "
          f"episodes with over>0: {sum(1 for x in v3.values() if x['over'])}; "
          f"errors: {sum(1 for x in v3.values() if x['err'])}", flush=True)
    out = {"core_n": len(core), "v3_run": picks[want]["run"], "v3_n": len(v3),
           "v3_dist": dist([x["score"] for x in v3.values()]), "oracle_n": len(oracle), "pairs": {}}

    # oracle 比例（v3 与 v2 各自）
    def ratios(scores):
        rr = []
        for k, x in scores.items():
            o = oracle.get(k)
            if o and o > 0:
                rr.append((x["score"] / o, k[0], k[1], x["score"], o))
        return rr
    v3r = ratios(v3)
    if v3r:
        out["v3_ratio_mean"] = round(statistics.mean(r[0] for r in v3r), 4)
        out["v3_ratio_median"] = round(statistics.median(r[0] for r in v3r), 4)
        print(f"v3 oracle ratio mean={out['v3_ratio_mean']:.3f} median={out['v3_ratio_median']:.3f}", flush=True)

    for lab, other in data.items():
        if lab == want:
            continue
        common = sorted(set(v3) & set(other))
        if not common:
            continue
        deltas = [v3[k]["score"] - other[k]["score"] for k in common]
        lo, hi = boot_ci(deltas)
        collapse_v3 = sum(1 for k in common if v3[k]["score"] < 0.5 * max(v3[k]["score"], other[k]["score"]))
        collapse_ot = sum(1 for k in common if other[k]["score"] < 0.5 * max(v3[k]["score"], other[k]["score"]))
        rep = {"n_paired": len(common), "mean_delta": round(sum(deltas) / len(deltas), 1),
               "ci95": [lo, hi],
               "win": sum(1 for d in deltas if d > 0), "loss": sum(1 for d in deltas if d < 0),
               "tie": sum(1 for d in deltas if d == 0),
               "collapse_v3": collapse_v3, "collapse_other": collapse_ot,
               "v3_mean_paired": round(sum(v3[k]["score"] for k in common) / len(common), 1),
               "other_mean_paired": round(sum(other[k]["score"] for k in common) / len(common), 1),
               "v3_over_steps": sum(v3[k]["over"] for k in common),
               "other_over_steps": sum(other[k]["over"] for k in common),
               "worst5": sorted(((v3[k]["score"] - other[k]["score"], k[0], k[1]) for k in common))[:5],
               "best5": sorted(((v3[k]["score"] - other[k]["score"], k[0], k[1]) for k in common), reverse=True)[:5]}
        # oracle 比例分层（按 other=v2 的比例分桶）
        if lab == "gkagent-ex-seed-v2":
            buckets = [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.0), (1.0, 99)]
            strat = {}
            for blo, bhi in buckets:
                ks = [k for k in common if oracle.get(k) and oracle[k] > 0
                      and blo <= other[k]["score"] / oracle[k] < bhi]
                if not ks:
                    continue
                ds = [v3[k]["score"] - other[k]["score"] for k in ks]
                clo, chi = boot_ci(ds)
                strat[f"[{blo:.0%},{bhi:.0%})"] = {
                    "n": len(ks), "mean_delta": round(sum(ds) / len(ds), 1), "ci95": [clo, chi],
                    "v2_mean": round(sum(other[k]["score"] for k in ks) / len(ks), 1),
                    "v3_mean": round(sum(v3[k]["score"] for k in ks) / len(ks), 1),
                    "win": sum(1 for d in ds if d > 0), "loss": sum(1 for d in ds if d < 0)}
            rep["oracle_strata_by_v2_ratio"] = strat
            # 最低比例 20 题逐局（v2 比例升序）
            low = sorted(((other[k]["score"] / oracle[k], k[0], k[1], other[k]["score"],
                           v3[k]["score"], oracle[k]) for k in common if oracle.get(k) and oracle[k] > 0))[:20]
            rep["lowest20_by_v2_ratio"] = [
                {"id": i, "slot": s, "v2_ratio": round(r, 3), "v2": v2s, "v3": v3s, "oracle": o,
                 "delta": v3s - v2s, "v3_ratio": round(v3s / o, 3)} for (r, i, s, v2s, v3s, o) in low]
            print("\noracle strata (by v2 ratio):", json.dumps(strat, ensure_ascii=False), flush=True)
        out["pairs"][lab] = rep
        print(f"\nvs {lab} (paired n={len(common)}):", json.dumps(rep, ensure_ascii=False), flush=True)
    p = ROOT / "data" / "_f2exv3_compare.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved:", p, flush=True)


if __name__ == "__main__":
    main()