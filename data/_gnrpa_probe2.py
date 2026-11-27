"""gnrpa-spec 探针2（不提交）：L1 domain prior（mechanics / 自蒸馏）+ L4 SAFE drinks 搜索级配对门。

前提修正（探针1 实锤）：v3 session.drinks 非空——loadout drink_ids 直通 NativeSession，原生 GNRPA
已搜全部饮料（含青汁 create_random / 苏打 draw）。故 L4 真实杠杆 = 把饮料搜索空间限制到 SAFE 子集
（移除 UNSAFE），门 = safe vs empty（任务书字面）+ safe vs current（实际决策）+ current vs empty。

L1：为 rules=69 重建 domain prior。两路单变量：
  mech   = cf0 特征权重（master 卡表 greedy 价值/费用效率，只 boost 不压制 setup 牌）；
  distill= learn_prior(2M GNRPA 教师路线)，教师种子与门种子不相交（防泄漏），sources 记录口径。
门：低 oracle 12 ∪ monster 5 = 16 题 × 2 门种子（s0 dev + s1 生成 exv3/1），同 transitions=2M /
seed=182 / stab=3，prior 单变量（drinks=current）；L4 drinks 单变量（prior=None）。bootstrap 10000 CI。

用法：python data/_gnrpa_probe2.py [stage: teachers|priors|gate|all]
"""
from __future__ import annotations

import ctypes
import gc
import json
import math
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

SAFE_KINDS = {"extra_plays", "score_buff", "half_cost", "double_cost", "stamina_cost",
              "stamina", "vitality", "aggressive", "impression", "full_power_point",
              "condition", "perfect_condition", "score"}
cat = json.loads((ROOT / "data" / "knowledge" / "drinks.json").read_text(encoding="utf-8"))
SAFE_IDS = set()
for d in cat["drinks"]:
    kinds = [e["kind"] for e in d.get("effects") or []]
    det = bool((d.get("rng") or {}).get("deterministic")) and not (d.get("rng") or {}).get("unknown")
    if kinds and all(k in SAFE_KINDS for k in kinds) and det:
        SAFE_IDS.add(d["id"])


def safe_subset(drinks):
    return [d for d in drinks if d in SAFE_IDS]


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
        print(f"  [mem] free {free_mb():.0f}MB < {min_mb}MB, sleep 60s ...", flush=True)
        time.sleep(60)


def gate_seeds(pid):
    out = []
    if pid in seeds["problems"]:
        out.append((int(seeds["problems"][pid][0]["seed"]), "s0"))
    k0 = 1 if pid in seeds["problems"] else 0
    for k in range(k0, 2):
        out.append((random.Random(f"{pid}/exv3/{k}").randrange(1, 1 << 31), f"s{k}"))
    return out[:2]


def distill_seeds(pid):
    return [(random.Random(f"{pid}/gnrpa-distill/{k}").randrange(1, 1 << 31), f"d{k}") for k in range(2)]


def search(ns, sess, prior, trans=TRANS, sd=182):
    ns._cache = None
    ns._root_prior = None
    t0 = time.perf_counter()
    path, st = ns.policy_search(sess, transitions=int(trans), seed=sd, variant="gnrpa",
                                stabilization=3, prior=prior)
    st["wall"] = round(time.perf_counter() - t0, 3)
    return path, st


def route_of(path):
    """select 入队、其余为路线（learn_prior / hif.build 同口径）。"""
    queue = [list(a[1]) for a in path if a[0] == "select"]
    route = tuple(tuple(a) for a in path if a[0] != "select")
    return queue, route


def replay(sess, queue, route):
    c = sess.clone()
    c.state.select_index_queue = [list(x) for x in queue]
    try:
        for a in route:
            if c.finished:
                break
            c.step(tuple(a), observe=False)
    except Exception:
        return None
    return int(c.state.score) if c.finished else None


