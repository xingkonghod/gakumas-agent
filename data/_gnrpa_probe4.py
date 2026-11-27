"""gnrpa-spec 探针4（不提交）：L3① multi-start prior 下行有界门。

starts=4 恰 1 路带 prior（i=3，sd=182+7919*3）其余 prior=0；RoutePool 单调采纳口径=取 max。
baseline = max(4× prior=0 starts)；multi_mech = max(p0_0,p0_1,p0_2, mech_3)；
multi_distill = max(p0_0,p0_1,p0_2, distill_3)。下行有界：prior 臂再差，pool 仍保 max(前3 prior=0)。
门同 L1：16 题×2 门种子 n=32，transitions=2M/seed sd_i/stab3/drinks=current，bootstrap 10000 CI。
重点：怪物题是否不再灾难负（distill 全局怪物 mean −620k）。
"""
from __future__ import annotations

import ctypes
import gc
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
V3 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v3"
os.environ["GKMS_ROOT"] = str(ROOT / "data" / "GKMSMainWheel")
for k in ("GKMSCLIGPU_LIB", "GKMS_NATIVE_LIB", "UINET_NATIVE_LIB"):
    os.environ[k] = str(V3 / "vendor" / "gkmscore.dll")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))

from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.save import expand_loadout  # noqa: E402
from GakumasCLI.scenario.hif import build_hif_loadout_session  # noqa: E402
from GakumasCLI.scenario import policy_search as PS  # noqa: E402

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

LOW12 = ["AS-3G6FFZZT", "AS-QV6QCSN9", "AS-P8ZJTXNA", "AS-VH8WYE6J", "AS-5XB2AEHN", "AS-DE36RWPS",
         "AS-BD5EAA22", "AS-DEBX8BX7", "AS-WDKWQYW5", "AS-B38CARVV", "AS-VWAF2GDN", "AS-HTNFZWKG"]
MONSTER5 = ["AS-5KZSXANK", "AS-AXME8QK2", "AS-WDKWQYW5", "AS-WNK6ARRZ", "AS-3ZT8ZKB6"]
PIDS = sorted(set(LOW12) | set(MONSTER5))
TRANS = 2_000_000
SD = [182 + 7919 * i for i in range(4)]   # v3 _pool_search sd 公式（pool.seed=182, pool.n=0）


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_mb():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1048576


def wait_free(min_mb=900):
    while free_mb() < min_mb:
        print(f"  [mem] free {free_mb():.0f}MB <{min_mb}, sleep 60s", flush=True)
        time.sleep(60)


def gate_seeds(pid):
    out = []
    if pid in seeds["problems"]:
        out.append(int(seeds["problems"][pid][0]["seed"]))
    k0 = 1 if pid in seeds["problems"] else 0
    for k in range(k0, 2):
        out.append(random.Random(f"{pid}/exv3/{k}").randrange(1, 1 << 31))
    return out[:2]


def search(ns, sess, prior, sd):
    ns._cache = None
    ns._root_prior = None
    path, st = ns.policy_search(sess, transitions=TRANS, seed=sd, variant="gnrpa",
                                stabilization=3, prior=prior)
    return int(st["best_score"]), int(st["status"]), int(st["expansions"])


def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return [0.0, 0.0]
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return [means[int(0.025 * iters)], means[int(0.975 * iters)]]


def ab(by, pairs, nm, base="baseline"):
    deltas = [by[(p, s, nm)] - by[(p, s, base)] for (p, s) in pairs]
    lo, hi = boot_ci(deltas)
    return {"n": len(deltas), "mean_delta": round(sum(deltas) / len(deltas), 1),
            "ci95": [lo, hi], "pos": sum(d > 0 for d in deltas), "neg": sum(d < 0 for d in deltas),
            "zero": sum(d == 0 for d in deltas),
            "per_pair": {f"{p}/{s}": d for (p, s), d in zip(pairs, deltas)}}


def main():
    wait_free()
    nat, ns = engine.native()
    master = engine.master()
    distill = PS.load_prior(str(ROOT / "data" / "_gnrpa_prior_distill.json"))
    mech = PS.load_prior(str(ROOT / "data" / "_gnrpa_prior_mech.json"))
    pairs, low_pairs, mon_pairs = [], [], []
    pid_seeds = {}
    for pid in PIDS:
        ss = gate_seeds(pid)
        pid_seeds[pid] = ss
        for s in ss:
            pairs.append((pid, s))
            (mon_pairs if pid in MONSTER5 else low_pairs).append((pid, s))
    by, rows = {}, []
    for (pid, seed) in pairs:
        wait_free()
        lo = expand_loadout(saves[pid]["loadout"])
        sess, _ = build_hif_loadout_session(master, lo, seed)
        p0 = []
        for i in range(4):
            b, status, exp = search(ns, sess, None, SD[i])
            p0.append(b)
            rows.append({"pid": pid, "seed": seed, "arm": f"p0_{i}", "sd": SD[i], "best": b,
                         "status": status, "expansions": exp})
        bm, sm, em = search(ns, sess, mech, SD[3])
        bd, sd_, ed = search(ns, sess, distill, SD[3])
        rows.append({"pid": pid, "seed": seed, "arm": "mech_3", "sd": SD[3], "best": bm, "status": sm, "expansions": em})
        rows.append({"pid": pid, "seed": seed, "arm": "distill_3", "sd": SD[3], "best": bd, "status": sd_, "expansions": ed})
        baseline = max(p0)
        multi_mech = max(p0[0], p0[1], p0[2], bm)
        multi_distill = max(p0[0], p0[1], p0[2], bd)
        by[(pid, seed, "baseline")] = baseline
        by[(pid, seed, "multi_mech")] = multi_mech
        by[(pid, seed, "multi_distill")] = multi_distill
        by[(pid, seed, "p0_3")] = p0[3]
        print(f"[L3] {pid}/{seed} base={baseline:,} p0_3={p0[3]:,} mech_3={bm:,}(s{sm}) "
              f"distill_3={bd:,}(s{sd_}) mM={multi_mech:,} mD={multi_distill:,}", flush=True)
        del sess
        gc.collect()
    summary = {}
    for nm in ("baseline", "multi_mech", "multi_distill"):
        vals = [by[(p, s, nm)] for (p, s) in pairs]
        summary[nm] = {"mean_best": round(sum(vals) / len(vals), 1)}
    abres = {}
    for nm in ("multi_mech", "multi_distill"):
        abres[nm] = {"overall": ab(by, pairs, nm), "low": ab(by, low_pairs, nm),
                     "monster": ab(by, mon_pairs, nm)}
    out = {"trans": TRANS, "sd": SD, "pids": PIDS, "pid_seeds": pid_seeds,
           "rows": rows, "summary": summary, "ab": abres}
    (ROOT / "data" / "_gnrpa_gateL3.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False), flush=True)
    for nm, v in abres.items():
        for stratum, b in v.items():
            print(f"AB {nm} {stratum}: mean={b['mean_delta']:,.0f} ci={[round(x) for x in b['ci95']]} "
                  f"p/n/z={b['pos']}/{b['neg']}/{b['zero']}", flush=True)
    print("saved data/_gnrpa_gateL3.json", flush=True)


if __name__ == "__main__":
    main()