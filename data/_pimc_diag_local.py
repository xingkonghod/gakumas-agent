"""pimc-opt 探针④：本地真实裁判逐步计时分解（原版 expectimax，零改动）。

用 algo 自带 meta（worlds_s / seconds_per_search / worlds / expected）分解每步耗时：
  jobs = n_actions × worlds；waves = ceil(jobs/threads)
  predicted_search = waves × sec；overhead = decide_ms − worlds_s×1000 − predicted_search
本地无网络、低竞争 → 量「结构性超时」（overhead×waves + 预算头寸不足）。
用法：python _pimc_diag_local.py [max_steps] [pids_csv|默认core8+重灾] [seed_tag]
输出 data/_pimc_diag_local.json。探针不提交。
"""
from __future__ import annotations
import importlib.util, json, math, os, random, sys, time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
os.environ.setdefault("GKMSCLIGPU_LIB", str(ROOT / "data" / "GKMSMainWheel" / "GakumasCLI" / "native" / "build" / "gkmscore.dll"))
os.environ.setdefault("GKBENCH_DATA", str(ROOT / "data" / "bench_local"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

SUB = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax"
spec = importlib.util.spec_from_file_location("algo_ex_orig", SUB / "algo.py")
EX = importlib.util.module_from_spec(spec); sys.modules["algo_ex_orig"] = EX
spec.loader.exec_module(EX)

from gkbench import engine
engine.setup()
from gkbench.referee import Referee, IllegalAction
from gkbench.runner import Ctx
from gkbench.save import expand_loadout

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line); saves[str(r.get("id"))] = r

CORE8 = ["AS-2AXJNW8X", "AS-323ADZVK", "AS-8MY3XH4R", "AS-ADDTACFE",
         "AS-227HBGHS", "AS-23D5RE8A", "AS-33JYSHDF", "AS-93WKA9BK"]
TOP_OVER = ["AS-K46XXQEY", "AS-3EW6E6HV", "AS-DS9H9NRD", "AS-3BB4BWTR", "AS-9VEFA9VH",
            "AS-VWAF2GDN", "AS-WNK6ARRZ", "AS-G9JK36BF", "AS-JMYV3PZV", "AS-3ZT8ZKB6"]

max_steps = int(sys.argv[1]) if len(sys.argv) > 1 else 14
pids = (sys.argv[2].split(",") if len(sys.argv) > 2 else CORE8 + TOP_OVER)
pids = [p for p in pids if p in saves]
seed_tag = sys.argv[3] if len(sys.argv) > 3 else "s0"

def seed_for(pid, tag):
    if tag == "s0" and pid in seeds["problems"]:
        return int(seeds["problems"][pid][0]["seed"])
    k = 0 if tag == "s0" else int(tag[1:])
    return random.Random(f"{pid}/pimc/{k}").randrange(1, 1 << 31)

PARAMS = dict(worlds=6, mode="eval", threads=4, margin=0.25, use=0.85, min_sec=0.03, use_prior=0)
BUDGET = 5.0
OVER_MS = BUDGET * 1200 + 50

rows = []
for pid in pids:
    seed = seed_for(pid, seed_tag)
    lo = expand_loadout(saves[pid]["loadout"])
    algo = EX.ExpectimaxAlgo(**PARAMS)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, BUDGET, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/worlds"), algo, seed)
    ctx.obs = ref.obs(); algo.begin(ctx)
    n = 0
    while not ref.finished and n < max_steps:
        ctx.obs = ref.obs()
        turn = ctx.obs["exam"]["turn"]
        nlegal = len(ctx.obs["legal"])
        t0 = time.perf_counter()
        try:
            d = algo.decide(ctx)
        except Exception as e:
            print("decide err", pid, e); break
        ms = (time.perf_counter() - t0) * 1000
        m = d.meta or {}
        ws_s = m.get("worlds_s"); sec = m.get("seconds_per_search"); nw = m.get("worlds")
        nact = len(m.get("expected") or {}) or nlegal
        jobs = nact * (nw or 6); waves = math.ceil(jobs / PARAMS["threads"])
        pred_search = waves * (sec or 0) * 1000
        overhead = ms - (ws_s or 0) * 1000 - pred_search
        rows.append({"pid": pid, "i": n, "turn": turn, "ms": round(ms, 1), "over": ms > OVER_MS,
                     "nlegal": nlegal, "worlds": nw, "sec": sec, "worlds_s": ws_s,
                     "waves": waves, "pred_search_ms": round(pred_search, 1),
                     "overhead_ms": round(overhead, 1), "mode": m.get("mode"), "hard": m.get("hard_rule")})
        try:
            ref.step(d.action)
        except Exception as e:
            print("step err", pid, e); break
        n += 1
    print(f"{pid}: {n} steps, over={sum(1 for r in rows if r['pid']==pid and r['over'])}", flush=True)
    del algo, ref

# 汇总
over = [r for r in rows if r["over"]]
oh = [r["overhead_ms"] for r in rows if r["mode"] == "eval"]
ws = [r["worlds_s"] * 1000 for r in rows if r.get("worlds_s") is not None]
ps = [r["pred_search_ms"] for r in rows if r["mode"] == "eval"]
def stat(xs):
    xs = sorted(xs); n = len(xs)
    if not n: return {}
    return {"n": n, "mean": round(sum(xs)/n,1), "med": round(xs[n//2],1),
            "p90": round(xs[min(n-1,int(0.9*n))],1), "max": round(xs[-1],1)}
summary = {"n_steps": len(rows), "over": len(over), "over_rate": round(len(over)/max(1,len(rows)),4),
           "decide_ms": stat([r["ms"] for r in rows]),
           "worlds_fetch_ms": stat(ws), "pred_search_ms": stat(ps), "overhead_ms": stat(oh),
           "over_by_turn": dict(Counter(r["turn"] for r in over)),
           "over_by_pid": dict(Counter(r["pid"] for r in over)),
           "overhead_by_waves": {w: stat([r["overhead_ms"] for r in rows if r["waves"]==w and r["mode"]=="eval"])
                                 for w in sorted(set(r["waves"] for r in rows))}}
out = {"params": PARAMS, "budget": BUDGET, "pids": pids, "summary": summary, "rows": rows}
(ROOT / "data" / "_pimc_diag_local.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("SUMMARY:", json.dumps(summary, ensure_ascii=False))
print("saved data/_pimc_diag_local.json")