# ---- stage: teachers ---------------------------------------------------------
def stage_teachers():
    wait_free()
    nat, ns = engine.native()
    master = engine.master()
    examples, meta = [], []
    for pid in PIDS:
        lo = expand_loadout(saves[pid]["loadout"])
        for (sd, lab) in distill_seeds(pid):
            sess, _ = build_hif_loadout_session(master, lo, sd)
            path, st = search(ns, sess, None)
            queue, route = route_of(path)
            score = replay(sess, queue, route)
            ok = score is not None and score == int(st["best_score"])
            meta.append({"pid": pid, "seed": sd, "lab": lab, "best": int(st["best_score"]),
                         "replay": score, "ok": ok, "n_drink": sum(1 for a in route if a[0] == "drink"),
                         "wall": st["wall"]})
            if ok:
                sess.state.select_index_queue = [list(x) for x in queue]
                examples.append((sess, route))
            print(f"[teacher] {pid}/{lab} best={st['best_score']:,} replay={score} ok={ok} "
                  f"drinks={meta[-1]['n_drink']} {st['wall']}s", flush=True)
            del sess
            gc.collect()
    prior = PS.learn_prior(examples, sources=(
        f"self-distill:gnrpa-{TRANS}-rules69", f"teachers:{len(examples)}/{len(meta)}",
        "drinks:current-full", "seeds:gnrpa-distill/disjoint-from-gate"))
    PS.save_prior(prior, str(ROOT / "data" / "_gnrpa_prior_distill.json"))
    (ROOT / "data" / "_gnrpa_teachers.json").write_text(
        json.dumps({"meta": meta, "n_examples": len(examples), "sources": list(prior.sources),
                    "n_weights": len(prior.weights)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[teachers] examples={len(examples)}/{len(meta)} weights={len(prior.weights)} saved", flush=True)


# ---- stage: priors (mechanics) ----------------------------------------------
def stage_priors():
    nat, ns = engine.native()
    master = engine.master()
    md, strings = nat.md, nat.strings
    # 用一张真 session 解析特征（与 native prior_table 同口径）
    lo = expand_loadout(saves[PIDS[0]]["loadout"])
    sess, _ = build_hif_loadout_session(master, lo, 1)
    feat_val, feat_cost = {}, {}
    for i in range(md.n_cards):
        row = md.cards[i]
        cid, upg = strings[row.id], int(row.upg)
        fake = {"produce_card_id": cid, "base_upgrade_count": upg, "current_upgrade_count": upg,
                "temporary_upgrade_count": 0, "support_upgrade_ids": [], "is_end_turn_lost": False}
        try:
            feat = PS._card_feature(sess, fake)
        except Exception:
            continue
        prow = master.cards.get((cid, upg)) or {}
        value, cost = 0, int(prow.get("stamina") or 0)
        for link in prow.get("playEffects") or ():
            eff = master.effects.get(link.get("produceExamEffectId")) if isinstance(link, dict) else None
            t = (eff or {}).get("effectType")
            t = t.get("number") if isinstance(t, dict) else t
            if t in (1, 56, 23):
                value += int((eff or {}).get("effectValue1") or 0)
            elif t == 49:
                value += 2 * int((eff or {}).get("effectValue1") or 0)
        feat_val[feat] = feat_val.get(feat, 0) + value
        feat_cost[feat] = feat_cost.get(feat, 0) + max(1, cost)
    eff = {f: feat_val[f] / feat_cost[f] for f in feat_val}
    eff_max = max(eff.values()) or 1.0
    default = 2.0 * math.log(0.5)
    weights = {}
    for f, e in eff.items():
        bonus = 1.5 * math.log1p(e) / math.log1p(eff_max)   # ∈[0,1.5]，只 boost 正分效率特征
        weights[("cf0", f)] = default + bonus
    prior = PS.ScorePrior(weights, sources=("mechanics:greedy-value/cost-efficiency-cf0",
                                            "rules:69", "boost-only:no-setup-suppression"))
    PS.save_prior(prior, str(ROOT / "data" / "_gnrpa_prior_mech.json"))
    print(f"[mech] features={len(weights)} eff_max={eff_max:.1f} saved", flush=True)
    del sess


# ---- stage: gate -------------------------------------------------------------
def boot_ci(deltas, iters=10000, seed=20261126):
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return [0.0, 0.0]
    means = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    return [means[int(0.025 * iters)], means[int(0.975 * iters)]]


def ab_block(by, pairs, nm, base):
    deltas = [by[(p, s, nm)]["best"] - by[(p, s, base)]["best"] for (p, s) in pairs]
    lo, hi = boot_ci(deltas)
    return {"n": len(deltas), "mean_delta": round(sum(deltas) / len(deltas), 1) if deltas else 0.0,
            "ci95": [lo, hi], "pos": sum(d > 0 for d in deltas), "neg": sum(d < 0 for d in deltas),
            "zero": sum(d == 0 for d in deltas),
            "per_pair": {f"{p}/{s}": d for (p, s), d in zip(pairs, deltas)}}


def stage_gate():
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
        for (s, _lab) in ss:
            pairs.append((pid, s))
            (mon_pairs if pid in MONSTER5 else low_pairs).append((pid, s))
    rows = []
    for (pid, seed) in pairs:
        wait_free()
        lo = expand_loadout(saves[pid]["loadout"])
        sess, _ = build_hif_loadout_session(master, lo, seed)
        full = list(sess.drinks)
        safe = safe_subset(full)
        arms = [("p0", None, full), ("mech", mech, full), ("distill", distill, full),
                ("empty", None, []), ("safe", None, safe)]
        for (nm, prior, dl) in arms:
            s = sess.clone()
            s.drinks = dl
            path, st = search(ns, s, prior)
            n_drink = sum(1 for a in path if a[0] == "drink")
            drink_ids = [s.drinks[a[1]] for a in path if a[0] == "drink" and a[1] < len(s.drinks)]
            rows.append({"pid": pid, "seed": seed, "arm": nm, "best": int(st["best_score"]),
                         "status": int(st["status"]), "expansions": int(st["expansions"]),
                         "wall": st["wall"], "n_drink": n_drink, "drink_ids": drink_ids,
                         "n_drinks_held": len(dl)})
            print(f"[gate] {pid}/{seed} {nm}: best={st['best_score']:,} drinks={n_drink} "
                  f"{st['wall']}s status={st['status']}", flush=True)
            del s
        del sess
        gc.collect()
    by = {(r["pid"], r["seed"], r["arm"]): r for r in rows}
    summary = {}
    for nm in ("p0", "mech", "distill", "empty", "safe"):
        rs = [by[(p, s, nm)] for (p, s) in pairs]
        summary[nm] = {"mean_best": round(sum(r["best"] for r in rs) / len(rs), 1),
                       "mean_drink_actions": round(sum(r["n_drink"] for r in rs) / len(rs), 2),
                       "errors": sum(1 for r in rs if r["status"] != 0),
                       "mean_wall": round(sum(r["wall"] for r in rs) / len(rs), 2)}
    ab = {
        "L1_mech_vs_p0": {"overall": ab_block(by, pairs, "mech", "p0"),
                          "low12": ab_block(by, low_pairs, "mech", "p0"),
                          "monster": ab_block(by, mon_pairs, "mech", "p0")},
        "L1_distill_vs_p0": {"overall": ab_block(by, pairs, "distill", "p0"),
                             "low12": ab_block(by, low_pairs, "distill", "p0"),
                             "monster": ab_block(by, mon_pairs, "distill", "p0")},
        "L4_safe_vs_empty": {"overall": ab_block(by, pairs, "safe", "empty"),
                             "low12": ab_block(by, low_pairs, "safe", "empty"),
                             "monster": ab_block(by, mon_pairs, "safe", "empty")},
        "L4_safe_vs_current": {"overall": ab_block(by, pairs, "safe", "p0"),
                               "low12": ab_block(by, low_pairs, "safe", "p0"),
                               "monster": ab_block(by, mon_pairs, "safe", "p0")},
        "L4_current_vs_empty": {"overall": ab_block(by, pairs, "p0", "empty"),
                                "low12": ab_block(by, low_pairs, "p0", "empty"),
                                "monster": ab_block(by, mon_pairs, "p0", "empty")},
    }
    out = {"trans": TRANS, "pids": PIDS, "pid_seeds": pid_seeds, "safe_ids": sorted(SAFE_IDS),
           "rows": rows, "summary": summary, "ab": ab}
    (ROOT / "data" / "_gnrpa_gate1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SUMMARY:", json.dumps(summary, ensure_ascii=False), flush=True)
    for k, v in ab.items():
        print(f"AB {k} overall: mean={v['overall']['mean_delta']} ci={v['overall']['ci95']} "
              f"pos/neg/zero={v['overall']['pos']}/{v['overall']['neg']}/{v['overall']['zero']}", flush=True)
    print("saved data/_gnrpa_gate1.json", flush=True)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("teachers", "all"):
        stage_teachers()
    if stage in ("priors", "all"):
        stage_priors()
    if stage in ("gate", "all"):
        stage_gate()