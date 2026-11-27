"""pimc-opt 探针⑤：在受控 CPU 竞争下复现托管 over_steps（原版 expectimax）。

机制假设：托管 --parallel 6 × threads 4 = 24 线程 + 其它子智能体 → 有效并行度 < threads，
N 个 job 排空慢于 waves×sec → 总墙钟 > 预算。本地 CPU 空闲时 over=0（探针④已证）。
本探针起 K 个自旋子进程（读 stop 文件自行退出，不强杀）制造竞争，同时跑 3 局原版，量 over 率。
用法：python _pimc_stress.py [spinners] [max_steps] [worlds_delay_s]
输出 data/_pimc_stress.json。探针不提交。
"""
from __future__ import annotations
import importlib.util, json, os, random, subprocess, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
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
from gkbench.referee import Referee
from gkbench.runner import Ctx
from gkbench.save import expand_loadout

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line); saves[str(r.get("id"))] = r

K = int(sys.argv[1]) if len(sys.argv) > 1 else 16
MAXS = int(sys.argv[2]) if len(sys.argv) > 2 else 18
DELAY = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
PIDS = ["AS-K46XXQEY", "AS-3EW6E6HV", "AS-33JYSHDF"]
PARAMS = dict(worlds=6, mode="eval", threads=4, margin=0.25, use=0.85, min_sec=0.03, use_prior=0)
BUDGET = 5.0; OVER_MS = BUDGET * 1200 + 50

STOP = ROOT / "data" / "_pimc_spin_stop"
STOP.write_text("0")
SPIN = ("import time,os,sys\n"
        "p=sys.argv[1]\n"
        "while True:\n"
        "    try:\n"
        "        if open(p).read().strip()=='1': break\n"
        "    except Exception: pass\n"
        "    x=0\n"
        "    for i in range(200000): x+=i*i\n")
spinfile = ROOT / "data" / "_pimc_spin_worker.py"
spinfile.write_text(SPIN)
procs = [subprocess.Popen([sys.executable, str(spinfile), str(STOP)]) for _ in range(K)]
print(f"started {K} spinners, delay={DELAY}s", flush=True)
time.sleep(2)

def play(pid):
    seed = int(seeds["problems"][pid][0]["seed"]) if pid in seeds["problems"] else random.Random(f"{pid}/pimc/0").randrange(1, 1<<31)
    lo = expand_loadout(saves[pid]["loadout"])
    algo = EX.ExpectimaxAlgo(**PARAMS)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, BUDGET, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/worlds"), algo, seed)
    if DELAY > 0:
        orig_worlds = ctx.worlds
        def slow_worlds(k):
            time.sleep(DELAY); return orig_worlds(k)
        ctx.worlds = slow_worlds
    ctx.obs = ref.obs(); algo.begin(ctx)
    rows = []; n = 0
    while not ref.finished and n < MAXS:
        ctx.obs = ref.obs()
        t0 = time.perf_counter()
        d = algo.decide(ctx)
        ms = (time.perf_counter() - t0) * 1000
        m = d.meta or {}
        rows.append({"pid": pid, "i": n, "ms": round(ms,1), "over": ms > OVER_MS,
                     "worlds_s": m.get("worlds_s"), "sec": m.get("seconds_per_search")})
        try: ref.step(d.action)
        except Exception: break
        n += 1
    del algo, ref
    return rows

try:
    with ThreadPoolExecutor(3) as pool:
        allrows = [r for rs in pool.map(play, PIDS) for r in rs]
finally:
    STOP.write_text("1")
    for p in procs:
        p.wait(timeout=15)
    print("spinners stopped", flush=True)

over = [r for r in allrows if r["over"]]
ms = sorted(r["ms"] for r in allrows)
summary = {"spinners": K, "delay": DELAY, "n_steps": len(allrows), "over": len(over),
           "over_rate": round(len(over)/max(1,len(allrows)),4),
           "ms_mean": round(sum(ms)/len(ms)), "ms_med": round(ms[len(ms)//2]),
           "ms_p90": round(ms[min(len(ms)-1,int(0.9*len(ms)))]), "ms_max": round(ms[-1]),
           "over_by_pid": {p: sum(1 for r in over if r["pid"]==p) for p in PIDS}}
(ROOT / "data" / "_pimc_stress.json").write_text(json.dumps({"summary": summary, "rows": allrows}, ensure_ascii=False, indent=1), encoding="utf-8")
print("SUMMARY:", json.dumps(summary, ensure_ascii=False))