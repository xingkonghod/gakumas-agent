"""pscale 离线配对门：gkagent-expectimax（原版 531k 口径基线）vs gkagent-expectimax-scale
（worlds×threads 搜索规模杠杆，fast u70+anytime 基）+ 原版 u85 单变量分离臂。

承 §14 pimc-opt 实证口径（data/_pimc_pair.py）：本地真实裁判无网络 over=0，故每步额外
RTT overlay 仿真托管 serverMs（server/hosted.go:179：serverMs=time.Since(obs_sent)−WorldsMs，
网络往返不补偿）：rtt = 0.9 + expovariate(1/0.45)（均值~1.35s），step_ms=decide_ms+rtt*1000，
over 阈值 5×1200+50=6050ms。overlay 对同 (题,种子,步) 全配置一致（配对）。分数=真实裁判终局分。
同 seed 背靠背（pair-major，块内各配置顺序跑）+ bootstrap 10000 CI（种子 20261126）。

子集：screen 6 题 ∪ 托管 over 重灾 4 题 = 7 题 ×2 seed = 14 配对（种子派生同 gate2）。
门：均分 Δ CI95 下界 > 0 且 over 不恶化（Δover≤0）。并发 ≤2 局；free<0.9GB sleep60 自节流。
断点续跑：rows jsonl 逐局 append，重启跳过已完成 pair 块。探针不提交。

用法：python _pscale_pair.py [configs_csv|all] [tag] [pids_csv|subset7] [nseed] [maxdec]
"""
from __future__ import annotations
import ctypes, importlib.util, json, os, random, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(r"D:\Games\gakumas-agent")
os.environ.setdefault("GKMS_ROOT", str(ROOT / "data" / "GKMSMainWheel"))
os.environ.setdefault("GKMSCLIGPU_LIB", str(ROOT / "data" / "GKMSMainWheel" / "GakumasCLI" / "native" / "build" / "gkmscore.dll"))
os.environ.setdefault("GKBENCH_DATA", str(ROOT / "data" / "bench_local"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

SUB_O = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax"
SUB_S = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-expectimax-scale"
def _load(nm, p):
    sp = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(sp)
    sys.modules[nm] = m; sp.loader.exec_module(m); return m
ORIG = _load("algo_ex_orig_ps", SUB_O / "algo.py")
SCALE = _load("algo_ex_scale_ps", SUB_S / "algo.py")
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

SCREEN6 = ["AS-227HBGHS", "AS-ADDTACFE", "AS-33JYSHDF", "AS-K46XXQEY", "AS-3EW6E6HV", "AS-DS9H9NRD"]
OVER4 = ["AS-K46XXQEY", "AS-3EW6E6HV", "AS-DS9H9NRD", "AS-3BB4BWTR"]
SUBSET7 = SCREEN6 + [p for p in OVER4 if p not in SCREEN6]   # 7 题（screen6 ∪ 重灾4）

BASE = dict(mode="eval", margin=0.25, min_sec=0.03, use_prior=0)
def _grid(cls, use, anytime):
    out = {}
    for w in (6, 12, 24, 32):
        for t in (4, 8, 16):
            nm = f"w{w}t{t}" + ("" if cls == "scale" else "_o")
            out[nm] = {"cls": cls, "params": {**BASE, "worlds": w, "threads": t, "use": use, "anytime": anytime}}
    return out
CONFIGS = {"orig": {"cls": "orig", "params": {**BASE, "worlds": 6, "threads": 4, "use": 0.85}}}
CONFIGS.update(_grid("scale", 0.70, 1))                      # fast 基 u70+anytime 全网格 12
CONFIGS.update({k: v for k, v in _grid("orig", 0.85, 0).items()
                if k in ("w12t4_o", "w32t4_o", "w32t16_o")})  # 原版 u85 无 anytime 分离臂 3
ORDER = ["orig"] + [f"w{w}t{t}" for w in (6, 12, 24, 32) for t in (4, 8, 16)] + ["w12t4_o", "w32t4_o", "w32t16_o"]

def make(cfg):
    c = CONFIGS[cfg]
    cls = ORIG.ExpectimaxAlgo if c["cls"] == "orig" else SCALE.ExpectimaxAlgo
    return cls(**c["params"])

def seed_for(pid, k):
    if k == 0 and pid in seeds["problems"]:
        return int(seeds["problems"][pid][0]["seed"])
    return random.Random(f"{pid}/pimc/{k}").randrange(1, 1 << 31)

BUDGET = 5.0; OVER_MS = BUDGET * 1200 + 50
RTT_MEAN = 0.45; MAXDEC = int(sys.argv[5]) if len(sys.argv) > 5 else 300

def rtt_overlay(pid, seed, i):
    rng = random.Random(f"{pid}/{seed}/rtt/{i}")
    return 0.9 + rng.expovariate(1.0 / RTT_MEAN)

class _MSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
def free_gb():
    st = _MSEX(); st.dwLength = ctypes.sizeof(st)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / 2**30
def mem_guard():
    while free_gb() < 0.9:
        print(f"  [mem] free={free_gb():.2f}GB<0.9 sleep60", flush=True)
        time.sleep(60)

def play(pid, seed, cfg):
    mem_guard()
    lo = expand_loadout(saves[pid]["loadout"])
    algo = make(cfg); ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, BUDGET, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/worlds"), algo, seed)
    ctx.obs = ref.obs(); algo.begin(ctx)
    dts, dtdec, overs, n, err = [], [], 0, 0, None
    wss, jfrac, secs = [], [], []
    while not ref.finished and n < MAXDEC:
        ctx.obs = ref.obs()
        t0 = time.perf_counter()
        try:
            d = algo.decide(ctx)
        except Exception as e:
            err = f"decide {type(e).__name__}: {e}"; break
        decide_ms = (time.perf_counter() - t0) * 1000
        rtt = rtt_overlay(pid, seed, n)
        step_ms = decide_ms + rtt * 1000
        time.sleep(rtt)
        dts.append(step_ms); dtdec.append(decide_ms); overs += 1 if step_ms > OVER_MS else 0
        mt = d.meta or {}
        if "worlds_s" in mt: wss.append(mt["worlds_s"])
        if "jobs_total" in mt and mt["jobs_total"]: jfrac.append(mt.get("jobs_done", 0) / mt["jobs_total"])
        if "seconds_per_search" in mt: secs.append(mt["seconds_per_search"])
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
           "decide_ms_mean": round(sum(dtdec)/len(dtdec)) if dtdec else 0,
           "worlds_s_mean": round(sum(wss)/len(wss), 3) if wss else None,
           "jobs_frac_mean": round(sum(jfrac)/len(jfrac), 3) if jfrac else None,
           "sec_per_search_mean": round(sum(secs)/len(secs), 3) if secs else None}
    del algo, ref
    return row

def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed); n = len(deltas)
    if n == 0: return (0.0, 0.0)
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return means[int(0.025*iters)], means[int(0.975*iters)]

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = ORDER if arg == "all" else [c for c in arg.split(",") if c in CONFIGS]
    tag = sys.argv[2] if len(sys.argv) > 2 else "gate"
    pids = (sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] != "subset7" else SUBSET7)
    pids = [p for p in pids if p in saves]
    nseed = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    if "orig" not in names: names.insert(0, "orig")
    pairs = [(pid, seed_for(pid, k)) for pid in pids for k in range(nseed)]
    rowsf = ROOT / "data" / f"_pscale_rows_{tag}.jsonl"
    done = {}
    if rowsf.exists():
        with rowsf.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line); done.setdefault((r["pid"], r["seed"]), set()).add(r["cfg"])
    todo = [pr for pr in pairs if not set(names) <= done.get(pr, set())]
    print(f"configs={len(names)} pids={len(pids)} pairs={len(pairs)} todo={len(todo)} rtt={RTT_MEAN} "
          f"free={free_gb():.2f}GB cpu={os.cpu_count()} maxdec={MAXDEC}", flush=True)
    lock = threading.Lock()
    t_start = time.time()
    def run_pair(pair):
        pid, seed = pair
        rs = []
        for nm in names:
            r = play(pid, seed, nm)
            rs.append(r)
            with lock:
                with rowsf.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  {pid} s{seed} {nm}: score={r['score']:,} ov={r['over_steps']} "
                  f"dec={r['decide_ms_mean']}ms step={r['step_ms_mean']}ms n={r['decisions']} "
                  f"err={r['err']} [{(time.time()-t_start)/60:.1f}min]", flush=True)
        return rs
    with ThreadPoolExecutor(2) as pool:   # 任务限 ≤2 局并发
        list(pool.map(run_pair, todo))

    allrows = []
    with rowsf.open(encoding="utf-8") as f:
        for line in f:
            allrows.append(json.loads(line))
    by = {(r["pid"], r["seed"], r["cfg"]): r for r in allrows}
    pairs = [pr for pr in pairs if all((p, s, nm) in by for nm in names for p, s in [pr])]
    summary = {}
    for nm in names:
        rs = [by[(p, s, nm)] for (p, s) in pairs]
        summary[nm] = {"mean_score": round(sum(r["score"] for r in rs)/len(rs)),
                       "over_steps": sum(r["over_steps"] for r in rs),
                       "step_ms_mean": round(sum(r["step_ms_mean"] for r in rs)/len(rs)),
                       "step_ms_max": max(r["step_ms_max"] for r in rs),
                       "decide_ms_mean": round(sum(r["decide_ms_mean"] for r in rs)/len(rs)),
                       "worlds_s_mean": round(sum(r["worlds_s_mean"] or 0 for r in rs)/len(rs), 3),
                       "jobs_frac_mean": round(sum(r["jobs_frac_mean"] or 1 for r in rs)/len(rs), 3),
                       "errors": sum(1 for r in rs if r["err"] or not r["finished"])}
    ab = {}
    for nm in names:
        if nm == "orig": continue
        deltas = [by[(p, s, nm)]["score"] - by[(p, s, "orig")]["score"] for (p, s) in pairs]
        do = [by[(p, s, nm)]["over_steps"] - by[(p, s, "orig")]["over_steps"] for (p, s) in pairs]
        lo, hi = boot_ci(deltas)
        ab[nm] = {"n": len(deltas), "mean_delta": round(sum(deltas)/len(deltas), 1),
                  "ci95": [round(lo, 1), round(hi, 1)],
                  "pos": sum(1 for d in deltas if d > 0), "neg": sum(1 for d in deltas if d < 0),
                  "zero": sum(1 for d in deltas if d == 0),
                  "over_delta_total": sum(do),
                  "gate_pass": (lo > 0 and sum(do) <= 0),
                  "over_improved": sum(do) < 0,
                  "per_pair": {f"{p}/{s}": d for (p, s), d in zip(pairs, deltas)}}
    out = {"task": "pscale worlds×threads 搜索规模杠杆门", "configs": {nm: CONFIGS[nm] for nm in names},
           "pids": pids, "rtt_mean": RTT_MEAN, "rtt_base": 0.9, "over_ms": OVER_MS, "budget": BUDGET,
           "gate": "ci95_lo>0 and over_delta<=0", "pairs": pairs, "rows": allrows,
           "summary": summary, "ab_vs_orig": ab,
           "wall_min": round((time.time()-t_start)/60, 1), "cpu": os.cpu_count()}
    op = ROOT / "data" / f"_pscale_{tag}.json"
    op.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False))
    print("AB:", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "per_pair"} for k, v in ab.items()}, ensure_ascii=False))
    print("saved:", op)

if __name__ == "__main__":
    main()