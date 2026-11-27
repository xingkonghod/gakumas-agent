"""gnrpa-spec 探针3（不提交）：L4 管线确认——锁定率/崩局/饮料喝频（搜索级门已答采纳问题）。

前提修正：v3 session.drinks 非空（loadout drink_ids 直通），原生 GNRPA 已搜全部饮料。
本探针在真实 Referee obs 管线跑 v3，臂 = current（loadout 全饮料）vs safe（loadout drink_ids
过滤到 SAFE 子集；裁判/算法同 loadout → 一致合法）。2 题 × 1 dev 种子 × 2 臂 = 4 局。
记 lock_turn/seed_found/score/崩局/喝频/饮料 id。内存守卫 free<1000MB sleep60（cap 600s 后谨慎起跑）。
"""
from __future__ import annotations

import ctypes
import gc
import importlib.util
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "data" / "bench_repo"))
V3 = ROOT / "data" / "bench_repo" / "submissions" / "gkagent-ex-seed-v3"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ALGO = _load("algo_exv3_p3", V3 / "algo.py")
from gkbench import engine  # noqa: E402
engine.setup()
from gkbench.referee import Referee, IllegalAction  # noqa: E402
from gkbench.runner import Ctx  # noqa: E402
from gkbench.save import expand_loadout  # noqa: E402

DL = ROOT / "data" / "bench_local" / "gkbench_dl" / "hif"
seeds = json.loads((DL / "seeds.json").read_text(encoding="utf-8"))
saves = {}
with (DL / "saves.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        saves[str(r.get("id"))] = r

SAFE_KINDS = {"extra_plays", "score_buff", "half_cost", "double_cost", "stamina_cost",
              "stamina", "vitality", "aggressive", "impression", "full_power_point",
              "condition", "perfect_condition", "score"}
cat = json.loads((ROOT / "data" / "knowledge" / "drinks.json").read_text(encoding="utf-8"))
SAFE_IDS = {d["id"] for d in cat["drinks"]
            if (ks := [e["kind"] for e in d.get("effects") or []])
            and all(k in SAFE_KINDS for k in ks)
            and (d.get("rng") or {}).get("deterministic") and not (d.get("rng") or {}).get("unknown")}

PIDS = ["AS-3G6FFZZT", "AS-5KZSXANK"]   # 锁定题(含青汁) + 失锁怪物


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


def wait_free(min_mb=1000, cap_s=600):
    t0 = time.perf_counter()
    while free_mb() < min_mb:
        if free_mb() < 600:
            print(f"  [mem] free {free_mb():.0f}MB <600, pause 90s", flush=True)
            time.sleep(90)
            continue
        if time.perf_counter() - t0 > cap_s:
            print(f"  [mem] cap expired free {free_mb():.0f}MB, proceed cautiously", flush=True)
            return
        print(f"  [mem] free {free_mb():.0f}MB <{min_mb}, sleep 60s", flush=True)
        time.sleep(60)


def play(pid, seed, arm):
    lo = expand_loadout(saves[pid]["loadout"])
    full = list(lo.get("drink_ids") or [])
    if arm == "safe":
        lo["drink_ids"] = [d for d in full if d in SAFE_IDS]
    wait_free()
    algo = ALGO.ExSeedV3Algo(procs=16, report=0, forced_play=0, starts=4,
                             lock_trans=2000000, scan_wait_mode="done", vote_sec_cap=2.0)
    ref = Referee(lo, seed)
    ctx = Ctx(ref, ref.loadout_public, 10.0, random.Random(f"{pid}/{seed}/algo"),
              random.Random(f"{pid}/{seed}/world"), algo, seed)
    ctx.obs = ref.obs()
    t0 = time.perf_counter()
    algo.begin(ctx)
    err, n, drink_acts = None, 0, []
    while not ref.finished and n < 300:
        if time.perf_counter() - t0 > 1200:
            err = "wall>1200s"
            break
        ctx.obs = ref.obs()
        try:
            d = algo.decide(ctx)
        except Exception as e:
            err = f"decide {type(e).__name__}: {e}"
            break
        if d.action[0] == "drink":
            drink_acts.append(list(d.action))
        try:
            ref.step(d.action)
        except IllegalAction as e:
            err = f"illegal {e}"
            break
        except Exception as e:
            err = f"step {type(e).__name__}: {e}"
            break
        n += 1
    g = algo.g
    mirror = getattr(g, "mirror", None)
    locked_seed = int(mirror.session.config.seed) if mirror is not None else None
    pool = getattr(algo, "pool", None)
    row = {"pid": pid, "seed": seed, "arm": arm, "loadout_drinks": lo.get("drink_ids"),
           "score": int(ref.score), "finished": bool(ref.finished), "err": err,
           "state": g.state, "lock_turn": g.lock_turn, "seed_found": locked_seed == seed,
           "n_drink_actions": len(drink_acts), "drink_actions": drink_acts,
           "drinks_left": list(ref.battle.session.drinks),
           "target": pool.target if pool else None, "bad_routes": pool.stats["bad_routes"] if pool else None,
           "wall_s": round(time.perf_counter() - t0, 1), "why": g.why}
    print(json.dumps(row, ensure_ascii=False), flush=True)
    del algo, ref
    gc.collect()
    return row


def main():
    rows = []
    for pid in PIDS:
        seed = int(seeds["problems"][pid][0]["seed"]) if pid in seeds["problems"] else 12345
        for arm in ("current", "safe"):
            rows.append(play(pid, seed, arm))
    (ROOT / "data" / "_gnrpa_probe3.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved data/_gnrpa_probe3.json", flush=True)


if __name__ == "__main__":
    main()