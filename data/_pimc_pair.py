"""pimc-opt 离线配对门：gkagent-expectimax（原版）vs gkagent-expectimax-fast（杠杆变体）。

根因（探针①④⑤ + server/hosted.go:179 实证）：托管 over_steps 非 CPU 竞争（22 自旋进程下本地
搜索墙钟仍 4.07s、over=0），而是网络 RTT——serverMs = time.Since(obs_sent) − WorldsMs
= 搜索 + overhead + (obs下载 + action上传 + worlds网络往返)，网络往返不被算法补偿。
本地裁判无网络 → over=0，故本门用「每步额外 RTT _overlay」仿真托管网络（校准到原版 over≈6%），
overlay 对原版/fast 同 (题,种子,步) 完全一致（配对）。分数用真实裁判终局分（不受 overlay 影响，
只经搜索时间变化间接影响）。同 seed 背靠背 + bootstrap 10000 CI（种子 20261126）。

门：over_steps 显著下降 且 均分 Δ CI95 下界 ≥ 0。逐杠杆单变量消融。探针不提交。
用法：python _pimc_pair.py [configs_csv] [tag] [pids_csv|core8+over] [nseed] [rtt_mean] [maxdec]
"""
from __future__ import annotations
import importlib.util, json, math, os, random, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
os.environ.setdefault("GKMSCLIGPU_LIB", str(ROOT / "data" / "GKMSMainWheel" / "GakumasCLI" / "native" / "build" / "gkmscore.dll"))
os.environ.setdefault("GKBENCH_DATA", str(ROOT / "data" / "bench_local"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

SUB_O = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax"
SUB_F = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax-fast"
def _load(nm, p):
    sp = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(sp)
    sys.modules[nm] = m; sp.loader.exec_module(m); return m
ORIG = _load("algo_ex_orig", SUB_O / "algo.py")
FAST = _load("algo_ex_fast", SUB_F / "algo.py")
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
OVER = ["AS-K46XXQEY", "AS-3EW6E6HV", "AS-DS9H9NRD", "AS-3BB4BWTR"]   # 托管 over 重灾（探针①）

# 杠杆配置：orig=原版行为；其余 fast 单变量/组合。anytime=0 复现原版 _eval。
BASE = dict(worlds=6, mode="eval", threads=4, margin=0.25, min_sec=0.03, use_prior=0)
CONFIGS = {
    "orig":    {"cls": "orig", "params": {**BASE, "use": 0.85}},
    "any":     {"cls": "fast", "params": {**BASE, "use": 0.85, "anytime": 1}},
    "u70":     {"cls": "fast", "params": {**BASE, "use": 0.70, "anytime": 1}},
    "u60":     {"cls": "fast", "params": {**BASE, "use": 0.60, "anytime": 1}},
    "u70w4":   {"cls": "fast", "params": {**BASE, "use": 0.70, "anytime": 1, "worlds": 4}},
    "u70es":   {"cls": "fast", "params": {**BASE, "use": 0.70, "anytime": 1, "early_stop": 1}},
    "u70t8":   {"cls": "fast", "params": {**BASE, "use": 0.70, "anytime": 1, "threads": 8}},
    "u80w4":   {"cls": "fast", "params": {**BASE, "use": 0.80, "anytime": 1, "worlds": 4}},
}

def make(cfg):
    c = CONFIGS[cfg]
    cls = ORIG.ExpectimaxAlgo if c["cls"] == "orig" else FAST.ExpectimaxAlgo
    return cls(**c["params"])

def seed_for(pid, k):
    if k == 0 and pid in seeds["problems"]:
        return int(seeds["problems"][pid][0]["seed"])
    return random.Random(f"{pid}/pimc/{k}").randrange(1, 1 << 31)

BUDGET = 5.0; OVER_MS = BUDGET * 1200 + 50
RTT_MEAN = float(sys.argv[5]) if len(sys.argv) > 5 else 0.45   # exp 尾均值；base 0.9 → 总均值~1.35
MAXDEC = int(sys.argv[6]) if len(sys.argv) > 6 else 300

def rtt_overlay(pid, seed, i):
    # 同 (题,种子,步) 对原版/fast 一致；仿真 obs下载+action上传+worlds网络往返（不被补偿部分）
    rng = random.Random(f"{pid}/{seed}/rtt/{i}")
    return 0.9 + rng.expovariate(1.0 / RTT_MEAN)

def play(pid, seed, cfg):
    lo = expand_loadout(saves[pid]["loadout"])
    algo = make(cfg); ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, BUDGET, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/worlds"), algo, seed)
    ctx.obs = ref.obs(); algo.begin(ctx)
    dts, overs, n, err = [], 0, 0, None
    while not ref.finished and n < MAXDEC:
        ctx.obs = ref.obs()
        t0 = time.perf_counter()
        try:
            d = algo.decide(ctx)
        except Exception as e:
            err = f"decide {type(e).__name__}: {e}"; break
        decide_ms = (time.perf_counter() - t0) * 1000
        rtt = rtt_overlay(pid, seed, n)
        step_ms = decide_ms + rtt * 1000          # 仿真服务器 serverMs
        time.sleep(rtt)                            # 真实消耗墙钟（仿真网络占用）
        dts.append(step_ms); overs += 1 if step_ms > OVER_MS else 0
        try:
            ref.step(d.action)
        except IllegalAction as e:
            err = f"illegal {e}"; break
        except Exception as e:
            err = f"step {type(e).__name__}: {e}"; break
        n += 1
    srt = sorted(dts)
    row = {"pid": pid, "seed": seed, "cfg": cfg, "score": int(ref.score), "finished": bool(ref.finished),
           "decisions": n, "err": err, "over_steps": overs,
           "step_ms_mean": round(sum(dts)/len(dts)) if dts else 0,
           "step_ms_max": round(srt[-1]) if srt else 0,
           "step_ms_p95": round(srt[min(len(srt)-1, int(0.95*len(srt)))]) if srt else 0,
           "decide_ms_mean": round(sum(dts)/len(dts) - (0.9+RTT_MEAN)*1000) if dts else 0}
    del algo, ref
    return row

def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed); n = len(deltas)
    if n == 0: return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025*iters)], means[int(0.975*iters)]

