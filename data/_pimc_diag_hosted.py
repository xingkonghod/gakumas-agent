"""pimc-opt 探针①：托管 expectimax 超时根因诊断（只读服务器 API，不起托管）。

拉 /api/runs 里 gkagent-expectimax 的 hif run，逐局逐步分析 over_steps（>6050ms）：
- 分布：按题 / 按步序（早中晚）/ 按回合 / step_ms 分桶
- 若服务器存 algo_meta：worlds_s（取世界网络往返）vs seconds_per_search×waves（搜索）归因
输出 data/_pimc_diag_hosted.json。探针不提交。
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx

ROOT = Path(r"D:\Games\gakumas-agent")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERVER = "https://hiro.matto.top/gkbench"
TOK = (Path.home() / ".config/gkbench/token").read_text().strip()
C = httpx.Client(base_url=SERVER, headers={"Authorization": f"Bearer {TOK}"}, timeout=120)

runs = C.get("/api/runs").json()
ex = [r for r in runs if "expectimax" in str(r.get("label", "")).lower() and r.get("set") == "hif"]
print("expectimax hif runs:")
for r in ex:
    print(f"  {r.get('run')}  n={r.get('episodes')}  mean={r.get('mean_score')}")

out = {"runs": []}
for r in ex:
    j = C.get(f"/api/runs/{r['run']}").json()
    eps = j.get("episodes") or []
    if not eps:
        continue
    info = {"run": r["run"], "n": len(eps), "mean": round(statistics.mean(e["score"] for e in eps)),
            "over_total": sum(int(e.get("over_steps") or 0) for e in eps),
            "errors": sum(1 for e in eps if e.get("err")),
            "unfinished": sum(1 for e in eps if not e.get("finished"))}
    # 逐步统计
    by_problem = defaultdict(lambda: [0, 0, 0])   # pid -> [games, steps, over]
    over_turn = Counter()
    over_idx_bucket = Counter()
    ms_buckets = Counter()
    over_ms_list = []
    meta_keys = Counter()
    over_meta = []
    step_fields = Counter()
    for e in eps:
        pid = e.get("id")
        sms = e.get("step_ms") or []
        by_problem[pid][0] += 1
        by_problem[pid][1] += len(sms)
        steps = e.get("steps") or []
        if steps:
            step_fields.update(steps[0].keys())
        for i, ms in enumerate(sms):
            ms_buckets["<=2000" if ms <= 2000 else "2000-4000" if ms <= 4000 else "4000-6050" if ms <= 6050
                       else "6050-8000" if ms <= 8000 else "8000-12000" if ms <= 12000 else ">12000"] += 1
            if ms > 6050:
                by_problem[pid][2] += 1
                over_ms_list.append(ms)
                over_idx_bucket[f"step{i // 10 * 10}-{i // 10 * 10 + 9}"] += 1
                st = steps[i] if i < len(steps) else {}
                if st:
                    over_turn[st.get("turn")] += 1
                    m = st.get("algo_meta") or {}
                    meta_keys.update(m.keys())
                    over_meta.append({"pid": pid, "slot": e.get("seed_index"), "i": i, "ms": ms,
                                      "turn": st.get("turn"), "worlds": st.get("worlds"),
                                      "worlds_s": m.get("worlds_s"), "sec": m.get("seconds_per_search"),
                                      "mode": m.get("mode"), "n_expected": len(m.get("expected") or {}),
                                      "hard": m.get("hard_rule"), "err": m.get("error")})
    info["ms_buckets"] = dict(ms_buckets)
    info["over_ms"] = {"n": len(over_ms_list), "mean": round(statistics.mean(over_ms_list)) if over_ms_list else 0,
                       "med": round(statistics.median(over_ms_list)) if over_ms_list else 0,
                       "max": max(over_ms_list) if over_ms_list else 0}
    info["over_turn"] = dict(sorted(over_turn.items(), key=lambda kv: (kv[0] is None, kv[0])))
    info["over_idx_bucket"] = dict(sorted(over_idx_bucket.items()))
    info["step_fields"] = dict(step_fields)
    info["meta_keys"] = dict(meta_keys)
    top = sorted(by_problem.items(), key=lambda kv: -kv[1][2])[:20]
    info["top_over_problems"] = [{"pid": p, "games": g, "steps": s, "over": o} for p, (g, s, o) in top]
    info["over_meta_sample"] = over_meta[:60]
    # worlds_s 归因（若有 meta）
    ws = [m["worlds_s"] for m in over_meta if m.get("worlds_s") is not None]
    if ws:
        info["over_worlds_s"] = {"mean": round(statistics.mean(ws), 3), "med": round(statistics.median(ws), 3),
                                 "max": round(max(ws), 3),
                                 "gt2s": sum(1 for x in ws if x > 2), "gt4s": sum(1 for x in ws if x > 4)}
    out["runs"].append(info)
    print(json.dumps({k: v for k, v in info.items() if k not in ("over_meta_sample", "top_over_problems")},
                     ensure_ascii=False))
    print("top over problems:", json.dumps(info["top_over_problems"][:10], ensure_ascii=False))

(ROOT / "data" / "_pimc_diag_hosted.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("saved data/_pimc_diag_hosted.json")