def main():
    names = (sys.argv[1] if len(sys.argv) > 1 else "orig,u70").split(",")
    tag = sys.argv[2] if len(sys.argv) > 2 else "gate"
    pids = (sys.argv[3].split(",") if len(sys.argv) > 3 else CORE8 + OVER)
    pids = [p for p in pids if p in saves]
    nseed = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    if "orig" not in names: names.insert(0, "orig")
    pairs = [(pid, seed_for(pid, k)) for pid in pids for k in range(nseed)]
    print(f"configs={names} pids={len(pids)} pairs={len(pairs)} rtt_mean={RTT_MEAN} maxdec={MAXDEC}", flush=True)

    # 每对 (pid,seed) 内各 config 背靠背（配对干净）；不同对之间 ≤3 并发（任务限探针≤3局）
    def run_pair(pair):
        pid, seed = pair
        return [play(pid, seed, nm) for nm in names]
    rows = []
    with ThreadPoolExecutor(3) as pool:
        for rs in pool.map(run_pair, pairs):
            rows.extend(rs)
            r0 = rs[0]
            print(f"  {r0['pid']} s{r0['seed']}: " + " ".join(f"{r['cfg']}={r['score']:,}/ov{r['over_steps']}" for r in rs), flush=True)

    by = {(r["pid"], r["seed"], r["cfg"]): r for r in rows}
    summary = {}
    for nm in names:
        rs = [by[(p, s, nm)] for (p, s) in pairs]
        summary[nm] = {"mean_score": round(sum(r["score"] for r in rs)/len(rs)),
                       "over_steps": sum(r["over_steps"] for r in rs),
                       "step_ms_mean": round(sum(r["step_ms_mean"] for r in rs)/len(rs)),
                       "step_ms_max": max(r["step_ms_max"] for r in rs),
                       "errors": sum(1 for r in rs if r["err"] or not r["finished"])}
    ab = {}
    for nm in names:
        if nm == "orig": continue
        deltas = [by[(p, s, nm)]["score"] - by[(p, s, "orig")]["score"] for (p, s) in pairs]
        do = [by[(p, s, nm)]["over_steps"] - by[(p, s, "orig")]["over_steps"] for (p, s) in pairs]
        lo, hi = boot_ci(deltas)
        ab[nm] = {"n": len(deltas), "mean_delta": round(sum(deltas)/len(deltas), 1),
                  "ci95": [round(lo,1), round(hi,1)],
                  "pos": sum(1 for d in deltas if d > 0), "neg": sum(1 for d in deltas if d < 0),
                  "zero": sum(1 for d in deltas if d == 0),
                  "over_delta_total": sum(do),
                  "gate_pass": (lo >= 0 and sum(do) < 0),
                  "per_pair": {f"{p}/{s}": d for (p, s), d in zip(pairs, deltas)}}
    out = {"configs": {nm: CONFIGS[nm] for nm in names}, "pids": pids, "rtt_mean": RTT_MEAN,
           "pairs": pairs, "rows": rows, "summary": summary, "ab_vs_orig": ab}
    op = ROOT / "data" / f"_pimc_{tag}.json"
    op.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False))
    print("AB:", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "per_pair"} for k, v in ab.items()}, ensure_ascii=False))
    print("saved:", op)

if __name__ == "__main__":
    main()